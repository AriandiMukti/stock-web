try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
from flask import Blueprint, redirect, render_template, request, flash, jsonify, current_app
from flask_login import login_required, current_user
from .models  import *
from . import db
from .analyze import *
from datetime import datetime, timedelta
import threading
from sqlalchemy import create_engine
from sqlalchemy import inspect
import base64
from concurrent.futures import ThreadPoolExecutor
import json
import re
import logging
import requests
import html
from xml.etree import ElementTree as ET
from email.utils import parsedate_to_datetime
from .news_links import decode_google_news as gnewsdecoder

from .config import DAILY_PATH
from .scanner import build_scanner_view, build_live_view, scanner_stats
from .stock_hub import build_hub
from .kering_screener import build_report as kering_report
from .insider_activity import build_page as insider_page
from .digest import build_digest, watchlist_membership
from .crowding import measure_many, GRID, VOL_BINS, VALUE_BINS, MARKET_BASELINE_20D as CROWD_BASELINE
from .screen_eval import build_report as screen_report
from .ownership import (build_ownership, build_ranking, fetch_idx_registry,
                        fetch_lbrpe, refresh_ksei, sync_ticker, status_data,
                        status_tarik_latar, mulai_tarik_latar, hentikan_tarik_latar,
                        skrip_registri_browser, impor_registri_browser,
                        skrip_lbrpe_browser, mulai_impor_lbrpe)

logger = logging.getLogger(__name__)

utilities = Blueprint('utilities', __name__)
path = DAILY_PATH  # kept as `path` since the rest of this file already uses that name

def is_support(table, i):
    fraction = 0.01
    if table['Low'][i] <= 200 :
        fraction = 0.02
    cond1 = (table['Low'][i] < table['Low'][i-1]) 
    cond2 = (table['Low'][i] < table['Low'][i+1]) 
    cond3 = (table['Low'][i+1] < table['Low'][i+2])
    cond4 = (table['Low'][i-1] < table['Low'][i-2])
    cond5 = ((abs(table['Low'][i] - table['Low'][i-1])/ table['Low'][i] <= fraction) or (abs(table['Low'][i] - table['Low'][i-2])/ table['Low'][i] <= fraction)) and ((abs(table['Low'][i] - table['Low'][i+1])/ table['Low'][i] <= fraction) or (abs(table['Low'][i] - table['Low'][i+2])/ table['Low'][i] <= fraction))
    return ((cond1 and cond2 and cond3 and cond4) or cond5)

# determine bearish fractal
def is_resistance(table, i):
    fraction = 0.01
    if table['High'][i] <= 200 :
        fraction = 0.02
    cond1 = table['High'][i] > table['High'][i-1] 
    cond2 = table['High'][i] > table['High'][i+1]
    cond3 = table['High'][i+1] > table['High'][i+2]
    cond4 = table['High'][i-1] > table['High'][i-2]
    cond5 = ((abs(table['High'][i] - table['High'][i-1])/ table['High'][i] <= fraction) or (abs(table['High'][i] - table['High'][i-2])/ table['High'][i] <= fraction) ) and ((abs(table['High'][i] - table['High'][i+1])/ table['High'][i] <= fraction) or (abs(table['High'][i] - table['High'][i+2])/ table['High'][i] <= fraction) )
    return ((cond1 and cond2 and cond3 and cond4) or cond5)


def compute_levels(levelTable):
    """
    Support/resistance level detection, extracted from the standalone
    chart-generation script so the web app can compute the same levels
    without needing matplotlib/mpl_finance/talib installed. Given a
    DataFrame with 'Low'/'High' columns, returns a sorted list of price
    levels that showed up as a support or resistance fractal at least
    twice, with levels that sit within ~5% of a lower level collapsed
    into that lower level (same dedup rule as the original script).
    """
    levels = []
    for i in range(2, levelTable.shape[0] - 2):
        if is_support(levelTable, i):
            levels.append(levelTable['Low'][i])
        elif is_resistance(levelTable, i):
            levels.append(levelTable['High'][i])

    if not levels:
        return []

    levels.sort()
    countLevels = pd.DataFrame(levels, columns=['Price'])
    countLevels['Count'] = countLevels.groupby('Price')['Price'].transform('count')
    countLevels = countLevels.drop_duplicates()
    countLevels = countLevels[countLevels['Count'] >= 2]
    levels = list(countLevels['Price'].values)

    removeList = []
    if levels:
        lowestPrice = levels[0]
        for index in range(len(levels)):
            tooClose = (levels[index] < lowestPrice * 1.02) or (
                (levels[index] > lowestPrice * 1.02) and (levels[index] <= lowestPrice * 1.05)
            )
            if (levels[index] != lowestPrice) and tooClose:
                removeList.append(levels[index])
            else:
                lowestPrice = levels[index]

    levels = [l for l in levels if l not in removeList]
    return [round(float(l), 2) for l in levels]


def compute_stock_targets(stock_data):
    """
    Given a stock ticker, returns [stock, close, target, target%, value,
    stop_loss, stop%] — the row shape count() needs.

    This replaces three separate ~150-line copies of the same logic that
    used to live inline in count() (once each for Best/Best Low/Portfolio,
    differing only in which record list they looped over), and reuses
    compute_levels() instead of re-implementing the same support/
    resistance search a third time.
    """
    filePath = path + 'Summary/' + stock_data + "_Summary.csv"
    df = pd.read_csv(filePath)

    levels = compute_levels(df.tail(200).reset_index(drop=True))

    close = df['Close'].iloc[-1]
    stopLoss, target = closest_below_and_above(close, levels)
    openPrice = df['Open'].iloc[-1]
    value = "{:.2f}".format(df['Volume'].iloc[-1] * ((openPrice + close) / 2) / 1000000000)

    targetPercentage = round(((target - close) / close * 100), 2)
    stopLossPercentage = round(((close - stopLoss) / close * 100), 2)

    return [stock_data, close, target, targetPercentage, value, stopLoss, stopLossPercentage]


ACQUISITION_SIGNALS_PATH = str(_runtime_file('', 'acquisition_signals.csv'))


def load_acquisition_signals():
    """
    Reads real acquisition/change-of-control news items (manually curated
    from web search, not derived from price/volume data) for the Akuisisi
    page. Backtesting showed technical patterns (sideways+spike, retail
    crossover, foreign/domestic divergence) don't reliably predict big
    rallies -- the actual biggest movers found in this watchlist were all
    driven by real M&A news or exchange-flagged speculative activity. This
    list tracks that instead, so it needs updating by hand as new
    acquisition news comes out -- it isn't computed from the daily CSVs.
    """
    if not os.path.exists(ACQUISITION_SIGNALS_PATH):
        return []
    try:
        df = pd.read_csv(ACQUISITION_SIGNALS_PATH)
    except Exception:
        return []
    df = df.sort_values('announcement_date', ascending=False)
    return [{k: (None if pd.isna(v) else v) for k, v in row.items()} for row in df.to_dict('records')]


# Google News RSS search terms this looks for -- no API key needed, just
# hits news.google.com/rss/search directly. Add more strings here to widen
# the net (e.g. a specific sector, "tender offer", "right issue", etc.);
# each one is queried and results are merged/deduped by link.
ACQUISITION_NEWS_QUERIES = [
    'akuisisi saham BEI',
    'pengambilalihan saham BEI',
    'pengendali baru saham BEI',
    'ganti pengendali saham BEI',
    'tender offer saham BEI',
]

_TICKER_IN_PARENS = re.compile(r'\(([A-Z]{4})\)')
_TICKER_BARE = re.compile(r'\b([A-Z]{4})\b')

# "<jumlah> Saham TICKER" -- checked BEFORE _TICKER_IN_PARENS. Found via the
# acquisition_news_cache backtest below: headlines like "Astra (ASII) Tender
# Offer 238 Juta Saham AUTO di Harga Premium" were tagging ASII (the
# acquirer, named in parens for attribution) instead of AUTO (the actual
# tender-offer target, whose price is what reacts) -- the parens match wins
# by running first and short-circuiting the rest of the chain. The word
# right after "saham" is almost always the company whose SHARES are the
# subject, which for an acquisition/tender-offer headline is the target.
# `(?!\s*[%\d])` excludes "Saham naik 159%" style hits, where the
# 4-letter word after "saham" is a common Indonesian verb (e.g. "Naik",
# "Jual", "Turun") that happens to also collide with a real IDX ticker --
# distinguished from a real ticker mention by being followed by a number/
# percent (the thing that rose/fell), not by the rest of a company name.
# Verified against all 96 cached headlines: 2 corrected (ASII->AUTO,
# MENN->BIKE), 1 false hit avoided (NAIK, a real ticker, off "Saham naik
# 159%"), 0 new false positives among the other 93.
_TICKER_AFTER_SAHAM = re.compile(r'\bsaham\s+([A-Z]{4})\b(?!\s*[%\d])', re.IGNORECASE)
ACQUISITION_NEWS_CACHE_PATH = str(_runtime_file('', 'acquisition_news_cache.csv'))
COMPANY_NAME_TO_TICKER_PATH = str(_runtime_file('', 'company_name_to_ticker.json'))

# A few hand-verified overrides, applied on top of the bulk-loaded map
# below -- these win on any name collision. idx.co.id itself blocks
# scraping (Cloudflare), so the bulk map instead comes from a GitHub
# mirror of the IDX-listed company names (wildangunawan/Dataset-Saham-IDX,
# ~920 of our 962 tickers, missing only the newest listings not yet in
# that mirror's snapshot). Names there are truncated at ~30 chars and
# sometimes drop the "Tbk" suffix mid-word, so a few of the longest
# company names may not match cleanly -- add a manual override here if
# you notice one.
COMPANY_NAME_TO_TICKER_OVERRIDES = {
    'bayan resources': 'BYAN',
    'era media sejahtera': 'DOOH',
    'hassana boga sejahtera': 'NAYZ',
    'satu visi putra': 'VISI',
}


def _load_company_name_to_ticker():
    mapping = {}
    if os.path.exists(COMPANY_NAME_TO_TICKER_PATH):
        try:
            with open(COMPANY_NAME_TO_TICKER_PATH, encoding='utf-8') as f:
                mapping.update(json.load(f))
        except Exception:
            logger.exception('Failed to load company_name_to_ticker.json')
    mapping.update(COMPANY_NAME_TO_TICKER_OVERRIDES)
    return mapping


COMPANY_NAME_TO_TICKER = _load_company_name_to_ticker()
# Longer/more specific names first -- matching stops at the first hit, so
# this avoids a short generic name (e.g. "Panin") wrongly matching inside
# a longer, different company's headline before the specific one is tried.
_COMPANY_NAME_PATTERNS = sorted(COMPANY_NAME_TO_TICKER.keys(), key=len, reverse=True)

# Cap on how many headline-only-untagged articles get the (much slower)
# full-article-content lookup per search, so one broad date range can't
# turn a page load into a multi-minute wait.
ARTICLE_CONTENT_LOOKUP_LIMIT = 20


_META_DESCRIPTION = re.compile(
    r'<meta\s+(?:property=["\']og:description["\']|name=["\']description["\'])\s+content=["\']([^"\']*)["\']'
    r'|<meta\s+content=["\']([^"\']*)["\']\s+(?:property=["\']og:description["\']|name=["\']description["\'])',
    re.IGNORECASE,
)


def _resolve_ticker_from_article(link):
    """
    Headline-only detection misses articles like "Sempat Disorot Bursa,
    Emiten Pelayaran Ini Tersengat Isu Akuisisi" -- no ticker or company
    name in the title at all, even though the body names it plainly (that
    one is about NELY). This follows the actual story: `link` from Google
    News RSS is an obfuscated redirect, not the real article URL, so it's
    decoded first (via the local bounded news-link resolver) to the publisher's
    actual page.

    Only the page's own meta/og description is scanned, not the full page
    text -- tried scanning the whole page first and it produced real false
    positives (an article about Danantara acquiring PNM Investment
    Management got tagged BMRI just because "Bank Mandiri (Persero) Tbk
    (BMRI)" was mentioned in passing three paragraphs in about an unrelated
    detail; another got tagged FAST off an incidental match somewhere in
    page boilerplate that had nothing to do with the article). The meta
    description is written specifically to summarize what the article is
    about, so it doesn't pick up unrelated sidebar/footer/related-article
    mentions the way the full page does -- lower recall, but a wrong
    ticker is worse than no ticker here.
    """
    try:
        decoded = gnewsdecoder(link, interval=1)
    except Exception:
        return None
    if not decoded or not decoded.get('status'):
        return None
    real_url = decoded.get('decoded_url')
    if not real_url:
        return None

    try:
        resp = requests.get(real_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=8, allow_redirects=False)
        resp.raise_for_status()
    except Exception:
        return None

    desc_match = _META_DESCRIPTION.search(resp.text)
    if not desc_match:
        return None
    text = html.unescape(desc_match.group(1) or desc_match.group(2) or '')

    m = _TICKER_IN_PARENS.search(text)
    if m and m.group(1) in stockList:
        return m.group(1)

    text_lower = text.lower()
    for name in _COMPANY_NAME_PATTERNS:
        if name in text_lower:
            ticker = COMPANY_NAME_TO_TICKER[name]
            if ticker in stockList:
                return ticker
    return None


def _dedupe_earliest_per_ticker(results):
    """
    Google News resurfaces the same acquisition story many times as it
    develops (rumor -> confirmation -> clarification, each covered by a
    different outlet) -- keep only the earliest article per ticker guess
    so the list reads as one entry per acquisition, not one per article.
    Results with no ticker guess can't be grouped this way, so all of
    those are kept as-is.
    """
    earliest_by_ticker = {}
    for r in results:
        t = r.get('ticker_guess')
        if not t:
            continue
        # Sentinel so an article with an unparseable date doesn't wrongly
        # win "earliest" against ones with a real date.
        candidate_key = r.get('published_date') or '9999-99-99'
        current = earliest_by_ticker.get(t)
        if current is None or candidate_key < (current.get('published_date') or '9999-99-99'):
            earliest_by_ticker[t] = r

    deduped = [r for r in results if not r.get('ticker_guess')]
    deduped.extend(earliest_by_ticker.values())
    deduped.sort(key=lambda r: r.get('published_date') or '', reverse=True)
    return deduped


def save_news_cache(results):
    """
    Persists search_acquisition_news() results to disk so past searches
    stay browsable (via the "Berita Tersimpan" button on the search page)
    without re-hitting Google News, and so results survive across
    restarts. Merges with whatever's already cached (dedup by link), then
    re-applies the earliest-per-ticker reduction across the *combined*
    set -- a later search might turn up an even earlier article for a
    ticker already in the cache.
    """
    if not results:
        return
    new_df = pd.DataFrame(results)
    if os.path.exists(ACQUISITION_NEWS_CACHE_PATH):
        try:
            existing = pd.read_csv(ACQUISITION_NEWS_CACHE_PATH)
            combined = pd.concat([existing, new_df], ignore_index=True)
        except Exception:
            combined = new_df
    else:
        combined = new_df

    combined = combined.drop_duplicates(subset=['link'])
    records = [{k: (None if pd.isna(v) else v) for k, v in row.items()} for row in combined.to_dict('records')]
    records = _dedupe_earliest_per_ticker(records)
    pd.DataFrame(records).to_csv(ACQUISITION_NEWS_CACHE_PATH, index=False)


def load_news_cache(date_from=None, date_to=None):
    """Reads back the persisted news cache, newest first."""
    if not os.path.exists(ACQUISITION_NEWS_CACHE_PATH):
        return []
    try:
        df = pd.read_csv(ACQUISITION_NEWS_CACHE_PATH)
    except Exception:
        return []
    if date_from:
        df = df[df['published_date'].fillna('') >= date_from]
    if date_to:
        df = df[df['published_date'].fillna('') <= date_to]
    df = df.sort_values('published_date', ascending=False)
    return [{k: (None if pd.isna(v) else v) for k, v in row.items()} for row in df.to_dict('records')]


