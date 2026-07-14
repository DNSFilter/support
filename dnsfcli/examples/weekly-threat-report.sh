#!/usr/bin/env bash
#
# weekly-threat-report.sh
#
# USE CASE
#   Scheduled reporting without dashboard logins: pull last week's traffic
#   and threat numbers and produce a Markdown report you can drop into
#   Slack, email, or a ticket. Designed to run from cron, e.g.:
#
#       0 7 * * MON  /path/to/weekly-threat-report.sh
#
# HOW IT WORKS
#   traffic-reports endpoints return per-day buckets under data.values;
#   --jq extracts that list and --sum adds up the per-bucket totals.
#
# PREREQUISITES
#   dnsfcli auth setup (a default org ID makes the calls org-scoped).
#
set -euo pipefail

# BSD (macOS) and GNU date both handled.
FROM=$(date -v-7d +%Y-%m-%d 2>/dev/null || date -d "7 days ago" +%Y-%m-%d)
TO=$(date +%Y-%m-%d)
REPORT="threat-report-$TO.md"

# Sum the per-day buckets into a single number.
total_requests=$(dnsfcli traffic-reports total-requests \
    --start-date "$FROM" --end-date "$TO" \
    --jq data.values --sum total --quiet | awk '{print $1}')

total_threats=$(dnsfcli traffic-reports total-threats \
    --start-date "$FROM" --end-date "$TO" \
    --jq data.values --sum total --quiet | awk '{print $1}')

{
    echo "# DNSFilter Weekly Report — $FROM to $TO"
    echo
    echo "- Total DNS requests: **$total_requests**"
    echo "- Threats blocked: **$total_threats**"
    echo
    echo "## Top requested domains"
} > "$REPORT"

# Top domains, one per line, numbered.
dnsfcli traffic-reports top-domains \
    --start-date "$FROM" --end-date "$TO" \
    --limit 15 \
    --jq data.values --pick domain | nl -w2 -s'. ' >> "$REPORT"

echo "Report written to $REPORT"
