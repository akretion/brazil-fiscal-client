[![Build Status](https://github.com/akretion/brazil-fiscal-client/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/OCA/l10n-brazil/actions/workflows/tests.yml?query=branch%3Amain)
[![codecov](https://codecov.io/gh/akretion/brazil-fiscal-client/branch/main/graph/badge.svg)](https://codecov.io/gh/akretion/brazil-fiscal-client)
[![PyPI](https://img.shields.io/pypi/v/brazil-fiscal-client)](https://pypi.org/project/brazil-fiscal-client)

# brazil-fiscal-client

A simple, modern and well tested SOAP client for the Brazilian Fiscal Authority.

This client is designed to be inherited by specialized clients such as for electronic
invoicing (NFe). But with some extra boiler plate code to deal with the SOAP enveloppe,
it can still be used alone as you can see in the usage section below.

It uses [xsdata](https://github.com/tefra/xsdata) for the
[databinding](https://xsdata.readthedocs.io/en/latest/data_binding/basics/) and it
overrides its SOAP
[client](https://xsdata.readthedocs.io/en/latest/codegen/wsdl_modeling/#client)

## Installation

`pip install brazil-fiscal-client`

## Usage

For instance, with an appropriate pkcs12 certificate, you can query the NFe server
status (remember specialized clients make all this simpler):

```python

from brazil_fiscal_client.fiscal_client import FiscalClient
from tests.fixtures.nfestatusservico4 import NfeStatusServico4SoapNfeStatusServicoNf
from nfelib.nfe.bindings.v4_0.cons_stat_serv_v4_00 import ConsStatServ
from nfelib.nfe.bindings.v4_0.ret_cons_stat_serv_v4_00 import RetConsStatServ

ambiente = "2"
path_to_your_pkcs12_certificate = "/path_to_your_certificate/pkcs12_certificate.p12"
certificate_password = "your_certificate_password"

with open(path_to_your_pkcs12_certificate, "rb") as pkcs12_buffer:
    pkcs12_data = pkcs12_buffer.read()

client = FiscalClient(
    ambiente=ambiente,
    versao="4.00",
    pkcs12_data=pkcs12_data,
    pkcs12_password=your_certificate_password,
)

result = client.send(
    NfeStatusServico4SoapNfeStatusServicoNf,
    "https://nfe-homologacao.svrs.rs.gov.br/ws/NfeStatusServico/NfeStatusServico4.asmx",
    {
        "Body": {
            "nfeDadosMsg": {
                "content": [
                    ConsStatServ(
                        tpAmb="2",
                        cUF="42",
                        xServ="STATUS",
                        versao="4.00",
                    ),
                ]
            }
        }
    },
)

>>> result.body.nfeResultMsg.content[0]
RetConsStatServ(tpAmb=<Tamb.VALUE_2: '2'>, verAplic='SVRS202401251654', cStat='107', xMotivo='Servico SVC em Operacao', cUF=<TcodUfIbge.VALUE_42: '42'>, dhRecbto='2024-04-01T16:18:03-03:00', tMed='1', dhRetorno=None, xObs=None, versao='4.00')
>>> result.body.nfeResultMsg.content[0].cStat
'107'
```

Notice this example uses the `ConsStatServ` and `RetConsStatServ` bindings from
[nfelib](https://github.com/akretion/nfelib). In this example
`NfeStatusServico4SoapNfeStatusServicoNf` has been generated from a previously
downloaded wsdl file and using the
[WSDL xsdata generator](https://xsdata.readthedocs.io/en/latest/codegen/wsdl_modeling/).
All this is usually done in the specialized clients that override this base
`brazil-fiscal-client`SOAP client.
