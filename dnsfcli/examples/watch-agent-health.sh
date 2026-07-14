#!/usr/bin/env bash
#
# watch-agent-health.sh
#
# USE CASE
#   Live monitoring during a rollout or incident: poll the roaming-client
#   fleet and get an audible alert the moment any agent is no longer in
#   the "protected" state (uninstalled, disabled, unprotected, ...).
#   Leave it running in a terminal during maintenance windows.
#
# HOW IT WORKS
#   --watch re-runs the command on an interval; --alert rings the terminal
#   bell and prints a banner whenever the filter matches a result row.
#   Agent fields are nested under "attributes", so the filter uses a
#   dotted path.
#
# PREREQUISITES
#   dnsfcli auth setup
#
set -euo pipefail

INTERVAL="${1:-60}"   # seconds between polls; pass a number to override

dnsfcli user-agents list \
    --all \
    --flatten \
    --columns id,attributes.hostname,attributes.agent_state,attributes.agent_version \
    --watch "$INTERVAL" \
    --alert "attributes.agent_state!=protected"
