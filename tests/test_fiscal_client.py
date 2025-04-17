from os import environ
from unittest import TestCase, mock

from nfelib.nfe.bindings.v4_0.cons_stat_serv_v4_00 import ConsStatServ
from nfelib.nfe.bindings.v4_0.leiaute_cons_stat_serv_v4_00 import TconsStatServXServ
from nfelib.nfe.bindings.v4_0.leiaute_nfe_v4_00 import Tamb as NFeTamb
from nfelib.nfe.bindings.v4_0.leiaute_nfe_v4_00 import TcodUfIbge as NFeTcodUfIbge
from nfelib.nfe.bindings.v4_0.ret_cons_stat_serv_v4_00 import RetConsStatServ
from requests.exceptions import RequestException
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
