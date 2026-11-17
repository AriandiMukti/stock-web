"""Kalender otomatis dan agenda KSEI. Tanggal tanpa jam tetap tanggal, bukan tengah malam."""
try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from urllib.parse import urljoin
import calendar
import io
import json
import re
import threading
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
try:
    from .html_parser import parse_html, fetch_html
except ImportError:
    from website.html_parser import parse_html, fetch_html

WIB = ZoneInfo('Asia/Jakarta')
ET = ZoneInfo('America/New_York')
ROOT = Path(__file__).parent
LOCK = threading.Lock()
FED = 'https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm'
BEA = 'https://www.bea.gov/news/schedule'
FF = 'https://nfs.faireconomy.media/ff_calendar_thisweek.json'
KSEI = 'https://web.ksei.co.id'
MONTHS = {v.lower(): i for i,v in enumerate(calendar.month_name) if v}
MONTHS.update(dict(zip('januari februari maret april mei juni juli agustus september oktober november desember'.split(),range(1,13))))

def get(url):
    session = requests.Session()
    session.mount('https://', HTTPAdapter(max_retries=Retry(total=2, backoff_factor=.5, status_forcelist=[429,500,502,503,504])))
    r = session.get(url, timeout=(5,20))
    r.raise_for_status()
    return r

def tanggal(s):
    m = re.search(r'(\d{1,2})\s+([A-Za-z]+)\s+(20\d{2})',s)
    if not m or m[2].lower() not in MONTHS: return None
    return datetime(int(m[3]),MONTHS[m[2].lower()],int(m[1])).date().isoformat()

def event(title, date, source, url, **extra):
    return dict(judul=title,tanggal=date,sumber=source,url=url,**extra)

def fed():
    soup=parse_html(fetch_html(FED)); rows=[]
    for panel in soup.css('.panel'):
        head=panel.css_first('.panel-heading')
        year=re.search(r'(20\d{2}) FOMC',head.text() if head else '')
        if not year: continue
        for row in panel.css('.fomc-meeting'):
            month=row.css_first('.fomc-meeting__month').text(strip=True).split('/')[-1]
            monthnum=MONTHS.get(month.lower()) or next((v for k,v in MONTHS.items() if k.startswith(month.lower())),None)
            day=re.findall(r'\d+',row.css_first('.fomc-meeting__date').text())
            if not monthnum or not day: continue
            date=datetime(int(year[1]),monthnum,int(day[-1])).date().isoformat()
            rows.append(event('Akhir rapat FOMC',date,'Federal Reserve',FED,kategori='The Fed',catatan='Tanggal rapat AS; jam pengumuman belum tersedia dari kalender ini.'))
    if not rows: raise ValueError('Format kalender Fed berubah')
    return rows

def bea():
    soup=parse_html(fetch_html(BEA)); rows=[]
    for table in soup.css('table'):
        heading=table.css_first('thead')
        match=re.search(r'20\d{2}',heading.text() if heading else '')
        if not match: raise ValueError('Tahun BEA tidak terbaca')
        year=int(match[0])
        for tr in table.css('tbody tr'):
            title=tr.css_first('.release-title'); date=tr.css_first('.release-date'); hour=tr.css_first('small')
            if not title or not date or not hour: continue
            title=title.text(separator=' ',strip=True)
            if not ('Personal Income and Outlays' in title or title.startswith('GDP (')): continue
            dt=datetime.strptime(f'{year} {date.text(strip=True)} {hour.text(strip=True)}','%Y %B %d %I:%M %p').replace(tzinfo=ET).astimezone(WIB)
            rows.append(event(title,dt.date().isoformat(),'BEA',BEA,waktu=dt.isoformat(),kategori='PCE / GDP'))
    if not rows: raise ValueError('Format jadwal BEA berubah')
    return rows

def macro():
    rows=[]
    for x in get(FF).json():
        if x.get('country')!='USD' or x.get('impact') not in ('High','Medium'): continue
        dt=datetime.fromisoformat(x['date']).astimezone(WIB)
        rows.append(event(x['title'],dt.date().isoformat(),'Forex Factory / Fair Economy',FF,waktu=dt.isoformat(),kategori='Ekonomi AS',konsensus=x.get('forecast'),sebelumnya=x.get('previous'),aktual=None))
    if not rows: raise ValueError('Kalender mingguan kosong')
    return rows

