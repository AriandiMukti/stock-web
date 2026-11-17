"""Berita makro global: RSS, cache 15 menit, snapshot untuk Sync HP."""
try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlencode, urlparse
import json
import re
from difflib import SequenceMatcher
from html import unescape
import threading
import xml.etree.ElementTree as ET
import requests
try:
    from .html_parser import parse_html, fetch_html
except ImportError:
    from website.html_parser import parse_html, fetch_html

CACHE = _runtime_file('', 'berita_global_cache.json')
LOCK = threading.Lock()
TTL = 900
TOPIK = {
    'The Fed': 'Federal Reserve FOMC interest rates',
    'NFP / Tenaga Kerja AS': 'US nonfarm payrolls jobs report unemployment',
    'Inflasi AS': 'US inflation CPI PCE',
    'MSCI': 'MSCI index review rebalance Indonesia emerging markets',
    'Risiko Global': 'global stocks tariffs geopolitical oil central banks',
}

def _ambil(topik, query):
    url = 'https://news.google.com/rss/search?' + urlencode({
        'q': query + ' when:7d', 'hl': 'en-US', 'gl': 'US', 'ceid': 'US:en'})
    response = requests.get(url, timeout=(4, 12), headers={'User-Agent': 'BDM-MarketNews/1.0'})
    response.raise_for_status()
    root = ET.fromstring(response.content)
    now = datetime.now(timezone.utc)
    hasil = []
    for item in root.findall('./channel/item'):
        title, link = item.findtext('title', '').strip(), item.findtext('link', '').strip()
        try:
            date = parsedate_to_datetime(item.findtext('pubDate', '')).astimezone(timezone.utc)
        except (ValueError, TypeError, OverflowError):
            continue
        if not title or urlparse(link).scheme != 'https' or not now - timedelta(days=7) <= date <= now:
            continue
        hasil.append({'judul': title, 'url': link, 'sumber': item.findtext('source', 'Google News'),
                      'kategori': topik, 'terbit': date.isoformat()})
    return sorted(hasil, key=lambda x: x['terbit'], reverse=True)[:6]

POLA = {
    'The Fed': r'\bfed\b|fomc|federal reserve|bank sentral as',
    'NFP / Tenaga Kerja AS': r'nonfarm|non-farm|payroll|tenaga kerja as|pengangguran as',
    'Inflasi AS': r'inflasi (as|amerika)|\bcpi\b|\bpce\b',
    'MSCI': r'\bmsci\b',
    'Risiko Global': r'wall street|tarif.*(as|trump)|minyak dunia|saham global|bursa global',
}
KONTEKS = {
    'The Fed': 'Perhatikan keputusan suku bunga dan panduan kebijakan berikutnya; keduanya relevan bagi dolar, yield obligasi, dan arus modal.',
    'NFP / Tenaga Kerja AS': 'Bandingkan penambahan pekerjaan, pengangguran, dan upah dengan konsensus serta revisi bulan sebelumnya.',
    'Inflasi AS': 'Perhatikan inflasi inti dan perubahan bulanan, bukan hanya angka tahunan.',
    'MSCI': 'Perhatikan saham yang masuk atau keluar indeks serta tanggal efektif perubahan bobot.',
    'Risiko Global': 'Perhatikan perkembangan lanjutan dan reaksi harga aset; dampaknya dapat berbeda antar sektor.',
}

def _kalimat(text):
    text = re.sub(r'\s+', ' ', text).strip()
    return [x.strip() for x in re.split(r'(?<=[.!?])\s+(?=[A-Z0-9“])', text)
            if 45 <= len(x.strip()) <= 650 and not re.search(r'baca juga|copyright|pewarta:|editor:', x, re.I)]

