# Partner Revenue Intelligence

A runnable synthetic data-engineering portfolio covering CRM, marketing attribution, sales/partner compensation, customer experience, governance, ML, Hadoop/HDFS, role-scoped REST APIs, PostgreSQL integration, Tableau, and AWS deployment code.



## Business use case

A business acquires enterprise leads through campaigns and channel partners. Marketing needs to connect spend to converted sales; finance needs to reconcile booked commissions, existing payments and unpaid accruals; support needs to monitor onboarding and service quality. This platform builds shared, validated reporting datasets for those decisions, with scoped API access and lead-conversion scoring.

## Verified results

These results come from local synthetic-data runs. They are engineering validation, not measured business outcomes or cloud performance.

| Check | Observed result |
|---|---|
| Functional and business-rule tests | **11 passed** |
| Main synthetic dataset | **10,000 leads**, **2,840 accepted sales** |
| Raw sales reconciliation | **2,842 = 2,840 accepted + 1 invalid + 1 replay duplicate** |
| Hadoop/HDFS | Live NameNode/DataNode; Spark read/write; **HEALTHY** filesystem |
| Larger batch measurement | **100,000 leads in 66.13 seconds**, single-host `local[2]` |
| ML holdout ROC AUC | **0.5716**, compared with a constant-score baseline of **0.5** |
| ML temporal split | **7,063 training / 1,870 holdout rows**, with a label-observation gap |
| API validation | **Eight report endpoints** returned data; role denial and partner isolation tested |
| Secure transfer | Authenticated HTTPS passed certificate and hostname verification |
| AWS infrastructure | CloudFormation static validation passed; **not deployed** |
| Tableau | Eight-sheet packaged workbook and overview dashboard created; native rendering **unverified** |

Evidence: [validation record](VALIDATION.json), [HDFS filesystem check](docs/HDFS_FSCK.txt), [ML metrics](docs/ML_METRICS.json), [benchmark measurement](docs/BENCHMARK.json), and [test source](tests/). The Linux PostgreSQL/HDFS integration [CI workflow](.github/workflows/validate.yml) is provided; no completed GitHub CI run is claimed yet. Local PostgreSQL runtime validation remains blocked by the tool environment's shared-memory restriction.

## Screenshots

Actual screenshots of the running local browser interface, using Spark-produced synthetic reports. These are application screenshots, not Tableau or AWS screenshots.

### Marketing performance

Channel-level lead counts, conversions and attributed revenue. Revenue-to-spend is descriptive attribution, not causal marketing ROI.

![Marketing performance report](docs/screenshots/marketing.png)

### Customer experience

Onboarding time, customer satisfaction, resolution hours and SLA breaches across Americas, EMEA and APAC.

![Customer-experience report](docs/screenshots/customer-experience.png)

### Data-quality reconciliation

One invalid financial record is quarantined and one identical replay is removed, preserving the raw-to-accepted reconciliation.

![Data-quality reconciliation](docs/screenshots/data-quality.png)

## Architecture

```text
Faker → raw CSV (7 entities) → Hadoop HDFS → Spark validation + transformations
                                         ├→ Spark ML: time-split evaluation + lead scores
                                         ├→ curated HDFS → local API reports / Tableau TWBX
                                         └→ PostgreSQL staging → transactional analytics promotion
User token → PBKDF2 verification → role + partner scope → REST API → browser interface
AWS: encrypted EBS + private application/HDFS/PostgreSQL + TLS + IAM/SSM tunnel + daily refresh
```

Core JD technologies: Hadoop/HDFS, Spark (including MLlib), PostgreSQL, Tableau, REST APIs. Faker/Python implement the synthetic data and application. AWS CloudFormation provisions the explicitly requested cloud environment. No extra web framework is required.

## Run locally

