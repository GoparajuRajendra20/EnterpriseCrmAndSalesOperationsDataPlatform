"""Create billable AWS resources, upload source, and wait for actual application readiness."""
import argparse,json,subprocess,time,zipfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--region',default='us-east-1');p.add_argument('--stack',default='partner-revenue-platform');a=p.parse_args()
base=Path(__file__).resolve().parents[1]
def aws(*args):return subprocess.check_output(['aws','--region',a.region,*args],text=True)
identity=json.loads(aws('sts','get-caller-identity'));print('Deploying to AWS account',identity['Account'])
config=base/'state/users.json'
if not config.exists():raise SystemExit('Provision users before deployment; see README')
artifact=base/'state/cloud-project.zip'
with zipfile.ZipFile(artifact,'w',zipfile.ZIP_DEFLATED) as z:
    for f in base.rglob('*'):
        rel=f.relative_to(base)
        if not f.is_file() or any(x in rel.parts for x in ['.git','.venv','__pycache__','state']):continue
        if f.suffix in ['.key','.pem','.log']:continue
        z.write(f,str(rel))
    z.write(config,'state/users.json')
aws('cloudformation','create-stack','--stack-name',a.stack,'--template-body','file://'+str(base/'cloud/stack.json'),'--capabilities','CAPABILITY_IAM')
# Bucket must exist before the waiting host can download its artifact.
bucket=None
for _ in range(120):
    r=json.loads(aws('cloudformation','list-stack-resources','--stack-name',a.stack))
    bucket=next((x.get('PhysicalResourceId') for x in r['StackResourceSummaries'] if x['LogicalResourceId']=='ArtifactBucket' and x['ResourceStatus']=='CREATE_COMPLETE'),None)
    if bucket:break
    time.sleep(5)
if not bucket:raise SystemExit('Bucket not ready; inspect CloudFormation events')
aws('s3','cp',str(artifact),'s3://'+bucket+'/project.zip','--sse','AES256')
aws('cloudformation','wait','stack-create-complete','--stack-name',a.stack)
out=json.loads(aws('cloudformation','describe-stacks','--stack-name',a.stack))['Stacks'][0]['Outputs'];values={x['OutputKey']:x['OutputValue'] for x in out};instance=values['InstanceId']
print('Host created:',instance,'; waiting for bootstrap readiness')
for _ in range(90):
    try:
        command=json.loads(aws('ssm','send-command','--instance-ids',instance,'--document-name','AWS-RunShellScript','--parameters',json.dumps({'commands':['test -f /opt/partner/state/cloud-ready && curl --fail --cacert /opt/partner/state/server.crt https://localhost:9443/health']})))['Command']['CommandId']
        time.sleep(5)
        result=json.loads(aws('ssm','get-command-invocation','--command-id',command,'--instance-id',instance))
        if result['Status']=='Success':
            (base/'state/cloud-deployment.json').write_text(json.dumps(values,indent=2));print('AWS APPLICATION READY',result['StandardOutputContent']);break
    except subprocess.CalledProcessError:pass
    time.sleep(15)
else:raise SystemExit('Host exists but application not ready; inspect /var/log/partner-bootstrap.log via SSM')
print('Tunnel: aws --region '+a.region+' ssm start-session --target '+instance+' --document-name AWS-StartPortForwardingSession --parameters '+"'{\"portNumber\":[\"9443\"],\"localPortNumber\":[\"9443\"]}'")
