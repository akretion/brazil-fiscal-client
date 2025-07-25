# Copyright (c) 2024-TODAY Akretion - Raphaël Valyi <raphael.valyi@akretion.com>
# MIT License

from __future__ import annotations  # Python 3.8 compat

import logging
import re
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

from requests.adapters import HTTPAdapter, Retry
from requests.exceptions import RequestException
from requests_pkcs12 import Pkcs12Adapter
from xsdata.exceptions import ParserError
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

    AC = "12"  # Acre
    AL = "27"  # Alagoas
    AP = "16"  # Amapá
    AM = "13"  # Amazonas
    BA = "29"  # Bahia
    CE = "23"  # Ceará
    DF = "53"  # Distrito Federal
    ES = "32"  # Espírito Santo
    GO = "52"  # Goiás
    MA = "21"  # Maranhão
    MT = "51"  # Mato Grosso
    MS = "50"  # Mato Grosso do Sul
    MG = "31"  # Minas Gerais
    PA = "15"  # Pará
    PB = "25"  # Paraíba
    PR = "41"  # Paraná
    PE = "26"  # Pernambuco
    PI = "22"  # Piauí
    RJ = "33"  # Rio de Janeiro
    RN = "24"  # Rio Grande do Norte
    RS = "43"  # Rio Grande do Sul
    RO = "11"  # Rondônia
    RR = "14"  # Roraima
    SC = "42"  # Santa Catarina
    SP = "35"  # São Paulo
    SE = "28"  # Sergipe
    TO = "17"  # Tocantins


SOAP11_ENV_NS = "http://schemas.xmlsoap.org/soap/envelope/"
SOAP12_ENV_NS = "http://www.w3.org/2003/05/soap-envelope"


class FiscalClient(Client):
    """A Brazilian fiscal client extending the xsdata SOAP wsdl client.

    It differs a bit from the xsdata client because the SOAP action
    (action_class or action URL) will not be passed in the constructor
    but when calling send to post a payload for a specific SOAP action.

    Attributes:
        pkcs12_data: Bytes of the PKCS12/PFX certificate.
        pkcs12_password: Password of the certificate.
        fake_certificate: True if you use a fake certificate (for tests).
        ambiente: "1" for production, "2" for tests.
        uf: Federal state IBGE code.
        service: "nfe"|"cte"|"mdfe"|"bpe".
        verify_ssl: Should OpenSSL verify SSL certificates?
    """

    def __init__(
        self,
        ambiente: str | Tamb,
        versao: str,
        pkcs12_data: bytes,
        pkcs12_password: str,
        uf: str | TcodUfIbge | None = None,
        service: str = "nfe",
        verify_ssl: bool = False,
        timeout: float = TIMEOUT,
        fake_certificate: bool = False,
        soap12_envelope: bool = False,
        **kwargs: Any,
    ):
        if isinstance(ambiente, str):
            if ambiente not in [t.value for t in Tamb]:
                raise ValueError(
                    f"Invalid ambiente value: {ambiente}, should be '1' or 2'"
                )
            self.ambiente = ambiente
        else:
            self.ambiente = ambiente.value
        if isinstance(uf, str):
            if uf not in [t.value for t in TcodUfIbge]:
                raise ValueError(f"Invalid uf value: {uf}")
            self.uf = uf
        elif uf:
            self.uf = uf.value

        super().__init__(config=kwargs.get("config", {}), **kwargs)
        self.versao = versao
        self.pkcs12_data = pkcs12_data
        self.pkcs12_password = pkcs12_password
        self.verify_ssl = verify_ssl
        self.service = service
        self.transport.timeout = timeout
        self.transport.session.verify = self.verify_ssl
        self.fake_certificate = fake_certificate
        self.soap12_envelope = soap12_envelope

    def __repr__(self):
        """Return the instance string representation."""
        return (
            f"<FiscalClient(ambiente={self.ambiente}, uf={self.uf}, "
            f"service={self.service}, versao={self.versao})>"
        )

    @classmethod
    def _timestamp(cls):
        FORMAT = "%Y-%m-%dT%H:%M:%S"
        return (
            datetime.strftime(datetime.now(tz=timezone(timedelta(hours=-3))), FORMAT)
            + str(timezone(timedelta(hours=-3)))[3:]
        )

    def send(
        self,
        action_class: Any,
        location: str,
        wrapped_obj: Any,
        placeholder_exp: str = "",
        placeholder_content: str = "",
        headers: dict | None = None,
        raise_on_soap_mismatch: bool = False,
    ) -> Any:
        """Build and send a request for the input object.

        Args:
            action_class: type generated with xsdata for the SOAP wsdl
            location: the URL for the SOAP action
            wrapped_obj: The request model instance or a pure dictionary
            placeholder_exp: placeholder where to inject placeholder_content
            placeholder_content: a string content to be injected in the
            payload. Used for signed content to avoid signature issues.
            headers: Additional headers to pass to the transport
            raise_on_soap_mismatch: Raise an exception if SOAP version mismatches

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
            self.transport.session.mount(
                server,
                Pkcs12Adapter(
                    pkcs12_data=self.pkcs12_data,
                    pkcs12_password=self.pkcs12_password,
                ),
            )
        data = self.prepare_payload(
            wrapped_obj,
            placeholder_exp,
            placeholder_content,
        )
        headers = self.prepare_headers(headers or {})
        try:
            _logger.debug(f"Sending SOAP request to {location} with headers: {headers}")
            _logger.debug(f"SOAP request payload: {data}")
            response = self.transport.post(
                location, data=data, headers=headers
            ).decode()
            _logger.debug(f"SOAP response: {response}")

            # Check if the response uses the SOAP 1.2 namespace and replace it
            # example NFe with Parana (UF 41) server
            # tests/nfe/test_client.py::SoapTest::test_0_status
            if self.soap12_envelope or (
                not raise_on_soap_mismatch
                and SOAP12_ENV_NS in response
                and SOAP11_ENV_NS not in response
            ):
                _logger.warning(
                    f"Detected SOAP 1.2 namespace in response from {location}. "
                    "Attempting to replace with SOAP 1.1 for parsing."
                )
                response = response.replace(SOAP12_ENV_NS, SOAP11_ENV_NS)

            return self.parser.from_string(response, action_class.output)
        except RequestException as e:
            _logger.error(f"Failed to send SOAP request to {location}: {e}")
            raise
        except ParserError as e:
            _logger.error(
                f"Failed to parse SOAP response as {action_class.output}\n"
                f"SOAP response:\n{response}"
            )
            _logger.error(f"Error: {e}")
            raise

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
            placeholder_exp: placeholder where to inject placeholder_content
            placeholder_content: a string content to be injected in the
            payload. Used for signed content to avoid signature issues.

        Returns:
            The serialized request body content as string or bytes.

        Raises:
            ClientValueError: If the config input type doesn't match the given object.
        """
        if isinstance(obj, dict):
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
        if self.soap12_envelope:
            data = data.replace(
                f'xmlns:soapenv="{SOAP11_ENV_NS}"',
                f'xmlns:soapenv="{SOAP12_ENV_NS}"',
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
