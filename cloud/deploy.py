"""Create billable AWS resources, upload source, and wait for actual application readiness."""

import argparse
import json
import subprocess
import time
import zipfile
from pathlib import Path


def main():
    """Provision and verify the application only through an explicit CLI invocation."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--stack", default="partner-revenue-platform")
    args = parser.parse_args()
    project_directory = Path(__file__).resolve().parents[1]

    def aws(*args):
        return subprocess.check_output(
            ["aws", "--region", args.region, *args], text=True
        )

    identity = json.loads(aws("sts", "get-caller-identity"))
    print("Deploying to AWS account", identity["Account"])
    config = project_directory / "state/users.json"
    if not config.exists():
        raise SystemExit("Provision users before deployment; see README")
    artifact = project_directory / "state/cloud-project.zip"
    with zipfile.ZipFile(artifact, "w", zipfile.ZIP_DEFLATED) as archive:
        for source_file in project_directory.rglob("*"):
            rel = source_file.relative_to(project_directory)
            if not source_file.is_file() or any(
                x in rel.parts for x in [".git", ".venv", "__pycache__", "state"]
            ):
                continue
            if source_file.suffix in [".key", ".pem", ".log"]:
                continue
            archive.write(source_file, str(rel))
        archive.write(config, "state/users.json")
    aws(
        "cloudformation",
        "create-stack",
        "--stack-name",
        args.stack,
        "--template-body",
        "file://" + str(project_directory / "cloud/stack.json"),
        "--capabilities",
        "CAPABILITY_IAM",
    )
    # Bucket must exist before the waiting host can download its artifact.
    bucket = None
    for _ in range(120):
        resources = json.loads(
            aws("cloudformation", "list-stack-resources", "--stack-name", args.stack)
        )
        bucket = next(
            (
                x.get("PhysicalResourceId")
                for x in resources["StackResourceSummaries"]
                if x["LogicalResourceId"] == "ArtifactBucket"
                and x["ResourceStatus"] == "CREATE_COMPLETE"
            ),
            None,
        )
        if bucket:
            break
        time.sleep(5)
    if not bucket:
        raise SystemExit("Bucket not ready; inspect CloudFormation events")
    aws("s3", "cp", str(artifact), "s3://" + bucket + "/project.zip", "--sse", "AES256")
    aws("cloudformation", "wait", "stack-create-complete", "--stack-name", args.stack)
    stack_outputs = json.loads(
        aws("cloudformation", "describe-stacks", "--stack-name", args.stack)
    )["Stacks"][0]["Outputs"]
    outputs = {x["OutputKey"]: x["OutputValue"] for x in stack_outputs}
    instance = outputs["InstanceId"]
    print("Host created:", instance, "; waiting for bootstrap readiness")
    for _ in range(90):
        try:
            command = json.loads(
                aws(
                    "ssm",
                    "send-command",
                    "--instance-ids",
                    instance,
                    "--document-name",
                    "AWS-RunShellScript",
                    "--parameters",
                    json.dumps(
                        {
                            "commands": [
                                "test -f /opt/partner/state/cloud-ready && curl --fail --cacert /opt/partner/state/server.crt https://localhost:9443/health"
                            ]
                        }
                    ),
                )
            )["Command"]["CommandId"]
            time.sleep(5)
            result = json.loads(
                aws(
                    "ssm",
                    "get-command-invocation",
                    "--command-id",
                    command,
                    "--instance-id",
                    instance,
                )
            )
            if result["Status"] == "Success":
                (project_directory / "state/cloud-deployment.json").write_text(
                    json.dumps(outputs, indent=2)
                )
                print("AWS APPLICATION READY", result["StandardOutputContent"])
                break
        except subprocess.CalledProcessError:
            pass
        time.sleep(15)
    else:
        raise SystemExit(
            "Host exists but application not ready; inspect /var/log/partner-bootstrap.log via SSM"
        )
    print(
        "Tunnel: aws --region "
        + args.region
        + " ssm start-session --target "
        + instance
        + " --document-name AWS-StartPortForwardingSession --parameters "
        + '\'{"portNumber":["9443"],"localPortNumber":["9443"]}\''
    )


if __name__ == "__main__":
    main()
