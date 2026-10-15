# JD coverage and evidence boundary

| JD area | Code provided | Runtime evidence needed |
|---|---|---|
| CRM, marketing, partner and sales compensation | Eight source entities, joins, attribution, quota tiers, approvals, simulated payout | Spark reports and API tests |
| Customer experience | Onboarding/support generator, regional CSAT and SLA metrics | Customer report rows |
| Data governance | Contracts, primary/foreign keys, quarantine, replay handling, lineage | Raw reconciliation and failure checks |
| Hadoop/HDFS + Spark | Actual NameNode/DataNode scripts, HDFS input/output and Spark transforms | HDFS fsck + job completion |
| Databases | PostgreSQL staging, atomic promotion, independent writer/reader, compensation RLS | Linux database integration tests; local execution blocked by sandbox |
| REST/full stack | Role-scoped reports, validated CRM inbox, browser UI | HTTP status, row isolation and workflow tests |
| Access controls | Salted per-user token hashes, role allowlists, partner scope, audit, separation of duties | API tests and database RLS test |
| Encryption/secure transfer | API TLS, cloud encrypted EBS/S3, TLS-only bucket, private listeners/SSM | Local verified HTTPS; cloud deployment readiness pending authentication |
| Tableau | Packaged workbook, CSV snapshots, eight sheets and overview dashboard | Archive/XML checks; native rendering must be separately verified |
| AI literacy / ML | Spark trained pipeline, temporal holdout, score output, baseline and caveats | Saved evaluation metrics |
| Cloud-first | AWS infrastructure/bootstrap, private access, service lifecycle and daily refresh | Actual AWS login, deployment and health check |
| Agile / collaboration | CI, backlog, acceptance criteria, role handoffs and runbooks | Actual human reviews are outside this solo prototype |
| Education / experience | No code can satisfy these eligibility requirements | Applicant's actual background |

No proof of causal marketing lift, actual customer improvement, enterprise scalability or real commission transfers is claimed. See VALIDATION.json for the observed results rather than assuming provided code has run everywhere.
