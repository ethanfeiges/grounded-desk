from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"
POLICY_CANONICAL = FIXTURES / "policies" / "canonical.txt"
POLICY_DECOY = FIXTURES / "policies" / "decoy_14_day.txt"
EMAILS = FIXTURES / "emails"
ANSWERS = FIXTURES / "answers"
ORDERS = FIXTURES / "orders"
