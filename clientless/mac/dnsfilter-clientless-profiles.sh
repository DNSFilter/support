#!/bin/zsh
# ------------------------------------------------------------------------------------------------
# DNSFilter Clientless - configuration profiles for your Macs
#
# QUICK START
#   1. Make a CSV file with one Mac per line. The first line names the columns:
#        name
#        Reception-MacBook
#        Design-iMac-02
#      "name" is what the Mac is called in your DNSFilter dashboard. Use the name your MDM shows for
#      the device, so you can match each profile to its Mac.
#   2. Run:  ./dnsfilter-clientless-profiles.sh devices.csv
#      The script asks for your DNSFilter API key and Site ID, or reads them from DNSFILTER_API_KEY and
#      DNSFILTER_SITE_ID.
#   3. Upload each .mobileconfig file in the output folder to your MDM, and assign it to that one Mac only.
#
# For each Mac in the CSV the script:
#   1. Finds its Clientless deployment on the Site, or creates one. The name identifies the deployment,
#      so running the script again never creates a duplicate.
#   2. Applies any per-Mac policy, schedule or block page from the CSV (Advanced, optional).
#   3. Downloads the Mac's signed configuration profile from DNSFilter and checks it. The profile sends
#      the Mac's DNS to DNSFilter over encrypted DNS (DNS over HTTPS), trusts the DNSFilter block page,
#      and keeps the Site's local domains on your local DNS servers.
# Nothing is installed on this computer, and nothing is sent to your Macs. Your MDM does that.
#
# Each profile belongs to exactly one Mac. A profile carries that Mac's unique ID, so if you assign one
# profile to several Macs they all report as the same deployment.
# Running the script again downloads the same profiles (same identifiers), so re-uploading one replaces
# the earlier copy on the Mac instead of adding a second.
#
# Optional CSV columns (Advanced): policy_id, scheduled_policy_id, block_page_id. Leave them out to use
# the Site's settings. Use either policy_id or scheduled_policy_id on a row, not both. Example:
#   name,policy_id,block_page_id
#   Reception-MacBook,7890,1201
#
# Requirements
#   - macOS 12 or later, on the computer that runs this script (the Macs themselves need an MDM)
#   - A DNSFilter API key (Account Settings > Security > API Keys) from an admin account
#   - The Site ID: Deployments > Sites, edit the Site; it is the number at the end of the page address
#
# Output (default folder ./dnsfilter-profiles, or the second argument):
#   <name>.mobileconfig   one per Mac
#   summary.csv           name, deployment ID, encrypted DNS address, profile file, result
#
# Exit codes: 0 every Mac done; 1 one or more Macs failed (see summary.csv); 2 nothing was done.
# ------------------------------------------------------------------------------------------------
emulate -L zsh
setopt no_unset pipe_fail

API_URL='https://api.dnsfilter.com'

SELF=${0:A}
usage() { sed -n '2,46p' "$SELF" | sed 's/^# \{0,1\}//'; }
die() { print -u2 "ERROR: $1"; exit 2; }

[[ ${1:-} == (-h|--help) ]] && { usage; exit 0; }
CSV=${1:-}; OUT=${2:-./dnsfilter-profiles}
[[ -n $CSV ]] || { usage; exit 2; }
[[ -r $CSV ]] || die "Can't read the CSV file '$CSV'."

API_KEY=${DNSFILTER_API_KEY:-}
SITE_ID=${DNSFILTER_SITE_ID:-}
if [[ -z $API_KEY ]]; then
    [[ -t 0 ]] || die 'No API key. Set DNSFILTER_API_KEY.'
    read -rs 'API_KEY?DNSFilter API key: '; print
fi
if [[ -z $SITE_ID ]]; then
    [[ -t 0 ]] || die 'No Site ID. Set DNSFILTER_SITE_ID.'
    read -r 'SITE_ID?Site ID: '
