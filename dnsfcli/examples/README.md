# dnsfcli example scripts

Ready-to-adapt shell scripts for common dnsfcli workflows. Each script has a
header comment explaining the use case, prerequisites, and how it works.

All scripts assume credentials are configured (`dnsfcli auth setup`, or
`DNSF_API_KEY`/`DNSF_ORG_ID` environment variables for CI).

| Script | Use case |
|---|---|
| [`bulk-onboard-networks.sh`](bulk-onboard-networks.sh) | Create many networks from a CSV with validation, error collection, and retry — the client-onboarding workflow. |
| [`fleet-safesearch-audit.sh`](fleet-safesearch-audit.sh) | Sweep every organization for policies with SafeSearch disabled; one combined compliance CSV. |
| [`export-org-inventories.sh`](export-org-inventories.sh) | Per-client network and roaming-agent inventory CSVs via `--each-org` path templating. |
| [`weekly-threat-report.sh`](weekly-threat-report.sh) | Cron-able Markdown report: request/threat totals and top domains for the past week. |
| [`watch-agent-health.sh`](watch-agent-health.sh) | Live-poll the agent fleet and ring the terminal bell when any agent leaves the protected state. |
| [`ci-config-guardrails.sh`](ci-config-guardrails.sh) | Pipeline checks that fail the build on config drift (permissive policies, legacy VPN, expiring API keys). |
| [`block-domains-from-feed.sh`](block-domains-from-feed.sh) | Pipe a threat-intel feed (one domain per line) into a policy blocklist, cron-safe. |
| [`sync-blocklist-from-csv.sh`](sync-blocklist-from-csv.sh) | True synchronization: diff a policy's block/allow list against a file, then add AND remove to match exactly. |
| [`cleanup-stale-agents.sh`](cleanup-stale-agents.sh) | Report unprotected agents, then optionally schedule server-side cleanup of long-inactive ones. |
| [`incident-domain-triage.sh`](incident-domain-triage.sh) | IR first response: classify a suspicious domain and find who has been resolving it. |
| [`agent-coverage-gap.sh`](agent-coverage-gap.sh) | Diff an AD/MDM device export against installed agents to find machines with NO DNSFilter protection. |
| [`clone-policy.sh`](clone-policy.sh) | Replicate a gold-standard policy — settings plus allow/block lists — into another org in one call. |
| [`emergency-permissive-mode.sh`](emergency-permissive-mode.sh) | Break-glass: temporarily disable blocking on a policy with a countdown and guaranteed auto-revert. |
| [`rotate-api-key.sh`](rotate-api-key.sh) | Credential hygiene: mint a replacement API key, verify it works, then revoke the old one. |

## Conventions used

- **Dotted field paths** — list responses use the JSON:API envelope, so
  nested fields are addressed as `attributes.name` in `--filter`; add
  `--flatten` when you also want them as `--columns`.
- **Exit codes** — scripts intended for CI/cron use `--fail-on-empty` /
  `--fail-on-pattern`, which exit 1 and print the reason to stderr.
- **Batch safety** — write operations prefer `--validate-only` or
  `--dry-run` first, and `--errors-to-csv` + `--retry-errors-csv` for
  resumable error handling.
