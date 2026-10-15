# Application features

[Back to project overview](../README.md)

### CRM lead onboarding and regional pipeline

The application models a lead's acquisition campaign, partner, assigned sales representative, creation date, company size, region and Open/Won outcome. The **CRM** report counts Open/Won leads across Americas, EMEA and APAC. It helps a sales-operations user compare regional pipeline composition.

The **CRM lead ingestion** form accepts a JSON lead. Admin and engineer users can stage it through `POST /api/leads`. The API checks the exact field set, positive IDs/counts, valid date, allowed status/region, nonempty company, reserved `@example.test` contact address, and existing campaign/partner/representative references. Existing or already-staged lead IDs return `409`, preventing replayed submissions. Accepted records enter an inbox; they become reporting inputs only after `scripts/merge_inbox.py` and a subsequent pipeline run. The inbox is retained for replay inspection. This is staged batch integration, not a live external CRM connector or a lead-editing application.

### Marketing attribution and budget planning

The **Marketing** report connects leads and accepted sales to the lead's single acquisition campaign. It exposes campaign spend, lead volume, accepted sale count, conversion rate, net revenue and revenue-to-spend. A marketing user can compare Email, Search, Partner event and Webinar acquisition performance using one set of governed definitions.

The **Budget scenario** report proposes a redistribution of the existing total campaign budget, weighting channels by historical revenue-to-spend. It preserves the total budget to rounding tolerance. This is a descriptive planning scenario: it does not estimate marginal returns, causal advertising lift, profit, or a mathematically optimal future allocation. Synthetic spend/revenue magnitudes are demonstration inputs, not realistic marketing economics.

### Partner commission reconciliation and scoped statements

The **Partner compensation** report separates net sales revenue, calculated commission, booked accruals, existing payments and reconciliation variance. Expected commission is calculated from net revenue and the partner's configured rate. Booked-minus-expected variance identifies accrual discrepancies that finance must investigate before approval.

Finance and admin users can inspect all partner rows. A partner user's token is associated with one partner ID and returns only that partner's row, even if they call the REST endpoint directly. The browser displays the same scoped results returned by the API. In the generated demonstration, partners 1–5 include deliberate booking discrepancies, while partners 6–10 have reconciled, unpaid accruals suitable for exercising the approval workflow.

### Approval and simulated payout workflow

The **Commission workflow** section lets an authorized finance/admin user submit a partner ID for approval. Approval requires zero reconciliation variance and a positive unpaid amount. The payable calculation subtracts both existing source payments and prior simulated settlements, so already-paid amounts are not offered again.

A different finance/admin identity must authorize the payout. The service rejects missing approval, same-person authorization, changed report fingerprints, duplicate approvals, repeated payouts and nonpositive remaining amounts. New approvals against changed accruals pay only the additional outstanding balance. Decisions are persisted using atomic JSON replacement and an in-process lock. The UI displays the operation's status and response. All payouts are **simulations**; no banking, payroll or payment service is connected. There is no multiworker transactional ledger or separate ledger-history screen.

### Sales representative quota and incentive analytics

The **Sales compensation** report aggregates net sales by representative and sale month. It shows monthly quota, quota attainment, base rate, accelerator rate and calculated commission. The base rate applies to revenue up to quota; the accelerator applies only to revenue above quota. Finance can compare attainment and incentive exposure using explicit synthetic policies. This report does not approve or disburse representative payments; the approval workflow above applies to partners.

### Customer onboarding and support experience

The **Customer experience** report combines customer onboarding records with synthetic support tickets. It shows customer counts, average onboarding days, ticket counts, average CSAT, average resolution hours and counts of tickets taking more than 48 hours to resolve, grouped by region. Onboarding averages are computed at the customer grain so additional tickets do not overweight a customer.

Support and admin users can use these metrics to identify regions with slower onboarding or more SLA breaches. This is reporting over generated records, not a ticket-management interface, customer-survey integration, or evidence that service quality has actually improved.

### Lead-conversion machine learning

Spark ML trains a logistic-regression pipeline using acquisition campaign, partner, employee count and creation month. Campaign/partner IDs are treated as categories through indexing and one-hot encoding. Open/Won status supplies the label and is excluded from predictors; post-sale revenue is also excluded.

Training uses leads created before August 2025; holdout evaluation uses leads created from September 2025 onward, leaving time for the assumed 30-day label-observation window. The job persists the model, holdout ROC AUC, training prevalence, split counts and a constant-score baseline. The **Lead scores** report provides lead IDs and conversion probabilities for marketing/admin review. This is batch scoring, not a real-time prediction endpoint, recommendation engine, or automated decision system. Generated Open outcomes are assumed negative at the simulated observation horizon; synthetic performance cannot establish real-world effectiveness.

### Data generation, quality and governance

Faker creates seven linked sources: **campaigns, partners, sales representatives, leads, sales, customers and support tickets**. Seeded generation supports reproducible examples and tests; contact addresses use the reserved example.test domain. No private source data is required.

Spark reads explicit schemas, checks dimension primary keys and foreign-key references, validates permitted lead states/regions, rates, spend, quotas and support metric ranges, and rejects conflicting sale IDs or sales preceding lead creation. Invalid financial rows are quarantined. Identical valid sale replays are collapsed safely. Bad dimensions/contracts fail the batch instead of silently publishing them.

The **Data quality** report reconciles raw, accepted, invalid and replay counts. Curated lineage metadata records generation time, raw/curated paths, report names, assumed currency and attribution policy. Raw records, quarantine, curated reports, ML features, model and evaluation outputs are kept separately. Definitions and acceptance checks are linked from this README. This is a small governance implementation, not a metadata-catalog service or a complete data-lineage platform.

