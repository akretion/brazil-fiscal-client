from os import environ
from unittest import TestCase, mock

from xsdata.formats.dataclass.transports import DefaultTransport

from brazil_fiscal_client.fiscal_client import FiscalClient
from tests.fixtures.cons_stat_serv_v4_00 import ConsStatServ
from tests.fixtures.nfestatusservico4 import NfeStatusServico4SoapNfeStatusServicoNf
from tests.fixtures.ret_cons_stat_serv_v4_00 import RetConsStatServ

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
                <cUF>41</cUF>
                <dhRecbto>2024-03-31T00:19:52-03:00</dhRecbto><tMed>1</tMed>
           </retConsStatServ>
        </nfeResultMsg>
    </soap:Body>
</soap:Envelope>
"""


class FiscalClientTests(TestCase):
    def test__init__(self):
        client = FiscalClient(
            ambiente="2",
            uf="41",
            pkcs12_data=b"fake_cert",
            pkcs12_password="123456",
            server="http://testurl.com",
            fake_certificate=True,
        )
        self.assertEqual(client.uf, "41")
        self.assertEqual(client.pkcs12_data, b"fake_cert")
        self.assertEqual(client.pkcs12_password, "123456")
        self.assertEqual(client.server, "http://testurl.com")
        self.assertIs(client.parser.context, client.serializer.context)

    @mock.patch.object(DefaultTransport, "post")
    def test_send_with_instance_object(self, mock_post):
        mock_post.return_value = response.encode()

        client = FiscalClient(
            ambiente="2",
            uf=41,
            pkcs12_data=b"fake_cert",
            pkcs12_password="123456",
            server="http://testurl.com",
            fake_certificate=True,
        )

        result = client.send(
            NfeStatusServico4SoapNfeStatusServicoNf,
            ConsStatServ(
                tpAmb="2",
                cUF="41",
                xServ="STATUS",
                versao="4.00",
            ),
        )

        self.assertIsInstance(result, RetConsStatServ)
        self.assertEqual(result.cStat, "107")

    @mock.patch.object(DefaultTransport, "post")
    def test_send_with_generic_envelope(self, mock_post):
        mock_post.return_value = response.encode()

        client = FiscalClient(
            ambiente="2",
            uf=41,
            pkcs12_data=b"fake_cert",
            pkcs12_password="123456",
            fake_certificate=True,
        )

        result = client.send(
            "https://nfe-homologacao.svrs.rs.gov.br/ws/NfeStatusServico/NfeStatusServico4.asmx",
            ConsStatServ(
                tpAmb="2",
                cUF="41",
                xServ="STATUS",
                versao="4.00",
            ),
        )

        self.assertIsInstance(result, RetConsStatServ)
        self.assertEqual(result.cStat, "107")

    @mock.patch.object(DefaultTransport, "post")
    def test_send_with_generic_envelope_action_name(self, mock_post):
        mock_post.return_value = response.encode()

        client = FiscalClient(
            ambiente="2",
            uf=41,
            pkcs12_data=b"fake_cert",
            pkcs12_password="123456",
            fake_certificate=True,
            server="https://nfe-homologacao.svrs.rs.gov.br",
        )

        result = client.send(
            "NfeStatusServico4.asmx",
            ConsStatServ(
                tpAmb="2",
                cUF="41",
                xServ="STATUS",
                versao="4.00",
            ),
        )

        self.assertIsInstance(result, RetConsStatServ)
        self.assertEqual(result.cStat, "107")

    def test_send_with_real_certificate(self):
        if not environ.get("CERT_FILE"):
            return
        with open(environ["CERT_FILE"], "rb") as buffer:
            pkcs12_data = buffer.read()

        client = FiscalClient(
            server="https://nfe-homologacao.svrs.rs.gov.br",
            ambiente="2",
            uf=41,
            pkcs12_data=pkcs12_data,
            pkcs12_password=environ["CERT_PASSWORD"],
        )

        result = client.send(
            NfeStatusServico4SoapNfeStatusServicoNf,
            ConsStatServ(
                tpAmb="2",
                cUF="41",
                xServ="STATUS",
                versao="4.00",
            ),
        )

        self.assertIsInstance(result, RetConsStatServ)
        self.assertEqual(result.cStat, "107")