def search_acquisition_news(date_from=None, date_to=None, extra_query=None):
    """
    Live-fetches recent acquisition/change-of-control news from Google News
    RSS (free, no API key) across ACQUISITION_NEWS_QUERIES, optionally plus
    one ad-hoc `extra_query`. Filters to `date_from`/`date_to` (date objects
    or 'YYYY-MM-DD' strings) when given. Best-effort tags each result with
    a ticker guess: first tries "Saham TICKER" (the company whose SHARES
    the headline is actually about -- for an acquisition/tender-offer story
    that's the target, which can differ from a company named in parens for
    attribution, e.g. the acquirer -- see _TICKER_AFTER_SAHAM), then a
    "(XXXX)" pattern in the headline (the common IDX style, e.g. "... Saham
    Andalan Sakti (ASPI) Melonjak 11%"), then falls back to any other bare
    4-letter all-caps word (e.g. "PNGO Tambah Kepemilikan..." with no
    parens) -- either way cross-checked
    against the real watchlist so a stray 4-letter word that isn't actually
    a ticker doesn't get suggested. Then COMPANY_NAME_TO_TICKER, for
    headlines that spell out the company name instead of the code (e.g.
    "Bayan Resources Akhirnya Bersuara..." with no "BYAN" anywhere). Last
    resort, for whatever's still untagged (capped at
    ARTICLE_CONTENT_LOOKUP_LIMIT articles): _resolve_ticker_from_article
    actually opens the article, for headlines that don't name the company
    at all (e.g. "Sempat Disorot Bursa, Emiten Pelayaran Ini Tersengat Isu
    Akuisisi" -- the body says NELY, the headline doesn't).
    """
    queries = list(ACQUISITION_NEWS_QUERIES)
    if extra_query:
        queries.append(extra_query)

    if isinstance(date_from, str) and date_from:
        date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
    if isinstance(date_to, str) and date_to:
        date_to = datetime.strptime(date_to, '%Y-%m-%d').date()

    seen_links = set()
    results = []
    for q in queries:
        try:
            resp = requests.get(
                'https://news.google.com/rss/search',
                params={'q': q, 'hl': 'id', 'gl': 'ID', 'ceid': 'ID:id'},
                headers={'User-Agent': 'Mozilla/5.0'},
                timeout=10,
            )
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
        except Exception:
            logger.exception('Acquisition news fetch failed for query %r', q)
            continue

        for item in root.findall('.//item'):
            link = item.findtext('link')
            if not link or link in seen_links:
                continue
            title = item.findtext('title') or ''
            pub_raw = item.findtext('pubDate')
            try:
                published = parsedate_to_datetime(pub_raw).date() if pub_raw else None
            except Exception:
                published = None

            if published:
                if date_from and published < date_from:
                    continue
                if date_to and published > date_to:
                    continue

            source_match = re.match(r'^(.*) - ([^-]+)$', title)
            headline = source_match.group(1) if source_match else title
            source = source_match.group(2) if source_match else None

            ticker_guess = None
            m = _TICKER_AFTER_SAHAM.search(headline)
            if m and m.group(1).upper() in stockList:
                ticker_guess = m.group(1).upper()

            if not ticker_guess:
                m = _TICKER_IN_PARENS.search(headline)
                if m and m.group(1) in stockList:
                    ticker_guess = m.group(1)
                else:
                    for candidate in _TICKER_BARE.findall(headline):
                        if candidate in stockList:
                            ticker_guess = candidate
                            break

            if not ticker_guess:
                headline_lower = headline.lower()
                for name in _COMPANY_NAME_PATTERNS:
                    if name in headline_lower:
                        ticker = COMPANY_NAME_TO_TICKER[name]
                        if ticker in stockList:
                            ticker_guess = ticker
                        break

            seen_links.add(link)
            results.append({
                'title': headline,
                'source': source,
                'link': link,
                'published_date': published.isoformat() if published else None,
                'ticker_guess': ticker_guess,
                'query': q,
            })

    # Headline-only detection leaves some articles untagged even though
    # the body plainly names the company -- try those (capped, and run in
    # parallel since each one is a couple of network round-trips).
    untagged = [r for r in results if not r['ticker_guess']][:ARTICLE_CONTENT_LOOKUP_LIMIT]
    if untagged:
        with ThreadPoolExecutor(max_workers=8) as executor:
            resolved = list(executor.map(lambda r: _resolve_ticker_from_article(r['link']), untagged))
        for r, ticker in zip(untagged, resolved):
            if ticker:
                r['ticker_guess'] = ticker

    deduped = _dedupe_earliest_per_ticker(results)
    save_news_cache(deduped)
    return deduped


def add_acquisition_signal(stock, announcement_date, new_controller=None, stake_pct=None, value_idr_b=None, description=''):
    """
    Appends one row to acquisition_signals.csv (creating it if needed) for
    the Akuisisi "add from search results" action. `stock` must be a real
    watchlist ticker -- rejects anything else so a stray form submission
    can't inject an arbitrary row.
    """
    clean_stock = re.sub(r'[^A-Za-z0-9]', '', stock or '').strip()[:6].upper()
    if clean_stock not in stockList:
        return False, f'{stock!r} is not a known watchlist ticker'

    try:
        datetime.strptime(announcement_date, '%Y-%m-%d')
    except (ValueError, TypeError):
        return False, 'announcement_date must be YYYY-MM-DD'

    new_row = {
        'stock': clean_stock,
        'announcement_date': announcement_date,
        'new_controller': new_controller or '',
        'stake_pct': stake_pct or '',
        'value_idr_b': value_idr_b or '',
        'description': description or '',
    }

    if os.path.exists(ACQUISITION_SIGNALS_PATH):
        df = pd.read_csv(ACQUISITION_SIGNALS_PATH)
        df = df[~((df['stock'] == clean_stock) & (df['announcement_date'] == announcement_date))]
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    else:
        df = pd.DataFrame([new_row])

    df.to_csv(ACQUISITION_SIGNALS_PATH, index=False)
    return True, None


_cumulative_flow_cache = {}


def compute_cumulative_flow(stock):
    """
    Cached wrapper around _compute_cumulative_flow_uncached() -- keyed on
    ticker + that ticker's own Summary CSV mtime (not a global mtime scan
    like live_scan/kering_screener, since this only ever reads ONE file).
    In-memory only (no pickle) -- Watchlist History caps at 300 entries
    (views.py:242), so worst case is ~300 tickers; even fully cold that's
    under 2 seconds, not worth persisting across restarts.

    Added after Watchlist History was flagged as the one place in the app
    still recomputing from raw CSV on every single page load.
    """
    clean_stock = re.sub(r'[^A-Za-z0-9]', '', stock or '').strip()[:6].upper()
    if not clean_stock:
        return None
    dailyPath = path + 'Summary/' + clean_stock + "_Summary.csv"
    try:
        mtime = os.path.getmtime(dailyPath)
    except OSError:
        return None

    cached = _cumulative_flow_cache.get(clean_stock)
    if cached and cached[0] == mtime:
        return cached[1]

    result = _compute_cumulative_flow_uncached(clean_stock)
    _cumulative_flow_cache[clean_stock] = (mtime, result)
    return result


def _compute_cumulative_flow_uncached(stock):
    """
    Lightweight version of what stockChartData() computes — just the
    latest cumulative Net Top5 Lot / Retail (and daily change/value) for
    one stock, without the full OHLC/levels/weekly payload. Used by the
    weekly report to scan a whole watchlist without paying for chart data
    it doesn't need.
    """
    clean_stock = re.sub(r'[^A-Za-z0-9]', '', stock or '').strip()[:6].upper()
    if not clean_stock:
        return None

    dailyPath = path + 'Summary/' + clean_stock + "_Summary.csv"
    if not os.path.exists(dailyPath):
        return None

    try:
        daily = pd.read_csv(dailyPath).fillna(0)
    except Exception:
        return None
    if daily.empty:
        return None

    daily['Date'] = pd.to_datetime(daily['Date'], format='%d-%b-%y')
    daily = daily.sort_values('Date').reset_index(drop=True)

    # Trailing 40-bar rolling sum of Net Top5 Lot, not an all-time cumsum —
    # window size validated by backtesting (backtest_signal.py) as the one
    # that best predicts a positive move after the sum flips positive.
    # Computed over the full history so the last-50 display slice below
    # isn't missing its first ~40 bars of lookback.
    net_top5_rolling40 = daily['Net Top5 All Lot'].rolling(window=40, min_periods=1).sum()

    daily = daily.tail(50).reset_index(drop=True)
    cumulative = net_top5_rolling40.tail(50).reset_index(drop=True)

    # Same sign-change scan the Compare table's crossover badge does
    # client-side, run here server-side over the last `lookback_days` bars
    # so the weekly report can flag it without a browser in the loop.
    crossing = None
    lookback_days = 7
    n = len(cumulative)
    for i in range(n - 1, max(0, n - lookback_days) - 1, -1):
        if i == 0:
            break
        prev, cur = cumulative.iloc[i - 1], cumulative.iloc[i]
        if prev <= 0 and cur > 0:
            crossing = {'dir': 'up', 'daysAgo': n - 1 - i}
            break
        if prev > 0 and cur <= 0:
            crossing = {'dir': 'down', 'daysAgo': n - 1 - i}
            break

    retail_cumulative = round(float(daily['Retail'].cumsum().iloc[-1]), 2)
    net_top5_slope = round(float(daily['Net Top5 All Lot'].tail(5).sum()), 2)
    retail_slope = round(float(daily['Retail'].tail(5).sum()), 2)

    # Price change over the last 10 trading days (11 bars: today vs 10
    # bars back) — a "quiet" price while big money accumulates and
    # retail distributes is the classic pattern; a stock that's already
    # ripped or dumped isn't quietly being accumulated anymore.
    price_change_10d = None
    if len(daily) >= 11:
        close_now = float(daily['Close'].iloc[-1])
        close_10d_ago = float(daily['Close'].iloc[-11])
        if close_10d_ago:
            price_change_10d = round((close_now - close_10d_ago) / close_10d_ago * 100, 2)

    # 0-3 confidence score: how many of the three conditions currently
    # hold — not a prediction, just a quick "how many boxes does this
    # tick" readout instead of scanning several columns.
    #   1. Net Top5 Lot net-bought in the last 5 days (not the full
    #      50-day window — a stock that accumulated a month ago but has
    #      since flipped shouldn't still score on that old activity).
    #   2. Retail net-sold in the same 5 days.
    #   3. Price hasn't moved more than 5% (either direction) over the
    #      last 10 days — still quietly under accumulation, not already
    #      off to the races or already dumped.
    confidence = sum([
        net_top5_slope > 0,
        retail_slope < 0,
        price_change_10d is not None and abs(price_change_10d) < 5,
    ])

    # Net Top5 Lot / Retail are in lots (1 lot = 100 shares), same unit as
    # the broker JSON's blot/slot — converting to Rupiah value needs that
    # ×100 alongside the latest avg price, same convention 'value' below
    # already uses for total transaction value.
    avg_price = float(daily['Avg Price'].iloc[-1])
    net_top5_value = round(float(cumulative.iloc[-1]) * 100 * avg_price / 1e9, 2)
    retail_value = round(retail_cumulative * 100 * avg_price / 1e9, 2)

    return {
        'stock': clean_stock,
        'netTop5Cumulative': round(float(cumulative.iloc[-1]), 2),
        'retailCumulative': retail_cumulative,
        'netTop5ValueB': net_top5_value,
        'retailValueB': retail_value,
        'netTop5Slope': net_top5_slope,
        'retailSlope': retail_slope,
        'priceChange10D': price_change_10d,
        'confidence': confidence,
        'change': round(float(daily['Change'].iloc[-1]), 2),
        'value': round(avg_price * float(daily['Volume'].iloc[-1]) / 1e9, 2),
        'avgPrice': avg_price,
        'lastClose': float(daily['Close'].iloc[-1]),
        'crossing': crossing,
    }


# Ambang pembalikan untuk fase & pemicu, dalam persen.
#
# BUKAN angka pilihan selera -- diuji di dua sampel yang terpisah periode
# DAN semestanya, pada ambang 5/6/8/10/12/15%:
#
#   "harga turun >=X% dari puncak tertinggi 20 hari" (pemicu keluar)
#     luar sampel 21 emiten 2016-2025, H+10 vs baseline:
#       5%  -1,03pp | 6%  -1,25pp | 8%  -1,81pp | 10% -1,98pp
#       12% -1,86pp | 15% -1,82pp     -- negatif di 11/11 tahun (5-12%)
#     kalibrasi 2026 semesta penuh, H+20: -3,1 s/d -4,4pp di semua ambang
#
#   "harga naik >=X% dari terendah 20 hari" (pemicu balik arah)
#     luar sampel, H+10: 5% +0,70 | 6% +1,25 | 8% +1,23 | 10% +1,85
#                        12% +1,67 | 15% +1,55   -- positif 10-11/11 tahun
#     kalibrasi 2026, H+10: +1,3 s/d +2,0pp di semua ambang
#
# Tandanya sama di SELURUH rentang ambang, di kedua sampel, di ketiga
# horizon -- ciri efek yang nyata, bukan parameter yang dicocok-cocokkan.
# Dipakai 10% karena paling kuat di dua arah sekaligus dan konsisten di
# tiap tahun, bukan karena paling besar di satu sel.
PHASE_REVERSAL_PCT = 10.0

# Rentang 20 hari yang lebih sempit dari ambang pembalikan berarti harga
# praktis tidak ke mana-mana -- itu yang disebut fase datar (basing).
PHASE_FLAT_PCT = PHASE_REVERSAL_PCT


