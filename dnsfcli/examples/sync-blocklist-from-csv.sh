#!/usr/bin/env bash
#
# sync-blocklist-from-csv.sh
#
# USE CASE
#   Make a policy's block (or allow) list EXACTLY match a file — adding
#   what's missing and removing entries no longer in the file. The add-*
#   operations are append-only, so true synchronization needs this diff
#   step; use it when a feed or spreadsheet is the source of truth.
#
# USAGE
#   ./sync-blocklist-from-csv.sh POLICY_ID desired-domains.txt            # report only
#   ./sync-blocklist-from-csv.sh POLICY_ID desired-domains.txt --apply    # execute
#   ./sync-blocklist-from-csv.sh POLICY_ID desired-domains.txt --apply --allow
#
#   desired-domains.txt: one domain per line ('#' comments and blank
#   lines are ignored). Pass --allow to sync the allowlist instead of
#   the blocklist.
#
# PREREQUISITES
#   dnsfcli auth setup; jq installed (used to read the current list).
#
set -euo pipefail

POLICY_ID="${1:?usage: $0 POLICY_ID DESIRED_FILE [--apply] [--allow]}"
DESIRED_FILE="${2:?usage: $0 POLICY_ID DESIRED_FILE [--apply] [--allow]}"
APPLY=0
LIST="block"
for arg in "${@:3}"; do
    case "$arg" in
        --apply) APPLY=1 ;;
        --allow) LIST="allow" ;;
        *) echo "unknown option: $arg" >&2; exit 2 ;;
    esac
done

# Attribute and operation names differ between the two list types.
if [[ "$LIST" == "block" ]]; then
    ATTR="blacklist_domains";  ADD_OP="add-blacklist-domain";  REMOVE_OP="remove-blacklist-domain"
else
    ATTR="whitelist_domains";  ADD_OP="add-whitelist-domain";  REMOVE_OP="remove-whitelist-domain"
fi

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

# ── Current state: the list lives on the policy object ──
dnsfcli policies show --id "$POLICY_ID" --json \
    | jq -r ".attributes.${ATTR}[]?" | sort -u > "$TMP/current.txt"

# ── Desired state: normalise the input file ──
grep -v '^\s*#' "$DESIRED_FILE" | tr -d ' \t' | grep -v '^$' | sort -u > "$TMP/desired.txt"

# ── Diff ──
comm -13 "$TMP/current.txt" "$TMP/desired.txt" > "$TMP/to-add.txt"      # desired only
comm -23 "$TMP/current.txt" "$TMP/desired.txt" > "$TMP/to-remove.txt"   # current only

echo "Policy $POLICY_ID ${LIST}list sync plan:"
echo "  currently on list : $(wc -l < "$TMP/current.txt" | tr -d ' ')"
echo "  desired           : $(wc -l < "$TMP/desired.txt" | tr -d ' ')"
echo "  to ADD            : $(wc -l < "$TMP/to-add.txt" | tr -d ' ')"
echo "  to REMOVE         : $(wc -l < "$TMP/to-remove.txt" | tr -d ' ')"

if [[ "$APPLY" -ne 1 ]]; then
    echo
    [[ -s "$TMP/to-add.txt" ]]    && { echo "Would add:";    sed 's/^/  + /' "$TMP/to-add.txt"; }
    [[ -s "$TMP/to-remove.txt" ]] && { echo "Would remove:"; sed 's/^/  - /' "$TMP/to-remove.txt"; }
    echo "Report only — re-run with --apply to execute."
    exit 0
fi

# ── Apply: one call per domain via stdin CSV (header + rows) ──
if [[ -s "$TMP/to-add.txt" ]]; then
    { echo "domain"; cat "$TMP/to-add.txt"; } \
        | dnsfcli policies "$ADD_OP" --id "$POLICY_ID" --from-csv - \
              --on-error continue --yes
fi
if [[ -s "$TMP/to-remove.txt" ]]; then
    { echo "domain"; cat "$TMP/to-remove.txt"; } \
        | dnsfcli policies "$REMOVE_OP" --id "$POLICY_ID" --from-csv - \
              --on-error continue --yes
fi

echo "Sync complete."
