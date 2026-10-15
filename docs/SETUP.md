# Setup and operation

[Back to project overview](../README.md)

## Local setup

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

## PostgreSQL

Initialize the schemas/reader group using `access.sql` as the database owner/admin. Provision distinct owner/writer and reader login credentials; grant `analytics_reader` only to the API login. `cloud/init_database.py` automates this on the AWS host. Set JDBC_URL, DB_USER, DB_PASSWORD, JDBC_JAR and WRITER_DATABASE_URL for batch processing. Spark writes staging tables; `scripts/promote_database.py` atomically promotes all reports and preserves analytics grants/policies. Then set DATABASE_URL to the reader connection string for the API.

Compensation row-level security defaults to no rows without an application role context, scopes partner IDs, and permits finance/admin. The API sets transaction-local context from its verified identity. Database credentials are trusted service credentials, not handed to end users. SQL integration tests live in `scripts/verify_database.py` and the Linux CI job. Local PostgreSQL execution remains blocked by the macOS tool sandbox's shared-memory restriction unless validation evidence says otherwise.

## Security and cloud deployment

Set TLS_CERT and TLS_KEY to enable HTTPS with minimum TLS 1.2. The local HTTPS endpoint was tested using an explicitly trusted generated certificate and hostname verification; do not disable certificate checks. Default local HTTP exists for UI development only.

The AWS template creates billable resources: a t3.large host, encrypted 60 GiB EBS storage, a private encrypted/versioned S3 artifact bucket, IAM role, VPC and subnet. The instance has no inbound security-group rules and requires IMDSv2. PostgreSQL, HDFS and HTTPS bind to loopback. Access uses IAM-authorized SSM port forwarding. Off-host data transfer uses HTTPS/S3 TLS or SSM; same-host JDBC/HDFS traffic stays on loopback. EBS encryption protects on-host data at rest. This is a single-host portfolio deployment, not a highly available production service.

```bash
aws sts get-caller-identity
.venv/bin/python cloud/deploy.py --region us-east-1
```

Provision users first. Deployment packages source and hashed identities; token files stay local. It creates the stack, uploads the source, then checks bootstrap readiness through SSM. It is not successful merely because a VM exists. Read `cloud/README.md` for access, teardown and credential requirements. AWS deployment must be reported as pending until a real readiness result exists.

## Tableau and machine learning

Open `tableau/PartnerRevenue.twbx` in Tableau Desktop. The package includes local CSV data, eight worksheets and an overview dashboard. `tableau/build_workbook.py` regenerates it. This workbook contains synthetic data and is a snapshot; refresh it after the pipeline. XML/archive validation is separate from native Tableau rendering; see VALIDATION.json for actual evidence.

`train.py` trains a Spark logistic-regression pipeline. Training ends before August 2025; holdout starts September 2025, leaving a 31-day label-observation gap. Campaign/partner IDs are encoded as categories. Outcome status and post-sale revenue are excluded from features. AUC, prevalence, split counts and a baseline are saved with the model. Synthetic labels embed campaign tendencies; holdout performance does not establish real-world predictive value. All generated Open leads are treated as negative at a fixed simulated observation horizon.

## Verification

```bash
.venv/bin/python -m unittest discover -s tests -v
# QA-only tool: pip install cfn-lint
cfn-lint cloud/stack.json
```

GitHub Actions additionally runs HDFS, Spark, ML, PostgreSQL promotion/RLS checks and workbook packaging on Linux. That workflow is implemented, but is not claimed to have run until GitHub reports a completed run. See `VALIDATION.json`, `JD_COVERAGE.md` and `DELIVERY.md` for honest coverage and residual limits.
