"""Rotasi sektor dari Summary lokal; median saham, bukan indeks sektoral resmi."""
try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib
import json
import threading
import numpy as np
import pandas as pd
from .config import DAILY_PATH, OWNERSHIP_PATH

SUMMARY = Path(DAILY_PATH) / 'Summary'
PROFILES = Path(OWNERSHIP_PATH) / 'idx'
CACHE = _runtime_file('', 'rotasi_sektor_cache.json')
LOCK = threading.Lock()
METHOD = ('Kinerja = median return saham dengan bobot setara, bukan indeks sektor resmi. '
          'Relatif = return 5 hari sektor dikurangi median seluruh saham yang dianalisis. '
          'Momentum = return 5 hari terakhir dikurangi 5 hari sebelumnya (poin persentase). '
          'Aktivitas = rata-rata estimasi nilai transaksi 5 hari / 20 hari sebelumnya. '
          'Estimasi nilai transaksi = Close × Volume, bukan arus dana bersih. '
          'Porsi = bagian estimasi transaksi sektor selama 5 hari terakhir; perubahan porsi dibanding 5 hari sebelumnya. '
          'Harga mengikuti Summary lokal; aksi korporasi atau kesalahan data dapat memengaruhi hasil. '
          'Klasifikasi sektor memakai profil terakhir yang tersedia.')


def calculate(close, volume, sectors):
    close = close.sort_index().replace([np.inf,-np.inf],np.nan)
    volume = volume.reindex(index=close.index,columns=close.columns).replace([np.inf,-np.inf],np.nan)
    if len(close)<26:
        return {'available':False,'message':'Perlu minimal 26 hari bursa Summary untuk membaca rotasi sektor.'}
    c=close.tail(26); v=volume.tail(26)
    good=(c.gt(0).all() & v.ge(0).all() & v.gt(0).sum().ge(24))
    mapped=pd.Series({k:sectors.get(k,'') for k in c.columns}).fillna('').astype(str).str.strip()
    good &= mapped.ne('')
    tickers=list(good[good].index)
    if not tickers:
        return {'available':False,'message':'Tidak ada saham dengan sektor dan 26 sesi lengkap (aktif minimal 24 sesi).'}
    c=c[tickers]; v=v[tickers]; value=c*v
    f=pd.DataFrame({'sektor':mapped[tickers]})
    for n in (1,5,20): f['r'+str(n)]=(c.iloc[-1]/c.iloc[-n-1]-1)*100
    f['prev5']=(c.iloc[-6]/c.iloc[-11]-1)*100
    f['nilai5']=value.tail(5).mean();f['nilai_sebelum5']=value.iloc[-10:-5].mean()
    f['nilai20']=value.iloc[:-5].tail(20).mean()
    total=float(f.nilai5.sum()); oldtotal=float(f.nilai_sebelum5.sum()); market=float(f.r5.median())
    rows=[]
    for sector,g in f.groupby('sektor'):
        returns={k:float(g[k].median()) for k in ('r1','r5','r20')}
        relative=returns['r5']-market; momentum=returns['r5']-float(g.prev5.median())
        phase=('Menguat' if momentum>=0 else 'Melambat') if relative>=0 else ('Memulih' if momentum>=0 else 'Tertinggal')
        val=float(g.nilai5.sum()); previous=float(g.nilai20.sum())
        share=100*val/total if total else 0
        oldshare=100*float(g.nilai_sebelum5.sum())/oldtotal if oldtotal else 0
        stocks=[{'ticker':t,'r5':float(x.r5),'nilai5':float(x.nilai5)} for t,x in g.sort_values('r5',ascending=False).iterrows()]
        rows.append(dict(sektor=sector,n=len(g),**returns,relatif=relative,momentum=momentum,fase=phase,
                         naik=int(g.r5.gt(0).sum()),turun=int(g.r5.lt(0).sum()),tetap=int(g.r5.eq(0).sum()),
                         breadth=float(g.r5.gt(0).mean()*100),nilai5=val,aktivitas=val/previous if previous>0 else None,
                         porsi=share,perubahan_porsi=share-oldshare,saham=stocks))
    rows.sort(key=lambda x:x['r5'],reverse=True)
    for i,row in enumerate(rows): row['peringkat']=i+1
    return dict(available=True,as_of=close.index[-1].strftime('%Y-%m-%d'),rows=rows,market5=market,
                n_saham=len(tickers),n_dibaca=len(close.columns),n_dikeluarkan=len(close.columns)-len(tickers),
                n_tanpa_sektor=int(mapped.eq('').sum()),metode=METHOD,
                message='Urutan berdasarkan median return 5 hari. Status menggambarkan gerakan historis, bukan sinyal beli.',
                periode={'awal5':close.index[-6].strftime('%Y-%m-%d'),'awal20':close.index[-21].strftime('%Y-%m-%d')})


def scan(force=False):
    with LOCK:
        files=sorted(SUMMARY.glob('*_Summary.csv')); profiles=sorted(PROFILES.glob('*/*.json'))
        signature=hashlib.sha256()
        for p in files+profiles:
            stat=p.stat();signature.update(f'{p}:{stat.st_mtime_ns}:{stat.st_size}'.encode())
        key='v1:'+signature.hexdigest()
        if not force:
            try:
                cached=json.loads(CACHE.read_text(encoding='utf-8'))
                if cached.get('signature')==key:return cached
            except (OSError,ValueError):pass
        sectors={}
        # Sort by modification time so latest valid profile wins across snapshots.
        for p in sorted(profiles,key=lambda p:p.stat().st_mtime_ns):
            try:
                j=json.loads(p.read_text(encoding='utf-8'))
                if j.get('ticker') and j.get('sector'):sectors[j['ticker']]=j['sector']
            except (ValueError,OSError):continue
        closes={}; volumes={}; failed=0
        today=pd.Timestamp(datetime.now(ZoneInfo('Asia/Jakarta')).date())
        for p in files:
            try:
                d=pd.read_csv(p,usecols=['Date','Close','Volume'])
                d['Date']=pd.to_datetime(d['Date'],format='%d-%b-%y',errors='coerce')
                d=d.dropna(subset=['Date']).drop_duplicates('Date',keep='last').set_index('Date').sort_index()
                d=d.loc[d.index<=today].tail(60)
                if d.empty:continue
                ticker=p.name.removesuffix('_Summary.csv')
                closes[ticker]=pd.to_numeric(d.Close,errors='coerce');volumes[ticker]=pd.to_numeric(d.Volume,errors='coerce')
            except (OSError,ValueError):failed+=1
        result=calculate(pd.DataFrame(closes),pd.DataFrame(volumes),sectors)
        result.update(signature=key,diperiksa=datetime.now(ZoneInfo('Asia/Jakarta')).isoformat(),n_file_gagal=failed)
        if result.get('available'):
            result['umur_hari']=(today-pd.Timestamp(result['as_of'])).days
            if result['umur_hari']>3:result['message']+=' Data harga lebih dari 3 hari kalender; perbarui Summary.'
        try:
            temp=CACHE.with_suffix('.tmp');temp.write_text(json.dumps(result,ensure_ascii=False,allow_nan=False),encoding='utf-8');temp.replace(CACHE)
        except OSError:pass
        return result