Use Python 3.11 and Java 17 for the portable setup. The prepared environment on this machine has also run with Python 3.13.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python generate.py --leads 10000
export JAVA_HOME=/absolute/path/to/java17
export HADOOP_HOME=/absolute/path/to/hadoop-3.4.3
export SPARK_LOCAL_IP=127.0.0.1
export PYSPARK_PYTHON="$PWD/.venv/bin/python"
./hadoop/start.sh
./hadoop/run.sh
.venv/bin/python tableau/build_workbook.py
.venv/bin/python scripts/provision_user.py demo admin --token-file state/demo-token
PORT=8001 .venv/bin/python server.py
```

Visit http://127.0.0.1:8001 and enter the token saved in `state/demo-token`. No tokens, private keys, credentials, database state or HDFS storage belong in Git. To provision a partner user, use `scripts/provision_user.py partner1 partner --partner-id 1 --token-file state/partner1-token`. Rotating a named user replaces that user's token hash; set active=false in the protected users config to revoke access.

The macOS tool sandbox may stop daemon processes launched by a short-lived shell. If that happens, run `hdfs namenode` and `hdfs datanode` in separate long-lived terminals using `HADOOP_CONF_DIR="$PWD/state/hadoop-conf"`. The checked-in launch scripts are intended for a normal terminal or the Linux cloud host. HDFS is single-node with replication=1 and loopback-only listeners. It is not a secure multi-tenant Hadoop cluster: no Kerberos or HDFS transparent-encryption zone is claimed.

For a CSV-only quick start, run `.venv/bin/spark-submit --master 'local[2]' pipeline.py`, then `train.py`, then `scripts/export_reports.py`. This mode does not demonstrate HDFS.

## Reports and business rules

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

## Access control and API

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

## PostgreSQL

Initialize the schemas/reader group using `access.sql` as the database owner/admin. Provision distinct owner/writer and reader login credentials; grant `analytics_reader` only to the API login. `cloud/init_database.py` automates this on the AWS host. Set JDBC_URL, DB_USER, DB_PASSWORD, JDBC_JAR and WRITER_DATABASE_URL for batch processing. Spark writes staging tables; `scripts/promote_database.py` atomically promotes all reports and preserves analytics grants/policies. Then set DATABASE_URL to the reader connection string for the API.

Compensation row-level security defaults to no rows without an application role context, scopes partner IDs, and permits finance/admin. The API sets transaction-local context from its verified identity. Database credentials are trusted service credentials, not handed to end users. SQL integration tests live in `scripts/verify_database.py` and the Linux CI job. Local PostgreSQL execution remains blocked by the macOS tool sandbox's shared-memory restriction unless validation evidence says otherwise.

## Encryption and AWS deployment

Set TLS_CERT and TLS_KEY to enable HTTPS with minimum TLS 1.2. The local HTTPS endpoint was tested using an explicitly trusted generated certificate and hostname verification; do not disable certificate checks. Default local HTTP exists for UI development only.

The AWS template creates billable resources: a t3.large host, encrypted 60 GiB EBS storage, a private encrypted/versioned S3 artifact bucket, IAM role, VPC and subnet. The instance has no inbound security-group rules and requires IMDSv2. PostgreSQL, HDFS and HTTPS bind to loopback. Access uses IAM-authorized SSM port forwarding. Off-host data transfer uses HTTPS/S3 TLS or SSM; same-host JDBC/HDFS traffic stays on loopback. EBS encryption protects on-host data at rest. This is a single-host portfolio deployment, not a highly available production service.

```bash
aws sts get-caller-identity
.venv/bin/python cloud/deploy.py --region us-east-1
```

Provision users first. Deployment packages source and hashed identities; token files stay local. It creates the stack, uploads the source, then checks bootstrap readiness through SSM. It is not successful merely because a VM exists. Read `cloud/README.md` for access, teardown and credential requirements. AWS deployment must be reported as pending until a real readiness result exists.

## Tableau and ML

Open `tableau/PartnerRevenue.twbx` in Tableau Desktop. The package includes local CSV data, eight worksheets and an overview dashboard. `tableau/build_workbook.py` regenerates it. This workbook contains synthetic data and is a snapshot; refresh it after the pipeline. XML/archive validation is separate from native Tableau rendering; see VALIDATION.json for actual evidence.

`train.py` trains a Spark logistic-regression pipeline. Training ends before August 2025; holdout starts September 2025, leaving a 31-day label-observation gap. Campaign/partner IDs are encoded as categories. Outcome status and post-sale revenue are excluded from features. AUC, prevalence, split counts and a baseline are saved with the model. Synthetic labels embed campaign tendencies; holdout performance does not establish real-world predictive value. All generated Open leads are treated as negative at a fixed simulated observation horizon.

## Verification

```bash
.venv/bin/python -m unittest discover -s tests -v
# QA-only tool: pip install cfn-lint
cfn-lint cloud/stack.json
```

GitHub Actions additionally runs HDFS, Spark, ML, PostgreSQL promotion/RLS checks and workbook packaging on Linux. That workflow is implemented, but is not claimed to have run until GitHub reports a completed run. See `VALIDATION.json`, `docs/JD_COVERAGE.md` and `docs/DELIVERY.md` for honest coverage and residual limits.
