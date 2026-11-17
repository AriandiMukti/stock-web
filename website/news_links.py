"""Narrow Google News link resolver using bounded HTML/JSON responses.

Google's batchexecute format is undocumented and can change. Failure returns
an unavailable result; it never invents a publisher URL or silently downgrades
to the removed third-party decoder.
"""
import ipaddress
import json
import re
from urllib.parse import urlsplit
import requests

from .html_parser import fetch_html, parse_html, read_response

GOOGLE_ORIGIN = 'https://news.google.com'
RPC_ID = 'Fbv4je'


def publisher_url(value):
    if not isinstance(value, str) or len(value) > 8192 or any(c.isspace() or ord(c) < 32 for c in value):
        raise ValueError('Invalid publisher URL')
    parts = urlsplit(value)
    host = (parts.hostname or '').rstrip('.')
    if parts.scheme not in {'http', 'https'} or not host or parts.username or parts.password:
        raise ValueError('Invalid publisher URL')
    if parts.port not in {None, 80, 443} or host == 'localhost' or host.endswith(('.localhost', '.local', '.internal')):
        raise ValueError('Invalid publisher address')
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if '.' not in host:
            raise ValueError('Invalid publisher address') from None
    else:
        if not address.is_global:
            raise ValueError('Invalid publisher address')
    return value


def _article_id(value):
    if not isinstance(value, str) or len(value) > 8192:
        raise ValueError('Invalid Google News URL')
    parts = urlsplit(value)
    if parts.scheme != 'https' or parts.hostname != 'news.google.com' or parts.username or parts.password or parts.port not in {None, 443}:
        raise ValueError('Invalid Google News URL')
    match = re.fullmatch(r'/(?:rss/)?(?:articles|read)/([A-Za-z0-9_-]{1,2048}={0,2})', parts.path)
    if not match:
        raise ValueError('Invalid Google News article path')
    return match.group(1)


def _rpc_result(body):
    text = body.decode('utf-8')
    # Google frames JSON on individual lines, sometimes preceded by lengths.
    for line in text.splitlines():
        if not line.lstrip().startswith('['):
            continue
        try:
            rows = json.loads(line)
        except (ValueError, RecursionError):
            continue
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, list) or len(row) < 3 or row[:2] != ['wrb.fr', RPC_ID] or not isinstance(row[2], str):
                continue
            payload = json.loads(row[2])
            if isinstance(payload, list) and len(payload) > 1 and payload[0] == 'garturlres':
                return publisher_url(payload[1])
    raise ValueError('Publisher URL is unavailable in the decoder response')


def decode_google_news(value, interval=None):
    """Compatibility result: {'status': bool, 'decoded_url': ...} on success.

    The legacy interval argument is accepted for callers; requests have timeouts
    and response budgets rather than an extra sleep after each request.
    """
    try:
        article = _article_id(value)
        document = parse_html(fetch_html(GOOGLE_ORIGIN + '/articles/' + article))
        element = document.css_first('c-wiz > div[jscontroller]')
        if element is None:
            raise ValueError('Google News decoder metadata is unavailable')
        signature = element.attributes.get('data-n-a-sg')
        timestamp = element.attributes.get('data-n-a-ts')
        if not signature or len(signature) > 512 or not timestamp or not re.fullmatch(r'[0-9]{1,20}', timestamp):
            raise ValueError('Google News decoder metadata is invalid')
        context = [['X', 'X', ['X', 'X'], None, None, 1, 1, 'US:en', None, 1,
                    None, None, None, None, None, 0, 1], 'X', 'X', 1, [1, 1, 1],
                   1, 1, None, 0, 0, None, 0]
        payload = ['garturlreq', context, article, int(timestamp), signature]
        frame = [[RPC_ID, json.dumps(payload, separators=(',', ':')), None, 'generic']]
        response = requests.post(
            GOOGLE_ORIGIN + '/_/DotsSplashUi/data/batchexecute',
            data={'f.req': json.dumps([frame], separators=(',', ':'))},
            timeout=(4, 12), allow_redirects=False, stream=True,
        )
        try:
            if 300 <= response.status_code < 400:
                raise ValueError('Google News decoder redirected')
            resolved = _rpc_result(read_response(response))
        finally:
            response.close()
        return {'status': True, 'decoded_url': resolved}
    except (ValueError, TypeError, UnicodeError, RecursionError, requests.RequestException):
        return {'status': False, 'message': 'Publisher URL is unavailable'}
