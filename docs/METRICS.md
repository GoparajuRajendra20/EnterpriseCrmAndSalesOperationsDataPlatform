# Reports and metric definitions

[Back to project overview](../README.md)

| Report | Decision supported |
|---|---|
| marketing | Lead conversion, acquisition-channel attributed revenue and revenue/spend |
| budget_allocation | Fixed-total budget scenario weighted by historical revenue/spend; descriptive heuristic, not causal optimization |
| compensation | Partner calculated vs booked accruals, existing payments and exceptions |
| rep_compensation | Monthly quotas, attainment, base commission and accelerated commission above quota |
| customer_experience | Regional onboarding time, support CSAT, resolution time and 48-hour SLA breaches |
| crm | Open/won lead counts across Americas, EMEA and APAC |
| quality | Raw/accepted/quarantined/duplicate reconciliation |
| lead_scores | Trained lead-conversion probabilities |

Revenue is gross minus refunds, in assumed USD. Partner expected commission = net revenue × rate, rounded to cents. Reconciliation variance = booked accrual minus expected accrual. Payable = expected accrual minus existing source payments minus previous simulated payouts; overbooked accruals block approval. Sales rep commissions apply the base rate up to monthly quota and the accelerator only to revenue above quota. These are explicit invented policies, not Cisco compensation rules. Quota inputs and spend are synthetic; revenue/spend is not profit ROI.

A finance user can approve the unpaid portion of reconciled partner accruals; another finance user can simulate payout. Duplicate approvals/payouts are rejected, and subsequent approvals only pay newly accrued amounts. A nonzero variance blocks approval. This records simulated ledger events and never transfers money.
