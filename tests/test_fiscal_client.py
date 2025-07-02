from os import environ
from unittest import TestCase, mock

from nfelib.nfe.bindings.v4_0.cons_stat_serv_v4_00 import ConsStatServ
from nfelib.nfe.bindings.v4_0.leiaute_cons_stat_serv_v4_00 import TconsStatServXServ
from nfelib.nfe.bindings.v4_0.leiaute_nfe_v4_00 import Tamb as NFeTamb
from nfelib.nfe.bindings.v4_0.leiaute_nfe_v4_00 import TcodUfIbge as NFeTcodUfIbge
from nfelib.nfe.bindings.v4_0.ret_cons_stat_serv_v4_00 import RetConsStatServ
from requests.exceptions import RequestException
from xsdata.exceptions import ParserError
from xsdata.formats.dataclass.transports import DefaultTransport

from brazil_fiscal_client.fiscal_client import FiscalClient, Tamb, TcodUfIbge
from tests.fixtures.nfestatusservico4 import NfeStatusServico4SoapNfeStatusServicoNf

response = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xmlns:xsd="http://www.w3.org/2001/XMLSchema">
    <soap:Body>
        <nfeResultMsg xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeStatusServico4">
            <retConsStatServ versao="4.00" xmlns="http://www.portalfiscal.inf.br/nfe">
                <tpAmb>2</tpAmb>
                <verAplic>SVRS202401251654</verAplic>
                <cStat>107</cStat>
                <xMotivo>Servico SVC em Operacao</xMotivo>
                <cUF>42</cUF>
                <dhRecbto>2024-03-31T00:19:52-03:00</dhRecbto><tMed>1</tMed>
           </retConsStatServ>
        </nfeResultMsg>
    </soap:Body>
</soap:Envelope>
"""

# Mock SOAP 1.2 response with the same inner content as the SOAP 1.1 'response'
response_soap12 = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xmlns:xsd="http://www.w3.org/2001/XMLSchema">
    <soap:Body>
        <nfeResultMsg xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeStatusServico4">
            <retConsStatServ versao="4.00" xmlns="http://www.portalfiscal.inf.br/nfe">
                <tpAmb>2</tpAmb>
                <verAplic>SVRS202401251654</verAplic>
                <cStat>107</cStat>
                <xMotivo>Servico SVC em Operacao</xMotivo>
                <cUF>42</cUF>
                <dhRecbto>2024-03-31T00:19:52-03:00</dhRecbto>
                <tMed>1</tMed>
           </retConsStatServ>
        </nfeResultMsg>
    </soap:Body>
</soap:Envelope>
"""

# Define namespaces as bytes for checking request data
SOAP11_ENV_NS = "http://schemas.xmlsoap.org/soap/envelope/"
SOAP12_ENV_NS = "http://www.w3.org/2003/05/soap-envelope"


