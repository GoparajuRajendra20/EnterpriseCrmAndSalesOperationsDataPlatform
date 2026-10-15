"""Boundary cases for rules shared by the HTTP API and finance workflows."""

import unittest

from workflows import approve_partner, simulate_payout


class CommissionBoundaryTests(unittest.TestCase):
    def test_existing_source_payments_reduce_the_approved_amount(self):
        statement = {
            "partner_id": 6,
            "expected_commission": "500.00",
            "paid_commission": "350.00",
            "commission_variance": "0.00",
        }
        approval = approve_partner(statement, None, {"name": "reviewer"})
        self.assertEqual(approval["amount"], "150.00")

    def test_changed_statement_requires_a_new_review(self):
        statement = {
            "partner_id": 6,
            "expected_commission": "500.00",
            "paid_commission": "0.00",
            "commission_variance": "0.00",
        }
        approval = approve_partner(statement, None, {"name": "reviewer"})
        changed_statement = dict(statement, expected_commission="550.00")
        with self.assertRaisesRegex(ValueError, "changed after approval"):
            simulate_payout(changed_statement, approval, {"name": "second-reviewer"})


if __name__ == "__main__":
    unittest.main()
