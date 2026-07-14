# Changelog

All notable changes to dnsfcli are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project adheres to [Semantic Versioning](https://semver.org/).

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