class FiscalClientTests(TestCase):
    def test__init__(self):
        client = FiscalClient(
            ambiente=Tamb.DEV,
            uf=TcodUfIbge.SC,
            versao="4.00",
            pkcs12_data=b"fake_cert",
            pkcs12_password="123456",
            fake_certificate=True,
        )
        self.assertEqual(client.uf, "42")
        self.assertEqual(client.ambiente, "2")
        self.assertEqual(client.pkcs12_data, b"fake_cert")
        self.assertEqual(client.pkcs12_password, "123456")
        self.assertIs(client.parser.context, client.serializer.context)

    @mock.patch.object(DefaultTransport, "post")
    def test_send_with_instance_object(self, mock_post):
        mock_post.return_value = response.encode()

        client = FiscalClient(
            ambiente=Tamb.DEV,
            uf=TcodUfIbge.SC,
            versao="4.00",
            pkcs12_data=b"fake_cert",
            pkcs12_password="123456",
            fake_certificate=True,
            service="nfe",
        )

        result = client.send(
            NfeStatusServico4SoapNfeStatusServicoNf,
            "https://nfe-homologacao.svrs.rs.gov.br/ws/NfeStatusServico/NfeStatusServico4.asmx",
            {
                "Body": {
                    "nfeDadosMsg": {
                        "content": [
                            ConsStatServ(
                                tpAmb=NFeTamb.VALUE_2,
                                cUF=NFeTcodUfIbge.VALUE_42,
                                xServ=TconsStatServXServ.STATUS,
                                versao="4.00",
                            ),
                        ]
                    }
                }
            },
        )

        self.assertIsInstance(result.body.nfeResultMsg.content[0], RetConsStatServ)
        self.assertEqual(result.body.nfeResultMsg.content[0].cStat, "107")

    def test_send_with_real_certificate(self):
        if not environ.get("CERT_FILE"):
            return
        with open(environ["CERT_FILE"], "rb") as buffer:
            pkcs12_data = buffer.read()

        client = FiscalClient(
            ambiente=Tamb.DEV,
            uf=TcodUfIbge.SC,
            versao="4.00",
            pkcs12_data=pkcs12_data,
            pkcs12_password=environ["CERT_PASSWORD"],
            service="nfe",
        )

        result = client.send(
            NfeStatusServico4SoapNfeStatusServicoNf,
            "https://nfe-homologacao.svrs.rs.gov.br/ws/NfeStatusServico/NfeStatusServico4.asmx",
            {
                "Body": {
                    "nfeDadosMsg": {
                        "content": [
                            ConsStatServ(
                                tpAmb=NFeTamb.VALUE_2,
                                cUF=NFeTcodUfIbge.VALUE_42,
                                xServ=TconsStatServXServ.STATUS,
                                versao="4.00",
                            ),
                        ]
                    }
                }
            },
        )

        self.assertIsInstance(result.body.nfeResultMsg.content[0], RetConsStatServ)
        self.assertEqual(result.body.nfeResultMsg.content[0].cStat, "107")

    def test_invalid_ambiente(self):
        with self.assertRaises(ValueError):
            FiscalClient(
                ambiente="3",  # Invalid ambiente
                uf="42",
                versao="4.00",
                pkcs12_data=b"fake_cert",
                pkcs12_password="123456",
                fake_certificate=True,
            )

    def test_network_error(self):
        client = FiscalClient(
            ambiente=Tamb.DEV,
            uf=TcodUfIbge.SC,
            versao="4.00",
            pkcs12_data=b"fake_cert",
            pkcs12_password="123456",
            fake_certificate=True,
        )
        with self.assertRaises(RequestException):
            client.send(
                NfeStatusServico4SoapNfeStatusServicoNf,
                "https://invalid-url",  # Invalid URL
                {
                    "Body": {
                        "nfeDadosMsg": {
                            "content": [
                                ConsStatServ(
                                    tpAmb=NFeTamb.VALUE_2,
                                    cUF=NFeTcodUfIbge.VALUE_42,
                                    xServ=TconsStatServXServ.STATUS,
                                    versao="4.00",
                                )
                            ]
                        }
                    }
                },
            )

    @mock.patch.object(DefaultTransport, "post")
    def test_send_force_soap12_request(self, mock_post):
        """Verify request uses SOAP 1.2 when soap12_envelope=True."""
        mock_post.return_value = response_soap12.encode()  # Return SOAP 1.2 response

        client = FiscalClient(
            ambiente=Tamb.DEV,
            uf=TcodUfIbge.SC,
            versao="4.00",
            pkcs12_data=b"fake_cert",
            pkcs12_password="123456",
            fake_certificate=True,
            service="nfe",
            soap12_envelope=True,  # Force SOAP 1.2 request
        )
        payload_obj = ConsStatServ(  # Use the inner content object
            tpAmb=NFeTamb.VALUE_2,
            cUF=NFeTcodUfIbge.VALUE_42,
            xServ=TconsStatServXServ.STATUS,
            versao="4.00",
        )
        wrapped_payload = {"Body": {"nfeDadosMsg": {"content": [payload_obj]}}}

        result = client.send(
            action_class=NfeStatusServico4SoapNfeStatusServicoNf,
            location="http://fake.location.com/service",
            wrapped_obj=wrapped_payload,
        )

        # Check that the *request* sent used SOAP 1.2 namespace
        mock_post.assert_called_once()
        sent_data = mock_post.call_args.kwargs.get("data", b"")
        self.assertIn(
            SOAP12_ENV_NS, sent_data, "SOAP 1.2 Namespace not found in request"
        )
        self.assertNotIn(
            SOAP11_ENV_NS, sent_data, "SOAP 1.1 Namespace unexpectedly found in request"
        )

        # Check that the result (from a SOAP 1.2 response fixed during parsing) is correct
        self.assertIsInstance(result.body.nfeResultMsg.content[0], RetConsStatServ)
        self.assertEqual(result.body.nfeResultMsg.content[0].cStat, "107")

    @mock.patch.object(DefaultTransport, "post")
    def test_send_default_soap11_request(self, mock_post):
        """Verify request uses SOAP 1.1 by default."""
        mock_post.return_value = response.encode()  # Return SOAP 1.1 response

        client = FiscalClient(
            ambiente=Tamb.DEV,
            uf=TcodUfIbge.SC,
            versao="4.00",
            pkcs12_data=b"fake_cert",
            pkcs12_password="123456",
            fake_certificate=True,
            service="nfe",
        )
        payload_obj = ConsStatServ(
            tpAmb=NFeTamb.VALUE_2,
            cUF=NFeTcodUfIbge.VALUE_42,
            xServ=TconsStatServXServ.STATUS,
            versao="4.00",
        )
        wrapped_payload = {"Body": {"nfeDadosMsg": {"content": [payload_obj]}}}

        result = client.send(
            action_class=NfeStatusServico4SoapNfeStatusServicoNf,
            location="http://fake.location.com/service",
            wrapped_obj=wrapped_payload,
        )

        # Check that the *request* sent used SOAP 1.1 namespace
        mock_post.assert_called_once()
        sent_data = mock_post.call_args.kwargs.get("data", b"")
        # Check based on prefix and namespace presence
        self.assertIn(
            'xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"', sent_data
        )
        self.assertIn("<soapenv:Envelope", sent_data)
        self.assertNotIn(SOAP12_ENV_NS, sent_data)

        # Check result
        self.assertIsInstance(result.body.nfeResultMsg.content[0], RetConsStatServ)
        self.assertEqual(result.body.nfeResultMsg.content[0].cStat, "107")

    @mock.patch.object(DefaultTransport, "post")
    def test_send_handles_soap12_response_by_default(self, mock_post):
        """Verify client handles SOAP 1.2 response when request was SOAP 1.1 (default)."""
        mock_post.return_value = response_soap12.encode()  # Return SOAP 1.2

        client = FiscalClient(
            ambiente=Tamb.DEV,
            uf=TcodUfIbge.SC,
            versao="4.00",
            pkcs12_data=b"fake_cert",
            pkcs12_password="123456",
            fake_certificate=True,
            service="nfe",
        )
        payload_obj = ConsStatServ(
            tpAmb=NFeTamb.VALUE_2,
            cUF=NFeTcodUfIbge.VALUE_42,
            xServ=TconsStatServXServ.STATUS,
            versao="4.00",
        )
        wrapped_payload = {"Body": {"nfeDadosMsg": {"content": [payload_obj]}}}

        # Send default (SOAP 1.1 request)
        result = client.send(
            action_class=NfeStatusServico4SoapNfeStatusServicoNf,
            location="http://fake.location.com/service",
            wrapped_obj=wrapped_payload,
        )

        # Check result - parsing should succeed due to response replacement
        self.assertIsInstance(result.body.nfeResultMsg.content[0], RetConsStatServ)
        self.assertEqual(result.body.nfeResultMsg.content[0].cStat, "107")

    @mock.patch.object(DefaultTransport, "post")
    def test_send_raise_on_soap_mismatch(self, mock_post):
        """Verify ParserError is raised when raise_on_soap_mismatch=True and response NS differs."""
        mock_post.return_value = response_soap12.encode()  # Return SOAP 1.2

        client = FiscalClient(
            ambiente=Tamb.DEV,
            uf=TcodUfIbge.SC,
            versao="4.00",
            pkcs12_data=b"fake_cert",
            pkcs12_password="123456",
            fake_certificate=True,
            service="nfe",
        )
        payload_obj = ConsStatServ(
            tpAmb=NFeTamb.VALUE_2,
            cUF=NFeTcodUfIbge.VALUE_42,
            xServ=TconsStatServXServ.STATUS,
            versao="4.00",
        )
        wrapped_payload = {"Body": {"nfeDadosMsg": {"content": [payload_obj]}}}

        # Expect ParserError because response is 1.2 but client expects 1.1 and raise=True
        with self.assertRaises(ParserError) as cm:
            client.send(
                action_class=NfeStatusServico4SoapNfeStatusServicoNf,
                location="http://fake.location.com/service",
                wrapped_obj=wrapped_payload,
                raise_on_soap_mismatch=True,  # Activate the flag
            )
        # Optionally check the error message content
        self.assertIn("Unknown property", str(cm.exception))
        self.assertIn(
            SOAP12_ENV_NS, str(cm.exception)
        )  # Check if error mentions the unexpected NS
