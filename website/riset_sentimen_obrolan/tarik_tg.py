"""Sampel pesan Telegram per hari bursa: 100 pesan terakhir sebelum 11:30 WIB dan sebelum 16:00 WIB.
Dua grup ditarik bersamaan (lebih dari itu kena flood wait). Bisa dilanjut: hari yang sudah ada dilewati."""
try:
    from ..runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import asyncio, os, shutil, sys, time
import pandas as pd
sys.path.insert(0, str(_PROJECT_DIR))
from website.ramai_dibahas import _kredensial_tg, TG_SESSION
from website.runtime_paths import research_groups
_GROUPS = research_groups(required=True)
TARGET = {row['name']:row['start'] for row in _GROUPS}
ARCHIVES = {row['name']:row['archive'] for row in _GROUPS}

OUT = str(_runtime_file('riset_sentimen_obrolan', 'tg_hist'))
os.makedirs(OUT, exist_ok=True)
SESI = str(_runtime_file('riset_sentimen_obrolan/tg_hist', 'sesi_salinan'))
shutil.copy(TG_SESSION + '.session', SESI + '.session')
JAM = ['11:30', '16:00']
ihsg = pd.read_pickle(str(_runtime_file("", 'research_cache/ihsg_2010-01-01_2026-10-18.pkl')))
KAL = pd.to_datetime(ihsg.index).tz_localize(None).normalize()


async def satu_grup(c, ent, g, mulai):
    f = str(_runtime_file('riset_sentimen_obrolan/tg_hist', ARCHIVES[g] + '.pkl'))
    lama = pd.read_pickle(f) if os.path.exists(f) else pd.DataFrame()
    sudah = set(lama['D']) if len(lama) else set()
    rows, t0 = [], time.time()
    hari = [d for d in KAL if d >= pd.Timestamp(mulai) and d not in sudah][::-1]   # terbaru dulu
    for i, d in enumerate(hari):
        for jam in JAM:
            batas = pd.Timestamp('%s %s' % (d.date(), jam), tz='Asia/Jakarta').tz_convert('UTC').to_pydatetime()
            async for m in c.iter_messages(ent, limit=100, offset_date=batas, wait_time=0):
                if m.message:
                    rows.append((d, jam, m.id, m.date, m.sender_id, m.message))
        if (i + 1) % 50 == 0 or i == len(hari) - 1:
            baru = pd.DataFrame(rows, columns=['D', 'sesi', 'id', 'waktu', 'pengirim', 'teks'])
            lama = pd.concat([lama, baru], ignore_index=True)
            lama.to_pickle(f)
            rows = []
            print(g, i + 1, '/', len(hari), d.date(), '%.0fs' % (time.time() - t0), flush=True)


async def main():
    from telethon import TelegramClient
    api_id, api_hash = _kredensial_tg()
    c = TelegramClient(SESI, int(api_id), api_hash, flood_sleep_threshold=600)
    await c.connect()
    dialog = [d async for d in c.iter_dialogs()]
    tugas = []
    for g, mulai in TARGET.items():
        ent = [d for d in dialog if (d.name or '').strip().lower() == g.lower()][0].entity
        tugas.append(satu_grup(c, ent, g, mulai))
    await asyncio.gather(*tugas)
    print('SELESAI', flush=True)
    await c.disconnect()

asyncio.run(main())
