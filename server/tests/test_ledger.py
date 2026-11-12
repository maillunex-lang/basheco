import unittest
from basheco.ledger import Transfer, apply_transfer, validate_transfer


class LedgerTests(unittest.TestCase):
    def test_transfer_conserves_money(self):
        before = {"a": 1001, "b": 99}
        after = apply_transfer(before, Transfer("a", "b", 101, "tx-1"))
        self.assertEqual(after, {"a": 900, "b": 200})
        self.assertEqual(sum(before.values()), sum(after.values()))
        self.assertEqual(before["a"], 1001)

    def test_insufficient_funds(self):
        with self.assertRaisesRegex(ValueError, "Insufficient"):
            apply_transfer({"a": 2, "b": 0}, Transfer("a", "b", 3, "tx-2"))

    def test_invalid_amounts(self):
        for amount in (0, -1, 1.5, True, "100"):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                validate_transfer(Transfer("a", "b", amount, "tx-3"))

    def test_self_transfer(self):
        with self.assertRaises(ValueError):
            validate_transfer(Transfer("a", "a", 1, "tx-4"))

    def test_unknown_wallet(self):
        with self.assertRaises(ValueError):
            apply_transfer({"a": 100}, Transfer("a", "b", 1, "tx-5"))

    def test_missing_idempotency_key(self):
        with self.assertRaises(ValueError):
            validate_transfer(Transfer("a", "b", 1, ""))


if __name__ == "__main__":
    unittest.main()