def _fase_ayunan(daily):
    """
    Fase siklus harga dari STRUKTUR AYUNAN, plus hari pemicunya.

    Kenapa dari harga, bukan dari arus Net Top5 vs Retail seperti versi
    pertama fitur ini: sumbu arus itu diukur dan ternyata tidak punya daya
    pisah sama sekali. 865 emiten, Jan-Sep 2026, return H+10 terhadap
    baseline -- akumulasi +0,67pp, distribusi +0,69pp, netral +0,69pp.
    Ketiganya sama. Label gabungannya malah terbalik dari namanya:
    'Lanjutan sungguhan' (terbaca bullish) -0,58pp di H+20, label
    TERBURUK; 'Mulai keluar diam-diam' (terbaca bearish) +2,02pp, TERBAIK.
    Akibat praktisnya nyata -- TOTL 7 Jul-7 Agu 2026 ditandai "mulai
    keluar diam-diam" sebulan penuh sementara harganya naik +27%.

    Versi kedua memakai kemiringan MA20 dan juga gagal, dengan cara lain:
    MA20 tertinggal ~2 minggu di titik balik, jadi WGSH 13 Mei-2 Jun 2026
    ditandai MARKDOWN padahal harganya naik +37%.

    Yang dipakai sekarang: ayunan. Batas fase diletakkan TEPAT di puncak
    dan dasar ayunan, jadi blok warnanya tidak pernah bisa berlawanan
    dengan lilin di bawahnya. Konsekuensinya jujur: batas itu baru bisa
    diketahui setelah harga berbalik PHASE_REVERSAL_PCT persen, jadi
    warnanya adalah pembacaan setelah kejadian. Yang bisa dipakai SAAT
    ITU JUGA adalah pemicunya -- itu yang ditandai terpisah.

    Mengembalikan (daftar fase per baris, daftar pemicu per baris).
    """
    close = daily['Close'].tolist()
    high = daily['High'].tolist()
    low = daily['Low'].tolist()
    n = len(close)
    R = PHASE_REVERSAL_PCT

    # --- ayunan: puncak & dasar ------------------------------------------
    # Arah awal ditebak 'naik'; kalau salah, tebakan itu terhapus sendiri
    # begitu pembalikan pertama terjadi, jauh sebelum jendela tampilan.
    legs = []
    arah = 'naik'
    ext_val, ext_idx, leg_start = close[0] if n else 0, 0, 0
    for i in range(1, n):
        c = close[i]
        if arah == 'naik':
            if c > ext_val:
                ext_val, ext_idx = c, i
            elif ext_val > 0 and (c / ext_val - 1) * 100 <= -R:
                legs.append((leg_start, ext_idx, 'naik'))
                leg_start, arah, ext_val, ext_idx = ext_idx, 'turun', c, i
        else:
            if c < ext_val:
                ext_val, ext_idx = c, i
            elif ext_val > 0 and (c / ext_val - 1) * 100 >= R:
                legs.append((leg_start, ext_idx, 'turun'))
                leg_start, arah, ext_val, ext_idx = ext_idx, 'naik', c, i
    if n:
        legs.append((leg_start, n - 1, arah))

    keys = [None] * n
    for start, end, arah_leg in legs:
        k = 'MARKUP' if arah_leg == 'naik' else 'MARKDOWN'
        for i in range(start, end + 1):
            keys[i] = k

    # --- fase datar menimpa arah ayunan ----------------------------------
    # Kalau rentang 20 hari terakhir lebih sempit dari ambang pembalikan,
    # harga praktis diam -- itu basis, bukan tren. Apakah ia akumulasi atau
    # distribusi ditentukan oleh arah harga yang MASUK ke basis itu (20 hari
    # sebelum jendela datarnya), bukan oleh arus siapa pun.
    for i in range(n):
        if i < 20 or not close[i]:
            continue
        hi = max(high[i - 19:i + 1])
        lo = min(low[i - 19:i + 1])
        if (hi - lo) / close[i] * 100 >= PHASE_FLAT_PCT:
            continue
        j = i - 20
        base = close[max(0, j - 20)]
        masuk = (close[j] / base - 1) * 100 if base else 0.0
        if masuk < -R / 2:
            keys[i] = 'AKUMULASI'
        elif masuk > R / 2:
            keys[i] = 'DISTRIBUSI'
        else:
            keys[i] = 'RANGE'

    # --- pemicu ----------------------------------------------------------
    # Aturannya PERSIS yang diuji: sentuhan PERTAMA harga ke -R% dari
    # tertinggi 20 hari (atau +R% dari terendah 20 hari). Memakai jendela
    # 20 hari, bukan ekstrem ayunan, supaya yang ditampilkan sama persis
    # dengan yang diukur.
    triggers = [None] * n
    turun_aktif = naik_aktif = False
    for i in range(n):
        if i < 19 or not close[i]:
            continue
        hi20 = max(close[i - 19:i + 1])
        lo20 = min(close[i - 19:i + 1])
        dd = (close[i] / hi20 - 1) * 100 if hi20 else 0.0
        ru = (close[i] / lo20 - 1) * 100 if lo20 else 0.0
        if dd <= -R:
            if not turun_aktif:
                triggers[i] = 'turun_dari_puncak'
            turun_aktif = True
        else:
            turun_aktif = False
        if ru >= R:
            if not naik_aktif:
                triggers[i] = 'naik_dari_dasar'
            naik_aktif = True
        else:
            naik_aktif = False
    return keys, triggers


@utilities.route('/stock-chart-data/<stock>')
@login_required
def stockChartData(stock):
    """
    JSON data for an interactive per-stock chart (candlestick + net-lot
    flow + volume), replacing the old approach of pre-rendering a static
    .jpg with matplotlib for every stock. The frontend renders this with
    Plotly.js, so charts are zoomable/pannable and don't need a batch
    image-generation job to run before you can view anything.
    """
    clean_stock = re.sub(r'[^A-Za-z0-9]', '', stock).strip()[:6].upper()
    if not clean_stock:
        return jsonify(found=False), 400

    dailyPath = path + 'Summary/' + clean_stock + "_Summary.csv"
    weeklyPath = path.replace('Daily/', 'Weekly/') + 'Summary/' + clean_stock + "_Weekly_Summary.csv"

    if not os.path.exists(dailyPath):
        return jsonify(found=False)

    try:
        daily = pd.read_csv(dailyPath).fillna(0)
    except Exception:
        return jsonify(found=False)

    # Support/resistance levels are computed over the last 100 daily
    # bars, same window the original script used.
    levels = compute_levels(daily.tail(100).reset_index(drop=True))

    daily['Date'] = pd.to_datetime(daily['Date'], format='%d-%b-%y')
    daily = daily.sort_values('Date').reset_index(drop=True)

    # Trailing 20-bar rolling sum, computed over full history first (not
    # the display window) so the crossover check below isn't missing
    # lookback -- this is *only* for crossover detection (window size
    # validated by backtesting as the one giving the best signal), kept
    # entirely separate from the green/red lines' own cumulative values
    # below.
    net_top5_roll20 = daily['Net Top5 All Lot'].rolling(window=20, min_periods=1).sum()
    retail_roll20 = daily['Retail'].rolling(window=20, min_periods=1).sum()

    # Struktur ayunan harga untuk fase & pemicu. Dihitung di SELURUH
    # riwayat dulu, baru dipotong ke jendela tampilan -- kalau dihitung
    # sesudah dipotong, ayunan yang sedang berjalan di lilin pertama layar
    # kehilangan titik awalnya dan fasenya salah.
    phase_keys_full, trigger_flags_full = _fase_ayunan(daily)

    # SELURUH riwayat dikirim (dari Januari), bukan cuma 100 bar terakhir.
    # Yang dibatasi cuma TAMPILAN AWAL-nya: chart terbuka di 100 hari
    # terakhir, dan begitu di-zoom out data Januari muncul. Sebelumnya data
    # lama memang tidak pernah dikirim, jadi zoom out cuma menampilkan
    # ruang kosong.
    #
    # `focusStart` di payload yang memberi tahu frontend di bar mana
    # tampilan awal itu dimulai.
    focus_index = None
    focus_param = request.args.get('focus')
    window_start, window_end = 0, len(daily)
    focus_start = max(0, len(daily) - 100)
    if focus_param:
        try:
            focus_dt = pd.to_datetime(focus_param)
        except Exception:
            focus_param = None

    # Crossover-detection series, sliced to the same window -- kept
    # separate from the green/red lines' data below (different definition
    # of "cumulative", see comment there).
    net_top5_roll20_tail = net_top5_roll20.iloc[window_start:window_end].reset_index(drop=True)
    retail_roll20_tail = retail_roll20.iloc[window_start:window_end].reset_index(drop=True)
    phase_keys_tail = phase_keys_full[window_start:window_end]
    trigger_flags_tail = trigger_flags_full[window_start:window_end]

    daily = daily.iloc[window_start:window_end].reset_index(drop=True)
    # Green/red line values: a plain running total starting at 0 on the
    # chart's own first displayed day (not a rolling window, and not
    # carrying forward the stock's whole history) -- computed *after*
    # slicing to the window so day 1 on screen is where the sum starts.
    daily['Cumulative'] = daily['Net Top5 All Lot'].cumsum()
    daily['RetailCumulative'] = daily['Retail'].cumsum()
    daily['VolUp'] = daily['Volume'] >= daily['Volume'].shift(1).fillna(0)

    if focus_param:
        try:
            diffs = (daily['Date'] - focus_dt).abs()
            candidate = int(diffs.values.argmin())
            # Only mark it if the signal date is actually within the
            # displayed 100 days -- with the window no longer centered on
            # it, an old enough signal could fall outside entirely, and
            # marking the nearest visible day instead would point at the
            # wrong date.
            if diffs.iloc[candidate] <= pd.Timedelta(days=2):
                focus_index = candidate
        except Exception:
            focus_index = None

    # Strongest crossover signal found by backtesting: Net Top5's rolling
    # sum flips up (<=0 -> >0) the *same day* Retail's rolling sum flips
    # down (>0 -> <=0) — a same-day handoff from retail selling to big-lot
    # buying, not just either flip happening on its own. Uses the rolling
    # series above, not the window-anchored `daily['Cumulative']` the
    # lines are drawn from -- a plain cumsum resets arbitrarily wherever
    # the display window happens to start, so its sign flips wouldn't mean
    # the same thing this signal was validated on.
    net_up = (net_top5_roll20_tail.shift(1) <= 0) & (net_top5_roll20_tail > 0)
    retail_down = (retail_roll20_tail.shift(1) > 0) & (retail_roll20_tail <= 0)
    combined_crossing_days = [i for i in range(len(daily)) if bool(net_up.iloc[i]) and bool(retail_down.iloc[i])]

    # ------------------------------------------------------------------
    # FASE SIKLUS HARGA + PEMICU
    #
    # Keduanya dihitung di _fase_ayunan() (lihat catatan panjang di sana
    # soal kenapa versi berbasis arus dan versi berbasis MA20 dibuang).
    # Di sini tinggal dirakit jadi rentang tanggal untuk chart.
    PHASE_LABEL = {
        'AKUMULASI': 'Akumulasi',
        'MARKUP': 'Markup',
        'NAIK_DIBORONG': 'Naik Diborong',
        'DISTRIBUSI': 'Distribusi',
        'MARKDOWN': 'Markdown',
        'TURUN_DILEPAS': 'Turun Dilepas',
        'RANGE': 'Range',
    }

    # Ambang "secara berarti" untuk arus bandar dalam satu fase: jumlah Net
    # Top5 sepanjang fase itu, dibagi total lot yang diperdagangkan di fase
    # yang sama, dalam persen.
    #
    # TIDAK ADA zona mati: labelnya ikut TANDA arus, bukan besarnya.
    #
    # Dua ambang sempat dicoba dan dua-duanya salah dengan cara yang sama.
    # Dengan ambang 2%, fase berarus -1,20% (garis Big Lot Flow jelas
    # menurun) masih disebut Markdown. Dengan 0,5%, masih tersisa 10% fase
    # yang labelnya berlawanan dengan arah garis -- semuanya jatuh di zona
    # matinya. Masalahnya memang zona mati itu sendiri: arus 0,25% dari
    # volume tetap menggerakkan garis kumulatif naik, dan yang dibaca mata
    # dari panel itu adalah ARAHNYA.
    #
    # Karena `arus` dihitung dari rentang yang sama persis dengan
    # perpindahan garisnya, memakai tanda saja membuat label MUSTAHIL
    # berlawanan dengan garis. Besarannya tidak hilang -- ia ada di hover
    # tiap blok, jadi "secara berarti" tetap bisa dinilai sendiri.
    BANDAR_BERARTI = 0.0

    # Gabungkan hari berturut-turut yang fasenya sama jadi satu rentang
    # tanggal -- chart menandai RENTANG, bukan mewarnai tiap lilin
    # sendiri-sendiri. Hari yang fasenya belum terdefinisi dilewati,
    # bukan dipaksa masuk salah satu fase.
    phases = []
    start = None
    for i in range(len(phase_keys_tail) + 1):
        habis = i == len(phase_keys_tail)
        if start is not None and (habis or phase_keys_tail[i] != phase_keys_tail[start]):
            key = phase_keys_tail[start]
            phases.append({'startIdx': start, 'endIdx': i - 1, 'key': key,
                           'label': PHASE_LABEL.get(key, key)})
            start = None
        if not habis and phase_keys_tail[i] is not None and start is None:
            start = i

    # Jaminan konsistensi: sebuah rentang baru boleh disebut Markup kalau
    # harganya memang NAIK sepanjang rentang itu, dan Markdown kalau memang
    # TURUN. Yang tidak lolos diturunkan jadi Range.
    #
    # Perlu karena penimpaan fase datar di atas bisa memotong satu ayunan
    # jadi beberapa pecahan, dan sebuah pecahan bisa bergerak melawan arah
    # ayunan induknya. Tanpa pemeriksaan ini 176 rentang di semesta penuh
    # (dari 5.683) masih berlawanan dengan harganya sendiri -- persis
    # keluhan yang membuat seluruh fitur ini dirombak. Sesudahnya: nol.
    closes = daily['Close'].tolist()
    for seg in phases:
        awal, akhir = closes[seg['startIdx']], closes[seg['endIdx']]
        if not awal:
            continue
        chg = akhir / awal - 1
        if (seg['key'] == 'MARKUP' and chg < 0) or (seg['key'] == 'MARKDOWN' and chg > 0):
            seg['key'] = 'RANGE'
            seg['label'] = PHASE_LABEL['RANGE']

    # Gabungkan lagi rentang bersebelahan yang fasenya jadi sama setelah
    # penurunan di atas, supaya tidak ada dua blok identik yang bersebelahan.
    digabung = []
    for seg in phases:
        if digabung and digabung[-1]['key'] == seg['key'] and digabung[-1]['endIdx'] + 1 == seg['startIdx']:
            digabung[-1]['endIdx'] = seg['endIdx']
        else:
            digabung.append(seg)
    phases = digabung

    # Arus bandar per fase -> penamaan ulang.
    #
    # Fase tetap DITENTUKAN harga (supaya blok tidak pernah berlawanan
    # dengan lilin), tapi NAMANYA ikut arus bandar, mengikuti kerangka
    # SIKLUS BANDAR -- bukan penamaan fase Wyckoff mentah:
    #
    #   Markup  = bandar sudah memegang barang dari fase akumulasi, tinggal
    #             menggiring harga naik. Justru karena itu dia TIDAK perlu
    #             membeli lagi -- malah mulai melepas ke pembeli yang datang.
    #             Jadi: harga naik, arus Top5 TIDAK positif berarti.
    #
    #   Markdown = bandar sudah selesai jualan di fase distribusi, tinggal
    #             menekan harga. Karena barangnya sudah habis dilepas, dia
    #             TIDAK menjual lagi -- malah mulai menyerap dari yang panik.
    #             Jadi: harga turun, arus Top5 TIDAK negatif berarti.
    #
    # Kalau arusnya justru IKUT searah harga, itu bukan penggiringan --
    # itu bandar yang benar-benar sedang memborong (harga naik) atau
    # benar-benar sedang melepas (harga turun). Dua keadaan itu dapat nama
    # sendiri: "Naik Diborong" dan "Turun Dilepas".
    #
    # CATATAN: ini koreksi ISTILAH, bukan sinyal. Sumbu arus sudah diukur
    # dan tidak punya daya pisah terhadap return ke depan (akumulasi
    # +0,67pp, distribusi +0,69pp, netral +0,69pp di H+10). Jadi "Markup"
    # tidak berarti lebih bagus daripada "Naik Diborong" -- cuma
    # menjelaskan siapa yang menggerakkan, bukan ke mana arahnya nanti.
    net5 = daily['Net Top5 All Lot'].tolist()
    vols = daily['Volume'].tolist()
    for seg in phases:
        s, e = seg['startIdx'], seg['endIdx']
        # Rentangnya s+1..e, BUKAN s..e. Garis Big Lot Flow adalah kumulatif,
        # jadi perubahan yang TERLIHAT membentang dari nilainya di bar s
        # sampai di bar e -- dan nilai di bar s sudah memuat arus bar s itu
        # sendiri. Ikut menjumlahkan bar s membuat angka ini bisa berlawanan
        # tanda dengan garis yang dilihat mata kalau bar pertamanya kebetulan
        # besar (nyata terjadi: WGSH satu fase, garis turun 6.994 lot tapi
        # hitungannya +0,93%).
        lot = sum(vols[s + 1:e + 1]) / 100.0
        arus = (sum(net5[s + 1:e + 1]) / lot * 100) if lot > 0 else 0.0
        seg['bandarPct'] = round(arus, 2)
        if seg['key'] == 'MARKUP' and arus > BANDAR_BERARTI:
            seg['key'] = 'NAIK_DIBORONG'
        elif seg['key'] == 'MARKDOWN' and arus < -BANDAR_BERARTI:
            seg['key'] = 'TURUN_DILEPAS'
        seg['label'] = PHASE_LABEL.get(seg['key'], seg['key'])

    # Pemicu -- bagian yang bisa ditindaklanjuti SAAT ITU JUGA, beda dari
    # warna fase yang baru pasti setelah harga berbalik.
    #
    # Angka di catatannya diuji di dua sampel yang terpisah periode DAN
    # semestanya, pada enam ambang (lihat PHASE_REVERSAL_PCT).
    #
    # Teksnya sengaja dipotong jadi baris-baris PENDEK dengan <br>. Versi
    # pertama menaruh seluruh paragraf bukti dalam satu baris, dan karena
    # chart memakai hovermode 'x unified', kotak hover-nya melebar sampai
    # menutupi chartnya sendiri. Penjelasan panjang tempatnya di halaman,
    # bukan di tooltip.
    TRIGGER_NOTE = {
        'turun_dari_puncak': (
            'Turun %d%% dari puncak 20 hari' % int(PHASE_REVERSAL_PCT),
            'H+10 vs pasar<br>2016-2025: -1,98pp<br>2026: -1,20pp<br>negatif 11/11 tahun'),
        'naik_dari_dasar': (
            'Naik %d%% dari dasar 20 hari' % int(PHASE_REVERSAL_PCT),
            'H+10 vs pasar<br>2016-2025: +1,85pp<br>2026: +1,36pp<br>positif 11/11 tahun'),
    }
    phase_triggers = []
    for i, kind in enumerate(trigger_flags_tail):
        if not kind:
            continue
        judul, catatan = TRIGGER_NOTE[kind]
        phase_triggers.append({'idx': i, 'kind': kind,
                               'label': judul, 'note': catatan})

    def normalize(series):
        # 0-1 scaling so the two flow lines can be overlaid on top of
        # the candlesticks on a shared axis, same idea as the
        # MinMaxScaler step in the original script.
        lo, hi = series.min(), series.max()
        if hi == lo:
            return [0.5] * len(series)
        return [round(float(v), 4) for v in ((series - lo) / (hi - lo))]

    weekly_dates, weekly_net_top3 = [], []
    if os.path.exists(weeklyPath):
        try:
            weekly = pd.read_csv(weeklyPath).fillna(0)
            weekly['Date'] = pd.to_datetime(weekly['Date'], format='%d-%b-%y')
            weekly = weekly.sort_values('Date')
            # Bars within the same date range as the daily window (not a
            # fixed row count) so the bars span the full display width
            # left-to-right -- capping at a fixed count of the most recent
            # rows left a gap on the left whenever the daily window (100
            # bars, ~20 weeks) started earlier than that fixed count could
            # reach, even though the weekly file actually had the data.
            weekly = weekly[(weekly['Date'] >= daily['Date'].iloc[0]) & (weekly['Date'] <= daily['Date'].iloc[-1])]
            # Include the year so bars from different years remain distinct
            # categories, matching the daily chart's date format.
            weekly_dates = weekly['Date'].dt.strftime('%d %b %Y').tolist()
            # Net Top3 All Lot, BUKAN Net Retail Lot. Berkas mingguan
            # memuat keduanya, dan batang ini sebelumnya memakai yang
            # retail -- artinya chart harian menampilkan arus bandar
            # sementara batang mingguan di bawahnya menampilkan lawannya,
            # tanpa ada yang menyebutkan bedanya. Perhatikan warnanya ikut
            # berbalik arah di stock_chart.js: retail negatif = akumulasi,
            # tapi Net Top3 POSITIF = akumulasi.
            weekly_net_top3 = weekly['Net Top3 All Lot'].tolist()
        except Exception:
            pass

    return jsonify(
        found=True,
        stock=clean_stock,
        dates=daily['Date'].dt.strftime('%d %b %Y').tolist(),
        open=daily['Open'].tolist(),
        high=daily['High'].tolist(),
        low=daily['Low'].tolist(),
        close=daily['Close'].tolist(),
        volume=daily['Volume'].tolist(),
        volUp=daily['VolUp'].tolist(),
        netTop3Lot=daily['Net Top3 All Lot'].tolist(),
        netTop5Lot=daily['Net Top5 All Lot'].tolist(),
        retail=daily['Retail'].tolist(),
        avgPriceSeries=daily['Avg Price'].tolist(),
        cumulativeNorm=normalize(daily['Cumulative']),
        retailCumulativeNorm=normalize(daily['RetailCumulative']),
        cumulative=daily['Cumulative'].tolist(),
        retailCumulative=daily['RetailCumulative'].tolist(),
        combinedCrossingDays=combined_crossing_days,
        phases=phases,
        phaseTriggers=phase_triggers,
        focusStart=focus_start,
        focusIndex=focus_index,
        levels=levels,
        lastClose=float(daily['Close'].iloc[-1]),
        avgPrice=float(daily['Avg Price'].iloc[-1]),
        value=round(float(daily['Avg Price'].iloc[-1]) * float(daily['Volume'].iloc[-1]) / 1e9, 2),
        change=round(float(daily['Change'].iloc[-1]), 2),
        weeklyDates=weekly_dates,
        weeklyNetTop3=weekly_net_top3,
    )


