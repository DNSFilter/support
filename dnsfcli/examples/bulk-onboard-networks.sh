#!/usr/bin/env bash
#
# bulk-onboard-networks.sh
#
# USE CASE
#   Onboard a new client (or site rollout) by creating many networks in one
#   batch from a spreadsheet, with resumable error handling. This is the
#   workflow for anything too big to click through the dashboard.
#
# HOW IT WORKS
#   1. Generate a blank CSV template for `networks create`.
#   2. You (or the client) fill it in with one row per network.
#   3. Run the batch: dnsfcli previews the rows, asks for confirmation,
#      then makes one API call per row.
#   4. Failed rows are written to a separate CSV so a partial failure can
#      be retried without re-creating the rows that succeeded.
#
# PREREQUISITES
#   dnsfcli auth setup    (or export DNSF_API_KEY / DNSF_ORG_ID)
#
set -euo pipefail

TEMPLATE="networks-to-create.csv"
REPORT="onboard-report.json"
FAILED="onboard-failed-rows.csv"

# ── Step 1: generate the template (only if you don't already have a CSV) ──
if [[ ! -f "$TEMPLATE" ]]; then
    dnsfcli networks create --template > "$TEMPLATE"
    echo "Template written to $TEMPLATE — fill it in (one network per row),"
    echo "then re-run this script."
    exit 0
fi

# ── Step 2: validate the CSV without touching the API ──
# Catches missing columns, bad types, and empty required cells up front.
dnsfcli networks create --from-csv "$TEMPLATE" --validate-only

# ── Step 3: run the batch ──
#   --on-error continue   keep going past individual failures
#   --errors-to-csv       collect failed rows for retry
#   --batch-report        machine-readable per-row outcome summary
#   --to-csv              save the created resources (with their new IDs)
dnsfcli networks create \
    --from-csv "$TEMPLATE" \
    --on-error continue \
    --errors-to-csv "$FAILED" \
    --batch-report "$REPORT" \
    --to-csv created-networks.csv

# ── Step 4: retry anything that failed (e.g. transient API errors) ──
if [[ -s "$FAILED" ]]; then
    echo "Some rows failed — retrying from $FAILED"
    dnsfcli networks create --retry-errors-csv "$FAILED" --yes
fi

echo "Done. New network IDs are in created-networks.csv; full outcomes in $REPORT."
