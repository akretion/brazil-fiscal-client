# brazil-fiscal-client

The base SOAP client of this lib is designed to be inherited by specialized clients such
as for electronic invoicing (NFe). But it can still be used alone.

It uses [xsdata](https://github.com/tefra/xsdata) for the
[databinding](https://xsdata.readthedocs.io/en/latest/data_binding/basics/) and it
overrides its SOAP
[client](https://xsdata.readthedocs.io/en/latest/codegen/wsdl_modeling/#client)

## Installation

`pip install brazil-fiscal-client`

## Usage

For instance, with an appropriate pkcs12 certificate, you can query the NFe server
status:

```python

from brazil_fiscal_client.soap_client import SoapClient
from tests.fixtures.nfestatusservico4 import NfeStatusServico4SoapNfeStatusServicoNf
from nfelib.nfe.bindings.v4_0.cons_stat_serv_v4_00 import ConsStatServ
from nfelib.nfe.bindings.v4_0.ret_cons_stat_serv_v4_00 import RetConsStatServ

ambiente = "2"
uf = "41"

with open("/path_to_your_certificate/some_pkcs12_certificate.p12", "rb") as pkcs12_data:
    client = SoapClient.from_service(
        NfeStatusServico4SoapNfeStatusServicoNf,
        server="https://nfe-homologacao.svrs.rs.gov.br",
        uf=uf,
        ambiente=ambiente,
        pkcs12_data=pkcs12_data.read(),
        pkcs12_password="your_certificate_password",
    )

result = client.send(
    NfeStatusServico4SoapNfeStatusServicoNf,
    ConsStatServ(
        tpAmb=ambiente,
        cUF=uf,
        xServ="STATUS",
        versao="4.00",
    ),
)
>>> print(result)
RetConsStatServ(tpAmb=<Tamb.VALUE_2: '2'>, verAplic='SVRS202401251654', cStat='107', xMotivo='Servico SVC em Operacao', cUF=<TcodUfIbge.VALUE_41: '41'>, dhRecbto='2024-04-01T14:54:30-03:00', tMed='1', dhRetorno=None, xObs=None, versao='4.00')
>>> print(result.cStat)
107
```

Notice this example uses the `ConsStatServ` and `RetConsStatServ` bindings from
[nfelib](https://github.com/akretion/nfelib). In this example
`NfeStatusServico4SoapNfeStatusServicoNf` has been generated from a previously
downloaded wsdl file and using the
[WSDL xsdata generator](https://xsdata.readthedocs.io/en/latest/codegen/wsdl_modeling/).
All this is usually done in the specialized clients that override this base
`brazil-fiscal-client`SOAP client.