@utilities.route('/pattern-predict/<stock>')
@login_required
def patternPredict(stock):
    """
    JSON data for the chart-pattern CNN prediction page: OHLC for the
    lookback window the model actually looked at, plus the predicted
    label/probabilities for the next PATTERN_FUTURE_DAYS days. The model
    itself lives in pattern_ml.py and is trained offline by
    deeplearning.py — this route just runs inference on demand.
    """
    clean_stock = re.sub(r'[^A-Za-z0-9]', '', stock).strip()[:6].upper()
    if not clean_stock:
        return jsonify(found=False), 400

    from . import pattern_ml

    try:
        result = pattern_ml.predict_pattern(clean_stock + '.JK')
    except FileNotFoundError as e:
        return jsonify(found=False, error=str(e)), 503
    except Exception:
        logger.exception("patternPredict(%s): prediction failed", clean_stock)
        return jsonify(found=False, error="Prediction failed for this ticker."), 502

    if result is None:
        return jsonify(found=False, error="Not enough price history for this ticker.")

    ohlc = result['ohlc']
    return jsonify(
        found=True,
        stock=clean_stock,
        dates=ohlc.index.strftime('%Y-%m-%d').tolist(),
        open=ohlc['Open'].tolist(),
        high=ohlc['High'].tolist(),
        low=ohlc['Low'].tolist(),
        close=ohlc['Close'].tolist(),
        volume=ohlc['Volume'].tolist(),
        label=result['label'],
        probabilities=result['probabilities'],
        asOf=result['as_of'],
        futureDays=result['future_days'],
    )


# Only the user-managed watchlists get history logged — the algorithmic
# screens (RetailSellStocks, ConsolStocks, etc.) churn constantly as new
# data comes in, so logging their add/delete would just be noise.
WATCHLIST_HISTORY_TYPES = {'PortfolioStocks', 'BestStocks', 'BestLowStocks', 'PatternUpStocks'}

# A move between these two lists isn't logged as a 'removed' event on the
# source side -- the stock hasn't left the watchlist ecosystem, just moved
# to a different bucket within it (the 'added' log on the destination side
# already captures the move). Only these specific directions are
# suppressed; anything else (e.g. anything -> Portfolio) still logs a
# normal removal.
SUPPRESSED_TRANSFER_REMOVALS = {
    ('PatternUpStocks', 'BestStocks'),
    ('PatternUpStocks', 'BestLowStocks'),
    ('BestStocks', 'PatternUpStocks'),
    ('BestLowStocks', 'PatternUpStocks'),
    ('BestStocks', 'BestLowStocks'),
    ('BestLowStocks', 'BestStocks'),
}


def log_watchlist_history(stock, listType, action, avgPrice, retailValue):
    if listType not in WATCHLIST_HISTORY_TYPES:
        return
    db.session.add(WatchlistHistory(
        stock=stock, listType=listType, action=action,
        avgPrice=avgPrice, retailValue=retailValue, userId=current_user.id,
    ))


@utilities.route('/admin', methods=['GET', 'POST'])
@login_required
def admin() :
    if request.method == "POST":
        status = ""
        param = request.args.get('param')
        if param != "analyze" :
            rawStock = request.args.get('stock')
            if not rawStock:
                return jsonify(rsp='error', message='Stock name is required')
            stockName = rawStock.strip()[:4].upper()

            dbType = TypeDB.main(request.args.get('type'))
            if dbType is None:
                return jsonify(rsp='error', message='Unknown stock list type')
            if dbType not in {PortfolioStocks, BestStocks, BestLowStocks, PatternUpStocks}:
                return jsonify(rsp='error', message='This market screen is read-only'), 403

            if param == "add":
                if len(stockName) < 4:
                    return jsonify(rsp='error', message='Stock name is too short')

                stocks = scoped_query(dbType).filter_by(data=stockName).all()
                if len(stocks) > 0 :
                    return jsonify(rsp='error', message=stockName + ' is already in this list')

                try:
                    filePath = path + 'Summary/' + stockName + '_Summary.csv'
                    master = pd.read_csv(filePath)
                    # Sort by Date before taking .iloc[-1] below -- a
                    # source CSV isn't guaranteed to already be in
                    # chronological row order (seen in practice: a
                    # duplicated historical block once pushed the true
                    # latest row off the physical end of a file), and
                    # compute_cumulative_flow() (read back moments later
                    # for the Watchlist History Return %) always sorts
                    # first, so skipping it here could silently pick a
                    # different day's Close than what gets compared
                    # against.
                    master['Date'] = pd.to_datetime(master['Date'], format='%d-%b-%y')
                    master = master.sort_values('Date').reset_index(drop=True)
                except (FileNotFoundError, pd.errors.EmptyDataError):
                    return jsonify(rsp='error', message='No data file found for ' + stockName)

                sourceDb = ''
                if 'source' in request.args :
                    source = TypeDB.main(request.args.get('source'))
                    if source is None:
                        return jsonify(rsp='error', message='Unknown source stock list type')
                    sourceDb = scoped_query(source).filter_by(data=stockName).all()

                diff5 = master['Net Top5 All Lot'].iloc[-1]
                retail = master['Retail'].iloc[-1]
                avgPrice = master['Avg Price'].iloc[-1]
                # Recorded as the watchlist row's entry price (and what
                # gets logged to WatchlistHistory) instead of the broker
                # Avg Price -- Return on the Watchlist History page reads
                # this back later and should be measuring "close on the
                # day it was added" vs "close now", not the broker average.
                # retailValue keeps using the actual broker Avg Price
                # (avgPrice above), since that's the real transaction value.
                closePrice = master['Close'].iloc[-1]
                retailValue = retail * 100 * avgPrice / 1000000000

                if dbType == PortfolioStocks and stockName not in stockList :
                    return jsonify(rsp='error', message=stockName + ' is not a recognized ticker')

                newPortfolio = dbType(data=stockName, diff5=diff5, retail=retail, avgPrice=closePrice, retailValue=retailValue, userId=current_user.id)
                db.session.add(newPortfolio)
                log_watchlist_history(stockName, dbType.__name__, 'added', closePrice, retailValue)

                # Jurnal Keputusan: snapshot kartu keputusan pada saat
                # menambah, di thread background supaya aksi "tambah ke
                # watchlist" tidak ikut menunggu scanner/kering/flow
                # dihitung (bisa dari cache, tapi tidak selalu instan).
                try:
                    from .decision_journal import capture_snapshot
                    app_obj = current_app._get_current_object()
                    threading.Thread(
                        target=capture_snapshot,
                        args=(stockName, dbType.__name__, 'watchlist_add', app_obj, current_user.id),
                        daemon=True,
                    ).start()
                except Exception:
                    pass

                # Once a stock is promoted into a real watchlist, clear it
                # out of whichever algorithmic screen it came from. See
                # SUPPRESSED_TRANSFER_REMOVALS -- some moves (Pattern Up ->
                # Best/Best Low, Best <-> Best Low) are graduations, not
                # drops, so the source side isn't logged as 'removed' (the
                # 'added' log above already captures it moving into the
                # new list). A genuine standalone delete (the elif branch
                # below) still logs normally.
                for stock in sourceDb :
                    db.session.delete(stock)
                    if (source.__name__, dbType.__name__) not in SUPPRESSED_TRANSFER_REMOVALS:
                        log_watchlist_history(stockName, source.__name__, 'removed', stock.avgPrice, stock.retailValue)

                db.session.commit()
                return jsonify(rsp='success', message=stockName + ' added')

            elif param =="delete" :
                # Personal watchlists are always restricted to their owner.
                stocks = scoped_query(dbType).filter_by(data=stockName).all()
                if len(stocks) == 0 :
                    return jsonify(rsp='error', message="Stock doesn't exist in this list")

                for stock in stocks :
                    db.session.delete(stock)
                    log_watchlist_history(stockName, dbType.__name__, 'removed', stock.avgPrice, stock.retailValue)
                db.session.commit()
                return jsonify(rsp='success', message=stockName + ' deleted')

        else :
            process()
            flash("Analyze is finished", category='success')
            return redirect(request.referrer)

    return jsonify(rsp=f'{status}')

    


def getRangeDate():
    currenDays = datetime.today().isoweekday()
    endDate = datetime.today().strftime('%m/%d/%Y')
    if currenDays > 5 :
        offset = currenDays - 5
        currenDays = 5
        endDate = (datetime.today()- timedelta(days=offset)).strftime('%m/%d/%Y')
    interval = currenDays - 1
    startDate  = (datetime.strptime(endDate, '%m/%d/%Y')- timedelta(days=interval)).strftime('%m/%d/%Y')
    # rangeDate = ' '+startDate + ' - ' + endDate
    rangeDate = ' '+endDate + ' - ' + endDate
    return rangeDate


def return_img_stream(img_local_path):
    img_stream = ''
    with open(img_local_path, 'rb') as img_f:
        img_stream = img_f.read()        
        img_stream = base64.b64encode(img_stream).decode()

    return img_stream  


# def get_type_path(stock):

#     listFolder = ["<market-data>/LQ45/Daily/", "<market-data>/K100/Daily/", "<market-data>/Other3/Daily/", "<market-data>/Other7/Daily/"]
    
#     typePath = ''

#     for folder in listFolder :
#         filePath = folder + "Email/" + stock + "-Graph.jpg"
#         if os.path.isfile(filePath) :
#             typePath = folder
#             break
#     return typePath

# def get_summary_path(stock):

#     listFolder = ["<market-data>/LQ45/Daily/", "<market-data>/K100/Daily/", "<market-data>/Other3/Daily/", "<market-data>/Other7/Daily/"]
    
#     typePath = ''

#     for folder in listFolder :
#         filePath = folder + "Summary/" + stock + "_Summary.csv"
#         if os.path.isfile(filePath) :
#             typePath = filePath
#             break
#     return typePath

def closest_below_and_above(x, y):
    stopLoss = [num for num in y if num <= x]
    target = [num for num in y if num > x]
    
    closest_lower = max(stopLoss, default= x * 0.98)   # return x if no stopLoss value
    # closest_higher = min(target, default=x*1.1) # return x if no target value
    if len(target) == 0 :
        closest_higher = x * 1.1
    else :
        closest_higher = target[:2]
        nearestTarget = (closest_higher[0] - x) / x * 100 
        if nearestTarget <=5 :
            if len(closest_higher) == 1 :
                closest_higher = x * 1.1
            else :
                closest_higher = closest_higher[1]
        else :
            closest_higher = closest_higher[0]
    # if ((x - closest_lower) / x * 100) > 
    # Round to 2 decimal places
    closest_lower = round(closest_lower, 2)
    closest_higher = round(closest_higher, 2)
    
    
    return closest_lower, closest_higher

TARGET_COLUMNS = ['Stock', 'Close', 'Target', 'Target%', 'Value', 'Stop Loss', 'Stop%']


def build_count_sections():
    """
    Shared by count() (renders the page) and send_count_whatsapp() (formats
    a WhatsApp message) so both always show identical numbers instead of
    two separate copies of this computation drifting apart.
    """
    watchlists = {
        'Best': scoped_query(BestStocks).order_by(BestStocks.data).all(),
        'Best Low': scoped_query(BestLowStocks).order_by(BestLowStocks.data).all(),
        'Pattern Up': scoped_query(PatternUpStocks).order_by(PatternUpStocks.data).all(),
        'Portfolio': scoped_query(PortfolioStocks).order_by(PortfolioStocks.data).all(),
    }

    sections = {}
    for label, records in watchlists.items():
        rows = []
        skipped = []
        for r in records:
            try:
                rows.append(compute_stock_targets(r.data))
            except (FileNotFoundError, IndexError, KeyError, ZeroDivisionError, pd.errors.EmptyDataError):
                # No CSV yet, or too little history to find levels for
                # this particular stock — skip it rather than 500 the
                # whole page over one bad file.
                skipped.append(r.data)

        df = pd.DataFrame(rows, columns=TARGET_COLUMNS)
        df = df.sort_values(by='Stock', ascending=True).reset_index(drop=True)
        sections[label] = {
            'rows': df.to_dict(orient='records'),
            'skipped': skipped,
        }
        logger.debug("count(): %s -> %d stocks (%d skipped)", label, len(df), len(skipped))

    return sections


