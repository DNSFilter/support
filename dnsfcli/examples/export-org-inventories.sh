#!/usr/bin/env bash
#
# export-org-inventories.sh
#
# USE CASE
#   Quarterly true-up / documentation: export every organization's network
#   and roaming-agent inventory to per-client CSV files. Handy for MSP
#   billing reconciliation, client QBRs, or just having an offline record.
#
# HOW IT WORKS
#   With --each-org, the {org_name} and {org_id} placeholders in an output
#   path expand per organization — so one command produces one file per
#   client, no loop required.
#
# PREREQUISITES
#   dnsfcli auth setup with an account that can see all client orgs.
#
set -euo pipefail

STAMP=$(date +%Y-%m-%d)
DIR="inventory-$STAMP"
mkdir -p "$DIR"

echo "Exporting network inventory per organization..."
dnsfcli networks list \
    --each-org --all \
    --flatten \
    --columns id,attributes.name,attributes.network_type,attributes.ip_count \
    --to-csv "$DIR/{org_name}-networks.csv"

echo "Exporting roaming agent inventory per organization..."
dnsfcli user-agents list \
    --each-org --all \
    --flatten \
    --columns id,attributes.hostname,attributes.agent_type,attributes.agent_version,attributes.agent_state \
    --to-csv "$DIR/{org_name}-agents.csv"

echo "Inventories written to $DIR/"
ls -1 "$DIR"
