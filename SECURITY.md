# Security review

Review date: 17 November 2026. Scope: the separated source copy, core account/portfolio routes, source artifact paths, synthetic regression tests, and the exact base runtime dependency set. This is not a penetration test or an assertion that every legacy feature is safe for a public multi-user service.

## Changes verified

- Position reads and edits/close/delete operations enforce account ownership. Cash is account-specific. Invalid objects do not disclose whether another account owns them.
- Personal watchlists/history and watchlist decision entries are scoped to the current account. Background decision capture receives the initiating owner explicitly. Manual writes to shared market-screen tables are rejected.
- Non-finite prices, quantities, balances, and overflowing transaction values are rejected before persistence. Account regression tests cover partial sales and cash conservation.
- Normal startup requires an externally supplied signing secret. CSRF remains enabled; logout accepts POST only. Session/remember cookies are HttpOnly and SameSite=Lax, with configurable Secure cookies for HTTPS.
- Missing authentication fields are normalized before validation. Login errors use the same message for unknown accounts and incorrect passwords. Only the expected legacy SHA256 format can migrate to current password hashing.
- Writable market artifacts, models, sessions, and caches use external runtime paths. Personal absolute paths and a hardcoded messaging recipient were removed. Importing the messaging module has no send/startup side effects.
- Default local startup binds to localhost, with debug/reloader and background worker disabled.

## Dependency audit after parser replacement

`pip-audit` checked all 33 pinned base runtime packages and reported zero known vulnerabilities on 17 November 2026. The previous `soupsieve==2.10` findings (CVE-2026-126190, CVE-2026-126193, CVE-2026-126191) were resolved for this base environment by removing that dependency entirely, together with BeautifulSoup and googlenewsdecoder. No advisory was suppressed.

HTML handling now uses `selectolax==1.0.2` with its Lexbor backend. Inputs are limited to 2 MiB, 50,000 elements, and a nesting depth of 64. HTML downloads use streamed size limits, per-request timeouts and elapsed-time checks between chunks. Automatic redirects are rejected. The elapsed-time check does not replace socket timeouts or provide a hard wall-clock deadline during a blocked network read. Selectors remain defined in source.

An independent, narrow Google News resolver replaces the third-party decoder. Metadata and RPC responses are bounded; invalid or changed formats return an unavailable result. It rejects non-web URLs, credentials in URLs, localhost and canonical private IP literals. This is not a complete SSRF/network-isolation guarantee: DNS resolution and all other existing fetch paths still require deployment review. Google's undocumented RPC format and live provider availability were not verified; synthetic protocol fixtures were used.

Tests confirm the removed parser packages are absent in the clean base environment. Optional ML/provider/messaging environments are not covered by this audit and can reintroduce additional parser dependencies; audit their complete dependency graphs separately. Audit tooling is excluded from the application lock.

## Other deployment limits

The application is still a legacy research workspace with shared market resources. There is no verified production rate limiter, administrator-role system, complete background-job isolation, or deployment hardening review. Use a separate database and authorized data for local evaluation. Complete a full route review, production server/TLS configuration, backup/concurrency testing, and secret management before exposing it to additional users.

Legacy unowned records are preserved but hidden; do not automatically assign them to whichever account logs in first. Source-only publication must exclude all private data, sessions, signing material, logs, model weights, generated output, and environment files. Ignore rules do not sanitize files already tracked by Git.

The credential scanner reported one reviewed false positive on a literal HTML table-sort attribute. No unresolved credential or personal-path match was found in the reviewed source copy. Pattern scanning cannot recognize all possible confidential business information.

## Synthetic demo

The opt-in demo creates a new external directory with synthetic CSVs and a fresh SQLite database. It refuses overwrite and source-directory targets, uses generated account/session secrets, disables background workers, and binds its server to localhost. Generated login/config files and databases are excluded by ignore rules and are not publication artifacts. A provenance marker enables a visible synthetic-data banner and response header.

Private conversation-group names and archive split metadata have been removed from research scripts. Optional Telegram research now loads explicitly authorized group metadata from an external configuration file with validated archive aliases and dates. No group names or chat archives are distributed.
