#!/usr/bin/env bash
#
# rotate-api-key.sh
#
# USE CASE
#   Scheduled credential hygiene: mint a replacement API key, prove it
#   works, then revoke the old one — so a key that leaked into shell
#   history, CI logs, or a laptop backup has a bounded lifetime. Run it
#   quarterly, or immediately after any suspected exposure.
#
# USAGE
#   ./rotate-api-key.sh OLD_KEY_ID
#
#   Find the ID of the key you're replacing with:  dnsfcli api-keys list
#
# NOTES
#   - The new key value is printed ONCE, to stderr (keeps stdout clean if
#     this script is piped). Store it in your secret manager immediately;
#     the API will not show it again.
#   - The old key is revoked only AFTER the new key passes verification,
#     so a failed rotation never locks you out.
#
set -euo pipefail

OLD_KEY_ID="${1:?usage: $0 OLD_KEY_ID   (see: dnsfcli api-keys list)}"

EXPIRY=$(date -v+1y +%Y-%m-%d 2>/dev/null || date -d "+1 year" +%Y-%m-%d)
NAME="rotated-$(date +%Y-%m-%d)"

echo "Creating replacement key \"$NAME\" (expires $EXPIRY)..."
NEW=$(dnsfcli api-keys create --name "$NAME" --expiry "$EXPIRY" --json)

NEW_ID=$(jq -r '.id // .data.id' <<<"$NEW")
NEW_TOKEN=$(jq -r '.attributes.token // .data.attributes.token' <<<"$NEW")
if [[ -z "$NEW_TOKEN" || "$NEW_TOKEN" == "null" ]]; then
    echo "Could not extract the new key token from the response — aborting" >&2
    echo "WITHOUT revoking the old key." >&2
    exit 1
fi

echo "Verifying the new key works before revoking anything..."
if ! DNSF_API_KEY="$NEW_TOKEN" dnsfcli auth verify; then
    echo "New key failed verification — old key left untouched." >&2
    echo "Investigate, then revoke the unused new key: dnsfcli api-keys revoke --id $NEW_ID" >&2
    exit 1
fi

echo "Revoking old key $OLD_KEY_ID..."
dnsfcli api-keys revoke --id "$OLD_KEY_ID" --yes

# stderr, once, on purpose — see NOTES.
{
    echo
    echo "════════════════════════════════════════════════════════"
    echo " NEW API KEY (id $NEW_ID) — store this NOW, it will not"
    echo " be shown again:"
    echo
    echo "   $NEW_TOKEN"
    echo "════════════════════════════════════════════════════════"
    echo
    echo "Update wherever the old key lived (CI secrets, .env files),"
    echo "then refresh the keychain:  dnsfcli auth setup"
} >&2
