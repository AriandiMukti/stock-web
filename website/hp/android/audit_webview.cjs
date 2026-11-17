// Offline renderer audit against exact JavaScript extracted from APKs.
// The marker is inspected as text; no injected HTML/script is executed.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const out = path.resolve(__dirname, '../../reports/apk-local-audit-26645675');
const marker = '"><img data-audit="injected" src=x onerror="window.__audit=true">';
function fixture() {
  return {saham:{BBCA:{hub:{current_score:{window:20},
    signals:[{stock:'BBCA',flow:[{available:true,horizon:5}]}],
    ownership:{available:true,pct_foreign:30,pct_local_non_retail:40,pct_retail:30}}}},
    menu:{digest:{market_regime:{available:true,window_days:20}},kabar:{},ramai:{},watchlist:{},
      tembus:{available:true,config:{UMUR_MAX:5},jurnal:{available:true,aturan:[{horizon:5,n_matang:1,n:2}]}},
      rapat:{available:true,jurnal:{available:true,horizon:[{n_matang:1,horizon:5,kelompok:[{nama:'AMBIL',n:2}]}]}},
      kecondongan:{available:true,jurnal:{available:true,horizon:[{horizon:5}]}},
      radar:{available:true,jurnal:{data_insider:{umur_hari:1}}}}};
}
const cases = [
  ['vRingkasan','menu.digest.market_regime.window_days'],
  ['sTembus','menu.tembus.config.UMUR_MAX'],
  ['sTembus','menu.tembus.jurnal.aturan.0.horizon'],
  ['sTembus','menu.tembus.jurnal.aturan.0.n_matang'],
  ['sTembus','menu.tembus.jurnal.aturan.0.n'],
  ['sRapat','menu.rapat.jurnal.horizon.0.horizon'],
  ['sKecondongan','menu.kecondongan.jurnal.horizon.0.horizon'],
  ['sInsider','menu.radar.jurnal.data_insider.umur_hari'],
  ['vSaham','saham.BBCA.hub.current_score.window'],
  ['vSaham','saham.BBCA.hub.signals.0.flow.0.horizon'],
  ...['pct_foreign','pct_local_non_retail','pct_retail'].map(k=>['vSaham','saham.BBCA.hub.ownership.'+k]),
];
const report = {};
for (const label of ['old','first_flagged','native_hardened','current']) {
  const context = vm.createContext({window:{addEventListener(){}},
    fetch:()=>new Promise(()=>{}),setTimeout(){}});
  vm.runInContext(fs.readFileSync(path.join(out,label+'-app.js'),'utf8'), context);
  report[label] = cases.map(([fn,field])=>{
    context.D=fixture();
    assert.ok(!context[fn]('BBCA').includes('<img data-audit='));
    const parts=field.split('.');let target=context.D;
    for(const part of parts.slice(0,-1)) target=target[part];
    target[parts.at(-1)]=marker;
    const html=context[fn]('BBCA');
    return {renderer:fn,field,unescaped_markup:html.includes('<img data-audit=')};
  });
  console.log(label+': '+report[label].filter(x=>x.unescaped_markup).length+'/'+cases.length+' manipulated fields reach HTML unescaped');
}
fs.writeFileSync(path.join(out,'renderer-findings.json'),JSON.stringify(report,null,2));
