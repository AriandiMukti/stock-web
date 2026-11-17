"""
Adds tickers to specific Stockbit watchlist categories (Best, Best Low,
Pattern Up, or any other tab name shown on stockbit.com/watchlist) by
driving the actual web page with Playwright.

Why not a plain HTTP API call: inspecting the network traffic while adding
BBCA to "Best" manually showed no REST/GraphQL request for the add action
at all -- Stockbit pushes watchlist changes over a WebSocket (their
primus.min.js real-time layer), which isn't a stable, documented endpoint
worth reverse-engineering. Driving the UI directly is slower but keeps
working if their internal protocol changes.

Why session-based, not email/password login: Google-account logins get
silently blocked in automated browsers (Google's own bot detection), and
this script should never need your password typed into it or stored
anywhere. Instead, you log in once yourself in a real, visible browser
window that this script opens, and it saves that session (cookies) to
reuse on every future run -- no credentials ever touch this file.

Setup (one-time):
    pip install playwright
    playwright install chromium
    python stockbit_watchlist.py --login
    (a browser window opens -- log in however you normally would, Google
    included, then come back to the terminal and press Enter)

Usage:
    python stockbit_watchlist.py BBCA:Best TLKM:"Pattern Up" ANTM:"Best Low"

Each argument is TICKER:LIST_NAME, where LIST_NAME must match a watchlist
tab label exactly as shown on stockbit.com/watchlist. Runs headless (no
visible window) by default; add --visible to watch it click through the
page instead, e.g. while debugging a change to add_to_list().
"""
try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import sys
import os
from playwright.sync_api import sync_playwright

WATCHLIST_URL = 'https://stockbit.com/watchlist'
SESSION_PATH = str(_runtime_file('', 'stockbit_session.json'))


def do_login():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(WATCHLIST_URL)
        input('Log in inside the browser window, then press Enter here once you see your watchlist... ')
        page.context.storage_state(path=SESSION_PATH)
        browser.close()
    print(f'Session saved to {SESSION_PATH}')


def add_to_list(page, ticker, list_name):
    page.goto(WATCHLIST_URL)
    page.wait_for_selector('text=All Watchlist', timeout=15000)

    tab = page.locator(f'text="{list_name}"').first
    if tab.count() == 0:
        print(f'  Skipping {ticker}: no watchlist tab named {list_name!r}')
        return
    tab.click()
    page.wait_for_timeout(500)

    add_box = page.get_by_placeholder('Type here to add compan', exact=False)
    add_box.click()
    add_box.fill(ticker)
    page.wait_for_timeout(800)

    suggestion = page.locator(f'text="{ticker}"').first
    if suggestion.count() == 0:
        print(f'  Skipping {ticker}: no autocomplete match found')
        return
    suggestion.click()
    page.wait_for_timeout(500)
    print(f'  Added {ticker} to {list_name}')


def main():
    if len(sys.argv) > 1 and sys.argv[1] == '--login':
        do_login()
        return

    if not os.path.exists(SESSION_PATH):
        print('No saved session yet -- run `python stockbit_watchlist.py --login` first.')
        sys.exit(1)

    # Runs headless (no visible window) by default once a session is
    # saved -- there's nothing to log in to at this point, so nothing to
    # watch. Pass --visible while debugging to actually see it click
    # through the page.
    args = sys.argv[1:]
    visible = '--visible' in args
    args = [a for a in args if a != '--visible']

    pairs = []
    for arg in args:
        ticker, _, list_name = arg.partition(':')
        if not ticker or not list_name:
            print(f'Skipping invalid argument: {arg!r} (expected TICKER:LIST_NAME)')
            continue
        pairs.append((ticker.upper(), list_name))

    if not pairs:
        print('Usage: python stockbit_watchlist.py BBCA:Best TLKM:"Pattern Up" [--visible]')
        sys.exit(1)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not visible)
        page = browser.new_page(storage_state=SESSION_PATH)
        for ticker, list_name in pairs:
            add_to_list(page, ticker, list_name)
        browser.close()


if __name__ == '__main__':
    main()
