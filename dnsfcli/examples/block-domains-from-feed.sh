#!/usr/bin/env bash
#
# block-domains-from-feed.sh
#
# USE CASE
#   Push a threat-intel feed (one domain per line) into a policy's
#   blocklist — e.g. an abuse.ch export, an internal SOC list, or the
#   output of another tool. Run daily from cron to keep a policy in sync
#   with a feed.
#
# USAGE
#   ./block-domains-from-feed.sh POLICY_ID feed.txt
#   cat feed.txt | ./block-domains-from-feed.sh POLICY_ID -
#
# HOW IT WORKS
#   The feed is converted to a one-column CSV (header "domain") and piped
#   to --from-csv, which makes one add-blacklist-domain call per row.
#   The policy ID is supplied once on the command line and reused for
#   every row. --yes skips the interactive batch confirmation (cron-safe).
#
set -euo pipefail

POLICY_ID="${1:?usage: $0 POLICY_ID feed.txt|-}"
FEED="${2:?usage: $0 POLICY_ID feed.txt|-}"

# Normalise the feed: strip comments/blank lines, prepend the CSV header.
# --from-csv - reads the CSV from stdin.
{
    echo "domain"
    grep -v '^\s*#' "$([ "$FEED" = "-" ] && echo /dev/stdin || echo "$FEED")" \
        | tr -d ' \t' | grep -v '^$'
} | dnsfcli policies add-blacklist-domain \
        --id "$POLICY_ID" \
        --from-csv - \
        --on-error continue \
        --errors-to-csv blocked-feed-failures.csv \
        --yes

echo "Feed applied to policy $POLICY_ID."
[[ -s blocked-feed-failures.csv ]] && echo "Some rows failed — see blocked-feed-failures.csv"
exit 0
