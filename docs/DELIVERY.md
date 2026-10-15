# Delivery backlog and handoffs

This is an implemented portfolio delivery, not evidence of real employment or stakeholder participation.

| Work item | Acceptance evidence / owner to review |
|---|---|
| CRM integration | Valid lead stages once; bad references and duplicates rejected; CRM owner |
| Marketing | Acquisition attribution and budget-total preservation; marketing analyst |
| Finance | Net/refund reconciliation; progressive rep tiers; variance blocks approval; different approver and delta payouts; finance reviewer |
| Customer support | Regional CSAT and 48-hour breach reporting; support reviewer |
| Governance | Typed source contracts, FK validation, quarantine, reconciliation and report lineage; data steward |
| ML | Temporal gap, no outcome leakage, baseline/holdout metrics; ML reviewer |
| Hadoop | HDFS raw and curated paths plus fsck evidence; platform engineer |
| Database | Transactional promotion, read-only service credential and compensation RLS; database administrator |
| BI | Open packaged Tableau workbook and inspect all sheets; BI reviewer |
| Cloud | CloudFormation validation, encrypted storage, SSM access and actual readiness; cloud operator |
| Release | Unit/integration CI, local commit and authenticated Git push; repository owner |

Review cadence: demonstrate the accepted outputs after each work item, capture issues as reproducible fixtures, and use pull requests/CI for subsequent changes. Americas/EMEA/APAC dimensions support global reporting; they do not establish actual global deployment or collaboration.

Known operating limits: batch overwrite rather than CDC; daily cloud maintenance window; single-node HDFS replication=1; simulated finance events only; simple token identity rather than SSO; no production scale/HA claim; native Tableau verification and AWS execution must be explicitly recorded as done or blocked.

Primary references used for integration design:
- Hadoop single-node setup: https://hadoop.apache.org/docs/r3.4.1/hadoop-project-dist/hadoop-common/SingleCluster.html
- Spark JDBC: https://spark.apache.org/docs/3.5.7/sql-data-sources-jdbc.html
- Tableau packaged workbooks: https://help.tableau.com/current/pro/desktop/en-gb/save_savework.htm
- AWS private SSM access: https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager.html
- Amazon Corretto installation: https://docs.aws.amazon.com/corretto/latest/corretto-17-ug/amazon-linux-install.html
