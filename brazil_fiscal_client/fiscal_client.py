# Copyright (c) 2024-TODAY Akretion - Raphaël Valyi <raphael.valyi@akretion.com>
# MIT License

import logging
import re
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, Optional, Type

from requests.adapters import HTTPAdapter, Retry
from requests_pkcs12 import Pkcs12Adapter
from xsdata.formats.dataclass.client import Client, Config
from xsdata.formats.dataclass.parsers import DictDecoder, XmlParser
from xsdata.formats.dataclass.serializers import XmlSerializer
from xsdata.formats.dataclass.serializers.config import SerializerConfig
from xsdata.formats.dataclass.transports import DefaultTransport, Transport

from brazil_fiscal_client.fiscal_envelope import FiscalSoapAction

_logger = logging.Logger(__name__)

RETRIES = 3
BACKOFF_FACTOR = 0.1
RETRY_ERRORS = (500, 502, 503, 504)
TIMEOUT = 20.0


class Tamb(Enum):
    """Tipo Ambiente."""

    VALUE_1 = "1"
    VALUE_2 = "2"


class TcodUfIbge(Enum):
    """Tipo Código da UF da tabela do IBGE."""

    VALUE_11 = "11"
    VALUE_12 = "12"
    VALUE_13 = "13"
    VALUE_14 = "14"
    VALUE_15 = "15"
    VALUE_16 = "16"
    VALUE_17 = "17"
    VALUE_21 = "21"
    VALUE_22 = "22"
    VALUE_23 = "23"
    VALUE_24 = "24"
    VALUE_25 = "25"
    VALUE_26 = "26"
    VALUE_27 = "27"
    VALUE_28 = "28"
    VALUE_29 = "29"
    VALUE_31 = "31"
    VALUE_32 = "32"
    VALUE_33 = "33"
    VALUE_35 = "35"
    VALUE_41 = "41"
    VALUE_42 = "42"
    VALUE_43 = "43"
    VALUE_50 = "50"
    VALUE_51 = "51"
    VALUE_52 = "52"
    VALUE_53 = "53"