fi
SITE_ID=${SITE_ID//[[:space:]]/}
# The value itself is never printed: an API key pasted into the Site ID must not reach the terminal or a log.
[[ $SITE_ID == <-> ]] || die 'The Site ID must be a number. See QUICK START for where to find it.'
[[ -n $API_KEY ]] || die 'No API key.'

TMP=$(mktemp -d) || die 'Could not create a temporary folder.'
trap 'rm -rf "$TMP"' EXIT
# The key goes to curl from a private file, so it never appears in the process list.
( umask 077; print -r -- "Authorization: Bearer $API_KEY" > "$TMP/auth" )
mkdir -p "$OUT" || die "Could not create the output folder '$OUT'."

# ------------------------------------------------------------------------------------------------
# JSON and CSV helpers (built-in JavaScript for Automation, so nothing needs installing)
# ------------------------------------------------------------------------------------------------
cat > "$TMP/helper.js" <<'EOF'
ObjC.import('Foundation')
function read(p) { return $.NSString.stringWithContentsOfFileEncodingError(p, $.NSUTF8StringEncoding, null).js }
function csv(text) {
  const rows = []; let row = [], f = '', q = false
  for (let i = 0; i < text.length; i++) {
    const c = text[i]
    if (q) { if (c === '"' && text[i + 1] === '"') { f += '"'; i++ } else if (c === '"') q = false; else f += c }
    else if (c === '"') q = true
    else if (c === ',') { row.push(f); f = '' }
    else if (c === '\n' || c === '\r') { if (c === '\r' && text[i + 1] === '\n') i++; row.push(f); rows.push(row); row = []; f = '' }
    else f += c
  }
  if (f !== '' || row.length) { row.push(f); rows.push(row) }
  return rows.map(r => r.map(x => x.trim())).filter(r => r.some(x => x !== ''))
}
function run(argv) {
  const op = argv[0]
  if (op === 'enc') return encodeURIComponent(argv[1])
  if (op === 'profile') {
    // The decoded profile plist: the DNS server address and how many block page certificates it carries.
    const d = $.NSDictionary.dictionaryWithContentsOfFile(argv[1])
    if (d.isNil()) return ''
    const p = ObjC.unwrap(d.objectForKey('PayloadContent')) || []
    let url = '', certs = 0
    for (const x of p) {
      const type = ObjC.unwrap(x.objectForKey('PayloadType'))
      if (type === 'com.apple.dnsSettings.managed') url = ObjC.unwrap(x.objectForKey('DNSSettings').objectForKey('ServerURL'))
      if (type === 'com.apple.security.root') certs++
    }
    return url + '\t' + certs
  }
  if (op === 'rows') {
    // One line per Mac: name<TAB>policy_id<TAB>scheduled_policy_id<TAB>block_page_id, or ERROR<TAB>message.
    const rows = csv(read(argv[1]).replace(/^﻿/, ''))
    if (!rows.length) return 'ERROR\tThe CSV file is empty.'
    const head = rows[0].map(h => h.toLowerCase()), cols = ['name', 'policy_id', 'scheduled_policy_id', 'block_page_id']
    if (head.indexOf('name') < 0) return 'ERROR\tThe first line of the CSV must name the columns, including "name".'
    const unknown = head.filter(h => cols.indexOf(h) < 0)
    if (unknown.length) return 'ERROR\tUnknown CSV column(s): ' + unknown.join(', ') + '. Allowed: ' + cols.join(', ') + '.'
    return rows.slice(1).map(r => cols.map(c => { const i = head.indexOf(c); return i < 0 ? '' : (r[i] || '').replace(/\t/g, ' ') }).join('\t')).join('\n')
  }
  const j = JSON.parse(read(argv[1]))
  if (op === 'get') { let v = j; for (const k of argv[2].split('.')) v = v == null ? null : v[k]; return v == null ? '' : String(v) }
  if (op === 'find') return j.data.filter(d => d.name === argv[2] && String(d.network_id) === argv[3] && !d.deleted_at).map(d => d.id).join('\n')
  if (op === 'field') { const d = j.data.find(x => x.id === argv[2]) || {}; return d[argv[3]] == null ? '' : String(d[argv[3]]) }
  if (op === 'error') {
    const text = x => x == null ? '' : typeof x === 'string' ? x : x.detail || x.title || x.message || JSON.stringify(x)
    return [].concat(j.errors || [], j.error ? [j.error] : []).map(text).filter(Boolean).join('; ') || JSON.stringify(j).slice(0, 300)
  }
}
EOF
js() { osascript -l JavaScript "$TMP/helper.js" "$@"; }
json() { # json <key=value>...  ->  a JSON object; numbers stay numbers, "null" is null
    local -a pairs=("$@")
    osascript -l JavaScript -e 'function run(a){const o={};for(const p of a){const i=p.indexOf("=");const k=p.slice(0,i),v=p.slice(i+1);o[k]=v==="null"?null:(/^\d+$/.test(v)&&k!=="name"?Number(v):v)}return JSON.stringify(o)}' "${pairs[@]}"
}

# api METHOD PATH [JSON]  ->  prints the HTTP status; the body is in $TMP/resp
api() {
    # --globoff: the API's page[size] would otherwise be read as a curl URL range.
    local -a args=(-sS --globoff --max-time 60 -o "$TMP/resp" -w '%{http_code}' -X "$1" -H "@$TMP/auth" -H 'Accept: application/json')
    [[ -n ${3:-} ]] && args+=(-H 'Content-Type: application/json' --data-binary "$3")
    curl "${args[@]}" "$API_URL$2" 2>"$TMP/curl.err" || { print 000; return 0 }
}
api_error() { # a readable reason for the last failed call
    local code=$1 detail=''
    [[ -s $TMP/resp ]] && detail=$(js error "$TMP/resp" 2>/dev/null || true)
    case $code in
        000) print "Could not reach $API_URL. Check this computer's internet access. (${$(<$TMP/curl.err)//$'\n'/ })" ;;
        401) print 'The API key was rejected.' ;;
        403) print "Not allowed (HTTP 403). ${detail:-Check that the account's plan includes Clientless.}" ;;
        404) print "Not found (HTTP 404). ${detail:-Check the Site ID, and that Clientless is enabled for your account.}" ;;
        503) print "DNSFilter could not sign the profile right now (HTTP 503). Try again later." ;;
        *)   print "HTTP $code. $detail" ;;
    esac
}

