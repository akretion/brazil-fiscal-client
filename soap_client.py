# Copyright 2024-TODAY Akretion - Raphael Valyi <raphael.valyi@akretion.com>
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.en.html).

import logging
import re
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Type

from requests.adapters import HTTPAdapter, Retry
from requests_pkcs12 import Pkcs12Adapter
from xsdata.formats.dataclass.client import Client, Config
from xsdata.formats.dataclass.parsers import DictDecoder, XmlParser
from xsdata.formats.dataclass.serializers import XmlSerializer
from xsdata.formats.dataclass.serializers.config import SerializerConfig
from xsdata.formats.dataclass.transports import DefaultTransport, Transport

_logger = logging.Logger(__name__)

RETRIES = 3
BACKOFF_FACTOR = 0.1
RETRY_ERRORS = (500, 502, 503, 504)
TIMEOUT = 5.0
PRETTY_PRINT = True  # since waiting the fisc server is 3+ sec, perf penaly is OK


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


class SoapClient(Client):
    """A Brazilian fiscal wsdl client."""

    pkcs12_data: bytes = None
    pkcs12_password: str = None
    fake_certificate: bool = False
    server: str = "undef"
    ambiente: Tamb = None  # Tamb.VALUE_2
    uf: TcodUfIbge = "undef"
    versao: str = "undef"
    response_bindings_packages: List[Type] = []
    serializer: XmlSerializer = XmlSerializer(
        config=SerializerConfig(pretty_print=PRETTY_PRINT)
    )
    parser: XmlParser = XmlParser()
    transport: Transport = DefaultTransport()
    verify_ssl: bool = False  # TODO is it a decent default?

    def __init__(
        self,
        config: Config,
        versao: str = "undef",
        response_bindings_packages: Optional[List[Type]] = None,
    ):
        self.versao = versao
        self.response_bindings_packages = response_bindings_packages or []

    @classmethod
    def from_service(
        cls,
        ambiente: Tamb,
        uf: TcodUfIbge,
        pkcs12_data: bytes,
        pkcs12_password: str,
        obj: Optional[Type] = None,
        fake_certificate: bool = False,
        verify_ssl: bool = False,
        **kwargs: str,
    ) -> Client:
        """Instantiate client from a service definition."""
        client = cls(config=Config.from_service(obj, **kwargs))
        client.ambiente = ambiente
        client.pkcs12_data = pkcs12_data
        client.pkcs12_password = pkcs12_password
        client.fake_certificate = fake_certificate
        client.verify_ssl = verify_ssl
        client.uf = uf
        if not kwargs.get("location"):
            client.server = client.get_server("nfe", uf)
        return client

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
        action_class: Type,
        obj: Any,
        return_type: Type,
        headers: Optional[Dict] = None,
        placeholder_exp: str = "",
        placeholder_content: str = "",
    ) -> Any:
        """Build and send a request for the input object."""
        path = "/".join(["/ws"] + action_class.location.split("/")[-2:])
        # FIXME some UF may not have /ws and might need a "?wsdl" suffix
        location = self.server + path
        self.config = Config.from_service(action_class, location=location)

        if isinstance(obj, Dict):  # see superclass
            decoder = DictDecoder(context=self.serializer.context)
            obj = decoder.decode(obj, self.config.input)

        if not isinstance(obj, dict) and not isinstance(obj, Type):
            obj = {"Body": {"nfeDadosMsg": {"content": [obj]}}}

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
        headers = self.prepare_headers(headers or {})
        response = self.transport.post(self.config.location, data=data, headers=headers)
        response = self.parser.from_bytes(response, self.config.output)
        _logger.debug("SOAP RESPONSE DATA:", response)

        # the challenge with the Fiscal SOAP is the return type
        # is a wildcard in the WSDL, so here we help xsdata to figure
        # out which dataclass to use to parse the resultMsg content
        # based on the XML qname of the element.
        anyElement = response.body.nfeResultMsg.content[0]  # TODO safe guard
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
