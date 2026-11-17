const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const payload = '<img src=x onerror="window.__injected=true">';
function fixture() {
  return {available: true, as_of: '2026-11-06', n_saham: 12, n_dikeluarkan: 2,
    n_dibaca: 14, n_tanpa_sektor: 0, n_file_gagal: 1, periode: {},
    rows: [{sektor: 'Keuangan', n: 12, naik: 7, turun: 3, tetap: 2, saham: []}]};
}
for (const relative of ['static/js/rotasi_sektor.js', 'hp/android/assets/rotasi_sektor.js']) {
  const file = path.join(__dirname, '..', relative);
  const context = vm.createContext({});
  vm.runInContext(fs.readFileSync(file, 'utf8'), context);
  const normal = context.rotasiHtml(fixture());
  assert.ok(normal.includes('12 saham'));
  assert.ok(normal.includes('Naik 7 · Turun 3 · Tetap 2'));
  for (const field of ['n_saham','n_dikeluarkan','n_dibaca','n_tanpa_sektor','n_file_gagal']) {
    const data = fixture(); data[field] = payload;
    assert.ok(!context.rotasiHtml(data).includes('<img'), `${relative}: unsafe ${field}`);
  }
  for (const field of ['n','naik','turun','tetap']) {
    const data = fixture(); data.rows[0][field] = payload;
    assert.ok(!context.rotasiHtml(data).includes('<img'), `${relative}: unsafe row ${field}`);
  }
  console.log(`${relative}: normal output and 9 injection cases passed`);
}
