import unittest
try:
    from pydantic import ValidationError
    from basheco.api import RegisterRequest, TransferRequest
except ImportError:
    RegisterRequest = TransferRequest = None

@unittest.skipIf(RegisterRequest is None, "API requirements not installed")
class ApiContractTests(unittest.TestCase):
    def test_email_normalization(self):
        x = RegisterRequest(email="TEST@Example.org",display_name="Tester",password="a-long-secure-password")
        self.assertEqual(x.email,"test@example.org")
    def test_short_password_rejected(self):
        with self.assertRaises(ValidationError):
            RegisterRequest(email="a@example.org",display_name="Tester",password="short")
    def test_fractional_money_rejected(self):
        from uuid import uuid4
        with self.assertRaises(ValidationError):
            TransferRequest(debit_wallet=uuid4(),credit_wallet=uuid4(),amount_kopecks=1.5,idempotency_key="transaction-1")
    def test_bad_idempotency_rejected(self):
        from uuid import uuid4
        with self.assertRaises(ValidationError):
            TransferRequest(debit_wallet=uuid4(),credit_wallet=uuid4(),amount_kopecks=1,idempotency_key="invalid space")
