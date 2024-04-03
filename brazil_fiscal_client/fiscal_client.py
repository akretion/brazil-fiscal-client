# Copyright (c) 2024-TODAY Akretion - Raphaël Valyi <raphael.valyi@akretion.com>
# MIT License

import logging
import re
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, Optional, Type
from xml.etree import ElementTree

from lxml import etree
from requests.adapters import HTTPAdapter, Retry
from requests_pkcs12 import Pkcs12Adapter
from xsdata.formats.dataclass.client import Client, Config
from xsdata.formats.dataclass.parsers import DictDecoder

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
    """A Brazilian fiscal client extending the xsdata SOAP wsdl client.

    It can work both with an "action class" generated
    by xsdata for a specific WSDL file
    (https://xsdata.readthedocs.io/en/latest/codegen/wsdl_modeling)
    or with only the SOAP URL location (or server + action_name).
    In this later case it will use a generic envelope.

    It differs a bit from the xsdata client because the SOAP action
    (action_class or action URL) will not be passed in the constructor
    but when calling send to post a payload for a specific SOAP action.

    In fact it is compatible with the xsdata SOAP client for convenience
    and because we already use xsdata for nfelib, but when used with the
    generic envelope mode it pretty much only uses a trivial requests query.

    Attributes:
        pkcs12_data: bytes of the pkcs12/pfx certificate
        pkcs12_password: password of the certificate
        fake_certificate: only True when used with pytest
        server: the server URL
        ambiente: "1" for production, "2" for tests
        uf: federal state ibge code
        versao: schema version for the service, like "4.00" for nfe
        service: "nfe"|"cte"|"mdfe"|"bpe"
        verify_ssl: should openssl use verify_ssl?
    """

    pkcs12_data: bytes = None
    pkcs12_password: str = None
    fake_certificate: bool = False
    server: str = "undef"
    ambiente: Tamb = None
    uf: TcodUfIbge = "undef"
    versao: str = "undef"
    service: str = "nfe"
    verify_ssl: bool = False  # TODO is it a decent default?

    def __init__(
        self,
        ambiente: str,
        uf: TcodUfIbge,
        pkcs12_data: bytes,
        pkcs12_password: str,
        fake_certificate: bool = False,
        server: Optional[str] = None,
        service: str = "nfe",
        versao: str = "undef",
        verify_ssl: bool = False,
        **kwargs: Any,
    ):
        if not kwargs.get("config"):
            config = {
                "style": "document",
                "transport": "http://schemas.xmlsoap.org/soap/http",
            }

        # TODO TODO FIXME TODO:
        # override Config and move params in FiscalConfig!

        super().__init__(config, **kwargs)
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
        retries = Retry(  # retry in case of errors
            total=RETRIES,
            backoff_factor=BACKOFF_FACTOR,
            status_forcelist=RETRY_ERRORS,
        )
        self.transport.timeout = TIMEOUT

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
            self.transport.session.verify = self.verify_ssl

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
        placeholder_exp: str = "",
        placeholder_content: str = "",  # TODO move up
        return_type: Optional[Type] = None,
        headers: Optional[Dict] = None,
    ) -> Any:
        """Build and send a request for the input object.

        Args:
            action: either a string for the complete SOAP action URL,
            either only the action name (end of URL), either an
            action_class Type generated with xsdata for the SOAP wsdl
            obj: The request model instance or a pure dictionary
            placeholder_content: a string content to be injected in the
            payload. Used for signed content to avoid signature issues.
            placeholder_exp: placeholder where to inject placeholder_content
            return_type: you can specific it to help xsdata wrapping
            the response into the right class. Usually useless if the
            proper return type has been imported already.
            headers: Additional headers to pass to the transport

        Returns:
            The response model instance.
        """
        if isinstance(action, Type):
            # case when an action_class generated from a wsdl file is provided:
            action_class = action
            path = "/".join(["/ws"] + action_class.location.split("/")[-2:])
            # FIXME some UF may not have /ws and might need a "?wsdl" suffix
            location = self.server + path
            self.config = Config.from_service(action_class, location=location)

        else:
            # case where the generic envelope will be used:
            action_class = None
            location = action if action.startswith("http") else self.server + action
            self.config = Config(
                location=location,
                style="document",
                transport="http://schemas.xmlsoap.org/soap/http",
                input=None,
                output=None,
                soap_action=None,
            )

        if action_class and not isinstance(obj, dict) and not isinstance(obj, Type):
            # will use the action_class envelope
            obj = {"Body": {f"{self.service}DadosMsg": {"content": [obj]}}}

        _logger.debug("SOAP REQUEST URL", self.config.location)
        data = self._prepare_fiscal_payload(
            obj, placeholder_exp, placeholder_content, location=location
        )
        _logger.debug("SOAP REQUEST DATA: ", data)
        headers = self.prepare_headers(headers or {})

        response = self.transport.post(self.config.location, data=data, headers=headers)
        _logger.debug("SOAP RESPONSE DATA:", response)

        if not action_class:
            return self._generic_response(response, return_type)
        return self._xsdata_response(response, return_type)

    def _prepare_fiscal_payload(
        self,
        obj: Any,
        placeholder_exp: str = "",
        placeholder_content: str = "",
        location: str = "",
    ) -> Any:
        """Prepare and serialize payload to be sent.

        Differ from xsdata _prepare_payload to skip namespaces
        to please the Fazenda and to be able to insert string
        placeholders to avoid useless parsing/serialization and
        signature issues. Is also able to use a generic envelope.
        """
        if isinstance(obj, Dict):
            # action_class case
            decoder = DictDecoder(context=self.serializer.context)
            obj = decoder.decode(obj, self.config.input)
            data = self.serializer.render(
                obj=obj, ns_map={None: f"http://www.portalfiscal.inf.br/{self.service}"}
            )
        else:
            # use generic envelope
            content = self.serializer.render(
                obj=obj, ns_map={None: f"http://www.portalfiscal.inf.br/{self.service}"}
            )
            # TODO: do we want it with or without .asmx extensions?
            action_name = location.split("/")[-1].split(".")[0]
            ns = f"http://www.portalfiscal.inf.br/{self.service}/{self.service}/{action_name}"
            data = f"""
            <soapenv:Envelope
                xmlns="http://www.portalfiscal.inf.br/{self.service}"
                xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
            >
                <soapenv:Body>
                    <ns2:{self.service}DadosMsg
                        xmlns:ns2="{ns}"
                    >
                        {content}
                    </ns2:{self.service}DadosMsg>
                </soapenv:Body>
            </soapenv:Envelope>
            """

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

    def _generic_response(self, response: str, return_type: Type) -> Any:
        # response from generic envelope
        response = response.decode().replace(
            '<?xml version="1.0" encoding="utf-8"?>', ""
        )
        root = etree.fromstring(response)
        xml_etree = (
            root.getchildren()[0].getchildren()[0].getchildren()[0]
        )  # TODO xpath?
        xml = ElementTree.tostring(xml_etree).decode()
        return self.parser.from_string(xml, return_type)

    def _xsdata_response(self, response: str, return_type: Type) -> Any:
        # the challenge with the Fiscal SOAP is the return type
        # is a wildcard in the WSDL, so here we help xsdata to figure
        # out which dataclass to use to parse the resultMsg content
        # based on the XML qname of the element.

        response = self.parser.from_bytes(response, self.config.output)
        result_msg = getattr(response.body, f"{self.service}ResultMsg")
        if result_msg:
            anyElement = result_msg.content[0]
            anyElement.qname = None
            anyElement.text = None
            xml = self.serializer.render(
                obj=anyElement,
                ns_map={None: f"http://www.portalfiscal.inf.br/{self.service}"},
            )
            return self.parser.from_string(xml, return_type)

        return self.parser.from_string(xml, return_type)
