
const DATA = JSON.parse(document.getElementById('DATA').textContent);
function el(id){ return document.getElementById(id); }
function fmt(x, d=2){ return (x==null||Number.isNaN(x)) ? '—' : Number(x).toFixed(d); }
function heatColor(v, lo, hi){
  if (v==null || hi<=lo) return '#2a3544';
  let t = Math.max(0, Math.min(1, (v-lo)/(hi-lo)));
  let r,g,b;
  if (t < 0.5){ const u=t*2; r=220; g=Math.round(80+140*u); b=Math.round(80+140*u); }
  else { const u=(t-0.5)*2; r=Math.round(220-160*u); g=Math.round(220-40*u); b=Math.round(220-160*u); }
  return `rgb(${r},${g},${b})`;
}
function invNorm(p){
  if (p<=0) return -8; if (p>=1) return 8;
  const a=[-39.69683028665376,220.9460984245205,-275.9285104469687,138.357751867269, -30.66479806614716,2.506628277459239];
  const b=[-54.47609879822406,161.5858368580577,-155.6989798598866,66.80131188771972,-13.28068155288572];
  const c=[-0.007784894002430293,-0.3223709511329187,-2.400758277161838,-2.549732539343734,4.374664141464968,2.938163982698783];
  const d=[0.007784695709041462,0.3224671290700398,2.445134137142996,3.754408661907416];
  const plow=0.02425, phigh=1-plow;
  if (p<plow){ const q=Math.sqrt(-2*Math.log(p)); return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5])/((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1); }
  if (p>phigh){ const q=Math.sqrt(-2*Math.log(1-p)); return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5])/((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1); }
  const q=p-0.5, r=q*q;
  return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q/(((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1);
}

const focus = DATA.focus || DATA.c14;
const p37 = DATA.p37;
const waves = DATA.waves;
const chartDefaults = { responsive:true, maintainAspectRatio:false, plugins:{ legend:{ labels:{ color:'#8b9aab' } } },
  scales:{ x:{ ticks:{ color:'#8b9aab' }, grid:{ color:'#2a354433' } }, y:{ ticks:{ color:'#8b9aab' }, grid:{ color:'#2a354433' } } } };

const betterPct = focus.n_pairs ? (100*focus.n_better/focus.n_pairs) : 0;
el('kpi-cards').innerHTML = [
  ['Pairs '+ (DATA.focus_id||'C17'), focus.n_pairs],
  ['Better rate', fmt(betterPct,1)+'%'],
  ['CV acc / AUC', fmt(focus.model?.cv_accuracy,2)+' / '+fmt(focus.model?.cv_auc,2)],
  ['Promoted '+(focus.promo_prefix||'37p'), (focus.promoted||[]).length],
  ['Short×ex-div', p37.total_short_crossed],
  ['Short paid ₽', Math.round(p37.total_short_div_paid).toLocaleString('ru')],
  ['Long recv ₽', Math.round(p37.total_long_div_received).toLocaleString('ru')],
  ['Div events', DATA.div_cal.n_events],
].map(([k,v]) => `<div class="card"><div class="k">${k}</div><div class="v sm">${v}</div></div>`).join('');

el('tbl-waves').innerHTML = `<thead><tr><th>wave</th><th>pairs</th><th>better</th><th>acc</th><th>AUC</th><th>promoted</th><th>symbols</th><th>TFs</th></tr></thead><tbody>` +
  waves.map(w => `<tr><td class="f">${w.id}</td><td>${w.n_pairs??'—'}</td><td>${w.n_better??'—'}</td><td>${fmt(w.acc,3)}</td><td>${fmt(w.auc,3)}</td><td>${w.n_promoted??'—'}</td><td>${(w.symbols||[]).length||'—'}</td><td>${(w.tfs||[]).join(', ')||'—'}</td></tr>`).join('') + `</tbody>`;

new Chart(el('ch-pairs'), { type:'bar', data:{ labels:waves.map(w=>w.id), datasets:[
  { label:'pairs', data:waves.map(w=>w.n_pairs), backgroundColor:'#3d9cf0aa' },
  { label:'promoted', data:waves.map(w=>w.n_promoted), backgroundColor:'#5ecf8caa' },
]}, options: chartDefaults });
new Chart(el('ch-metrics'), { type:'line', data:{ labels:waves.map(w=>w.id), datasets:[
  { label:'CV acc', data:waves.map(w=>w.acc), borderColor:'#3d9cf0', tension:.25 },
  { label:'AUC', data:waves.map(w=>w.auc), borderColor:'#5ecf8c', tension:.25 },
]}, options: chartDefaults });

/* Walk-forward */
const wf = (focus.walk_forward||[]).filter(r=>!r.skipped);
el('tbl-wf').innerHTML = `<thead><tr><th>test year</th><th>n train</th><th>n test</th><th>train better%</th><th>test better%</th><th>OOS acc</th><th>OOS AUC</th></tr></thead><tbody>` +
  (focus.walk_forward||[]).map(r => r.skipped
    ? `<tr><td class="f">${r.test_year}</td><td>${r.n_train}</td><td>${r.n_test}</td><td colspan="4">skipped</td></tr>`
    : `<tr><td class="f">${r.test_year}</td><td>${r.n_train}</td><td>${r.n_test}</td><td>${fmt(100*r.train_better_rate,1)}%</td><td>${fmt(100*r.test_better_rate,1)}%</td><td>${fmt(r.oos_accuracy,3)}</td><td>${fmt(r.oos_auc,3)}</td></tr>`
  ).join('') + `</tbody>`;
if (wf.length){
  new Chart(el('ch-wf'), { type:'line', data:{ labels:wf.map(r=>String(r.test_year)), datasets:[
    { label:'OOS acc', data:wf.map(r=>r.oos_accuracy), borderColor:'#3d9cf0', tension:.25 },
    { label:'OOS AUC', data:wf.map(r=>r.oos_auc), borderColor:'#5ecf8c', tension:.25 },
  ]}, options: chartDefaults });
}
const near = focus.near_ex_div_heatmap || {};
const nearKeys = Object.keys(near).sort();
let hn = `<table class="heat"><thead><tr><th>bucket</th><th>n</th><th>better%</th></tr></thead><tbody>`;
nearKeys.forEach(k=>{
  const v=near[k]; const pct=100*(v.better_rate||0);
  hn += `<tr><td class="f">${k}</td><td>${v.n}</td><td style="background:${heatColor(pct,20,40)}"><div class="cell-v">${pct.toFixed(1)}%</div></td></tr>`;
});
el('heat-near').innerHTML = hn + (nearKeys.length?`</tbody></table>`:`<p class="note">нет данных</p>`);

const tfs = ['1m','5m','10m','15m','30m','1h','1d','1w'];
const fuSet = new Set(['CNYRUBF','GLDRUBF','IMOEXF']);
const syms = Object.keys(focus.cov_mean||{}).sort((a,b)=> (fuSet.has(a)-fuSet.has(b)) || a.localeCompare(b));
let vals=[]; syms.forEach(s=>tfs.forEach(tf=>{ const v=focus.cov_mean[s]?.[tf]; if(v!=null) vals.push(v); }));
const lo=Math.min(...vals), hi=Math.max(...vals);
let heat = `<table class="heat"><thead><tr><th></th>${tfs.map(t=>`<th>${t}</th>`).join('')}</tr></thead><tbody>`;
syms.forEach(s=>{
  heat += `<tr><td class="f">${s}</td>`;
  tfs.forEach(tf=>{
    const v=focus.cov_mean[s]?.[tf], n=focus.cov_n[s]?.[tf];
    if (v==null) heat += `<td class="empty">—</td>`;
    else heat += `<td style="background:${heatColor(v,lo,hi)}"><div class="cell-v">${v.toFixed(0)}</div><div class="cell-n">n=${n}</div></td>`;
  });
  heat += `</tr>`;
});
el('heat-cov').innerHTML = heat + `</tbody></table>`;

const tfKeys = Object.keys(focus.tf_overall||{});
new Chart(el('ch-tf'), { type:'bar', data:{ labels:tfKeys, datasets:[{ label:'mean ΔPnL', data:tfKeys.map(k=>focus.tf_overall[k].mean), backgroundColor:'#3d9cf0aa' }]}, options: chartDefaults });
const symKeys = Object.keys(focus.sym_overall||{}).sort((a,b)=>focus.sym_overall[a].mean-focus.sym_overall[b].mean);
new Chart(el('ch-sym'), { type:'bar', data:{ labels:symKeys, datasets:[{ label:'mean ΔPnL', data:symKeys.map(k=>focus.sym_overall[k].mean), backgroundColor:symKeys.map(k=>fuSet.has(k)?'#e0b45eaa':'#3d9cf0aa') }]}, options:{...chartDefaults, indexAxis:'y'} });

const kindKeys = Object.keys(focus.kind_overall||{}).sort((a,b)=>focus.kind_overall[b].mean-focus.kind_overall[a].mean);
new Chart(el('ch-kind'), { type:'bar', data:{ labels:kindKeys, datasets:[{ label:'mean ΔPnL', data:kindKeys.map(k=>focus.kind_overall[k].mean), backgroundColor:'#5ecf8caa' }]}, options:{...chartDefaults, indexAxis:'y'} });
const kbr = focus.kind_better_rate || {};
const kindBrKeys = Object.keys(kbr).sort((a,b)=>(kbr[b].rate||0)-(kbr[a].rate||0));
new Chart(el('ch-kind-br'), { type:'bar', data:{ labels:kindBrKeys, datasets:[{ label:'better %', data:kindBrKeys.map(k=>100*(kbr[k].rate||0)), backgroundColor:'#e0b45eaa' }]}, options:{...chartDefaults, indexAxis:'y'} });
const eq = focus.kind_by_ac?.equity||{}, fu = focus.kind_by_ac?.future||{};
const allK = Array.from(new Set([...Object.keys(eq), ...Object.keys(fu)]));
new Chart(el('ch-kind-ac'), { type:'bar', data:{ labels:allK, datasets:[
  { label:'equity', data:allK.map(k=>eq[k]?.mean ?? null), backgroundColor:'#3d9cf0aa' },
  { label:'future', data:allK.map(k=>fu[k]?.mean ?? null), backgroundColor:'#e0b45eaa' },
]}, options:{...chartDefaults, indexAxis:'y'} });

const br = focus.better_rate_side_kind || {};
const sides = Object.keys(br);
const kinds2 = Array.from(new Set(sides.flatMap(s=>Object.keys(br[s]||{}))));
let hs = `<table class="heat"><thead><tr><th>side \\ kind</th>${kinds2.map(k=>`<th>${k.replace('change_period_','p').replace('add_block_','+').replace('remove_block_','-')}</th>`).join('')}</tr></thead><tbody>`;
sides.forEach(s=>{
  hs += `<tr><td class="f">${s}</td>`;
  kinds2.forEach(k=>{
    const cell = br[s]?.[k];
    if (!cell) { hs += `<td class="empty">—</td>`; return; }
    const [rate,n] = cell; const pct = rate*100;
    hs += `<td style="background:${heatColor(pct,20,45)}"><div class="cell-v">${pct.toFixed(0)}%</div><div class="cell-n">n=${n}</div></td>`;
  });
  hs += `</tr>`;
});
el('heat-side').innerHTML = hs + `</tbody></table>`;

const sample = (focus.delta_sample||[]).slice().sort((a,b)=>a-b);
const bins=40, min=sample[0], max=sample[sample.length-1], width=(max-min)/bins||1, counts=Array(bins).fill(0);
sample.forEach(v=>{ counts[Math.min(bins-1, Math.floor((v-min)/width))]++; });
new Chart(el('ch-hist'), { type:'bar', data:{ labels:counts.map((_,i)=>(min+i*width).toFixed(0)), datasets:[{ label:'count', data:counts, backgroundColor:'#3d9cf088' }]}, options:{...chartDefaults, plugins:{legend:{display:false}}} });
const n=sample.length, mean=sample.reduce((a,b)=>a+b,0)/n, sd=Math.sqrt(sample.reduce((a,b)=>a+(b-mean)**2,0)/(n-1))||1;
const step=Math.max(1, Math.floor(n/120)), qq=[];
for(let i=0;i<n;i+=step) qq.push({x:invNorm((i+0.5)/n), y:(sample[i]-mean)/sd});
new Chart(el('ch-qq'), { type:'scatter', data:{ datasets:[
  { label:'sample', data:qq, backgroundColor:'#3d9cf0aa', pointRadius:2 },
  { label:'y=x', data:[{x:-3,y:-3},{x:3,y:3}], showLine:true, borderColor:'#5ecf8c', pointRadius:0, fill:false },
]}, options:{...chartDefaults, scales:{ x:{ title:{display:true,text:'theoretical',color:'#8b9aab'}, ticks:{color:'#8b9aab'}, grid:{color:'#2a354433'} }, y:{ title:{display:true,text:'sample z',color:'#8b9aab'}, ticks:{color:'#8b9aab'}, grid:{color:'#2a354433'} } }} });

el('loso-note').textContent = focus.loso_note || '';
const loso = focus.loso_1d || {}, losoKeys = Object.keys(loso);
new Chart(el('ch-loso'), { type:'bar', data:{ labels:losoKeys, datasets:[
  { label:'accuracy', data:losoKeys.map(k=>loso[k].accuracy), backgroundColor:'#3d9cf0aa' },
  { label:'AUC', data:losoKeys.map(k=>loso[k].auc), backgroundColor:'#5ecf8caa' },
]}, options: chartDefaults });
const imp = (focus.importance||[]).slice(0,15);
new Chart(el('ch-imp'), { type:'bar', data:{ labels:imp.map(x=>x[0]), datasets:[{ label:'importance', data:imp.map(x=>x[1]), backgroundColor:'#e0b45eaa' }]}, options:{...chartDefaults, indexAxis:'y'} });

function pairTable(rows){
  return `<thead><tr><th>sym</th><th>tf</th><th>base</th><th>kind</th><th>Δ</th><th>side</th></tr></thead><tbody>`+
    rows.map(r=>`<tr><td class="f">${r.symbol}</td><td>${r.tf}</td><td class="f">${r.base}</td><td>${r.kind}</td><td>${fmt(r.delta,1)}</td><td>${r.side||'—'}</td></tr>`).join('')+`</tbody>`;
}
el('tbl-top').innerHTML = pairTable(focus.top20||[]);
el('tbl-bot').innerHTML = pairTable(focus.bottom20||[]);
el('promo-label').textContent = (focus.promo_prefix||'37p')+'-*';
el('tbl-prom').innerHTML = `<thead><tr><th>to</th><th>kind</th><th>mean Δ</th><th>n win</th><th>symbols</th></tr></thead><tbody>`+
  (focus.promoted||[]).map(p=>`<tr><td class="f">${p.to}</td><td>${p.kind}</td><td>${fmt(p.mean_delta,1)}</td><td>${p.n_symbols_win}</td><td class="f">${(p.symbols_win||[]).join(', ')}</td></tr>`).join('')+`</tbody>`;

el('div-kpi').innerHTML = [
  ['Short×ex-div', p37.total_short_crossed],
  ['Short paid ₽', Math.round(p37.total_short_div_paid).toLocaleString('ru')],
  ['Long received ₽', Math.round(p37.total_long_div_received).toLocaleString('ru')],
  ['LS short paid ₽', Math.round(p37.ls_short_div_paid).toLocaleString('ru')],
].map(([k,v])=>`<div class="card"><div class="k">${k}</div><div class="v sm">${v}</div></div>`).join('');
const ps = Object.keys(p37.per_symbol);
new Chart(el('ch-div-sym'), { type:'bar', data:{ labels:ps, datasets:[
  { label:'short crossed', data:ps.map(s=>p37.per_symbol[s].short_crossed), backgroundColor:'#e07070aa' },
  { label:'Δ PnL (all sides)', data:ps.map(s=>p37.per_symbol[s].delta), backgroundColor:'#3d9cf055' },
]}, options: chartDefaults });
el('div-meta').textContent = `source: ${DATA.div_cal.source} · fetched ${DATA.div_cal.fetched_at} · ${DATA.div_cal.n_events} events`;
const maxDiv = Math.max(...DATA.div_cal.events.map(e=>e.div||0), 1);
el('div-tl').innerHTML = DATA.div_cal.events.map(e => {
  const w = Math.round(100*(e.div||0)/maxDiv);
  return `<div class="tl-row"><span>${e.date}</span><span class="tl-sym">${e.symbol}</span><div class="tl-bar-wrap"><div class="tl-bar" style="width:${w}%"></div></div><span class="tl-div">${e.div??'—'} ₽</span></div>`;
}).join('');

const svg = el('dag');
const nodes = [
  {id:'C7', x:70, y:150, label:['C7','policy']},
  {id:'C12', x:200, y:80, label:['C9–C12','multi-sym']},
  {id:'C13', x:340, y:80, label:['C13','all TF']},
  {id:'C14', x:480, y:80, label:['C14','+futures']},
  {id:'C15', x:620, y:80, label:['C15','§7I BH']},
  {id:'C16', x:760, y:80, label:['C16','ATR/rm']},
  {id:'C17', x:920, y:150, label:['C17','WF+div']},
  {id:'P37', x:620, y:220, label:['P3.7','div cal']},
];
[['C7','C12'],['C12','C13'],['C13','C14'],['C14','C15'],['C15','C16'],['C16','C17'],['P37','C15'],['P37','C17']].forEach(([a,b])=>{
  const A=nodes.find(n=>n.id===a), B=nodes.find(n=>n.id===b);
  const line=document.createElementNS('http://www.w3.org/2000/svg','line');
  line.setAttribute('x1', A.x+40); line.setAttribute('y1', A.y);
  line.setAttribute('x2', B.x-40); line.setAttribute('y2', B.y);
  line.setAttribute('stroke', '#2a3544'); line.setAttribute('stroke-width', '2');
  svg.appendChild(line);
});
nodes.forEach(n=>{
  const g=document.createElementNS('http://www.w3.org/2000/svg','g');
  const r=document.createElementNS('http://www.w3.org/2000/svg','rect');
  r.setAttribute('x', n.x-48); r.setAttribute('y', n.y-28); r.setAttribute('width', 96); r.setAttribute('height', 56);
  r.setAttribute('rx', 10); r.setAttribute('fill', n.id==='C17'?'#1e3a2f':'#1a2330');
  r.setAttribute('stroke', n.id==='C17'?'#5ecf8c':'#3d9cf0');
  g.appendChild(r);
  const t=document.createElementNS('http://www.w3.org/2000/svg','text');
  t.setAttribute('x', n.x); t.setAttribute('y', n.y-8); t.setAttribute('text-anchor','middle');
  t.setAttribute('fill', '#e8eef4'); t.setAttribute('font-size', '11');
  n.label.forEach((line,i)=>{
    const tp=document.createElementNS('http://www.w3.org/2000/svg','tspan');
    tp.setAttribute('x', n.x); tp.setAttribute('dy', i===0?0:14); tp.textContent=line;
    t.appendChild(tp);
  });
  g.appendChild(t); svg.appendChild(g);
});
