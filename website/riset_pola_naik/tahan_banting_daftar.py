import os, pickle, pandas as pd, numpy as np, warnings; warnings.filterwarnings('ignore')
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'tahan_banting.py')).read().split("hasil = {}")[0])   # muat C, V, ihsg, eps
eps_d = {e[0]: e for e in eps}
p, tr = pd.Timestamp('2026-09-08'), pd.Timestamp('2026-10-19')
d15, d16, d19, d20 = [pd.Timestamp(x) for x in ['2026-10-15','2026-10-16','2026-10-19','2026-10-20']]
a0, a1 = eps_d['2026a'][1], eps_d['2026a'][2]
liq = V.loc[:p].tail(60).median()
w = C.loc[:p].tail(260).resample('W-FRI').last().pct_change()
wi = ihsg.loc[:p].tail(260).resample('W-FRI').last().pct_change()
beta = w.apply(lambda s: s.cov(wi)/wi.var() if s.notna().sum()>=40 else np.nan)
# berapa hari IHSG turun >=1% (sejak 2026-01) saham ini ikut tidak turun
ri = ihsg.pct_change(); rs = C.pct_change()
hari = ri['2026-01-20':'2026-10-19']; hari = hari[hari <= -0.01].index
tahan_hari = (rs.loc[hari] >= 0).sum() / rs.loc[hari].notna().sum()
df = pd.DataFrame({
  'nilai_M': liq/1e9, 'beta': beta,
  'sep8_okt19': C.loc[tr]/C.loc[p]-1,
  'crash_15_19': C.loc[d19]/C.loc[d15]-1,
  'okt20': C.loc[d20]/C.loc[d19]-1,
  'jan_jun': C.loc[a1]/C.loc[a0]-1,
  'jan20_skrg': C.loc[d20]/C.loc[a0]-1,
  'hari_merah_tahan': tahan_hari,
}).dropna(subset=['sep8_okt19','crash_15_19'])
df = df[(df.nilai_M >= 5)]
print('IHSG: sep8->okt19 %+.1f%%, 15->19 okt %+.1f%%, 20 okt %+.1f%%, jan20->skrg %+.1f%%' % (
  (ihsg[tr]/ihsg[p]-1)*100, (ihsg[d19]/ihsg[d15]-1)*100, (ihsg[d20]/ihsg[d19]-1)*100, (ihsg[d20]/ihsg[a0]-1)*100))
print('saham likuid (>=Rp5M/hari):', len(df), ' naik/rata sep8->okt19:', (df.sep8_okt19>=0).sum(), ' naik/rata 15->19 okt:', (df.crash_15_19>=0).sum())
pd.set_option('display.width', 250); pd.set_option('display.max_rows', 200)
f = lambda x: x.round(3)
print('\n--- tahan/naik sep8->okt19, urut ---')
print(f(df.sort_values('sep8_okt19', ascending=False).head(40)))
print('\n--- konsisten: tahan di DUA kaki 2026 (jan-jun >= -15% dan sep-okt >= -10%) ---')
k = df[(df.jan_jun >= -0.15) & (df.sep8_okt19 >= -0.10)].sort_values('jan20_skrg', ascending=False)
print(f(k))
df.to_csv(os.path.join(OUT,'tahan_banting_daftar.csv'))