def format_count_sections_as_text(sections):
    """Plain-text rendering of build_count_sections() for WhatsApp -- just
    stock name and Value, not the full target/stop-loss breakdown shown on
    the page itself."""
    lines = ["*BDM — Stock List*"]
    for label, section in sections.items():
        lines.append(f"\n*{label}* ({len(section['rows'])})")
        if not section['rows']:
            lines.append("_no stocks_")
            continue
        for row in section['rows']:
            lines.append(f"{row['Stock']}  {row['Value']}")
    return "\n".join(lines)


@utilities.route('/count', methods=['GET', 'POST'])
@login_required
def count() :
    """
    Target/stop-loss levels for Best, Best Low, Pattern Up, and Portfolio
    watchlists, computed from each stock's support/resistance levels. Previously this
    only logged the result and redirected — nothing was ever shown to the
    user. Now renders count.html with the actual tables.
    """
    sections = build_count_sections()
    whatsapp_text = format_count_sections_as_text(sections)
    return render_template("count.html", user=current_user, sections=sections, whatsapp_text=whatsapp_text)



@utilities.route('/count/send-whatsapp', methods=['POST'])
@login_required
def send_count_whatsapp():
    """
    Sends the current count() output to WhatsApp via Twilio's WhatsApp API.

    Requires four environment variables to be set — without them this
    returns a clear error instead of silently failing:
      TWILIO_ACCOUNT_SID   - from your Twilio console
      TWILIO_AUTH_TOKEN    - from your Twilio console
      TWILIO_WHATSAPP_FROM - your Twilio WhatsApp sender, e.g. 'whatsapp:+14155238886'
      WHATSAPP_TO_NUMBER   - your own WhatsApp number, e.g. 'whatsapp:<recipient-number>'

    Twilio's WhatsApp sandbox requires the destination number to have
    opted in (send 'join <sandbox-word>' to the sandbox number once from
    WhatsApp) before it will deliver messages.
    """
    account_sid = os.environ.get('TWILIO_ACCOUNT_SID')
    auth_token = os.environ.get('TWILIO_AUTH_TOKEN')
    from_number = os.environ.get('TWILIO_WHATSAPP_FROM')
    to_number = os.environ.get('WHATSAPP_TO_NUMBER')

    missing = [
        name for name, val in [
            ('TWILIO_ACCOUNT_SID', account_sid),
            ('TWILIO_AUTH_TOKEN', auth_token),
            ('TWILIO_WHATSAPP_FROM', from_number),
            ('WHATSAPP_TO_NUMBER', to_number),
        ] if not val
    ]
    if missing:
        return jsonify(rsp='error', message='Missing env vars: ' + ', '.join(missing))

    try:
        from twilio.rest import Client
    except ImportError:
        return jsonify(rsp='error', message="Twilio isn't installed — run: pip install twilio")

    sections = build_count_sections()
    body = format_count_sections_as_text(sections)

    # WhatsApp messages have a ~1600 character limit via Twilio; trim with
    # a note rather than letting the API call fail outright.
    if len(body) > 1550:
        body = body[:1500] + "\n\n_(truncated — open the app for the full list)_"

    try:
        client = Client(account_sid, auth_token)
        client.messages.create(from_=from_number, to=to_number, body=body)
    except Exception as e:
        logger.exception("send_count_whatsapp(): failed to send")
        return jsonify(rsp='error', message='Twilio error: ' + str(e))

    return jsonify(rsp='success', message='Sent to WhatsApp')


@utilities.route('/broker-summary', methods=['GET', 'POST'])
@login_required
def broker() :

    
    # Ketiga masukan ini dulu dipakai tanpa dijaga sama sekali: rangeDate
    # yang kosong bikin .split() jalan di None (AttributeError), tanggal yang
    # bentuknya lain bikin strptime melempar, dan stockType selain
    # All/Foreign bikin `typePath` tidak pernah di-assign (UnboundLocalError).
    # Ketiganya keluar sebagai 500 -- padahal semuanya cuma masukan salah.
    stockType = (request.form.get('stockType') or '').strip()
    stock = (request.form.get('stock') or '').strip().upper()
    rangeDate = (request.form.get('rangeDate') or '').split('-')

    if stockType not in ('All', 'Foreign'):
        return jsonify(message='stockType harus All atau Foreign.'), 400
    if not stock:
        return jsonify(message='Kode saham kosong.'), 400
    if len(rangeDate) < 2:
        return jsonify(message='rangeDate harus berbentuk "MM/DD/YYYY - MM/DD/YYYY".'), 400
    try:
        startDate = datetime.strptime(rangeDate[0].strip(), '%m/%d/%Y')
        endDate = datetime.strptime(rangeDate[1].strip(), '%m/%d/%Y')
    except ValueError:
        return jsonify(message='Tanggal tidak terbaca; pakai MM/DD/YYYY.'), 400
    if endDate < startDate:
        return jsonify(message='Tanggal akhir lebih awal dari tanggal mulai.'), 400
    pathList= []

    
        
    for n in range(int ((endDate - startDate).days)+1):
        date = (startDate + timedelta(n)).strftime('%Y-%m-%d')
        if stockType == 'All' :
            typePath = path + 'All/' + date + "\\" +stock + "_ALL_" + date + ".json"
            xlsPath = path + 'All/' + date + "\\" + stock + ".xls"
        else :
            typePath = path + 'Foreign/' + date + "\\" + stock + "_FOREIGN_" + date + ".json"
            xlsPath = path + 'Foreign/' + date + "\\" + stock + ".xls"

        # JSON (Stockbit API, sumber lama) diutamakan kalau ada. Kalau
        # tidak ada - misal harinya cuma di-export lewat .xls IPOT
        # (BrokerActivitySummaryAll.py/Foreign.py, lihat <external-tools>/
        # BDM\SummaryActivityDaily.py buat definisi kolomnya) - pakai .xls
        # itu sebagai gantinya, bukan langsung dianggap tidak ada data.
        if not os.path.exists(typePath) and os.path.exists(xlsPath):
            typePath = xlsPath

        if os.path.exists(typePath):
            pathList.append(typePath)
    

    path_metadata_mapping = {}
    
    for full_path in pathList:
        # Cari pola tanggal YYYY-MM-DD menggunakan Regex
        match = re.search(r'\d{4}-\d{2}-\d{2}', full_path)
        if match:
            date_iso = match.group(0)
            # Konversi ke format tampilan bursa (Contoh: '18-Aug-26')
            date_display = datetime.strptime(date_iso, "%Y-%m-%d").strftime("%d-%b-%y")
        else:
            date_display = "Unknown"
        path_metadata_mapping[full_path] = date_display

    
    def _xls_num(v):
        s = str(v).strip().replace(',', '')
        if not s:
            return 0.0
        try:
            return float(s)
        except ValueError:
            return 0.0

    def process_xls_to_dataframe(target_path):
        """Padanan process_json_to_dataframe, sumbernya .xls export IPOT
        (BrokerActivitySummaryAll.py/Foreign.py) dipakai kalau .json Stockbit
        untuk tanggal itu tidak ada. Layout kolom (baris data mulai index 3,
        setelah 3 baris header) dikonfirmasi di <external-tools>/BDM\\
        SummaryActivityDaily.py: 0=NBY(kode) 1=NBLot 2=NBVal 3=BAvg 4=# 5=NSL
        6=NSLot 7=NSVal 8=SAvg. NSLot/NSVal sudah negatif di sumbernya, sama
        seperti 'slot' di JSON - dipakai apa adanya tanpa dibalik supaya
        konsisten dengan langkah .abs() yang sudah ada di bawah."""
        import xlrd
        wb = xlrd.open_workbook(target_path)
        sh = wb.sheet_by_index(0)
        buy_list, sell_list = [], []
        for r in range(3, sh.nrows):
            row = sh.row_values(r)
            if len(row) < 9:
                continue
            if str(row[0]).strip():
                buy_list.append({'netbs_broker_code': str(row[0]).strip(),
                                  'blot': _xls_num(row[1]), 'netbs_buy_avg_price': _xls_num(row[3])})
            if str(row[5]).strip():
                sell_list.append({'netbs_broker_code': str(row[5]).strip(),
                                   'slot': _xls_num(row[6]), 'netbs_sell_avg_price': _xls_num(row[8])})

        if buy_list:
            df_b = pd.DataFrame(buy_list).rename(
                columns={'netbs_broker_code': 'Buyer', 'blot': 'B Lot', 'netbs_buy_avg_price': 'B Average'}
            )
        else:
            df_b = pd.DataFrame(columns=['Buyer', 'B Lot', 'B Average'])

        if sell_list:
            df_s = pd.DataFrame(sell_list).rename(
                columns={'netbs_broker_code': 'Seller', 'slot': 'S Lot', 'netbs_sell_avg_price': 'S Average'}
            )
        else:
            df_s = pd.DataFrame(columns=['Seller', 'S Lot', 'S Average'])

        return pd.concat([df_b, df_s], axis=1)

    # 3. Fungsi pekerja untuk membaca dan menyusun tabel harian secara paralel
    def process_json_to_dataframe(target_path):
        if target_path.lower().endswith('.xls'):
            return process_xls_to_dataframe(target_path)

        # We no longer need to fetch the date_label metadata variable here

        with open(target_path, "r", encoding="utf-8") as file:
            market_data = json.load(file)

        summary = market_data.get('data', {}).get('broker_summary', {})
        buy_list = summary.get('brokers_buy', [])
        sell_list = summary.get('brokers_sell', [])

        if buy_list:
            df_b = pd.DataFrame(buy_list)[['netbs_broker_code', 'blot', 'netbs_buy_avg_price']].rename(
                columns={'netbs_broker_code': 'Buyer', 'blot': 'B Lot', 'netbs_buy_avg_price': 'B Average'}
            )
        else:
            df_b = pd.DataFrame(columns=['Buyer', 'B Lot', 'B Average'])
            
        if sell_list:
            df_s = pd.DataFrame(sell_list)[['netbs_broker_code', 'slot', 'netbs_sell_avg_price']].rename(
                columns={'netbs_broker_code': 'Seller', 'slot': 'S Lot', 'netbs_sell_avg_price': 'S Average'}
            )
        else:
            df_s = pd.DataFrame(columns=['Seller', 'S Lot', 'S Average'])
            
        # Glue the datasets side-by-side
        df_day = pd.concat([df_b, df_s], axis=1)
        
        # ❌ REMOVED: df_day.insert(0, 'Date', date_label)
        
        return df_day

    # Parallelize file reading routines
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(process_json_to_dataframe, pathList))

    valid_dfs = [df for df in results if df is not None]
    if not valid_dfs:
        # Dulu mengembalikan pd.DataFrame() langsung dari view -- Flask tidak
        # tahu cara mengubahnya jadi response, jadi keluar 500 padahal
        # kondisinya normal: memang tidak ada berkas broker untuk rentang itu.
        return jsonify(message='Tidak ada data broker untuk %s pada rentang tersebut.' % stock), 404
        
    table = pd.concat(valid_dfs, ignore_index=True)
    # Convert numeric fields up-front to float to prevent any string computation crashes
    table['B Lot'] = pd.to_numeric(table['B Lot'], errors='coerce').fillna(0.0)
    table['B Average'] = pd.to_numeric(table['B Average'], errors='coerce').fillna(0.0)
    table['S Lot'] = pd.to_numeric(table['S Lot'], errors='coerce').fillna(0.0)
    table['S Average'] = pd.to_numeric(table['S Average'], errors='coerce').fillna(0.0)

    # ==============================================================================
    # 4. INSTANT VECTORIZED WEIGHTED VALUE MATRIX CALCULATION (VWAP)
    # ==============================================================================
    
    # Calculate Buyer Total Weighted Cost Basis
    table["B_Val_Harian"] = table["B Lot"] * table["B Average"]
    grouped1 = table.groupby("Buyer").agg({"B Lot": "sum", "B_Val_Harian": "sum"}).reset_index()
    grouped1["B Average"] = np.where(grouped1["B Lot"] > 0, round(grouped1["B_Val_Harian"] / grouped1["B Lot"], 1), 0.0)
    grouped1 = grouped1.drop(columns=["B_Val_Harian"])

    # Calculate Seller Total Weighted Cost Basis (.abs() to neutralize internal math)
    table["S_Val_Harian"] = table["S Lot"].abs() * table["S Average"]
    grouped2 = table.groupby("Seller").agg({"S Lot": "sum", "S_Val_Harian": "sum"}).reset_index()
    grouped2["S Lot"] = grouped2["S Lot"].abs() 
    grouped2["S Average"] = np.where(grouped2["S Lot"] > 0, round(grouped2["S_Val_Harian"] / grouped2["S Lot"], 1), 0.0)
    grouped2 = grouped2.drop(columns=["S_Val_Harian"])

    # ==============================================================================
    # 5. MATRIKS NETTING POSISI KONSOLIDASI (BUYER VS SELLER ARBITRAGE)
    # ==============================================================================
    # Restore original negative formatting (-) to the transaction database
    grouped2["S Lot"] = -grouped2["S Lot"]
    
    df_net = pd.merge(grouped1, grouped2, left_on="Buyer", right_on="Seller", how="outer", suffixes=("_b", "_s"))
    df_net["Broker"] = df_net["Buyer"].fillna(df_net["Seller"])
    df_net[["B Lot", "S Lot"]] = df_net[["B Lot", "S Lot"]].fillna(0.0)

    # Netting Arbitrage Formula
    df_net["Net_Lot"] = df_net["B Lot"] + df_net["S Lot"]

    # ==============================================================================
    # 6. DOUBLE-BALANCED SIDE-BY-SIDE CONCATENATION (RETAINING NATIVE NaNs)
    # ==============================================================================
    
    # Isolate net Accumulation rows
    final_buyer = df_net[df_net["Net_Lot"] >= 0][["Broker", "Net_Lot", "B Average"]].copy()
    final_buyer.columns = ["Buyer", "B Lot", "B Average"]
    # Drop rows that are fully settled out to zero
    final_buyer = final_buyer[final_buyer["B Lot"] > 0].sort_values(["B Lot"], ascending=False).reset_index(drop=True)

    # Isolate net Distribution rows
    final_seller = df_net[df_net["Net_Lot"] < 0][["Broker", "Net_Lot", "S Average"]].copy()
    final_seller.columns = ["Seller", "S Lot", "S Average"]
    
    # EDGE CASE HANDLER: Catch edge case zeros like broker 'TS' that belong to the seller profile
    broker_nol = df_net[(df_net["Net_Lot"] == 0) & (df_net["S Lot"] != 0)][["Broker", "Net_Lot", "S Average"]].copy()
    broker_nol.columns = ["Seller", "S Lot", "S Average"]
    final_seller = pd.concat([final_seller, broker_nol], ignore_index=True)
    
    # Sort largest distribution balances (most negative values) on top
    final_seller = final_seller.sort_values(["S Lot"], ascending=True).reset_index(drop=True)

    # CRITICAL CHANGE: Glue datasets side-by-side WITHOUT calling .fillna("")
    # This leaves empty grid alignments as floats/NaNs, keeping column arrays balanced
    master_table = pd.concat([final_buyer, final_seller], axis=1)

    totalLot = master_table['B Lot'].sum()
        
    table = master_table.replace(np.nan, '', regex=True)

    avgPrice = 0
    for i in range(len(table['B Lot'])):
        if not isinstance(table['B Lot'][i], str) :
            avgPrice += table['B Lot'][i] / totalLot * round(table['B Average'][i], 1)

    # totalBuy5 = pd.to_numeric(table['B Lot'])[0:5].sum() * avgPrice / 10000000
    # totalSell5 = pd.to_numeric(table['S Lot'])[0:5].sum() * avgPrice / 10000000

    # totalBuy3 = pd.to_numeric(table['B Lot'])[0:3].sum() * avgPrice / 10000000
    # totalSell3 = pd.to_numeric(table['S Lot'])[0:3].sum() * avgPrice / 10000000

    # totalValue = totalBuy3 if totalBuy5 > abs(totalSell5) else totalSell3
    totalValue = (pd.to_numeric(table['B Lot'][0:5]).sum() + pd.to_numeric(table['S Lot'][0:5]).sum()) * avgPrice / 10000000

    table.drop(columns=['B Average', 'S Average'], inplace=True)
    table['Avg Price'] = ''
    # DataFrame.applymap sudah usang sejak pandas 2.1 (diganti DataFrame.map).
    # Dipertahankan mundur supaya tetap jalan di pandas lama.
    _map_sel = getattr(table, 'map', None) or table.applymap
    table = _map_sel(lambda x: f"{x:.0f}" if isinstance(x, (int, float)) else x)
    table.loc[0, 'Avg Price'] =  f'{avgPrice:.1f}'


    table.loc[1, 'Avg Price'] =  f'{totalValue:.1f} B'

    resultFinal = table
    resultFinal = resultFinal.replace(np.nan, '', regex=True)
    resultFinal = resultFinal.set_index('Buyer')
    
    resultFinal = resultFinal.to_html()
    
    resultFinal = resultFinal.replace('<thead>', '<!-- <thead>')
    resultFinal = resultFinal.replace('</thead>', '</thead> -->')
    resultFinal = resultFinal.replace('<table border="1" class="dataframe">', '<table border="1" class="dataframe"> \n <thead> \n <tr style="text-align: right;"> \n <th>Buyer</th> \n <th>B Lot</th> \n <th>Seller</th> \n <th>S Lot</th> \n <th>Average</th> \n</thead>')


    # Dark theme matching the site's flow palette: aqua for buy-side
    # lots, coral for sell-side, neutral slate for the suspect broker.
    style = (
        "<style>"
        " tr { line-height: 34px; text-align: center; border-bottom: 1px solid #38455A; }"
        " th { text-align: center; line-height: 15px; color: #93A2B6; font-weight: 700;"
        "      background-color: #26313F; font-size: 11px; letter-spacing: 0.4px; text-transform: uppercase; padding: 6px 4px; }"
        " td { width: 100px; color: #F4F7FB; font-weight: 600; background-color: #1B2330; font-size: 13px; font-family: 'JetBrains Mono', monospace; }"
        " .dataframe td:nth-child(2) { text-align: right; color: #16E0AE; font-weight: 700; }"
        " .dataframe td:nth-child(3) { text-align: center; }"
        " .dataframe td:nth-child(4) { text-align: right; color: #FF6076; font-weight: 700; }"
        " .dataframe td:nth-child(5) { text-align: center; color: #93A2B6; font-weight: 700; font-size: 12px; }"
        " table.dataframe { border-collapse: collapse; width: 100%; }"
        " </style>\n"
    )

    resultFinal = resultFinal.replace('<table border="1" class="dataframe">', style + '\n <table border="1" class="dataframe" id="dataframe"> \n')
    resultFinal = resultFinal.replace('<tr style="text-align: right;">', '<tr style="text-align: right; color:#93A2B6; font-weight: 700; background-color: #26313F;">')
    resultFinal = resultFinal.replace('<col class="index" />', '')
    resultFinal = resultFinal.replace('<th></th>', '<th style="font-size: 0;">K</th>')

    foreignBroker = ['KZ', 'AK', 'RX', 'YU', 'ZP', 'BK', 'CS', 'MS']
    # retailBroker = ['YP', 'PD', 'XL', 'NI', 'CC', 'XC', 'KK', 'SQ', 'GR', 'DH']
    retailBroker = ['YP', 'PD', 'XL', 'XC']
    suspectBroker = ['MG']

    for i in foreignBroker:
        resultFinal = resultFinal.replace('<td>'+i+'</td>', '<td style="color: #FF6076; font-weight: 700;">'+i+'</td>')
        resultFinal = resultFinal.replace('<th>'+i+'</th>', '<th style="color: #FF6076; font-weight: 700;">'+i+'</th>')
    for i in retailBroker:
        resultFinal = resultFinal.replace('<td>'+i+'</td>', '<td style="color: #16E0AE; font-weight: 700;">'+i+'</td>')
        resultFinal = resultFinal.replace('<th>'+i+'</th>', '<th style="color: #16E0AE; font-weight: 700;">'+i+'</th>')

    for i in suspectBroker:
        resultFinal = resultFinal.replace('<td>'+i+'</td>', '<td style="color: #93A2B6; font-weight: 700;">'+i+'</td>')
        resultFinal = resultFinal.replace('<th>'+i+'</th>', '<th style="color: #93A2B6; font-weight: 700;">'+i+'</th>')

    return jsonify(message=f' {resultFinal} ')


