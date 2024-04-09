# Copyright (c) 2024-TODAY Akretion - Raphaël Valyi <raphael.valyi@akretion.com>
# MIT License

import logging
import re
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, Optional, Type

from requests.adapters import HTTPAdapter, Retry
from requests_pkcs12 import Pkcs12Adapter
from xsdata.formats.dataclass.client import Client, ClientValueError, Config
from xsdata.formats.dataclass.parsers import DictDecoder

_logger = logging.Logger(__name__)

RETRIES = 3
BACKOFF_FACTOR = 0.1
RETRY_ERRORS = (500, 502, 503, 504)
TIMEOUT = 20.0


class Tamb(Enum):
    """Tipo Ambiente."""

    PROD = "1"
    DEV = "2"


class TcodUfIbge(Enum):
    """Tipo Código da UF da tabela do IBGE."""

    AC = "11"  # Acre
    AL = "12"  # Alagoas
    AP = "13"  # Amapá
    AM = "14"  # Amazonas
    BA = "15"  # Bahia
    CE = "16"  # Ceará
    DF = "17"  # Distrito Federal
    ES = "21"  # Espírito Santo
    GO = "22"  # Goiás
    MA = "23"  # Maranhão
    MT = "24"  # Mato Grosso
    MS = "25"  # Mato Grosso do Sul
    MG = "31"  # Minas Gerais
    PA = "32"  # Pará
    PB = "33"  # Paraíba
    PR = "41"  # Paraná
    PE = "42"  # Pernambuco
    PI = "43"  # Piauí
    RJ = "50"  # Rio de Janeiro
    RN = "51"  # Rio Grande do Norte
    RS = "52"  # Rio Grande do Sul
    RO = "53"  # Rondônia
    RR = "21"  # Roraima
    SC = "22"  # Santa Catarina
    SP = "23"  # São Paulo
    SE = "24"  # Sergipe
    TO = "25"  # Tocantins


class FiscalClient(Client):
    """A Brazilian fiscal client extending the xsdata SOAP wsdl client.

    It differs a bit from the xsdata client because the SOAP action
    (action_class or action URL) will not be passed in the constructor
    but when calling send to post a payload for a specific SOAP action.

    Attributes:
        pkcs12_data: bytes of the pkcs12/pfx certificate
        pkcs12_password: password of the certificate
        fake_certificate: only True when used with pytest
        ambiente: "1" for production, "2" for tests
        uf: federal state ibge code
        service: "nfe"|"cte"|"mdfe"|"bpe"
        verify_ssl: should openssl use verify_ssl?
    """

    pkcs12_data: bytes = None
    pkcs12_password: str = None
    fake_certificate: bool = False
    ambiente: Tamb = None
    uf: TcodUfIbge = None
    versao: str = None
    service: str = "nfe"
    verify_ssl: bool = False  # TODO is it a decent default?
    messages = []

    def __init__(
        self,
        ambiente: str,
        uf: TcodUfIbge,
        versao: str,
        pkcs12_data: bytes,
        pkcs12_password: str,
        fake_certificate: bool = False,
        service: str = "nfe",
        verify_ssl: bool = False,
        **kwargs: Any,
    ):
        if not kwargs.get("config"):
            config = {}
            # creating a Config is useless because it is a frozen dataclass:
            # see https://github.com/tefra/xsdata/issues/1009

        super().__init__(config, **kwargs)
        self.ambiente = ambiente
        self.uf = uf
        self.versao = versao
        self.pkcs12_data = pkcs12_data
        self.pkcs12_password = pkcs12_password
        self.fake_certificate = fake_certificate
        self.verify_ssl = verify_ssl
        self.service = service
        self.transport.timeout = TIMEOUT
        self.transport.session.verify = self.verify_ssl
        self.messages = []

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
        location: str,
        wrapped_obj: Any,
        placeholder_exp: Optional[str] = None,
        placeholder_content: Optional[str] = None,
        return_type: Optional[Type] = None,
        headers: Optional[Dict] = None,
        subclass_message: Optional[Dict] = None,
    ) -> Any:
        """Build and send a request for the input object.

        Args:
            action_class: Type generated with xsdata for the SOAP wsdl
            wrapped_obj: The request model instance or a pure dictionary
            location: the URL for the SOAP action
            placeholder_content: a string content to be injected in the
            payload. Used for signed content to avoid signature issues.
            placeholder_exp: placeholder where to inject placeholder_content
            return_type: you can specific it to help xsdata wrapping
            the response into the right class. Usually useless if the
            proper return type has been imported already.
            headers: Additional headers to pass to the transport
            subclass_message: a recording message passed from a subclass

        Returns:
            The response model instance.
        """
        server = "https://" + location.split("/")[2]
        self.config = Config.from_service(action_class, location=location)

        retries = Retry(  # retry in case of errors
            total=RETRIES,
            backoff_factor=BACKOFF_FACTOR,
            status_forcelist=RETRY_ERRORS,
        )
        self.transport.session.mount(server, HTTPAdapter(max_retries=retries))

        if not self.fake_certificate:
            # SSL request doesn't work with the fake cert we use in tests
            self.transport.session.mount(
                server,
                Pkcs12Adapter(
                    pkcs12_data=self.pkcs12_data,
                    pkcs12_password=self.pkcs12_password,
                ),
            )
        message = subclass_message or {}
        if not subclass_message:  # else append will happen in the subclass
            self.messages.append(message)
        message["input_url"] = location
        message["action"] = "GENERIC_SEND"
        message["input_wrapped_object"] = wrapped_obj
        data = self.prepare_payload(wrapped_obj, placeholder_exp, placeholder_content)
        message["input_xml"] = data
        _logger.debug(f"FISCAL SOAP REQUEST to {location}:", data)
        headers = self.prepare_headers(headers or {})
        response = self.transport.post(location, data=data, headers=headers)
        message["output_xml"] = response
        _logger.debug("FISCAL SOAP RESPONSE:", response)
        result = self.parser.from_bytes(response, action_class.output)
        message["output_wrapped_object"] = result
        return result

    def prepare_payload(
        self,
        obj: Any,
        placeholder_exp: str = "",
        placeholder_content: str = "",
    ) -> Any:
        """Prepare and serialize payload to be sent.

        It differs from xsdata _prepare_payload: it skips namespaces
        to please the Fazenda and it allows to insert string
        placeholders to avoid useless parsing/serialization and
        signature issues.

        Args:
            obj: The request model instance or a pure dictionary
            placeholder_content: a string content to be injected in the
            payload. Used for signed content to avoid signature issues.
            placeholder_exp: placeholder where to inject placeholder_content

        Returns:
            The serialized request body content as string or bytes.

        Raises:
            ClientValueError: If the config input type doesn't match the given object.
        """
        if isinstance(obj, Dict):
            decoder = DictDecoder(context=self.serializer.context)
            obj = decoder.decode(obj, self.config.input)

        if not isinstance(obj, self.config.input):
            raise ClientValueError(
                f"Invalid input service type, "
                f"expected `{self.config.input.__name__}` "
                f"got `{type(obj).__name__}`"
            )

        data = self.serializer.render(
            obj=obj, ns_map={None: f"http://www.portalfiscal.inf.br/{self.service}"}
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


@contextmanager
def soap_recorder(fiscal_client: FiscalClient):
    """A contextmanager allowing to record all SOAP messages in the block.

    This is specially usefull to record all messages when several SOAP
    actions are performed inside a single method.
    For instance authorizing an NFe and then waiting and reading its
    receipt involves 2 or more SOAP calls.
    """
    fiscal_client.messages = []
    yield fiscal_client.messages
