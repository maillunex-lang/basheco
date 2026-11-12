"""Pure game-money transfer validation; integer kopecks, not floats.

Not a persistent ledger or API. Production transfers require transactional
wallet locks, idempotency enforcement and atomic journal postings.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Transfer:
    debit_wallet: str
    credit_wallet: str
    amount_kopecks: int
    idempotency_key: str


def validate_transfer(transfer: Transfer) -> None:
    if not transfer.debit_wallet or not transfer.credit_wallet:
        raise ValueError("Both wallet IDs are required")
    if transfer.debit_wallet == transfer.credit_wallet:
        raise ValueError("Self transfers are not allowed")
    if type(transfer.amount_kopecks) is not int or transfer.amount_kopecks <= 0:
        raise ValueError("Amount must be a positive integer number of kopecks")
    if not transfer.idempotency_key or len(transfer.idempotency_key) > 128:
        raise ValueError("Valid idempotency key required")


def apply_transfer(balances: dict[str, int], transfer: Transfer) -> dict[str, int]:
    """Pure simulation helper. Returns a copy and never mutates input."""
    validate_transfer(transfer)
    if transfer.debit_wallet not in balances or transfer.credit_wallet not in balances:
        raise ValueError("Unknown wallet")
    if any(type(v) is not int or v < 0 for v in balances.values()):
        raise ValueError("Balances must be nonnegative integer kopecks")
    if balances[transfer.debit_wallet] < transfer.amount_kopecks:
        raise ValueError("Insufficient funds")
    result = balances.copy()
    result[transfer.debit_wallet] -= transfer.amount_kopecks
    result[transfer.credit_wallet] += transfer.amount_kopecks
    return result
