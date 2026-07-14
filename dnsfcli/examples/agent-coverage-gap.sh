#!/usr/bin/env bash
#
# agent-coverage-gap.sh
#
# USE CASE
#   Answer the real security question about roaming clients: not "are the
#   agents I know about healthy?" but "which machines have NO agent at
#   all?" Feed it a device inventory exported from AD / Intune / Jamf /
#   your MDM (one hostname per line, or a CSV whose first column is the
#   hostname) and it reports every device with no DNSFilter agent, plus
#   any agents not present in the inventory (retired machines to clean up).
#
# USAGE
#   ./agent-coverage-gap.sh devices.txt
#   ./agent-coverage-gap.sh devices.csv        # first column = hostname
#
# NOTES
#   Hostname matching is case-insensitive. Agents report the machine's
#   hostname in attributes.hostname.
#
set -euo pipefail

INVENTORY="${1:?usage: $0 DEVICE_INVENTORY_FILE}"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

# ── Inventory hostnames: first CSV column, skip a header line if present,
#    strip comments/blanks, lowercase for case-insensitive matching ──
awk -F, 'NR==1 && tolower($1) ~ /host|device|computer|name/ {next} {print $1}' "$INVENTORY" \
    | grep -v '^\s*#' | tr -d ' \t\r' | grep -v '^$' \
    | tr '[:upper:]' '[:lower:]' | sort -u > "$TMP/inventory.txt"

# ── Hostnames that actually have an agent installed ──
dnsfcli user-agents list --all \
    --pick attributes.hostname \
    | tr '[:upper:]' '[:lower:]' | sort -u > "$TMP/agents.txt"

# ── Diff both directions ──
comm -23 "$TMP/inventory.txt" "$TMP/agents.txt" > "$TMP/unprotected.txt"  # in MDM, no agent
comm -13 "$TMP/inventory.txt" "$TMP/agents.txt" > "$TMP/unknown.txt"      # agent, not in MDM

echo "Coverage report ($(date +%Y-%m-%d))"
echo "  devices in inventory : $(wc -l < "$TMP/inventory.txt" | tr -d ' ')"
echo "  devices with agent   : $(wc -l < "$TMP/agents.txt" | tr -d ' ')"
echo "  UNPROTECTED          : $(wc -l < "$TMP/unprotected.txt" | tr -d ' ')"
echo "  agent but not in MDM : $(wc -l < "$TMP/unknown.txt" | tr -d ' ')"
echo

if [[ -s "$TMP/unprotected.txt" ]]; then
    echo "Devices with NO DNSFilter agent (deploy targets):"
    sed 's/^/  ✗ /' "$TMP/unprotected.txt"
fi
if [[ -s "$TMP/unknown.txt" ]]; then
    echo
    echo "Agents with no matching inventory entry (retired machines? see"
    echo "cleanup-stale-agents.sh):"
    sed 's/^/  ? /' "$TMP/unknown.txt"
fi

# Exit non-zero when unprotected devices exist, so this can run in CI/cron.
[[ -s "$TMP/unprotected.txt" ]] && exit 1 || exit 0
