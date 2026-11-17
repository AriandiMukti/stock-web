"""Bounded HTML parsing with the maintained Lexbor backend; no Soup Sieve."""
from html.parser import HTMLParser
import time
import requests
from selectolax.lexbor import LexborHTMLParser

MAX_HTML_BYTES = 2 * 1024 * 1024
MAX_ELEMENTS = 50000
MAX_DEPTH = 64
VOID_ELEMENTS = frozenset('area base br col embed hr img input link meta param source track wbr'.split())


class _DocumentBudget(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.stack = []
        self.elements = 0

    def _element(self):
        self.elements += 1
        if self.elements > MAX_ELEMENTS:
            raise ValueError('HTML document has too many elements')

    def handle_starttag(self, tag, attrs):
        self._element()
        if tag not in VOID_ELEMENTS:
            self.stack.append(tag)
            if len(self.stack) > MAX_DEPTH:
                raise ValueError('HTML document nesting exceeds the limit')

    def handle_startendtag(self, tag, attrs):
        self._element()

    def handle_endtag(self, tag):
        if tag in self.stack:
            position = len(self.stack) - 1 - self.stack[::-1].index(tag)
            del self.stack[position:]


def parse_html(content):
    if not isinstance(content, (str, bytes)):
        raise TypeError('HTML input must be text or bytes')
    raw = content.encode('utf-8') if isinstance(content, str) else content
    if len(raw) > MAX_HTML_BYTES:
        raise ValueError('HTML document exceeds the size limit')
    budget = _DocumentBudget()
    budget.feed(raw.decode('utf-8', errors='replace'))
    budget.close()
    return LexborHTMLParser(content)


def read_response(response, limit=MAX_HTML_BYTES):
    """Read a streamed response without retaining an unbounded body."""
    response.raise_for_status()
    declared = response.headers.get('Content-Length')
    if declared:
        try:
            if not 0 <= int(declared) <= limit:
                raise ValueError('Response exceeds the size limit')
        except ValueError:
            raise ValueError('Invalid or excessive response size') from None
    chunks = []
    total = 0
    started = time.monotonic()
    for chunk in response.iter_content(chunk_size=8192):
        if not chunk:
            continue
        total += len(chunk)
        if total > limit or time.monotonic() - started > 30:
            raise ValueError('Response exceeds the size or elapsed-time limit')
        chunks.append(chunk)
    return b''.join(chunks)


def fetch_html(url, **kwargs):
    """HTML GET with bounded storage and no automatic cross-host redirects."""
    kwargs.setdefault('timeout', (4, 12))
    kwargs['allow_redirects'] = False
    kwargs['stream'] = True
    response = requests.get(url, **kwargs)
    try:
        if 300 <= response.status_code < 400:
            raise ValueError('HTML endpoint redirected; review its URL before following')
        return read_response(response)
    finally:
        response.close()
