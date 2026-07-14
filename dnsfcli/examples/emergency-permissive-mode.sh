#!/usr/bin/env bash
#
# emergency-permissive-mode.sh
#
# USE CASE
#   Break-glass troubleshooting: an app is failing and you need to know in
#   the next five minutes whether DNS filtering is the cause. This flips a
#   policy into permissive mode (log but don't block), waits, and — the
#   important part — AUTOMATICALLY REVERTS, so a debugging session can't
#   accidentally leave a client unfiltered over the weekend. Ctrl-C also
#   reverts before exiting.
#
# USAGE
#   ./emergency-permissive-mode.sh POLICY_ID            # 10-minute window
#   ./emergency-permissive-mode.sh POLICY_ID 30         # custom minutes
#
set -euo pipefail

POLICY_ID="${1:?usage: $0 POLICY_ID [MINUTES]}"
MINUTES="${2:-10}"

# Current state first — don't "revert" a policy that was already permissive.
echo "Current permissive-mode state for policy $POLICY_ID:"
dnsfcli policies permissive-mode --id "$POLICY_ID" --raw

revert() {
    echo
    echo "Reverting policy $POLICY_ID to enforcing mode..."
    dnsfcli policies set-permissive-mode --id "$POLICY_ID" --permissive-mode false --quiet
    echo "Filtering re-enabled. Verify:"
    dnsfcli policies permissive-mode --id "$POLICY_ID" --raw
}
# Revert on ANY exit: timer expiry, Ctrl-C, or an error mid-script.
trap revert EXIT

echo
echo "╔════════════════════════════════════════════════════════════╗"
echo "║  ENABLING PERMISSIVE MODE — policy $POLICY_ID"
echo "║  Blocking is OFF for the next $MINUTES minute(s)."
echo "║  Auto-revert on timer expiry or Ctrl-C.                     ║"
echo "╚════════════════════════════════════════════════════════════╝"
dnsfcli policies set-permissive-mode --id "$POLICY_ID" --permissive-mode true

# Countdown so the terminal shows this is a live, temporary state.
for ((remaining=MINUTES; remaining>0; remaining--)); do
    printf '\r  permissive mode active — %2d minute(s) remaining (Ctrl-C to revert now) ' "$remaining"
    sleep 60
done
printf '\n  time window elapsed.\n'
# trap fires on exit and reverts.
