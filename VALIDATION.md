# Validation

Verified 17 November 2026 using a newly created virtual environment on Windows with Python 3.10.2. Runtime versions are pinned in `requirements-lock.txt` (33 packages). This installation was tested separately from the original application environment.

```text
python -B run_tests.py
Ran 93 tests
OK

python -m pip check
No broken requirements found.
```

The suite includes 19 new HTML/provider/decoder regressions, 16 security/configuration regressions and existing broker consistency, point-in-time/market calculations, agent workflow, account isolation, cache fallback, and CSRF tests. It uses synthetic fixtures and temporary databases. Network connections and reads from original/private project paths are blocked by the test runner. Its runtime and market roots always override inherited environment settings.

An additional offline smoke check initialized the actual application with an in-memory database and obtained HTTP 200 for `/`, `/login`, `/sign-up`, the PWA manifest, and Bootstrap CSS. No background worker was started. Importing `website.whatsapp` did not import its optional messaging dependency or send a message.

The synthetic legacy cash migration preserved the previous balance without assigning ownership. Two-account tests verify that portfolio updates, cash, personal watchlists, and personal decision entries do not cross account boundaries.

Source checks include Python AST parsing, personal absolute-path scanning, a source-only file inventory, and Gitleaks v8.30.1. Its one HTML attribute match was reviewed as a false positive. All modified/copied files are hashed in the parent package's manifest. These checks do not cover every browser interaction or research branch.

`pip-audit` found zero known advisories across the 33 pinned base runtime dependencies after the parser replacement. The removed BeautifulSoup, Soup Sieve, and googlenewsdecoder packages are absent from the new clean environment. Provider fixtures cover Fed/BEA/KSEI calendars, article extraction, Telegram messages, streamed-response limits, malformed/deep HTML, and Google News RPC success/failure handling. Live provider requests were not tested. This validation does not approve public deployment. Optional research/ML libraries, real market inputs, trained models, Android builds, messaging integrations, all legacy routes, and production concurrency were not verified.

Three additional demo tests verify deterministic synthetic OHLCV, a fresh populated database that refuses overwrite, and real CSRF-protected login followed by portfolio/watchlist/stock-chart requests for all three seeded symbols. The demo seed runs in a fresh subprocess and never uses an existing database. All demo pages and data responses are labelled synthetic.
