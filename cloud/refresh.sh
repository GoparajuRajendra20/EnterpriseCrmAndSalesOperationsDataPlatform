#!/bin/bash
set -euo pipefail
cd /opt/partner
exec 9>state/refresh.lock
flock -n 9 || exit 0
systemctl stop partner-api.service || true
trap 'systemctl start partner-api.service' EXIT
sudo -u platform bash -c 'set -euo pipefail; cd /opt/partner; source state/pipeline.env; .venv/bin/python scripts/merge_inbox.py; export JDBC_JAR=/opt/partner/postgresql.jar; ./hadoop/run.sh; .venv/bin/python scripts/promote_database.py; .venv/bin/python tableau/build_workbook.py'
