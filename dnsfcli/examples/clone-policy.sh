#!/usr/bin/env bash
#
# clone-policy.sh
#
# USE CASE
#   Replicate a "gold standard" policy — all filtering settings plus the
#   allow/block domain lists and blocked categories — as a new policy,
#   typically into a freshly onboarded client org. The dashboard has no
#   clone button; this is the scripted equivalent.
#
# USAGE
#   ./clone-policy.sh SOURCE_POLICY_ID DEST_ORG_ID "New Policy Name"
#
# HOW IT WORKS
#   Reads the source policy once, then passes its settings to
#   `policies create`. The create operation accepts whitelist_domains /
#   blacklist_domains / blacklist_categories as arrays, so the lists are
#   copied in the same call — no per-domain loop needed.
#
# PREREQUISITES
#   dnsfcli auth setup; jq installed.
#
set -euo pipefail

SRC_ID="${1:?usage: $0 SOURCE_POLICY_ID DEST_ORG_ID NEW_NAME}"
DEST_ORG="${2:?usage: $0 SOURCE_POLICY_ID DEST_ORG_ID NEW_NAME}"
NEW_NAME="${3:?usage: $0 SOURCE_POLICY_ID DEST_ORG_ID NEW_NAME}"

SRC=$(dnsfcli policies show --id "$SRC_ID" --json)

echo "Cloning policy $SRC_ID ($(jq -r '.attributes.name' <<<"$SRC"))"
echo "  → org $DEST_ORG as \"$NEW_NAME\""

# Build the create arguments from the source attributes. Boolean settings
# are copied only when present (jq emits true/false; null flags are skipped
# so the API's defaults apply).
args=(--name "$NEW_NAME" --organization-id "$DEST_ORG")

for flag_attr in \
    allow-unknown-domains:allow_unknown_domains \
    google-safesearch:google_safesearch \
    bing-safe-search:bing_safe_search \
    duck-duck-go-safe-search:duck_duck_go_safe_search \
    ecosia-safesearch:ecosia_safesearch \
    yandex-safe-search:yandex_safe_search \
    youtube-restricted:youtube_restricted \
    interstitial:interstitial \
    allow-list-only:allow_list_only
do
    flag="${flag_attr%%:*}"; attr="${flag_attr##*:}"
    # NOTE: jq's '// empty' would treat false like null and drop disabled
    # settings — test for null explicitly so false is copied faithfully.
    val=$(jq -r "if .attributes.${attr} == null then empty else .attributes.${attr} end" <<<"$SRC")
    [[ -n "$val" ]] && args+=("--$flag" "$val")
done

# youtube_restricted_level is a string enum, only meaningful when set.
yt_level=$(jq -r '.attributes.youtube_restricted_level // empty' <<<"$SRC")
[[ -n "$yt_level" ]] && args+=(--youtube-restricted-level "$yt_level")

# The allow/block lists travel as compact JSON arrays.
for list_attr in whitelist-domains:whitelist_domains \
                 blacklist-domains:blacklist_domains \
                 blacklist-categories:blacklist_categories
do
    flag="${list_attr%%:*}"; attr="${list_attr##*:}"
    val=$(jq -c ".attributes.${attr} // []" <<<"$SRC")
    [[ "$val" != "[]" ]] && args+=("--$flag" "$val")
done

# Preview the exact request, then create for real.
dnsfcli policies create "${args[@]}" --dry-run
read -r -p "Create this policy? [y/N] " answer
[[ "$answer" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 1; }

dnsfcli policies create "${args[@]}"
echo "Done. Note: application allow/block rules are managed per-application"
echo "(policies add-allowed-application / add-blocked-application) and are"
echo "not copied by this script."
