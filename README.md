# stock-web

A Flask application for broker-flow research, market screens, personal watchlists, decision journals, and portfolio tracking. This source-only copy separates application code from private market files, databases, saved account sessions, caches, model weights, and generated reports.

The original project is preserved. No private dataset or trained model is required to start the application or run its fixture tests. Data-dependent research pages require authorized local inputs; historical research results have not been independently reproduced in this release.

## Installation

Python 3.10 is verified. Use a separate virtual environment. From this directory on Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -B run_tests.py
```

`requirements-lock.txt` records all 33 packages in the verified runtime dependency graph. `requirements.txt` expresses compatible version ranges. The lock was verified on Windows/Python 3.10; other platforms may resolve different packages. The verified base dependency graph contains no known advisories at the time of review; deployment limits are documented in [SECURITY.md](SECURITY.md).

## Local startup

```powershell
$env:SECRET_KEY = .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
$env:FLASK_RUNTIME_DIR = [IO.Path]::GetFullPath('../var')
$env:BDM_BASE_PATH = [IO.Path]::GetFullPath('../market-data')
.\.venv\Scripts\python.exe main.py
```

Open `http://127.0.0.1:5000`. Keep the same strong session key across restarts using a deployment secret store or protected environment configuration; do not commit it. Missing or short keys stop normal startup. The development entry point binds to localhost, disables debug/reloading, and does not start background workers or downloads automatically.

Sign up with a valid email, a name, and a password of 10–1024 characters. Personal portfolios, cash balances, watchlists, history, and decision entries are scoped to the authenticated account. Research market screens and market-derived caches remain shared application resources.

## Synthetic stock demo

To preview populated pages without any private files, run these commands from the repository root in the base virtual environment:

```powershell
.\.venv\Scripts\python.exe -B -m website.demo seed --out ../stock-web-demo
.\.venv\Scripts\python.exe -B -m website.demo serve --root ../stock-web-demo --port 5087
```

Open `http://127.0.0.1:5087` and use the locally generated credentials in `../stock-web-demo/demo-login.txt`. The seed command refuses to overwrite an existing directory and always creates its database outside source code. Session secrets and passwords are generated locally, never stored in this repository.

The demo contains ADRO, BBRI, and TLKM with 80 deterministic synthetic weekday sessions each, personal watchlists, three portfolio positions, and an illustrative cash balance. The ticker symbols are real; every quote, flow, position and balance is invented for UI demonstration. Pages display a **DEMO SINTETIS** banner and responses include `X-Data-Provenance: synthetic-demo`. The demo is not a research result or a trading recommendation. Its database, generated CSV files and login configuration remain outside the repository.

## Configuration and private files

| Variable | Purpose / default |
| --- | --- |
| `SECRET_KEY` | Required random signing secret, at least 32 characters |
| `FLASK_RUNTIME_DIR` | Private writable root; defaults to `../var` outside the source directory |
| `BDM_BASE_PATH` | Authorized market inputs; defaults to `var/market-data` |
| `DATABASE_URL` | Defaults to SQLite at `var/databases/database.db` |
| `PATTERN_MODEL_PATH` | Optional trained pattern model; defaults to `var/models/best_stock_pattern_model.keras` |
| `COOKIE_SECURE` | Set to `1` behind HTTPS to require secure session/remember cookies |
| `DREAM_AGENT_WORKER_ENABLED` | Optional background worker; disabled unless explicitly set to `1` |
| `TELEGRAM_RESEARCH_CONFIG` | Optional private JSON group metadata (`name`, safe `archive` alias, ISO `start`/`split` dates); must be outside source |
| `KERING_SOURCE_DIR` | Optional external screener implementation; not included |
| `ANDROID_HOME` / `ANDROID_SDK_ROOT`, `JAVA_HOME` | Optional Android build toolchains |

Runtime artifacts are routed to `cache/`, `data/`, `databases/`, `models/`, `secrets/`, and `logs/` below the private runtime root. Source and market roots must be separate. The database and external model location can also be configured explicitly; never point them at the original project when testing a migration.

Market readers expect the original dataset schemas under `Daily/Summary`, `Daily/All`, `Weekly`, `Monthly/Ownership`, and other feature-specific subdirectories. These files are not distributed. Missing data is not replaced by invented observations. Data-dependent features can report unavailable results until inputs, external tools, or rebuilt caches exist.

The parent package provides `assemble_runtime.py` to stage this code and, optionally, the separated private files into a new directory with `code/` and `var/` siblings. It verifies hashes, excludes saved credentials by default, and does not run the app. No removed cache is restored. Saved user StockLang scripts are runtime data; bundled examples remain in source.

## Database migration

Startup creates missing tables and applies additive SQLite changes for position closing fields and account ownership on cash/decision entries. Existing unowned cash and personal decision rows remain unassigned and are not exposed to another account. They require an explicit, reviewed ownership migration on a backup; the application does not guess an owner. Existing watchlist/position rows with missing owners likewise remain hidden.

Only a fresh synthetic database and a synthetic legacy cash schema were tested. Back up and migrate a separate copy before using real account history. Other database backends and production concurrency are not verified.

## Architecture

- `website/__init__.py`, `auth.py`, `models.py`: application factory, sessions, accounts, and database schema.
- `website/views.py`, `utilities.py`, `templates/`, `static/`: routes and user interface.
- `website/runtime_paths.py`, `config.py`: private artifact routing and market input configuration.
- `website/html_parser.py`, `news_links.py`: bounded Lexbor HTML parsing and an independent Google News link resolver.
- Broker/market modules and `riset_pola_naik/`, `sebaran/`, `twin/`: exploratory analytics and research.
- `stocklang/`: a domain-specific research language; `dream_agent/`: optional local research workflow.
- `website/tests/` and `run_tests.py`: synthetic behavioral, authorization, temporal, and workflow checks.

Many existing features and reports retain Indonesian text. Historical calibration constants are research assumptions, not verified performance guarantees. Model loading uses trusted-local serialization formats; do not load arbitrary pickle/checkpoint files.

## Optional features

`requirements-integrations.txt` adds Yahoo, Telegram, and Twilio clients. `requirements-research.txt` adds larger ML/scientific libraries. These optional environments were not installed or audited as part of the base release. They require their own dependency review and input/model validation. Optional provider/GUI packages can reintroduce BeautifulSoup/Soup Sieve transitively; use a separate environment and audit its complete dependency graph before enabling them.

The optional WhatsApp GUI tool requires `pywhatkit`, explicit `WHATSAPP_RECIPIENT` and `WHATSAPP_IMAGE_DIR` settings, and an explicit CLI invocation with an account ID. Importing it sends nothing. Android/signing and firewall tools are separate Windows utilities; they were not executed or validated. Signing material belongs under the private runtime root.

## Validation and release status

The verified base environment passes 93 tests and offline startup/page smoke checks. Tests use temporary synthetic databases, override market/runtime paths, block network connections, and block access to the original/private project. See [VALIDATION.md](VALIDATION.md).

The previous three Soup Sieve advisories are removed from the base runtime by replacing the parser and removing BeautifulSoup, Soup Sieve, and the third-party news decoder. The 33-package base lock has no known advisories in the recorded audit. Google News uses an undocumented protocol; the replacement resolver is verified with synthetic responses, and live provider compatibility is not guaranteed. HTML responses have size/nesting/element budgets and redirects are rejected. A provider URL change can therefore require an explicit configuration/code update. This copy is prepared for local review, not approved for public deployment. No license has been selected.
