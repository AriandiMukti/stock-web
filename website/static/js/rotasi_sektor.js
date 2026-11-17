/* Shared presentation for web and offline Android; all source text is escaped. */
function rotasiEsc(x) { return String(x == null ? '' : x).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];}); }
function rotasiNum(x,d) {return x==null||!isFinite(x)?'—':Number(x).toLocaleString('id-ID',{maximumFractionDigits:d==null?2:d});}
function rotasiChange(x) {return '<span style="color:'+(x>0?'#16E0AE':x<0?'#FF6076':'#B3C0D1')+'">'+(x>0?'+':'')+rotasiNum(x)+'%</span>';}
function rotasiHtml(d,sort) {
 if(!d||!d.available)return '<p>'+rotasiEsc(d&&d.message||'Data belum tersedia. Jalankan Sync di laptop.')+'</p>';
 var rows=(d.rows||[]).slice().sort(function(a,b){var k=sort||'r5';return (b[k]==null?-Infinity:b[k])-(a[k]==null?-Infinity:a[k]);});
 var h='<p><b>Data '+rotasiEsc(d.as_of)+'</b> · '+rotasiNum(d.n_saham,0)+' saham · '+rows.length+' sektor</p><p>'+rotasiEsc(d.message)+'</p>';
 h+='<p style="color:#B3C0D1">Median pasar 5 hari: '+rotasiChange(d.market5)+'. '+rotasiNum(d.n_dikeluarkan,0)+' dari '+rotasiNum(d.n_dibaca,0)+' saham dikeluarkan karena data tidak lengkap, kurang aktif, atau sektor belum tersedia ('+rotasiNum(d.n_tanpa_sektor,0)+').'+(d.n_file_gagal?' '+rotasiNum(d.n_file_gagal,0)+' file gagal dibaca.':'')+'</p>';
 h+='<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;white-space:nowrap"><thead><tr>';
 ['Sektor','1 hari','5 hari','20 hari','Saham naik (5h)','Aktivitas','Porsi transaksi','Δ porsi','Kondisi relatif'].forEach(function(t){h+='<th style="text-align:left;padding:10px;border-bottom:1px solid #38455A">'+t+'</th>';});
 h+='</tr></thead><tbody>';
 rows.forEach(function(r){
  h+='<tr><td style="padding:10px;border-bottom:1px solid #38455A"><b>'+rotasiEsc(r.sektor)+'</b><br><small>'+rotasiNum(r.n,0)+' saham'+(r.n<5?' · sampel kecil':'')+'</small></td>';
  ['r1','r5','r20'].forEach(function(k){h+='<td style="padding:10px;background:'+(r[k]>0?'rgba(22,224,174,.08)':r[k]<0?'rgba(255,96,118,.08)':'transparent')+'">'+rotasiChange(r[k])+'</td>';});
  h+='<td style="padding:10px">'+rotasiNum(r.naik,0)+'/'+rotasiNum(r.n,0)+' ('+rotasiNum(r.breadth,0)+'%)</td><td style="padding:10px">'+rotasiNum(r.aktivitas)+'×</td><td style="padding:10px">'+rotasiNum(r.porsi)+'%</td><td style="padding:10px">'+(r.perubahan_porsi>0?'+':'')+rotasiNum(r.perubahan_porsi)+' pp</td><td style="padding:10px">'+rotasiEsc(r.fase)+'</td></tr>';
 });
 h+='</tbody></table></div><p style="color:#B3C0D1">Menguat / Melambat: kinerja relatif di atas median pasar, momentum naik / turun. Memulih / Tertinggal: relatif di bawah median pasar, momentum naik / turun. pp = poin persentase.</p>';
 rows.forEach(function(r){h+='<details style="padding:12px 0;border-bottom:1px solid #38455A"><summary style="cursor:pointer">'+rotasiEsc(r.sektor)+' · '+rotasiNum(r.n,0)+' saham · '+rotasiEsc(r.fase)+'</summary><p>Relatif 5 hari: '+rotasiNum(r.relatif)+' pp · Momentum: '+rotasiNum(r.momentum)+' pp<br>Rata-rata estimasi transaksi harian 5 hari: Rp'+rotasiNum(r.nilai5/1e9)+' miliar<br>Naik '+rotasiNum(r.naik,0)+' · Turun '+rotasiNum(r.turun,0)+' · Tetap '+rotasiNum(r.tetap,0)+'</p><div style="display:flex;flex-wrap:wrap;gap:8px">'+(r.saham||[]).map(function(s){return '<span style="border:1px solid #38455A;border-radius:8px;padding:8px">'+rotasiEsc(s.ticker)+' '+rotasiChange(s.r5)+'</span>';}).join('')+'</div></details>';});
 return h+'<details style="margin-top:16px"><summary>Cara membaca &amp; perhitungan</summary><p>'+rotasiEsc(d.metode)+'</p><p>Minimal 26 sesi lengkap dan aktif setidaknya 24 sesi. Periode 5 hari mulai '+rotasiEsc(d.periode.awal5)+'; 20 hari mulai '+rotasiEsc(d.periode.awal20)+'.</p></details>';
}
