from unittest import TestCase, mock

from xsdata.formats.dataclass.client import Config
from xsdata.formats.dataclass.transports import DefaultTransport

from soap_client import SoapClient as Client
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


class ClientTests(TestCase):
    def test__init__(self):
        config = Config.from_service(
            NfeStatusServico4SoapNfeStatusServicoNf, transport="foobar"
        )
        client = Client(config)
        self.assertIsInstance(client, Client)

        # TODO FIXME
        # this seems to be due to the workaround with Client.__slots__ ...
        # self.assertIs(client.parser.context, client.serializer.context)
        #
        # client = Client(config, parser=XmlParser())
        # self.assertIs(client.parser.context, client.serializer.context)
        #
        # client = Client(config, serializer=XmlSerializer())
        # self.assertIs(client.parser.context, client.serializer.context)

    def test_from_service(self):
        client = Client.from_service(
            NfeStatusServico4SoapNfeStatusServicoNf,
            location="http://testurl.com",
            uf="41",
            pkcs12_data=b"fake_cert",
            pkcs12_password="123456",
            fake_certificate=True,
        )
        self.assertEqual(client.uf, "41")
        self.assertEqual(client.pkcs12_data, b"fake_cert")
        self.assertEqual(client.pkcs12_password, "123456")

    @mock.patch.object(DefaultTransport, "post")
    def test_send_with_instance_object(self, mock_post):
        mock_post.return_value = response.encode()

        client = Client.from_service(
            NfeStatusServico4SoapNfeStatusServicoNf,
            location="http://testurl.com",
            uf=41,
            pkcs12_data=b"fake_cert",
            pkcs12_password="123456",
            fake_certificate=True,
        )

        result = client.send(
            NfeStatusServico4SoapNfeStatusServicoNf,
            ConsStatServ(
                tpAmb="1",
                cUF="41",
                xServ="STATUS",
                versao="4.00",
            ),
            RetConsStatServ,
        )

        self.assertIsInstance(result, RetConsStatServ)
        self.assertEqual(result.cStat, "107")
