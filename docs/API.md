# API and access control

[Back to project overview](../README.md)

| Role | Access |
|---|---|
| admin | All reports, CRM staging, approval, simulated payout, audit |
| marketing | Marketing, budget scenario, CRM, lead scores |
| finance | Partner/sales compensation, approvals and simulated payouts |
| support | Customer experience |
| engineer | Data quality and CRM staging |
| partner | Own partner compensation row only |

GET `/api/<report>` serves the reports above; GET `/api/audit` is admin-only. POST `/api/leads` validates and stages a synthetic lead in an idempotent inbox. POST `/api/approvals` and `/api/payouts` accept `{"partner_id":1}`. GET `/health` reports the active backend without exposing data. Missing credentials return 401; insufficient role returns 403. Audit records omit tokens. The API is a small single-process demo, not a production identity provider. Ledger/inbox writes are protected by an in-process lock and atomic replacement; use PostgreSQL transactions before deploying multiple API workers.

`merge_inbox.py` merges staged records once; stop the API during that maintenance operation. The cloud refresh service does this and restarts the API after the batch. Daily refresh has a short reporting maintenance window.

### Browser reporting interface and REST API

The browser interface provides buttons for eight analytical reports and the admin audit view, a partner approval/payout form, a lead JSON staging form, masked credential entry, formatted numeric values, and operation/error messages. Report cells are populated as text rather than interpreted HTML. Tables scroll horizontally on narrow screens; the CSV links below expose the full report columns independently of screenshots. There are no interactive chart filters, search, user-management screens, or browser CSV-export buttons.

| Endpoint | Application behavior |
|---|---|
| `GET /api/marketing` | Channel acquisition and revenue metrics |
| `GET /api/budget_allocation` | Fixed-total budget planning scenario |
| `GET /api/compensation` | Partner commissions, scoped by role/partner |
| `GET /api/rep_compensation` | Monthly representative quotas and incentive calculations |
| `GET /api/customer_experience` | Regional onboarding/support metrics |
| `GET /api/crm` | Regional Open/Won lead counts |
| `GET /api/quality` | Raw-to-curated financial-record reconciliation |
| `GET /api/lead_scores` | Batch lead-conversion probabilities |
| `GET /api/audit` | Latest 100 audit events; admin only |
| `POST /api/leads` | Validate and stage a synthetic lead; admin/engineer |
| `POST /api/approvals` | Approve a reconciled unpaid partner accrual; admin/finance |
| `POST /api/payouts` | Simulate the approved payout using a different identity; admin/finance |
| `GET /health` | Unauthenticated process/backend-mode check; not a database-readiness probe |

Report responses are capped at 1,000 rows and do not support pagination or filtering parameters. Full generated report files remain available in curated storage. POST requests are limited to 16 KiB. HTTP status codes distinguish validation/state errors (`400`), identity/role errors (`401`/`403`), duplicate/conflicting operations (`409`), unknown routes (`404`) and unavailable reporting/storage (`503`).
