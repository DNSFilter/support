#!/usr/bin/env bash
#
# cleanup-stale-agents.sh
#
# USE CASE
#   Roaming-client hygiene: machines get reimaged or retired and their
#   agents linger forever, cluttering reports and inflating seat counts.
#   This first REPORTS agents that look stale, then (with --apply) creates
#   a server-side cleanup job for agents inactive for N days.
#
# USAGE
#   ./cleanup-stale-agents.sh ORG_ID            # report only
#   ./cleanup-stale-agents.sh ORG_ID --apply    # actually schedule cleanup
#
set -euo pipefail

ORG_ID="${1:?usage: $0 ORG_ID [--apply] [INACTIVE_DAYS]}"
MODE="${2:-report}"
DAYS="${3:-30}"

echo "Agents not currently protected (candidates for cleanup):"
dnsfcli user-agents list \
    --organization-ids "[\"$ORG_ID\"]" --all \
    --flatten \
    --filter "attributes.agent_state!=protected" \
    --columns id,attributes.hostname,attributes.agent_state,attributes.agent_version

if [[ "$MODE" != "--apply" ]]; then
    echo
    echo "Report only. Re-run with --apply to create a cleanup job for agents"
    echo "inactive for $DAYS+ days."
    exit 0
fi

# Preview the exact request first, then create the cleanup job.
dnsfcli user-agent-cleanups create \
    --organization-ids "[\"$ORG_ID\"]" \
    --inactive-for "$DAYS" \
    --dry-run

dnsfcli user-agent-cleanups create \
    --organization-ids "[\"$ORG_ID\"]" \
    --inactive-for "$DAYS"

echo "Cleanup job created. Track it with: dnsfcli user-agent-cleanups list"
