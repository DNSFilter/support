# Changelog

All notable changes to dnsfcli are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project adheres to [Semantic Versioning](https://semver.org/).

## [0.2.0] — 2026-07-23

Internal refactor, security hardening, and test-suite overhaul. No changes to
the set of supported endpoints/operations.

### Security

- `--exec`: closed a command-injection path where attacker-controlled API data
  (e.g. an MSP tenant's org name / device label) could execute a shell command
  on the operator's machine. Substituted values are shell-quoted and any value
  containing shell metacharacters or a leading `-` is refused rather than run.
- `--cache-ttl`: the response cache key is now scoped to the resolved API key
  and base URL. Previously a cached GET could be served across different
  credentials/accounts on the same path.
- Secret redaction is now applied consistently: `--save-as` aliases,
  `--verbose`/`--dry-run` output, `--batch-report`, and the audit history all
  drop or mask secret-bearing flags and secret-named fields (including values
  nested in lists). Responses from `api-keys` are never written to the on-disk
  cache. `--errors-to-csv`, `--batch-report`, and config files are written
  owner-only (0600).

### Changed

- Batch `--retry` only retries idempotent methods (GET/PUT/DELETE) on 5xx;
  POST/PATCH rows are no longer retried, avoiding silent duplicate writes.
- `--wait` now exits non-zero when the polled job fails, times out, or its
  status can't be determined (previously always exited 0).
- `--confirm-each` now forces sequential execution instead of being silently
  ignored under `--concurrency > 1`.
- `--concurrency` and `--org-concurrency` are bounded (max 64 / 32).

### Fixed

- `--all --limit N` now returns exactly N items (previously overshot by up to
  one page).
- `--sort` no longer crashes on a field whose values mix types (e.g. numbers
  and strings across rows).
- `--transform` rejects sequence-repetition expressions (`"x"*10**9`) that could
  exhaust memory.

### Internal

- The monolithic `cli.py` was split into focused modules (`cliopts`,
  `cliparams`, `runopts`, `pagination`, `jobs`, `preview`, `batch`,
  `postprocess`, `apps`, `commands/*`).
- Added a golden-snapshot characterization harness and rebuilt the security
  tests to exercise the real code paths with adversarial inputs.

## [0.1.0] — 2026-07-13

Initial public release.

### Added

- Full coverage of the DNSFilter v1/v2 API: 36 endpoint groups, 240+ operations,
  with dynamic command routing (`dnsfcli ENDPOINT FUNCTION [OPTIONS]`).
- Authentication via OS keychain with multiple named profiles
  (`auth setup`, `auth verify`, `auth use`, `auth export`).
- Rich table output with `--columns`, `--sort`, `--filter` (AND/OR modes),
  `--limit`, `--all` pagination, `--group-by`, and aggregate flags
  (`--count`, `--sum`, `--avg`, `--min`, `--max`).
- Scripting-friendly output: `--json`, `--jsonl`, `--raw`, `--pick`, `--jq`,
  `--format` templates (both `{field}` and `{{.field}}` styles), and automatic
  JSON when stdout is piped.
- CSV bulk operations: `--template` generation, `--from-csv` batch execution
  with validation and preview, `--to-csv`/`--to-markdown` export,
  `--skip-rows`, `--max-rows`, `--batch-report`.
- Data transformation: `--map`, `--transform` (safe restricted expressions),
  `--add-field`, `--join`, `--flatten`, `--strip-nulls`.
- Watch mode: `--watch`, `--watch-until`, `--watch-diff`, `--alert`.
- CI helpers: `--fail-on-empty`, `--fail-on-pattern`, `--exec`, `--dry-run`,
  `--tee`, `--log-file`.
- Multi-organization fan-out: `--each-org`, `--org-filter`, `--org-csv`,
  `--parallel-orgs`.
- Configuration file with column presets, format presets, and command bundles;
  saved command aliases (`--save-as NAME`, then `dnsfcli NAME`).
- Shell completion (bash/zsh/fish), `doctor` diagnostics, audit and history
  logs (written with owner-only permissions, credentials scrubbed).
- Client-side rate limiting, automatic 429 retry with bounded attempts, and
  connection-error backoff.