### Hadoop/HDFS processing and report distribution

The project runs an actual Hadoop NameNode and DataNode, uploads source files to `/partner/raw`, reads and writes HDFS through Spark, and stores curated outputs under `/partner/curated`. Lifecycle scripts configure, start and stop the local cluster, apply owner-only permissions and produce a filesystem-check report. The verified configuration is a single node with replication factor 1 and loopback-bound endpoints.

The batch runner copies report part files back to local storage for the API and combines them into stable CSV files for BI consumption. HDFS also retains the trained model and evaluation artifacts. Spark executes typed joins, deduplication, validation, financial calculations and aggregations. A separate benchmark script measures larger generated inputs without replacing the main demonstration data. This is not a distributed throughput, high-availability, Kerberos or HDFS encryption-zone demonstration.

### PostgreSQL analytics integration

When configured, Spark writes to a PostgreSQL **staging** schema. A separate transaction promotes reports into **analytics**, preserving the reporting tables, reader grants and compensation row-level policy. Writer and API reader credentials are separate; reporting access has no write privilege.

For compensation queries, the API supplies transaction-local role and partner context derived from its verified user. The database policy denies partner rows without the appropriate context and scopes them to the partner ID. Database credentials remain trusted application-service credentials. Without DATABASE_URL, the application reads curated CSV part files instead; the local demo uses that mode. PostgreSQL integration code and Linux CI checks are included, but local database execution is blocked by the tool sandbox and the remote CI job has not yet run.

### Role-based access, authentication, audit and HTTPS

The application offers **admin, marketing, finance, support, engineer and partner** roles. A provisioning script creates per-user random tokens, stores only salted PBKDF2-SHA256 hashes in the identity configuration, and saves the returned token separately with restricted file permissions. Reprovisioning a named user rotates their token; marking the user inactive revokes it. Tokens are entered into a masked browser field and sent as bearer credentials. The role matrix below defines the exact report/action allowlists.

The API returns `401` for absent/invalid authentication and `403` for disallowed roles. Access-decision events and successful write events are recorded without token contents; the admin-only **Audit** report shows the latest 100 audit entries. These logs are application records, not a tamper-proof or complete final-response audit trail. API responses disable caching and set a no-sniff header. Optional certificate/key configuration enables HTTPS with TLS 1.2 or newer; certificate and hostname verification were exercised locally. This is token authentication, not SSO, MFA or an enterprise identity provider.

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

### Tableau reporting package

The packaged workbook includes CSV snapshots, eight analytical sheets and a **Revenue Operations Overview** dashboard. Sheets cover campaign revenue, campaign conversion, partner commission variance, sales quota attainment, customer satisfaction, customer SLA breaches, regional CRM pipeline and proposed campaign budget. The build script regenerates the TWB/TWBX after reports refresh; the workbook is a snapshot rather than a live API connection.

The package, embedded data references and worksheet/dashboard counts were checked programmatically. Native Tableau opening/rendering has not been verified, and it has not been published to Tableau Server, Tableau Cloud or Tableau Public. The screenshots below show this project's browser interface, not Tableau views.

### AWS deployment and scheduled operations

Deployment code packages the project and hashed identity configuration, creates an AWS stack, uploads the artifact to private encrypted/versioned S3, waits for provisioning, and checks actual host/application readiness through Systems Manager. The host installs Java, Hadoop, Spark and PostgreSQL; generates on-host service credentials; and starts systemd-managed HDFS and HTTPS API services. A daily timer runs at 02:00 UTC, merges staged leads, refreshes reports and the model, promotes database outputs, and rebuilds the Tableau package. Refreshes take an exclusive batch lock and stop/restart the API for the maintenance window.

The stack requests encrypted EBS storage, a TLS-only S3 policy, IMDSv2, an instance role limited to the project artifact plus SSM management, and no inbound security-group rules. The host uses a public subnet for outbound downloads; the application, database and Hadoop listeners bind to loopback and are accessed through an IAM-authorized SSM tunnel. Certificate trust still needs proper client/organizational configuration. The application does not expose an AWS management screen.

**Cloud execution is currently on hold because of cost concerns.** The template was statically validated; no AWS resources were created and no cloud readiness result is claimed. The implementation is a single-host portfolio deployment, with no automatic backup, failover, production identity provider or production load balancer. Teardown guidance covers persistent bucket versions and billable resources.

### Reproducibility, testing and delivery artifacts

The repository includes dependency pins, seeded data generation, local/HDFS launch scripts, typed financial logic, reconciliation tests, role-isolation and approval-state tests, API checks, native TLS verification evidence, workbook source/package checks, HDFS health output, saved ML evaluation, a scale-measurement script, JD mapping and an acceptance/handoff backlog.

GitHub Actions is configured to run the pipeline against HDFS and PostgreSQL on Linux, check row-level security and read-only permissions, build the Tableau package, run tests, lint CloudFormation and retain validation artifacts. That remote workflow is supplied but has not yet executed because repository publication is blocked by GitHub authentication. No actual stakeholder review, degree qualification or employment experience is represented by these artifacts.

Full sample outputs: [marketing](../data/curated/marketing.csv), [budget scenario](../data/curated/budget_allocation.csv), [partner commissions](../data/curated/compensation.csv), [sales quotas](../data/curated/rep_compensation.csv), [customer experience](../data/curated/customer_experience.csv), [CRM](../data/curated/crm.csv), [data quality](../data/curated/quality.csv), and [lead scores](../data/curated/lead_scores.csv).
