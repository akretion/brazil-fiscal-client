from unittest import TestCase

from brazil_fiscal_client.fiscal_client import FiscalClient, Tamb


class FiscalClientReprTests(TestCase):
    def test_repr_works_without_uf(self):
        client = FiscalClient(
            ambiente=Tamb.DEV,
            versao="4.00",
            pkcs12_data=b"fake_cert",
            pkcs12_password="123456",
            fake_certificate=True,
        )

        self.assertEqual(
            repr(client),
            "<FiscalClient(ambiente=2, uf=None, service=nfe, versao=4.00)>",
        )
