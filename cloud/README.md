# AWS operation

Use your own AWS CLI login/SSO session with permission to provision CloudFormation, EC2, VPC, S3, IAM and SSM. Never add access keys to source or paste them into chat. `aws sts get-caller-identity` must succeed before running deploy.py. Choose the correct account and region; resources incur charges until removed.

`deploy.py` creates a new stack (not an in-place updater), packages source without Git/runtime/private keys, uploads it to encrypted S3, waits for CloudFormation completion, and then checks application health via SSM. Failure leaves a diagnosable stack; inspect events and `/var/log/partner-bootstrap.log` with an SSM session. Host readiness is recorded under state/cloud-deployment.json only after a successful application check.

Connect using the printed SSM port-forward command (requires the AWS Session Manager plugin). To trust the application certificate, retrieve `/opt/partner/state/server.crt` through your IAM-authorized SSM session and use it explicitly as a CA in your client. For a normal browser deployment, replace the generated certificate with a certificate trusted by your organization; do not bypass a browser security warning. API tokens are the same locally provisioned tokens; only hashes are deployed.

The host installs Hadoop 3.4.3 (checksummed), Spark, Java 17 and PostgreSQL. HDFS starts on boot; daily systemd refresh stages/validates/promotes data, trains the model and rebuilds the workbook. The API restarts after each refresh. Secrets are generated on-host in mode-600 environment files. HDFS data, local ledger and PostgreSQL storage live on encrypted EBS. They are not highly available or automatically backed up; take snapshots/exports before deleting the stack.

Teardown: inspect the stack outputs, preserve any desired outputs, empty all object versions/delete markers in its artifact bucket, then run `aws cloudformation delete-stack --stack-name partner-revenue-platform --region us-east-1`. Bucket versioning means a simple `s3 rm --recursive` is insufficient to empty it. Stack deletion intentionally fails for a nonempty bucket rather than silently discarding its data.

Security boundary: HDFS simple authentication is acceptable only inside this loopback-only single-user host. Distributed/multi-user Hadoop would need Kerberos and service-level encryption, which this template does not claim to configure. The model and ledger are synthetic demonstration assets. An operational cloud claim requires an authenticated deployment and runtime verification.