def _ekstrak(row):
    """Ambil kalimat artikel penerbit; hanya URL ANTARA yang telah diverifikasi."""
    try:
        if urlparse(row['url']).hostname not in ('www.antaranews.com','antaranews.com'): return row
        soup=parse_html(fetch_html(row['url'])); body=soup.css_first('.post-content')
        if not body: return row
        published=soup.css_first('meta[property="article:published_time"]')
        if published:
            try:
                date=datetime.fromisoformat(published.attributes['content']).astimezone(timezone.utc)
                if not datetime.now(timezone.utc)-timedelta(days=7)<=date<=datetime.now(timezone.utc): return {}
                row=dict(row,terbit=date.isoformat())
            except (ValueError,KeyError): return {}
        if not row.get('terbit'): return {}
        # Remove children before selected ancestors; native DOM nodes must not
        # be accessed after an ancestor has been freed.
        for node in reversed(body.css('script,style,aside,.baca-juga')): node.decompose()
        paragraphs=[p.text(separator=' ',strip=True) for p in body.css('p')]
        text=' '.join(paragraphs) if paragraphs else body.text(separator=' ',strip=True)
        all_sentences=_kalimat(text)
        sentences=[]
        for i,sentence in enumerate(all_sentences):
            if not re.search(POLA[row['kategori']],sentence,re.I): continue
            if i and re.match(r'(Beberapa|Hal (ini|tersebut)|Ini|Itu|Sementara itu|Selain itu|Ia |Dia |Menurutnya)',sentence):
                sentence=all_sentences[i-1]+' '+sentence
            sentences.append(sentence)
        # Pilih lead dan fakta paling relevan; pertahankan urutan sumber.
        scored=sorted(enumerate(sentences),key=lambda pair: (3 if pair[0]==0 else 0)+len(re.findall(POLA[row['kategori']],pair[1],re.I))*2+bool(re.search(r'\d',pair[1])),reverse=True)
        chosen=[]
        for i,sentence in scored:
            if any(SequenceMatcher(None,sentence.lower(),v.lower()).ratio()>.65 for _,v in chosen): continue
            if sum(len(v.split()) for _,v in chosen)+len(sentence.split())>95: continue
            chosen.append((i,sentence))
            if len(chosen)==3: break
        if chosen:
            row=dict(row,isi=' '.join(v for _,v in sorted(chosen)),metode='Petikan kalimat penting artikel')
    except (requests.RequestException,ValueError):
        pass
    return row

def _feed_penerbit(kanal):
    url='https://www.antaranews.com/rss/'+kanal+'.xml'
    response=requests.get(url,timeout=(4,12)); response.raise_for_status()
    root=ET.fromstring(response.content); rows=[]; now=datetime.now(timezone.utc)
    for x in root.findall('./channel/item'):
        title=x.findtext('title',''); category=next((k for k,v in POLA.items() if re.search(v,title,re.I)),None)
        if not category: continue
        try: date=parsedate_to_datetime(x.findtext('pubDate','')).astimezone(timezone.utc)
        except (ValueError,TypeError): continue
        if not now-timedelta(days=7)<=date<=now: continue
        rows.append(dict(judul=title,url=x.findtext('link',''),sumber='ANTARA',kategori=category,terbit=date.isoformat()))
    return rows

def _cari_penerbit(pair):
    category,query=pair
    soup=parse_html(fetch_html('https://www.antaranews.com/search',params={'q':query}))
    return [dict(judul=a.text(separator=' ',strip=True),url=a.attributes['href'],sumber='ANTARA',kategori=category,terbit=None)
            for a in soup.css('.card__post__title h2 a[href]')[:3]]

def _penerbit():
    rows=[]
    with ThreadPoolExecutor(max_workers=3) as pool:
        for part in pool.map(_feed_penerbit,['ekonomi-bursa','ekonomi-finansial','dunia']):
            rows.extend(part)
    with ThreadPoolExecutor(max_workers=5) as pool:
        for part in pool.map(_cari_penerbit, zip(TOPIK, ['the fed','nonfarm payroll','inflasi AS','MSCI','wall street'])):
            rows.extend(part)
    unique={(x['url'],x['kategori']):x for x in rows}
    with ThreadPoolExecutor(max_workers=5) as pool:
        return [x for x in pool.map(_ekstrak,list(unique.values())[:25]) if x.get('terbit') and x.get('isi')]

