#!/usr/bin/env bash
#
# ci-config-guardrails.sh
#
# USE CASE
#   Run in a CI pipeline (or nightly cron) to assert that your DNSFilter
#   configuration still matches policy. Each check exits non-zero on
#   violation, so the pipeline fails loudly instead of config drift going
#   unnoticed. Failure messages go to stderr; stdout stays clean.
#
# PREREQUISITES
#   Set DNSF_API_KEY (and DNSF_ORG_ID) as CI secrets — no keychain needed.
#
set -euo pipefail

FAILED=0

echo "Check 1: no policy may allow uncategorised domains"
dnsfcli policies list --all --quiet \
    --fail-on-pattern "attributes.allow_unknown_domains=true" || FAILED=1

echo "Check 2: no network may still use the legacy VPN"
dnsfcli networks list --all --quiet \
    --fail-on-pattern "attributes.is_legacy_vpn_active=true" || FAILED=1

echo "Check 3: at least one block page must exist"
dnsfcli block-pages list --quiet --fail-on-empty >/dev/null || FAILED=1

echo "Check 4: no API keys expiring in the next 30 days"
SOON=$(date -v+30d +%Y-%m-%d 2>/dev/null || date -d "+30 days" +%Y-%m-%d)
dnsfcli api-keys list --quiet --flatten \
    --fail-on-pattern "attributes.expiry<$SOON" || FAILED=1

if [[ "$FAILED" -ne 0 ]]; then
    echo "One or more guardrail checks failed — see above." >&2
    exit 1
fi
echo "All guardrail checks passed."