def _berkas_broker_harian(stockType, date, clean):
    """
    Berkas broker satu emiten satu hari: JSON Stockbit kalau ada, .xls IPOT
    kalau tidak (unduhannya pindah ke .xls sejak 16 Sep 2026 -- lihat
    broker_ledger.py). None kalau dua-duanya tidak ada.
    """
    if stockType == 'Foreign':
        folder, js = path + 'Foreign/' + date + "\\", clean + "_FOREIGN_" + date + ".json"
    else:
        folder, js = path + 'All/' + date + "\\", clean + "_ALL_" + date + ".json"
    for p in (folder + js, folder + clean + ".xls"):
        if os.path.exists(p):
            return p
    return None


def aggregate_broker_footprint(stocks, stockType, startDate, endDate):
    """
    Sums buy/sell lots per broker code across every stock in `stocks` over
    the date range — answers "which broker was most active across this
    whole watchlist", which broker() can't since it only ever looks at
    one stock at a time.
    """
    from .broker_ledger import ringkasan_broker

    paths = []
    for stock in stocks:
        clean = re.sub(r'[^A-Za-z0-9]', '', stock).strip()[:6].upper()
        if not clean:
            continue
        for n in range(int((endDate - startDate).days) + 1):
            date = (startDate + timedelta(n)).strftime('%Y-%m-%d')
            p = _berkas_broker_harian(stockType, date, clean)
            if p:
                paths.append(p)

    def read_one(p):
        summary = ringkasan_broker(p)
        if summary is None:
            return None
        return summary.get('brokers_buy', []), summary.get('brokers_sell', [])

    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(read_one, paths))

    def to_float(v):
        # blot/slot come through as strings in the source JSON, not numbers.
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0

    buy_totals, sell_totals = {}, {}
    for r in results:
        if not r:
            continue
        buys, sells = r
        for b in buys:
            code = b.get('netbs_broker_code')
            lot = to_float(b.get('blot'))
            if code:
                buy_totals[code] = buy_totals.get(code, 0) + lot
        for s in sells:
            code = s.get('netbs_broker_code')
            lot = to_float(s.get('slot'))
            if code:
                sell_totals[code] = sell_totals.get(code, 0) + abs(lot)

    top_buyers = sorted(buy_totals.items(), key=lambda x: x[1], reverse=True)[:15]
    top_sellers = sorted(sell_totals.items(), key=lambda x: x[1], reverse=True)[:15]
    return top_buyers, top_sellers


@utilities.route('/broker-footprint-data', methods=['POST'])
@login_required
def brokerFootprintData():
    stocks = [s.strip() for s in (request.form.get('stocks') or '').split(',') if s.strip()]
    stockType = request.form.get('stockType', 'All')
    rangeDate = (request.form.get('rangeDate') or '').split('-')

    if not stocks or len(rangeDate) != 2:
        return jsonify(buyers=[], sellers=[])
    try:
        startDate = datetime.strptime(rangeDate[0].strip(), '%m/%d/%Y')
        endDate = datetime.strptime(rangeDate[1].strip(), '%m/%d/%Y')
    except ValueError:
        return jsonify(buyers=[], sellers=[])

    buyers, sellers = aggregate_broker_footprint(stocks, stockType, startDate, endDate)
    return jsonify(
        buyers=[{'broker': b, 'lot': round(l, 1)} for b, l in buyers],
        sellers=[{'broker': b, 'lot': round(l, 1)} for b, l in sellers],
    )


def broker_trend_series(stock, brokerCode, stockType, startDate, endDate):
    """
    One broker's daily buy/sell lot for one stock across a date range —
    answers "has this broker been a consistent net buyer here over
    months", which the footprint's single-range snapshot can't show.
    """
    clean_stock = re.sub(r'[^A-Za-z0-9]', '', stock or '').strip()[:6].upper()
    brokerCode = (brokerCode or '').strip().upper()
    if not clean_stock or not brokerCode:
        return []

    from .broker_ledger import ringkasan_broker

    days = []
    for n in range(int((endDate - startDate).days) + 1):
        date = (startDate + timedelta(n)).strftime('%Y-%m-%d')
        p = _berkas_broker_harian(stockType, date, clean_stock)
        if p:
            days.append((date, p))

    def read_one(item):
        date, p = item
        summary = ringkasan_broker(p)
        if summary is None:
            return None
        buyLot = next((b.get('blot') for b in summary.get('brokers_buy', [])
                       if (b.get('netbs_broker_code') or '').upper() == brokerCode), 0)
        sellLot = next((s.get('slot') for s in summary.get('brokers_sell', [])
                        if (s.get('netbs_broker_code') or '').upper() == brokerCode), 0)

        def to_float(v):
            try:
                return float(v)
            except (TypeError, ValueError):
                return 0.0

        buyLot, sellLot = to_float(buyLot), abs(to_float(sellLot))
        return {'date': date, 'buyLot': buyLot, 'sellLot': sellLot, 'netLot': buyLot - sellLot}

    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(read_one, days))

    series = [r for r in results if r]
    series.sort(key=lambda r: r['date'])
    return series


@utilities.route('/broker-trend-data', methods=['POST'])
@login_required
def brokerTrendData():
    stock = request.form.get('stock', '')
    brokerCode = request.form.get('brokerCode', '')
    stockType = request.form.get('stockType', 'All')
    rangeDate = (request.form.get('rangeDate') or '').split('-')

    if not stock or not brokerCode or len(rangeDate) != 2:
        return jsonify(series=[])
    try:
        startDate = datetime.strptime(rangeDate[0].strip(), '%m/%d/%Y')
        endDate = datetime.strptime(rangeDate[1].strip(), '%m/%d/%Y')
    except ValueError:
        return jsonify(series=[])

    series = broker_trend_series(stock, brokerCode, stockType, startDate, endDate)
    return jsonify(series=series)


@utilities.route('/kepemilikan-saham-data', methods=['POST'])
@login_required
def kepemilikanSahamData():
    """
    Komposisi kepemilikan satu emiten. Data KSEI dibaca dari arsip lokal
    yang sudah ditarik `python -m website.ownership fetch`; registri IDX
    ditarik on-demand kalau emiten itu belum pernah dibuka, karena satu
    request IDX per emiten jauh lebih murah daripada memuat ribuan
    emiten di muka.
    """
    stock = re.sub(r'[^A-Za-z0-9]', '', request.form.get('stock') or '')[:6].upper()
    if not stock:
        return jsonify(available=False, message='Isi kode saham dulu.')

    data = build_ownership(stock)

    # Registri IDX dan LBRPE ditarik on-demand saat emiten pertama kali
    # dibuka. Keduanya opsional: tanpa registri, tabel pemegang saham
    # kosong; tanpa LBRPE, free float turun ke basis registri dan jumlah
    # pemegang saham belum ada. Semua angka KSEI tetap utuh, jadi satu
    # sumber gagal tidak boleh menggagalkan seluruh response.
    fetched = False
    if data.get('available') and not data.get('has_registry'):
        try:
            fetch_idx_registry(stock)
            fetched = True
        except Exception as exc:
            logger.warning('Gagal tarik registri IDX untuk %s: %s', stock, exc)

    if data.get('available') and not data.get('has_lbrpe'):
        try:
            # LBRPE = unduh + parse PDF, jadi jauh lebih lambat daripada
            # dua sumber lain; sekali tarik lalu dipakai sebulan.
            fetch_lbrpe(stock)
            fetched = True
        except Exception as exc:
            logger.warning('Gagal tarik LBRPE untuk %s: %s', stock, exc)

    if fetched:
        data = build_ownership(stock)

    return jsonify(data)


@utilities.route('/kepemilikan-saham-ranking', methods=['POST'])
@login_required
def kepemilikanSahamRanking():
    """
    Semua emiten dari bulan KSEI terakhir, untuk tabel peringkat yang bisa
    disortir dan difilter di halaman. Penyortiran sendiri dikerjakan di
    browser -- sekitar 900 baris, jauh lebih murah daripada bolak-balik
    ke server tiap kali ganti kolom.
    """
    return jsonify(build_ranking())


@utilities.route('/kepemilikan-saham/refresh-ksei', methods=['POST'])
@login_required
def kepemilikanSahamRefreshKsei():
    """
    Tombol "Refresh KSEI" -- sama dengan `python -m website.ownership
    fetch --months N`. Berjalan sinkron karena satu bulan cuma unduh ZIP
    ~120 KB; dua bulan selesai dalam belasan detik.
    """
    try:
        months = int(request.form.get('months') or 2)
    except ValueError:
        months = 2
    months = max(1, min(months, 12))

    result = refresh_ksei(months, force=request.form.get('force') == '1')
    return jsonify(ok=True, months=months, saved=result['saved'], log=result['log'])


@utilities.route('/kepemilikan-saham/sync', methods=['POST'])
@login_required
def kepemilikanSahamSync():
    """
    Tombol "Sync Emiten" -- sama dengan `python -m website.ownership sync
    <TICKER>`: tarik registri IDX + LBRPE. Menerima beberapa kode saham
    dipisah koma supaya bisa sekaligus, tapi dibatasi agar satu klik tidak
    memicu puluhan unduhan PDF.
    """
    raw = request.form.get('stocks') or request.form.get('stock') or ''
    tickers = [t.strip().upper() for t in raw.split(',') if t.strip()][:10]
    if not tickers:
        return jsonify(ok=False, message='Isi kode saham dulu.')

    log = []
    for ticker in tickers:
        result = sync_ticker(ticker, force=request.form.get('force') == '1')
        log.append('== %s' % (result['ticker'] or ticker))
        log.extend('   ' + line for line in result['log'])
    return jsonify(ok=True, tickers=tickers, log=log)


@utilities.route('/perbarui-kepemilikan/status', methods=['POST'])
@login_required
def perbaruiKepemilikanStatus():
    """Posisi tiap sumber kepemilikan + pekerjaan latar yang sedang jalan."""
    return jsonify(status_data())


@utilities.route('/perbarui-kepemilikan/latar', methods=['POST'])
@login_required
def perbaruiKepemilikanLatar():
    """
    Status ringan pekerjaan latar saja, untuk dipoll tiap beberapa detik
    selama tarik massal berjalan -- tanpa membaca ulang semesta emiten.
    """
    return jsonify(status_tarik_latar())


@utilities.route('/perbarui-kepemilikan/mulai', methods=['POST'])
@login_required
def perbaruiKepemilikanMulai():
    """
    Mulai tarik massal registri IDX / LBRPE di latar. Ratusan emiten
    dengan jeda sopan = puluhan menit, jadi tidak mungkin sinkron seperti
    tombol Refresh KSEI. Kode saham opsional; kosong = semesta Summary.
    """
    jenis = request.form.get('jenis') or ''
    raw = request.form.get('stocks') or ''
    daftar = [t.strip() for t in re.split(r'[\s,;]+', raw) if t.strip()]
    ok, pesan = mulai_tarik_latar(jenis, semua=request.form.get('semua') == '1',
                                  daftar=daftar or None)
    return jsonify(ok=ok, message=pesan)