class FiscalClient(Client):
    """A Brazilian fiscal wsdl client."""

    pkcs12_data: bytes = None
    pkcs12_password: str = None
    fake_certificate: bool = False
    server: str = "undef"
    ambiente: Tamb = None
    uf: TcodUfIbge = "undef"
    versao: str = "undef"
    service: str = "nfe"
    serializer: XmlSerializer = XmlSerializer(config=SerializerConfig())
    parser: XmlParser = XmlParser()
    transport: Transport = DefaultTransport()
    verify_ssl: bool = False  # TODO is it a decent default?

    def __init__(
        self,
        ambiente: str,
        uf: TcodUfIbge,
        pkcs12_data: bytes,
        pkcs12_password: str,
        fake_certificate: bool = False,
        server: Optional[str] = None,
        config: Config = None,
        versao: str = "undef",
        service: str = "nfe",
        verify_ssl: bool = False,
        transport: Optional[Transport] = None,
        parser: Optional[XmlParser] = None,
        serializer: Optional[XmlSerializer] = None,
    ):
        if config is None:
            config = {
                "style": "document",
                "transport": "http://schemas.xmlsoap.org/soap/http",
            }
        super().__init__(
            config=config, transport=transport, parser=parser, serializer=serializer
        )
        self.ambiente = ambiente
        self.uf = uf
        self.pkcs12_data = pkcs12_data
        self.pkcs12_password = pkcs12_password
        self.fake_certificate = fake_certificate
        self.verify_ssl = verify_ssl
        self.service = service
        self.versao = versao
        if server:
            self.server = server
        else:
            self.server = self._get_server(service, uf)

    @classmethod
    def _get_server(cls, service: str, uf: str) -> str:
        """Meant to be overriden as URL change with service, uf and ambiente."""
        return "not implemented here"

    @classmethod
    def _timestamp(self):
        FORMAT = "%Y-%m-%dT%H:%M:%S"
        return (
            datetime.strftime(datetime.now(tz=timezone(timedelta(hours=-3))), FORMAT)
            + str(timezone(timedelta(hours=-3)))[3:]
        )

    def send(
        self,
        action: Any,
        obj: Any,
        return_type: Optional[Type] = None,
        headers: Optional[Dict] = None,
        placeholder_exp: str = "",
        placeholder_content: str = "",
    ) -> Any:
        """Build and send a request for the input object."""
        if isinstance(action, Type):
            # case when an action_class generated from a wsdl file is provided:
            action_class = action
            path = "/".join(["/ws"] + action_class.location.split("/")[-2:])
            # FIXME some UF may not have /ws and might need a "?wsdl" suffix
            location = self.server + path
            dadosMsg = self.service + "DadosMsg"
            resultMsg = self.service + "ResultMsg"
        else:
            # case where the generic FiscalEnvelope will be used:
            action_class = FiscalSoapAction
            location = action if action.startswith("http") else self.server + action
            dadosMsg = "fiscalDadosMsg"
            resultMsg = "fiscalResultMsg"

        self.config = Config.from_service(action_class, location=location)

        if isinstance(obj, Dict):  # see superclass
            decoder = DictDecoder(context=self.serializer.context)
            obj = decoder.decode(obj, self.config.input)

        if not isinstance(obj, dict) and not isinstance(obj, Type):
            obj = {"Body": {dadosMsg: {"content": [obj]}}}

        self.transport.session.verify = self.verify_ssl

        retries = Retry(  # retry in case of errors
            total=RETRIES,
            backoff_factor=BACKOFF_FACTOR,
            status_forcelist=RETRY_ERRORS,
        )
        self.transport.session.mount(self.server, HTTPAdapter(max_retries=retries))
        if not self.fake_certificate:
            # SSL request doesn't work with the fake cert we use in tests
            self.transport.session.mount(
                self.server,
                Pkcs12Adapter(
                    pkcs12_data=self.pkcs12_data,
                    pkcs12_password=self.pkcs12_password,
                ),
            )
        self.transport.timeout = TIMEOUT

        _logger.debug("SOAP REQUEST URL", self.config.location)
        data = self.prepare_payload(obj, placeholder_exp, placeholder_content)
        _logger.debug("SOAP REQUEST DATA: ", data)
        print(data)
        if action_class == FiscalSoapAction:
            data = data.replace("fiscalDadosMsg", "nfeDadosMsg").replace(
                "fiscalResultMsg", "nfeResultMsg"
            )
        print(data)
        headers = self.prepare_headers(headers or {})
        response = self.transport.post(
            self.config.location, data=data, headers=headers
        ).decode()
        if action_class == FiscalSoapAction:
            response = response.replace("nfeDadosMsg", "fiscalDadosMsg").replace(
                "nfeResultMsg", "fiscalResultMsg"
            )
            response = response.replace(
                'xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeStatusServico4"',
                'xmlns="fiscal_namespace"',
            )

        print("\n\n", response)
        print(self.config.output)

        response = self.parser.from_string(response, self.config.output)
        _logger.debug("SOAP RESPONSE DATA:", response)

        # the challenge with the Fiscal SOAP is the return type
        # is a wildcard in the WSDL, so here we help xsdata to figure
        # out which dataclass to use to parse the resultMsg content
        # based on the XML qname of the element.
        anyElement = getattr(response.body, resultMsg).content[0]  # TODO safe guard
        anyElement.qname = None
        anyElement.text = None
        # TODO deal with children or attributes (and remove their qname and text) ?

        xml = self.serializer.render(
            obj=anyElement, ns_map={None: "http://www.portalfiscal.inf.br/nfe"}
        )
        return self.parser.from_string(xml, return_type)

    def prepare_payload(
        self,
        obj: Any,
        placeholder_exp: str = "",
        placeholder_content: str = "",
    ) -> Any:
        """Prepare and serialize payload to be sent.

        Overriden to skip namespaces to please the Fazenda
        and to be able to insert string placeholders to
        avoid useless parsing/serialization and signature issues.
        """
        if isinstance(obj, Dict):
            decoder = DictDecoder(context=self.serializer.context)
            obj = decoder.decode(obj, self.config.input)

        data = self.serializer.render(
            obj=obj, ns_map={None: "http://www.portalfiscal.inf.br/nfe"}
        )
        if placeholder_exp and placeholder_content:
            # used to match "<NFe/>" in the payload for instance
            # this allows injecting the signed XML in the payload without
            # having to serialize the XML again and possibly screw the signature
            exp = re.compile(placeholder_exp)
            matches = exp.search(data)
            if matches:
                data = (
                    data.replace(matches[0], placeholder_content)
                    .replace("\n", "")
                    .replace("\r", "")
                )

        return data