# ------------------------------------------------------------------------------------------------
# Read the CSV and the Site
# ------------------------------------------------------------------------------------------------
ROWS=$(js rows "$CSV") || die 'Could not read the CSV file.'
[[ $ROWS == ERROR$'\t'* ]] && die "${ROWS#ERROR$'\t'}"
[[ -n $ROWS ]] || die 'The CSV file lists no Macs.'

code=$(api GET "/v1/networks/$SITE_ID")
[[ $code == 200 ]] || die "Could not read Site $SITE_ID. $(api_error $code)"
SITE_NAME=$(js get "$TMP/resp" data.attributes.name)
ORG_ID=$(js get "$TMP/resp" data.relationships.organization.data.id)
print "Site $SITE_ID ($SITE_NAME). Writing profiles to $OUT"

SUMMARY="$OUT/summary.csv"
print 'name,deployment_id,doh_address,profile,result' > "$SUMMARY"
csvq() { print -rn -- "\"${1//\"/\"\"}\""; }
record() { # name id doh file result
    print -r -- "$(csvq "$1"),$(csvq "$2"),$(csvq "$3"),$(csvq "$4"),$(csvq "$5")" >> "$SUMMARY"
}

typeset -A seen seenfile
ok=0 failed=0
for line in "${(@f)ROWS}"; do
    # Split on every tab, keeping empty fields: read with IFS=tab would merge them and shift the columns.
    fields=("${(@ps:\t:)line}")
    name=${fields[1]:-} policy=${fields[2]:-} sched=${fields[3]:-} block=${fields[4]:-}
    fail() { print "  FAILED: $1"; record "$name" "${id:-}" "${doh:-}" '' "FAILED: $1"; (( failed++ )); }
    id='' doh=''
    print "$name"
    if [[ -z $name ]]; then fail 'This CSV row has no name.'; continue; fi
    if [[ -n ${seen[$name]:-} ]]; then fail 'This name is in the CSV more than once. Each Mac needs its own name.'; continue; fi
    seen[$name]=1
    bad=''
    for v in $policy $sched $block; do [[ $v == <-> ]] || bad=1; done
    if [[ -n $bad ]]; then fail 'policy_id, scheduled_policy_id and block_page_id must be numbers.'; continue; fi
    if [[ -n $policy && -n $sched ]]; then fail 'Use either policy_id or scheduled_policy_id, not both.'; continue; fi

    # 1. Find or create the deployment. The name search also matches partial names, so keep exact matches only.
    query="/v2/clientless?network_id=$SITE_ID&name=$(js enc "$name")&page[size]=100"
    [[ -n $ORG_ID ]] && query+="&organization_id=$ORG_ID"
    code=$(api GET "$query")
    if [[ $code != 200 ]]; then fail "$(api_error $code)"; continue; fi
    matches=("${(@f)$(js find "$TMP/resp" "$name" "$SITE_ID")}")
    matches=(${matches:#})
    if (( ${#matches} > 1 )); then fail "${#matches} deployments are named '$name' on this Site. Archive the extra ones in the dashboard."; continue; fi

    overrides=()
    [[ -n $policy ]] && overrides+=("policy_id=$policy")
    [[ -n $sched ]] && overrides+=("scheduled_policy_id=$sched")
    [[ -n $block ]] && overrides+=("block_page_id=$block")

    if (( ${#matches} == 0 )); then
        code=$(api POST /v2/clientless "$(json network_id=$SITE_ID name="$name" $overrides)")
        if [[ $code != 2?? ]]; then fail "Could not create the deployment. $(api_error $code)"; continue; fi
        id=$(js get "$TMP/resp" data.id)
        if [[ -z $id ]]; then fail 'DNSFilter did not return a deployment ID.'; continue; fi
        print "  Created deployment $id"
    else
        id=${matches[1]}
        # Only change the settings the CSV names and that differ from the deployment.
        changes=()
        for kv in $overrides; do
            [[ $(js field "$TMP/resp" "$id" "${kv%%=*}") != ${kv#*=} ]] && changes+=("$kv")
        done
        if (( ${#changes} )); then
            [[ -n $policy ]] && changes+=('scheduled_policy_id=null')
            [[ -n $sched ]] && changes+=('policy_id=null')
            code=$(api PATCH "/v2/clientless/$id" "$(json $changes)")
            if [[ $code != 2?? ]]; then fail "Could not update the deployment. $(api_error $code)"; continue; fi
            print "  Updated deployment $id: ${(j:, :)changes}"
        else
            print "  Using existing deployment $id"
        fi
    fi

    # 2. Download the signed profile and check it before handing it to the MDM.
    file=${name//[^A-Za-z0-9._-]/-}.mobileconfig
    [[ -n ${seenfile[$file]:-} ]] && file=${file%.mobileconfig}-${id[1,8]}.mobileconfig
    seenfile[$file]=1
    code=$(curl -sS --globoff --max-time 60 -o "$TMP/profile" -w '%{http_code}' -H "@$TMP/auth" "$API_URL/v2/clientless/$id/mobileconfig" 2>"$TMP/curl.err" || print 000)
    if [[ $code != 200 ]]; then cp "$TMP/profile" "$TMP/resp" 2>/dev/null || :; fail "Could not download the profile. $(api_error $code)"; continue; fi
    if ! security cms -D -i "$TMP/profile" -o "$TMP/profile.plist" 2>/dev/null; then fail 'The downloaded profile is not a signed configuration profile.'; continue; fi
    IFS=$'\t' read -r doh certs <<< "$(js profile "$TMP/profile.plist")"
    if [[ -z $doh ]]; then fail 'The downloaded profile could not be read.'; continue; fi
    if [[ $doh != */$id ]]; then fail "The profile's DNS address ($doh) is not this deployment's."; continue; fi
    if (( certs < 1 )); then fail 'The profile has no block page certificate.'; continue; fi
    cp "$TMP/profile" "$OUT/$file"
    print "  Profile: $OUT/$file"
    record "$name" "$id" "$doh" "$file" 'OK'
    (( ok++ ))
done

print
print "Done: $ok Mac(s) ready, $failed failed. Details: $SUMMARY"
(( failed )) && exit 1
exit 0