@utilities.route('/perbarui-kepemilikan/skrip-registri', methods=['POST'])
@login_required
def perbaruiKepemilikanSkripRegistri():
    """
    Skrip Console untuk menarik registri IDX dari browser sendiri -- jalur
    utama sejak Cloudflare IDX menolak klien Python (lihat ownership.py,
    bagian "registri lewat browser").
    """
    skrip, jumlah = skrip_registri_browser(semua=request.form.get('semua') == '1')
    return jsonify(ok=True, jumlah=jumlah, skrip=skrip)


@utilities.route('/perbarui-kepemilikan/impor-registri', methods=['POST'])
@login_required
def perbaruiKepemilikanImporRegistri():
    berkas = request.files.get('berkas')
    if not berkas:
        return jsonify(ok=False, log=['Pilih file JSON hasil skrip dulu.'])
    return jsonify(impor_registri_browser(berkas.read()))


@utilities.route('/perbarui-kepemilikan/skrip-lbrpe', methods=['POST'])
@login_required
def perbaruiKepemilikanSkripLbrpe():
    """Skrip Console LBRPE: browser mengambil PDF, server yang mem-parse."""
    skrip, jumlah = skrip_lbrpe_browser(semua=request.form.get('semua') == '1')
    return jsonify(ok=True, jumlah=jumlah, skrip=skrip)


@utilities.route('/perbarui-kepemilikan/impor-lbrpe', methods=['POST'])
@login_required
def perbaruiKepemilikanImporLbrpe():
    """
    Upload file LBRPE dari browser (~50 MB untuk semua emiten). Parse PDF-
    nya jalan sebagai pekerjaan latar; kemajuannya dipoll seperti tarik
    massal lewat /perbarui-kepemilikan/latar.
    """
    berkas = request.files.get('berkas')
    if not berkas:
        return jsonify(ok=False, message='Pilih file JSON hasil skrip dulu.')
    ok, pesan = mulai_impor_lbrpe(berkas.read(), nama=berkas.filename or 'lbrpe.json')
    return jsonify(ok=ok, message=pesan)


@utilities.route('/perbarui-kepemilikan/skrip-pk', methods=['POST'])
@login_required
def perbaruiKepemilikanSkripPk():
    """
    Skrip Console pengumuman Pemantauan Khusus untuk jurnal maju
    pk_jurnal.py. Sama alasannya dengan registri: IDX menolak Python.
    """
    from .pk_jurnal import skrip_browser
    skrip, rentang = skrip_browser()
    return jsonify(ok=True, jumlah=1, rentang=rentang, skrip=skrip)


@utilities.route('/perbarui-kepemilikan/impor-pk', methods=['POST'])
@login_required
def perbaruiKepemilikanImporPk():
    from .pk_jurnal import impor_browser
    berkas = request.files.get('berkas')
    if not berkas:
        return jsonify(ok=False, log=['Pilih file JSON hasil skrip dulu.'])
    return jsonify(impor_browser(berkas.read()))


@utilities.route('/perbarui-kepemilikan/hentikan', methods=['POST'])
@login_required
def perbaruiKepemilikanHentikan():
    return jsonify(ok=hentikan_tarik_latar())


@utilities.route('/scanner-lab-data', methods=['POST'])
@login_required
def scannerLabData():
    """
    Sinyal scanner terbaru + konteks kepemilikan/harian + skor.

    Dibatasi jumlahnya karena enrich() membaca ratusan file Summary; tanpa
    batas, satu request bisa memindai seluruh 881 file untuk sinyal yang
    tidak akan ditampilkan.
    """
    scanner = (request.form.get('scanner') or '').strip() or None
    try:
        limit = int(request.form.get('limit') or 200)
    except ValueError:
        limit = 200
    limit = max(20, min(limit, 500))

    try:
        return jsonify(build_scanner_view(scanner=scanner, limit=limit))
    except Exception as exc:
        logger.exception('Gagal membangun Scanner Lab')
        return jsonify(available=False, message='Gagal memuat sinyal: %s' % exc)


@utilities.route('/scanner-lab-stats', methods=['POST'])
@login_required
def scannerLabStats():
    """Statistik historis tiap scanner + tabel efek volume."""
    try:
        return jsonify(scanner_stats())
    except Exception as exc:
        logger.exception('Gagal menghitung statistik scanner')
        return jsonify(available=False, message=str(exc))


@utilities.route('/scanner-lab-live', methods=['POST'])
@login_required
def scannerLabLive():
    """
    Sinyal yang masih berjalan, sampai hari terakhir data.

    Pemindaian penuh 881 emiten memakan ~48 detik, jadi hasilnya
    di-cache dan hanya dipindai ulang kalau ada file Summary yang lebih
    baru daripada cache-nya, atau kalau diminta paksa lewat tombol.
    """
    scanner = (request.form.get('scanner') or '').strip() or None
    force = request.form.get('force') == '1'
    try:
        days_back = int(request.form.get('days_back') or 60)
    except ValueError:
        days_back = 60
    days_back = max(7, min(days_back, 180))

    try:
        return jsonify(build_live_view(scanner=scanner, limit=300,
                                       days_back=days_back, force=force))
    except Exception as exc:
        logger.exception('Gagal memindai sinyal berjalan')
        return jsonify(available=False, message='Gagal memindai: %s' % exc)


@utilities.route('/saham-data/<stock>', methods=['POST'])
@login_required
def stockHubData(stock):
    """
    Data gabungan untuk halaman hub satu emiten. ?light=1 melewati
    bagian yang tidak dipakai kartu keputusan (dipakai Watchlist/Screens
    yang cuma butuh kartu, bukan seluruh detail Halaman Saham).
    """
    light = request.args.get('light') == '1'
    try:
        return jsonify(build_hub(stock, light=light))
    except Exception as exc:
        logger.exception('Gagal membangun hub untuk %s', stock)
        return jsonify(available=False, message='Gagal memuat data: %s' % exc)


@utilities.route('/saham-watchlist-data')
@login_required
def stockHubWatchlistData():
    """
    Daftar ticker per watchlist (Portfolio/Best/Best Low/Pattern Up) --
    untuk tombol pindah cepat antar saham watchlist di Halaman Saham,
    tanpa perlu mengetik kode satu-satu.
    """
    try:
        membership = watchlist_membership()
        groups = {}
        for ticker, lists in membership.items():
            for label in lists:
                groups.setdefault(label, []).append(ticker)
        order = ['Portfolio', 'Best', 'Best Low', 'Pattern Up']
        result = [{'label': label, 'tickers': sorted(groups[label])}
                  for label in order if groups.get(label)]
        return jsonify(available=True, groups=result)
    except Exception as exc:
        logger.exception('Gagal memuat daftar watchlist')
        return jsonify(available=False, message='Gagal memuat: %s' % exc)


@utilities.route('/screen-record', methods=['POST'])
@login_required
def screenRecord():
    """
    Rekam jejak keempat screen otomatis app.

    Ditampilkan apa adanya termasuk yang hasilnya buruk -- menyembunyikan
    screen yang kalah dari pasar akan membuat halaman Screens menyesatkan.
    """
    try:
        return jsonify(screen_report())
    except Exception as exc:
        logger.exception('Gagal menghitung rekam jejak screen')
        return jsonify(available=False, message=str(exc))


@utilities.route('/crowding-data', methods=['POST'])
@login_required
def crowdingData():
    """
    Lensa keramaian untuk sekumpulan saham (satu watchlist).

    Dibatasi jumlahnya karena tiap saham berarti satu file Summary
    dibaca; watchlist normal puluhan saham, tapi batas ini mencegah satu
    request tidak sengaja memindai seluruh bursa.
    """
    raw = request.form.get('stocks') or ''
    stocks = [s.strip().upper() for s in raw.split(',') if s.strip()][:200]
    if not stocks:
        return jsonify(available=False, message='Tidak ada saham untuk dinilai.')

    try:
        result = measure_many(stocks)
        result['baseline'] = CROWD_BASELINE
        # Matriks ikut dikirim supaya halaman bisa menampilkan dasar
        # penilaiannya, bukan cuma hasilnya.
        result['grid'] = [
            {'vol': v, 'value': b, 'mean': GRID[(v, b)][0], 'n': GRID[(v, b)][1]}
            for _, _, v in VOL_BINS for _, _, b in VALUE_BINS if (v, b) in GRID
        ]
        result['vol_bins'] = [b[2] for b in VOL_BINS]
        result['value_bins'] = [b[2] for b in VALUE_BINS]
        return jsonify(result)
    except Exception as exc:
        logger.exception('Gagal menghitung lensa keramaian')
        return jsonify(available=False, message=str(exc))


@utilities.route('/kering-screener-data', methods=['POST'])
@login_required
def keringScreenerData():
    """
    Data untuk halaman Kering Screener. Panggilan pertama (belum ada
    cache, atau data harian sudah berubah) makan waktu ~30 detik karena
    memindai 875 emiten -- selanjutnya dari cache, di bawah 1 detik.
    """
    force = request.form.get('force') == '1'
    try:
        days_back = int(request.form.get('days_back') or 30)
    except ValueError:
        days_back = 30
    days_back = max(7, min(days_back, 120))

    try:
        return jsonify(kering_report(days_back=days_back, force=force))
    except Exception as exc:
        logger.exception('Gagal memuat Kering Screener')
        return jsonify(available=False, message='Gagal memuat: %s' % exc)


@utilities.route('/insider-activity-data', methods=['POST'])
@login_required
def insiderActivityData():
    """Data untuk halaman Aktivitas Insider. Cepat (~0,6 detik untuk 1.014 file) -- tidak perlu cache."""
    try:
        days_back = int(request.form.get('days_back') or 30)
    except ValueError:
        days_back = 30
    days_back = max(7, min(days_back, 365))

    action_filter = request.form.get('action_filter') or 'trade'
    if action_filter not in ('trade', 'buy', 'sell', 'all'):
        action_filter = 'trade'
    ticker_filter = (request.form.get('ticker') or '').strip() or None

    try:
        return jsonify(insider_page(days_back=days_back, action_filter=action_filter,
                                    ticker_filter=ticker_filter))
    except Exception as exc:
        logger.exception('Gagal memuat Aktivitas Insider')
        return jsonify(available=False, message='Gagal memuat: %s' % exc)


@utilities.route('/watchlist-digest-data', methods=['POST'])
@login_required
def watchlistDigestData():
    """
    Data untuk Ringkasan Watchlist. Pemanggilan pertama (cache masih
    dingin di live_scan/kering_screener/screen_eval) bisa ~50 detik;
    selanjutnya di bawah 3 detik selama cache-nya masih segar.
    """
    raw = request.form.get('watchlists') or ''
    watchlists = [w.strip() for w in raw.split(',') if w.strip()] or None
    try:
        return jsonify(build_digest(watchlists=watchlists))
    except Exception as exc:
        logger.exception('Gagal memuat Ringkasan Watchlist')
        return jsonify(available=False, message='Gagal memuat: %s' % exc)


@utilities.route('/jurnal-keputusan-data')
@login_required
def decisionJournalData():
    """Data untuk Jurnal Keputusan -- lihat decision_journal.journal_entries()."""
    try:
        from .decision_journal import journal_entries
        hasil = {'available': True, 'entries': journal_entries()}

        # Agregatnya dilampirkan di request yang sama: dua-duanya membaca
        # tabel yang sama dan totalnya ~0,2 detik, jadi request kedua cuma
        # menambah bulat-balik tanpa menghemat apa pun.
        try:
            from .jejak_keputusan import rekam_jejak
            hasil['jejak'] = rekam_jejak()
        except Exception:
            logger.exception('Gagal menghitung rekam jejak keputusan')

        return jsonify(hasil)
    except Exception as exc:
        logger.exception('Gagal memuat Jurnal Keputusan')
        return jsonify(available=False, message='Gagal memuat: %s' % exc)


@utilities.route('/serapan-float-data', methods=['POST'])
@login_required
def serapanFloatData():
    """Data untuk Serapan Float -- lihat float_squeeze.scan()."""
    try:
        from .float_squeeze import scan
        days = request.form.get('days', type=int) or None
        force = request.form.get('force') == '1'
        return jsonify(scan(days=days, force=force))
    except Exception as exc:
        logger.exception('Gagal memuat Serapan Float')
        return jsonify(available=False, message='Gagal memuat: %s' % exc)


@utilities.route('/akumulasi-palsu-data', methods=['POST'])
@login_required
def akumulasiPalsuData():
    """Data untuk Akumulasi Palsu -- lihat fake_accumulation.scan()."""
    try:
        from .fake_accumulation import scan
        days = request.form.get('days', type=int) or None
        return jsonify(scan(days=days))
    except Exception as exc:
        logger.exception('Gagal memuat Akumulasi Palsu')
        return jsonify(available=False, message='Gagal memuat: %s' % exc)


@utilities.route('/jatuh-dalam-data', methods=['POST'])
@login_required
def jatuhDalamData():
    """Data untuk Jatuh Dalam -- lihat jatuh_dalam.scan()."""
    try:
        from .jatuh_dalam import scan
        return jsonify(scan(force=request.form.get('force') == '1'))
    except Exception as exc:
        logger.exception('Gagal memuat Jatuh Dalam')
        return jsonify(available=False, message='Gagal memuat: %s' % exc)


@utilities.route('/tembus-basis-data', methods=['POST'])
@login_required
def tembusBasisData():
    """Data untuk Tembus Basis -- lihat tembus_basis.scan()."""
    try:
        from .tembus_basis import scan
        return jsonify(scan(force=request.form.get('force') == '1'))
    except Exception as exc:
        logger.exception('Gagal memuat Tembus Basis')
        return jsonify(available=False, message='Gagal memuat: %s' % exc)


@utilities.route('/chart-mirip-data/<stock>')
@login_required
def chartMiripData(stock):
    """Kartu Chart Termirip di Halaman Saham -- lihat chart_mirip.cari()."""
    try:
        from .chart_mirip import cari
        return jsonify(cari(stock))
    except Exception as exc:
        logger.exception('Gagal memuat Chart Termirip')
        return jsonify(available=False, message='Gagal memuat: %s' % exc)


@utilities.route('/skor-kecondongan-data', methods=['POST'])
@login_required
def skorKecondonganData():
    """Data untuk Skor Kecondongan -- lihat kecondongan.scan()."""
    try:
        from .kecondongan import scan
        return jsonify(scan(force=request.form.get('force') == '1'))
    except Exception as exc:
        logger.exception('Gagal memuat Skor Kecondongan')
        return jsonify(available=False, message='Gagal memuat: %s' % exc)


@utilities.route('/kabar-semalam-data', methods=['POST'])
@login_required
def kabarSemalamData():
    """Data Kabar Semalam -- lihat kabar_semalam.scan()."""
    try:
        from .kabar_semalam import scan
        return jsonify(scan(force=request.form.get('force') == '1'))
    except Exception as exc:
        logger.exception('Gagal memuat Kabar Semalam')
        return jsonify(available=False, message='Gagal memuat: %s' % exc)


@utilities.route('/ramai-dibahas-data', methods=['POST'])
@login_required
def ramaiDibahasData():
    """Data Ramai Dibahas -- lihat ramai_dibahas.scan()."""
    try:
        from .ramai_dibahas import scan
        return jsonify(scan(force=request.form.get('force') == '1'))
    except Exception as exc:
        logger.exception('Gagal memuat Ramai Dibahas')
        return jsonify(available=False, message='Gagal memuat: %s' % exc)


@utilities.route('/ramai-dibahas-tarik', methods=['POST'])
@login_required
def ramaiDibahasTarik():
    """Mulai tarik Stockbit + Telegram di thread latar; status lewat /ramai-dibahas-data."""
    from .ramai_dibahas import mulai_tarik, status_tarik
    mulai = mulai_tarik(stockbit=request.form.get('stockbit', '1') == '1',
                        telegram=request.form.get('telegram', '1') == '1')
    return jsonify(mulai=mulai, tarik=status_tarik())


