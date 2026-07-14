#!/usr/bin/env bash
#
# incident-domain-triage.sh
#
# USE CASE
#   During an incident: given a suspicious domain, find out (1) how
#   DNSFilter classifies it and (2) which of your networks/devices have
#   been resolving it recently. First response before deciding to block.
#
# USAGE
#   ./incident-domain-triage.sh suspicious-domain.com [DAYS_BACK]
#
set -euo pipefail

DOMAIN="${1:?usage: $0 DOMAIN [DAYS_BACK]}"
DAYS="${2:-7}"

FROM=$(date -v-"$DAYS"d +%Y-%m-%d 2>/dev/null || date -d "$DAYS days ago" +%Y-%m-%d)
TO=$(date +%Y-%m-%d)

echo "══ Classification ═════════════════════════════════════"
# lookupdomain resolves the domain's content categories and any
# application associations in one human-readable panel.
dnsfcli lookupdomain "$DOMAIN"

echo
echo "══ Recent query activity ($FROM → $TO) ════════════════"
# --grep filters rows where any field matches the pattern, so hits on the
# domain (or its subdomains) surface regardless of which column they're in.
dnsfcli traffic-reports query-logs \
    --start-date "$FROM" --end-date "$TO" \
    --all --max-pages 10 \
    --grep "$DOMAIN"

echo
echo "Next steps if malicious:"
echo "  dnsfcli policies add-blacklist-domain --id POLICY_ID --domain \"$DOMAIN\" --note \"IR $(date +%Y-%m-%d)\""
echo "  dnsfcli domains suggest-threat --fqdn \"$DOMAIN\" --notes \"Observed in incident\""