def _rangkuman(items):
    """Satu kartu per tema; rangkum poin judul, tanpa mengarang isi artikel."""
    groups = {}
    seen = []
    for item in sorted(items, key=lambda x: (bool(x.get('isi')),x['terbit']), reverse=True):
        title = item['judul'].rsplit(' - ', 1)[0].strip()
        normalized = re.sub(r'[^\w ]', '', title.lower())
        if any(SequenceMatcher(None, normalized, old).ratio() > .72 for old in seen):
            continue
        seen.append(normalized)
        text = title.lower()
        theme = item['kategori']
        for label, pattern in [('The Fed', r'\bfed\b|fomc|federal reserve'),
                               ('NFP / Tenaga Kerja AS', r'nonfarm|non-farm|payroll|jobs report'),
                               ('Inflasi AS', r'\bcpi\b|\bpce\b|us inflation'),
                               ('MSCI', r'\bmsci\b')]:
            if re.search(pattern, text):
                theme = label
                break
        groups.setdefault(theme, []).append(dict(item, judul=title))
    result = []
    for theme, rows in groups.items():
        rows.sort(key=lambda x: (bool(x.get('isi')), x['terbit']), reverse=True)
        first = dict(rows[0])
        first.update(kategori=theme, judul=theme,
                     ringkasan=first.get('isi') or first['judul'],
                     konteks=KONTEKS.get(theme,''),
                     jumlah_liputan=len(rows),
                     sumber=first['sumber'],
                     dasar_ringkasan=first.get('metode') or 'Isi artikel belum tersedia; hanya judul sumber',
                     kedaluwarsa=any(x.get('kedaluwarsa') for x in rows[:3]))
        result.append(first)
    return result


def berita(force=False):
    with LOCK:
        now = datetime.now(timezone.utc)
        try:
            old = json.loads(CACHE.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            old = {}
        if not force and old.get('format') == 3 and old.get('diperbarui') and (now - datetime.fromisoformat(old['diperbarui'])).total_seconds() < TTL and not old.get('gagal'):
            return old
        items, gagal = [], []
        try:
            items.extend(_penerbit())
        except Exception:
            gagal.append('ANTARA')
            items.extend(dict(x,kedaluwarsa=True) for x in old.get('raw_items',[]) if x.get('sumber')=='ANTARA')
        with ThreadPoolExecutor(max_workers=5) as pool:
            jobs = {k: pool.submit(_ambil, k, q) for k, q in TOPIK.items()}
            for k, job in jobs.items():
                try:
                    items.extend(job.result())
                except Exception:
                    gagal.append(k)
                    items.extend(dict(x, kedaluwarsa=True) for x in old.get('raw_items', []) if x['kategori'] == k)
        seen, unique = set(), []
        for item in sorted(items, key=lambda x: (bool(x.get('isi')),x['terbit']), reverse=True):
            if item['url'] not in seen:
                seen.add(item['url'])
                unique.append(item)
        result = {'format': 3, 'available': bool(unique), 'items': _rangkuman(unique), 'raw_items': unique, 'gagal': gagal,
                  'diperiksa': now.isoformat(),
                  'diperbarui': old.get('diperbarui') if len(gagal) == len(TOPIK) + 1 else now.isoformat(),
                  'stale': bool(gagal), 'interval_detik': TTL,
                  'message': 'Sebagian sumber gagal diakses; berita bertanda data lama belum diperbarui.' if gagal else
                             'Kalimat penting dari artikel yang tersedia; satu kartu per tema. Konteks pemantauan adalah informasi umum, bukan prediksi.'}
        try:
            temp = CACHE.with_suffix('.tmp')
            temp.write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
            temp.replace(CACHE)
        except OSError:
            pass
        return result