def pdf_events(row):
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(get(row['url']).content)) as pdf:
            text='\n'.join(p.extract_text() or '' for p in pdf.pages[:3])
        out=[]
        for line in text.splitlines():
            date=tanggal(line)
            if not date: continue
            label=re.sub(r'^\d+\.\s*','',line[:re.search(r'\d{1,2}\s+[A-Za-z]+\s+20\d{2}',line).start()]).strip()
            if not re.search(r'cum |ex |recording|pencatatan|pembayaran|pelaksanaan.*rapat|tanggal.*rups',label,re.I): continue
            out.append(dict(row,judul=label,tanggal=date,catatan='Jadwal dalam dokumen KSEI; periksa perubahan atau pembatalan.',jenis_tanggal='Pelaksanaan'))
        return out or [dict(row,catatan='Tanggal pengumuman; tanggal pelaksanaan belum terbaca.',jenis_tanggal='Pengumuman')]
    except Exception:
        return [dict(row,catatan='Dokumen belum terbaca; ini tanggal pengumuman, bukan pelaksanaan.',jenis_tanggal='Pengumuman')]

def ksei(slug,label):
    url=KSEI+'/publications/corporate-action-schedules/'+slug
    soup=parse_html(fetch_html(url)); rows=[]
    for tr in soup.css('tbody tr'):
        cells=tr.css('td'); a=tr.css_first('a[href]')
        if len(cells)<3 or not a: continue
        title=cells[1].text(separator=' ',strip=True); code=re.search(r'\(([A-Z]{4})\)',title)
        date=tanggal(cells[2].text())
        if not date: continue
        ticker=code[1] if code and code[1] not in ('RUPS','RUPO','RUPU','HMET') else ''
        rows.append(event(title,date,'KSEI',urljoin(KSEI,a.attributes['href']),ticker=ticker,kategori=label))
    if not soup.css('table'): raise ValueError('Tabel KSEI tidak terbaca')
    with ThreadPoolExecutor(max_workers=5) as pool:
        return [e for batch in pool.map(pdf_events, rows[:20]) for e in batch]

def scan(kind,force=False):
    sources={'Federal Reserve':fed,'BEA':bea,'Kalender AS mingguan':macro} if kind=='kalender' else {
        'Dividen':lambda:ksei('cash-dividend','Dividen'),
        'RUPS':lambda:ksei('rups-rupo','RUPS'),
        'HMETD':lambda:ksei('rights-distribution','HMETD'),
        'Aksi lainnya':lambda:ksei('masr','Merger / Split')}
    with LOCK:
        path=_runtime_file('', 'agenda_' + kind + '_cache.json'); now=datetime.now(WIB)
        try: old=json.loads(path.read_text(encoding='utf-8'))
        except (OSError,ValueError): old={}
        if not force and old.get('diperiksa') and (now-datetime.fromisoformat(old['diperiksa'])).total_seconds()<3600:
            return old
        data={}; status=[]
        with ThreadPoolExecutor(max_workers=4) as pool:
            jobs={k:pool.submit(fn) for k,fn in sources.items()}
            for name,job in jobs.items():
                try:
                    data[name]=job.result(); status.append(dict(nama=name,ok=True))
                except Exception:
                    data[name]=[dict(x,stale=True) for x in old.get('per_sumber',{}).get(name,[])]
                    status.append(dict(nama=name,ok=False))
        start=(now-timedelta(days=7)).date().isoformat(); end=(now+timedelta(days=120)).date().isoformat()
        unique={}
        for rows in data.values():
            for x in rows:
                if start<=x['tanggal']<=end:
                    key=(x.get('ticker',''),x['judul'],x['tanggal'])
                    unique[key]=x
        rows=sorted(unique.values(),key=lambda x:(x['tanggal'],x.get('waktu',''),x.get('ticker','')))
        result=dict(available=bool(rows),items=rows,per_sumber=data,sources=status,diperiksa=now.isoformat(),stale=any(not x['ok'] for x in status),
                    message='Jadwal 7 hari terakhir hingga 120 hari ke depan. Kalender AS tambahan hanya minggu berjalan.' if kind=='kalender' else 'Maksimal 20 pengumuman terbaru per jenis dari KSEI. Tanggal pengumuman dipisahkan dari pelaksanaan; cakupan belum seluruh emiten.')
        try:
            temp=path.with_suffix('.tmp'); temp.write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8'); temp.replace(path)
        except OSError:
            result['message'] += ' Cache tidak dapat disimpan; data tetap tersedia untuk sesi ini.'
        return result