@utilities.route('/ramai-dibahas-sumber', methods=['POST'])
@login_required
def ramaiDibahasSumber():
    """Simpan daftar channel publik & grup Telegram (satu per baris)."""
    from .ramai_dibahas import simpan_sumber
    publik = request.form.get('publik', '').splitlines()
    grup = request.form.get('grup', '').splitlines()
    return jsonify(sumber=simpan_sumber(publik, grup))


@utilities.route('/kirim-hp/mulai', methods=['POST'])
@login_required
def kirimHpMulai():
    """Tombol Sync: ekspor data terbaru lalu siaga mengirimnya ke BDM Saku -- lihat kirim_hp.py."""
    from .kirim_hp import mulai_dari_web
    return jsonify(mulai_dari_web(tanpa_ekspor=request.form.get('tanpa_ekspor') == '1'))


@utilities.route('/kirim-hp/status', methods=['POST'])
@login_required
def kirimHpStatus():
    from .kirim_hp import status
    return jsonify(status())


@utilities.route('/kirim-hp/berhenti', methods=['POST'])
@login_required
def kirimHpBerhenti():
    from .kirim_hp import berhenti
    return jsonify(berhenti())


@utilities.route('/rapat-agen-data', methods=['POST'])
@login_required
def rapatAgenData():
    """Data Rapat Agen -- lihat rapat_agen.scan()."""
    try:
        from .rapat_agen import scan
        return jsonify(scan(force=request.form.get('force') == '1'))
    except Exception as exc:
        logger.exception('Gagal memuat Rapat Agen')
        return jsonify(available=False, message='Gagal memuat: %s' % exc)


@utilities.route('/dicicil-insider-data', methods=['POST'])
@login_required
def dicicilInsiderData():
    """Data Dicicil Insider -- lihat dicicil_insider.scan()."""
    try:
        from .dicicil_insider import scan
        hari = request.form.get('hari', type=int)
        minggu = request.form.get('min_minggu', type=int)
        hari = hari if hari in (30, 60, 90) else None
        minggu = minggu if minggu in (3, 4, 6, 8) else None
        return jsonify(scan(hari=hari, min_minggu=minggu, force=request.form.get('force') == '1'))
    except Exception as exc:
        logger.exception('Gagal memuat Dicicil Insider')
        return jsonify(available=False, message='Gagal memuat: %s' % exc)


@utilities.route('/radar-insider-data', methods=['POST'])
@login_required
def radarInsiderData():
    """Data untuk Radar Insider -- lihat insider_signal.scan() dan insider_jurnal."""
    try:
        from .insider_signal import scan
        hasil = dict(scan(force=request.form.get('force') == '1'))

        # Jurnal maju dilampirkan TERPISAH dari cache radar (umurnya beda),
        # dan dicatat dulu di sini: membuka halaman ini sesudah data insider
        # ditarik ikut menjaga jurnalnya -- sama seperti Apa Berubah.
        try:
            from .insider_jurnal import jalankan
            hasil['jurnal'] = jalankan()
        except Exception:
            logger.exception('Gagal memuat jurnal maju insider')
            hasil['jurnal'] = {'available': False, 'message': 'Jurnal maju gagal dimuat.'}
        return jsonify(hasil)
    except Exception as exc:
        logger.exception('Gagal memuat Radar Insider')
        return jsonify(available=False, message='Gagal memuat: %s' % exc)


@utilities.route('/penemu-pola-data', methods=['POST'])
@login_required
def penemuPolaData():
    """Data untuk Penemu Pola -- lihat pattern_miner.mine()."""
    try:
        from .pattern_miner import mine
        force = request.form.get('force') == '1'
        max_orde = request.form.get('max_orde', type=int) or None
        hasil = mine(force=force, max_orde=max_orde)

        # Hasil maju dilampirkan TERPISAH (dict berkunci pola), bukan
        # disuntikkan ke tiap temuan: `hasil` bisa datang dari cache
        # pattern_miner, dan menempelinya berarti angka jurnal ikut
        # terkunci di cache yang umurnya beda.
        try:
            from .pola_jurnal import evaluasi
            hasil['jurnal'] = evaluasi(hasil.get('temuan'))
        except Exception:
            logger.exception('Gagal membaca jurnal maju Penemu Pola')

        return jsonify(hasil)
    except Exception as exc:
        logger.exception('Gagal memuat Penemu Pola')
        return jsonify(available=False, message='Gagal memuat: %s' % exc)


@utilities.route('/sidik-jari-broker-data', methods=['POST'])
@login_required
def sidikJariBrokerData():
    """Data untuk Sidik Jari Broker -- lihat broker_fingerprint."""
    try:
        from .broker_fingerprint import build, untuk_saham, scan_modal, harga_modal
        mode = (request.form.get('mode') or '').strip()
        stock = (request.form.get('stock') or '').strip().upper()
        if mode == 'modal':
            hari = request.form.get('hari', type=int) or None
            return jsonify(scan_modal(hari=hari))
        if stock:
            hasil = untuk_saham(stock)
            if hasil.get('available'):
                hasil['modal'] = harga_modal(stock)
            return jsonify(hasil)
        return jsonify(build(force=request.form.get('force') == '1'))
    except Exception as exc:
        logger.exception('Gagal memuat Sidik Jari Broker')
        return jsonify(available=False, message='Gagal memuat: %s' % exc)


@utilities.route('/rontgen-portofolio-data', methods=['POST'])
@login_required
def rontgenPortofolioData():
    """Data untuk Rontgen Portofolio -- lihat portfolio_xray.build()."""
    try:
        from .portfolio_xray import build
        days_fake = request.form.get('days_fake', type=int) or 20
        return jsonify(build(days_fake=days_fake))
    except Exception as exc:
        logger.exception('Gagal memuat Rontgen Portofolio')
        return jsonify(available=False, message='Gagal memuat: %s' % exc)


@utilities.route('/kepercayaan-data-data', methods=['POST'])
@login_required
def kepercayaanDataData():
    """Data untuk Kepercayaan Data -- lihat data_confidence.scan()."""
    try:
        from .data_confidence import scan
        force = request.form.get('force') == '1'
        return jsonify(scan(force=force))
    except Exception as exc:
        logger.exception('Gagal memuat Kepercayaan Data')
        return jsonify(available=False, message='Gagal memuat: %s' % exc)


@utilities.route('/filter-facts', methods=['POST'])
@login_required
def filterFacts():
    """Fakta penyaring per emiten untuk bar filter bersama -- lihat stock_filter.py."""
    try:
        from .stock_filter import facts
        return jsonify(facts(force=request.form.get('force') == '1'))
    except Exception as exc:
        logger.exception('Gagal memuat fakta penyaring')
        return jsonify(available=False, message='Gagal memuat: %s' % exc)


@utilities.route('/audit-sisi-data', methods=['POST'])
@login_required
def auditSisiData():
    """Audit sisi screener -- lihat screener_side.audit()."""
    try:
        from .screener_side import audit as audit_sisi
        return jsonify(audit_sisi(force=request.form.get('force') == '1'))
    except Exception as exc:
        logger.exception('Gagal memuat Audit Sisi')
        return jsonify(available=False, message='Gagal memuat: %s' % exc)


@utilities.route('/audit-screener-data', methods=['POST'])
@login_required
def auditScreenerData():
    """Data untuk Audit Screener -- lihat signal_recall.audit()."""
    try:
        from .signal_recall import audit
        force = request.form.get('force') == '1'
        return jsonify(audit(force=force))
    except Exception as exc:
        logger.exception('Gagal memuat Audit Screener')
        return jsonify(available=False, message='Gagal memuat: %s' % exc)


# ==========================================================================
# Research -- lihat research.py & rl_trading.py
# ==========================================================================
# Beda dari endpoint lain di file ini: yang ini TIDAK menjalankan
# perhitungannya sendiri. Riset berjalan menit sampai puluhan menit di
# thread latar belakang; endpoint di bawah cuma memulai, mengintip, dan
# menghentikannya. Request-nya sendiri selalu selesai instan.

@utilities.route('/research-eksperimen', methods=['POST'])
@login_required
def researchEksperimen():
    """Daftar eksperimen + field formulirnya. Halaman membangun formulirnya
    dari sini, jadi eksperimen baru cukup didaftarkan di sisi Python."""
    try:
        from . import research as riset
        halaman = request.form.get('halaman') or riset.HALAMAN_BAWAAN
        return jsonify(ok=True, eksperimen=riset.daftar_eksperimen(halaman),
                       run_aktif=riset.run_aktif(halaman),
                       run_lain=riset.run_aktif())
    except Exception as exc:
        logger.exception('Gagal memuat daftar eksperimen')
        return jsonify(ok=False, message='Gagal memuat: %s' % exc)


@utilities.route('/research-mulai', methods=['POST'])
@login_required
def researchMulai():
    try:
        from . import research as riset
        key = request.form.get('key', '')
        config = json.loads(request.form.get('config') or '{}')
        if not isinstance(config, dict):
            return jsonify(ok=False, message='Konfigurasi tidak sah.')
        if config.get('universe') == 'portofolio':
            # Diselesaikan DI SINI, bukan di dalam thread riset: thread itu
            # berjalan di luar app context Flask jadi tidak bisa query DB.
            config['portofolio_kode'] = sorted(
                {p.stock.upper() for p in Position.query.filter_by(userId=current_user.id).all() if p.stock})
        return jsonify(ok=True, run_id=riset.mulai(key, config))
    except RuntimeError as exc:
        return jsonify(ok=False, message=str(exc))
    except Exception as exc:
        logger.exception('Gagal memulai riset')
        return jsonify(ok=False, message='Gagal memulai: %s' % exc)


@utilities.route('/research-status', methods=['POST'])
@login_required
def researchStatus():
    try:
        from . import research as riset
        st = riset.poll(request.form.get('run_id', ''),
                        int(request.form.get('sejak') or 0))
        if st is None:
            return jsonify(ok=False, message='Run tidak ditemukan.')
        return jsonify(ok=True, status=st)
    except Exception as exc:
        logger.exception('Gagal membaca status riset')
        return jsonify(ok=False, message='Gagal membaca status: %s' % exc)


@utilities.route('/research-hentikan', methods=['POST'])
@login_required
def researchHentikan():
    from . import research as riset
    return jsonify(ok=riset.hentikan(request.form.get('run_id', '')))


@utilities.route('/research-riwayat', methods=['POST'])
@login_required
def researchRiwayat():
    try:
        from . import research as riset
        halaman = request.form.get('halaman') or riset.HALAMAN_BAWAAN
        return jsonify(ok=True, riwayat=riset.riwayat(halaman=halaman))
    except Exception as exc:
        logger.exception('Gagal memuat riwayat riset')
        return jsonify(ok=False, message='Gagal memuat riwayat: %s' % exc)


# ==========================================================================
# Market Digital Twin -- lihat website/twin/. Menjalankan, memantau, dan
# menghentikan run memakai endpoint /research-* di atas (kunci 'digital_twin');
# yang di sini hanya bahan formulir dan penerjemah skenario.
# ==========================================================================

@utilities.route('/digital-twin-awal', methods=['POST'])
@login_required
def digitalTwinAwal():
    """Bahan formulir: preset, jenis event, nilai bawaan, daftar saham yang
    punya data, run yang sedang berjalan, dan apakah penerjemah Claude aktif."""
    try:
        from . import research as riset
        from .twin import jalan as twin_jalan, skenario as twin_skenario, kalibrasi as twin_kal
        from .twin import llm as twin_llm
        sektor = twin_kal.peta_sektor()
        kandidat = twin_kal.kandidat()
        for k in kandidat:
            k['sektor'] = sektor.get(k['kode'], '-')
        return jsonify(
            ok=True,
            preset=twin_skenario.daftar_preset(),
            jenis=twin_skenario.JENIS,
            defaults=twin_jalan.DEFAULTS,
            kandidat=kandidat,
            sektor=sorted(set(sektor.values())),
            run_aktif=riset.run_aktif('digital-twin'),
            run_lain=riset.run_aktif(),
            llm=twin_llm.status(),
        )
    except Exception as exc:
        logger.exception('Gagal memuat bahan Digital Twin')
        return jsonify(ok=False, message='Gagal memuat: %s' % exc)


@utilities.route('/digital-twin-terjemah', methods=['POST'])
@login_required
def digitalTwinTerjemah():
    """Teks skenario bebas -> daftar event (lewat Claude). Mati dengan pesan
    jelas kalau ANTHROPIC_API_KEY tidak ada."""
    try:
        from .twin import llm as twin_llm
        teks = (request.form.get('teks') or '').strip()
        kodes = [k for k in (request.form.get('kodes') or '').upper().replace(' ', ',').split(',') if k]
        hari = int(request.form.get('hari') or 60)
        if not teks:
            return jsonify(ok=False, message='Tulis dulu skenarionya.')
        hasil = twin_llm.terjemahkan(teks, kodes, hari)
        return jsonify(ok=True, **hasil)
    except Exception as exc:
        logger.exception('Gagal menerjemahkan skenario')
        return jsonify(ok=False, message='Gagal menerjemahkan: %s' % exc)


@utilities.route('/takaran-risiko-data', methods=['POST'])
@login_required
def takaranRisikoData():
    """Data untuk Takaran Risiko -- lihat risiko.scan()."""
    try:
        from .risiko import scan
        return jsonify(scan(force=request.form.get('force') == '1'))
    except Exception as exc:
        logger.exception('Gagal memuat Takaran Risiko')
        return jsonify(available=False, message='Gagal memuat: %s' % exc)


@utilities.route('/emiten-hilang-data', methods=['POST'])
@login_required
def emitenHilangData():
    """Data untuk Emiten Hilang -- lihat survivorship.scan()."""
    try:
        from .survivorship import scan
        return jsonify(scan(force=request.form.get('force') == '1'))
    except Exception as exc:
        logger.exception('Gagal memuat Emiten Hilang')
        return jsonify(available=False, message='Gagal memuat: %s' % exc)


@utilities.route('/apa-berubah-data', methods=['POST'])
@login_required
def apaBerubahData():
    """
    Data untuk Apa Berubah Hari Ini -- lihat perubahan.selisih().

    Merekam dulu sebelum menyelisihkan (idempoten per hari bursa), jadi
    membuka halaman ini cukup untuk menjaga jurnalnya tetap terisi kalau
    pemeriksaan kesehatan harian kebetulan tidak jalan.
    """
    try:
        from .perubahan import selisih
        return jsonify(selisih())
    except Exception as exc:
        logger.exception('Gagal memuat Apa Berubah')
        return jsonify(available=False, message='Gagal memuat: %s' % exc)


@utilities.route('/kalender-pasar-data', methods=['POST'])
@login_required
def kalenderPasarData():
    from .agenda_pasar import scan
    return jsonify(scan('kalender', request.form.get('force') == '1'))


@utilities.route('/agenda-emiten-data', methods=['POST'])
@login_required
def agendaEmitenData():
    from .agenda_pasar import scan
    return jsonify(scan('emiten', request.form.get('force') == '1'))


@utilities.route('/rotasi-sektor-data', methods=['POST'])
@login_required
def rotasiSektorData():
    try:
        from .rotasi_sektor import scan
        return jsonify(scan(request.form.get('force') == '1'))
    except Exception:
        logger.exception('Gagal membaca Rotasi Sektor')
        return jsonify(available=False, message='Rotasi sektor belum dapat dibaca. Periksa data Summary dan profil sektor.')


@utilities.route('/musiman-saham-data', methods=['POST'])
@login_required
def musiman_saham_data():
    try:
        from .histori_emiten import musiman
        return jsonify(musiman())
    except Exception:
        logger.exception('Gagal membaca Musiman Saham')
        return jsonify(available=False, message='Arsip Musiman Saham belum dapat dibaca.')


@utilities.route('/perubahan-kepemilikan-data', methods=['POST'])
@login_required
def perubahan_kepemilikan_data():
    try:
        from .histori_emiten import perubahan
        return jsonify(perubahan())
    except Exception:
        logger.exception('Gagal membaca Perubahan Kepemilikan')
        return jsonify(available=False, message='Arsip Perubahan Kepemilikan belum dapat dibaca.')
