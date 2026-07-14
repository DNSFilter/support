#!/usr/bin/env bash
#
# fleet-safesearch-audit.sh
#
# USE CASE
#   MSP compliance sweep: check every organization on the account and list
#   the policies that do NOT have Google SafeSearch enforced. Useful for
#   K-12 / CIPA-style requirements where SafeSearch must be on everywhere,
#   or any "which clients drifted from the baseline?" question.
#
# HOW IT WORKS
#   --each-org runs the same command once per organization. Policy fields
#   live under the JSON:API "attributes" envelope, so filters and columns
#   use dotted paths (--flatten makes the nested fields addressable as
#   columns).
#
# PREREQUISITES
#   dnsfcli auth setup with an account that can see all client orgs.
#
set -euo pipefail

OUT="safesearch-audit-$(date +%Y-%m-%d).csv"

rm -f "$OUT"
dnsfcli policies list \
    --each-org \
    --filter "attributes.google_safesearch=false" \
    --flatten \
    --columns id,attributes.name,attributes.google_safesearch \
    --to-csv "$OUT" \
    --append

echo "Non-compliant policies written to $OUT"
