# -*- coding: utf-8 -*-
"""Build a self-contained, searchable & readable index.html from data.json."""
import json, os
HERE = os.path.dirname(__file__)
data = json.load(open(os.path.join(HERE, 'data.json'), encoding='utf-8'))
DATA_JSON = json.dumps(data, ensure_ascii=False)

HTML = r'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>성장하는 도시를 위한 도시계획 · Urban Planning for Growing Cities</title>
<style>
:root{
  --ink:#16202b; --ink2:#46586b; --ink3:#7d8ea0; --line:#e4e9ef; --line2:#eef2f6;
  --bg:#f6f8fb; --card:#fff; --han:#1d6fb8; --han-d:#15527f; --han-l:#eaf3fb;
  --gold:#c08a2d; --gold-l:#f7efe0; --green:#2f7d5b; --green-l:#e7f3ec;
  --shadow:0 1px 2px rgba(20,40,70,.04),0 8px 24px rgba(20,40,70,.06);
  --shadow-lg:0 12px 40px rgba(20,40,70,.14);
}
*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{font-family:"Pretendard","Apple SD Gothic Neo","Malgun Gothic",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  color:var(--ink);background:var(--bg);line-height:1.6;-webkit-font-smoothing:antialiased}
.wrap{max-width:1180px;margin:0 auto;padding:0 24px}
mark{background:#ffe9a8;color:inherit;padding:0 1px;border-radius:2px}

/* Header */
header.hero{background:linear-gradient(150deg,#0f3a5f 0%,#1d6fb8 60%,#2f88cf 100%);color:#fff;position:relative;overflow:hidden}
header.hero::after{content:"";position:absolute;right:-80px;top:-60px;width:340px;height:340px;border-radius:50%;
  background:radial-gradient(circle at center,rgba(255,255,255,.16),transparent 70%)}
.hero-in{padding:44px 0 38px;position:relative;z-index:1}
.kicker{font-size:13px;letter-spacing:.16em;opacity:.9;font-weight:600}
.hero h1{margin:.32em 0 .1em;font-size:34px;font-weight:800;letter-spacing:-.01em}
.hero .en{font-size:17px;opacity:.92;font-weight:500;font-style:italic}
.hero .sub{font-size:14px;opacity:.78;margin-top:7px}
.stats{display:flex;gap:30px;margin-top:22px;flex-wrap:wrap}
.stat .n{font-size:29px;font-weight:800;line-height:1}
.stat .l{font-size:12.5px;opacity:.82;margin-top:3px}

/* Toolbar */
.toolbar{position:sticky;top:0;z-index:40;background:rgba(246,248,251,.9);backdrop-filter:blur(10px);
  border-bottom:1px solid var(--line);padding:11px 0}
.toolbar-in{display:flex;gap:12px;align-items:center;flex-wrap:wrap}
.tabs{display:flex;background:#e9eef4;border-radius:11px;padding:3px}
.tab{border:0;background:transparent;padding:8px 15px;border-radius:8px;font-size:14px;font-weight:600;color:var(--ink2);cursor:pointer;transition:.15s}
.tab.active{background:#fff;color:var(--han-d);box-shadow:0 1px 3px rgba(0,0,0,.08)}
.search{flex:1;min-width:200px;position:relative}
.search input{width:100%;padding:9px 32px 9px 36px;border:1px solid var(--line);border-radius:10px;font-size:14px;background:#fff;font-family:inherit}
.search input:focus{outline:none;border-color:var(--han);box-shadow:0 0 0 3px var(--han-l)}
.search svg{position:absolute;left:12px;top:50%;transform:translateY(-50%);width:15px;height:15px;color:var(--ink3)}
.search .clr{position:absolute;right:9px;top:50%;transform:translateY(-50%);border:0;background:#dde5ee;color:#5a6b7d;width:20px;height:20px;border-radius:50%;cursor:pointer;font-size:13px;line-height:1;display:none}
.search.has .clr{display:block}
.filters{display:flex;gap:7px;flex-wrap:wrap}
.chip{border:1px solid var(--line);background:#fff;padding:6px 13px;border-radius:20px;font-size:13px;font-weight:600;color:var(--ink2);cursor:pointer;transition:.15s;white-space:nowrap}
.chip.active{background:var(--han);border-color:var(--han);color:#fff}

main{padding:28px 0 70px;min-height:55vh}

/* Part groups + chapter cards */
.part-group{margin-bottom:38px}
.part-h{display:flex;align-items:baseline;gap:12px;margin:0 0 16px;padding-bottom:9px;border-bottom:2px solid var(--line)}
.part-h .pt{font-size:18px;font-weight:800;color:var(--han-d)}
.part-h .pc{font-size:13px;color:var(--ink3);font-weight:600}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:15px;padding:19px 20px 16px;cursor:pointer;
  transition:.18s;box-shadow:var(--shadow);display:flex;flex-direction:column}
.card:hover{transform:translateY(-3px);box-shadow:var(--shadow-lg);border-color:#cfe0ee}
.card .num{display:inline-block;font-size:11.5px;font-weight:800;letter-spacing:.05em;color:var(--han);background:var(--han-l);padding:3px 9px;border-radius:6px;margin-bottom:10px;align-self:flex-start}
.card h3{margin:0 0 3px;font-size:18.5px;font-weight:800;letter-spacing:-.01em}
.card .en{font-size:12.5px;color:var(--ink3);font-style:italic;margin-bottom:12px}
.card .outline{font-size:13px;color:var(--ink2);display:flex;flex-direction:column;gap:3px;margin-bottom:12px}
.card .outline .ol{display:flex;gap:7px;align-items:flex-start}
.card .outline .dot{color:var(--ink3);flex:none;margin-top:.1em}
.card .foot{display:flex;justify-content:space-between;align-items:center;border-top:1px dashed var(--line);padding-top:11px;margin-top:auto}
.card .cc{font-size:12.5px;font-weight:700;color:var(--gold)}
.card .read{font-size:12px;font-weight:700;color:var(--han)}

/* Keyword table */
.tbl-wrap{background:#fff;border:1px solid var(--line);border-radius:14px;overflow:hidden;box-shadow:var(--shadow)}
table.cases{width:100%;border-collapse:collapse;font-size:14px}
table.cases th{background:#f0f4f8;text-align:left;padding:12px 16px;font-size:12.5px;font-weight:700;color:var(--ink2);border-bottom:1px solid var(--line);position:sticky;top:56px;z-index:5}
table.cases td{padding:12px 16px;border-bottom:1px solid var(--line2);vertical-align:top}
table.cases tr:last-child td{border-bottom:0}
table.cases tr.crow{cursor:pointer;transition:.12s}
table.cases tr.crow:hover{background:var(--han-l)}
.tnum{font-weight:800;color:var(--han);white-space:nowrap;font-size:13px}
.tpart{color:var(--ink3);font-size:12.5px;white-space:nowrap}
.tcase{font-weight:600;color:var(--ink)}
.kw{display:inline-block;background:var(--gold-l);color:#8a6418;border:1px solid #ecdcb8;border-radius:14px;padding:3px 10px;font-size:12.5px;font-weight:700;margin:2px 4px 2px 0;white-space:nowrap}
.part-sep td{background:#fafbfd;font-weight:800;color:var(--han-d);font-size:13px;padding:9px 16px}

/* Search results */
.sr-head{font-size:14px;color:var(--ink2);margin-bottom:14px}
.sr-item{background:#fff;border:1px solid var(--line);border-radius:12px;padding:14px 17px;margin-bottom:10px;cursor:pointer;transition:.12s;box-shadow:var(--shadow)}
.sr-item:hover{border-color:#cfe0ee;transform:translateY(-1px)}
.sr-src{font-size:12px;font-weight:700;color:var(--han);margin-bottom:5px}
.sr-src .chip-sm{background:var(--han-l);padding:1px 7px;border-radius:5px;margin-right:6px}
.sr-snip{font-size:13.5px;color:var(--ink2);line-height:1.55}
.sr-kind{display:inline-block;font-size:10.5px;font-weight:700;padding:1px 7px;border-radius:5px;margin-right:6px;vertical-align:1px}
.k-h{background:var(--green-l);color:var(--green)} .k-core{background:var(--gold-l);color:var(--gold)} .k-p{background:#eef1f4;color:var(--ink3)}

/* Reading view */
.reader{display:none}
.reader.on{display:block}
.list-view.off{display:none}
.rbar{position:sticky;top:55px;z-index:20;background:rgba(246,248,251,.92);backdrop-filter:blur(8px);border-bottom:1px solid var(--line);padding:10px 0;margin-bottom:8px}
.rbar-in{display:flex;align-items:center;gap:14px}
.back{border:1px solid var(--line);background:#fff;border-radius:9px;padding:7px 13px;font-size:13.5px;font-weight:700;color:var(--han-d);cursor:pointer;white-space:nowrap}
.back:hover{background:var(--han-l)}
.rbar .rt{font-weight:800;font-size:15px}
.rbar .rt small{color:var(--ink3);font-weight:600;margin-left:7px}
.read-layout{display:grid;grid-template-columns:230px 1fr;gap:34px;align-items:start}
.toc{position:sticky;top:118px;font-size:13px;max-height:calc(100vh - 140px);overflow-y:auto;padding-right:6px}
.toc a{display:block;color:var(--ink2);text-decoration:none;padding:4px 9px;border-radius:7px;border-left:2px solid transparent;line-height:1.4;margin-bottom:1px}
.toc a:hover{background:#eef2f6}
.toc a.t1{font-weight:700;color:var(--ink)}
.toc a.t2{padding-left:18px;font-size:12.5px}
.toc a.core{color:var(--gold);font-weight:700}
.toc a.active{border-left-color:var(--han);background:var(--han-l);color:var(--han-d)}
article.read{max-width:740px;background:#fff;border:1px solid var(--line);border-radius:16px;padding:38px 46px 50px;box-shadow:var(--shadow);font-size:16px;line-height:1.85}
article.read .doc-h{font-size:13px;font-weight:800;color:var(--han);letter-spacing:.05em;margin-bottom:4px}
article.read>h1{font-size:30px;font-weight:800;margin:2px 0 4px;letter-spacing:-.01em}
article.read>.den{font-size:15px;color:var(--ink3);font-style:italic;margin-bottom:30px;padding-bottom:22px;border-bottom:2px solid var(--line)}
article.read h2{font-size:23px;font-weight:800;margin:38px 0 6px;scroll-margin-top:130px;letter-spacing:-.01em}
article.read h2 .en{display:block;font-size:14px;color:var(--ink3);font-style:italic;font-weight:500;margin-top:2px}
article.read h3{font-size:18.5px;font-weight:700;margin:26px 0 4px;color:var(--ink);scroll-margin-top:130px}
article.read h4{font-size:16px;font-weight:700;margin:18px 0 2px;color:var(--ink2);scroll-margin-top:130px}
article.read p{margin:0 0 15px;color:#24323f}
article.read .cap{font-size:13.5px;color:var(--ink3);background:#f6f8fb;border-left:3px solid #cfd9e3;padding:7px 13px;border-radius:0 7px 7px 0;margin:4px 0 18px;font-style:italic}
article.read .case-h{background:var(--gold-l);border:1px solid #ecdcb8;border-radius:11px;padding:13px 18px;margin:36px 0 8px}
article.read .case-h h2{margin:0;font-size:21px;color:#8a6418}
article.read .case-h .cbadge{display:inline-block;font-size:11px;font-weight:800;background:var(--gold);color:#fff;padding:2px 9px;border-radius:11px;margin-bottom:7px;letter-spacing:.03em}
article.read .case-h .kws{margin-top:9px}
article.read .case-h .kws .kw{margin-top:0}
article.read .refs-h{color:var(--ink2)}
article.read ul.refs{font-size:13.5px;color:var(--ink3);line-height:1.7;padding-left:20px}
article.read .hl{background:#fff2c2;animation:hlf 2.4s ease}
@keyframes hlf{0%,40%{background:#ffe27a}100%{background:transparent}}

.empty{text-align:center;padding:70px 20px;color:var(--ink3)}
footer{border-top:1px solid var(--line);padding:24px 0;color:var(--ink3);font-size:12.5px;text-align:center}
@media(max-width:820px){.read-layout{grid-template-columns:1fr}.toc{display:none}article.read{padding:26px 22px 36px;font-size:15.5px}}
@media(max-width:560px){.hero h1{font-size:26px}.stats{gap:18px}}
</style>
</head>
<body>
<header class="hero">
  <div class="wrap hero-in">
    <div class="kicker" id="h-pub"></div>
    <h1 id="h-kr"></h1>
    <div class="en" id="h-en"></div>
    <div class="sub">서울의 도시계획 이야기 — 챕터·소제목 및 서울의 경험 사례 정리 · 본문 읽기/검색</div>
    <div class="stats">
      <div class="stat"><div class="n" id="st-ch">0</div><div class="l">챕터 Chapters</div></div>
      <div class="stat"><div class="n" id="st-case">0</div><div class="l">서울의 경험 사례 Cases</div></div>
      <div class="stat"><div class="n" id="st-part">0</div><div class="l">부 Parts</div></div>
    </div>
  </div>
</header>

<div class="toolbar">
  <div class="wrap toolbar-in">
    <div class="tabs">
      <button class="tab active" data-view="chapters">📖 챕터 목록</button>
      <button class="tab" data-view="table">📑 사례 키워드표</button>
    </div>
    <div class="search" id="searchBox">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg>
      <input id="q" type="text" placeholder="본문·제목·사례 전체 검색…  (Full-text search)">
      <button class="clr" id="clrBtn">×</button>
    </div>
    <div class="filters" id="filters"></div>
  </div>
</div>

<main><div class="wrap">
  <div class="list-view" id="listView"></div>
  <div class="reader" id="reader"></div>
</div></main>

<footer class="wrap" id="foot"></footer>

<script>
const DATA = __DATA__;
const CH = DATA.chapters;
const M = DATA.meta;
const PARTS = [...new Set(CH.map(c=>c.partname))];
let view='chapters', query='', partFilter='all', curRead=null;

document.getElementById('h-pub').textContent = '발간 · '+M.publisher;
document.getElementById('h-kr').textContent = M.titleKR;
document.getElementById('h-en').textContent = M.titleEN;
document.getElementById('st-ch').textContent = CH.length;
document.getElementById('st-case').textContent = CH.reduce((s,c)=>s+c.caseCount,0);
document.getElementById('st-part').textContent = new Set(CH.map(c=>c.part)).size;
document.getElementById('foot').innerHTML = M.titleKR+' · '+M.titleEN+' &nbsp;|&nbsp; '+M.publisher+' &nbsp;|&nbsp; 초본 검수용 · 원문 docx 자동 추출';

function esc(s){return (s||'').replace(/[&<>]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[m]));}
function hl(s,q){ if(!q) return esc(s); const i=s.toLowerCase().indexOf(q.toLowerCase());
  if(i<0) return esc(s); return esc(s.slice(0,i))+'<mark>'+esc(s.slice(i,i+q.length))+'</mark>'+esc(s.slice(i+q.length)); }

// filters
const fbox=document.getElementById('filters');
function buildFilters(){
  const items=[['all','전체']].concat(PARTS.map(p=>[p,p.replace(/ ·.*$/,'').replace(/^Part \d+\. /,'')]));
  fbox.innerHTML=items.map(([v,l])=>`<button class="chip ${v===partFilter?'active':''}" data-f="${v}">${esc(l)}</button>`).join('');
  fbox.querySelectorAll('.chip').forEach(b=>b.onclick=()=>{partFilter=b.dataset.f;buildFilters();render();});
}
document.querySelectorAll('.tab').forEach(t=>t.onclick=()=>{
  document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));
  t.classList.add('active'); view=t.dataset.view; closeReader(); render();
});
const sbox=document.getElementById('searchBox');
document.getElementById('q').addEventListener('input',e=>{query=e.target.value.trim();sbox.classList.toggle('has',!!query);if(curRead===null)render();else if(query){closeReader();render();}});
document.getElementById('clrBtn').onclick=()=>{query='';document.getElementById('q').value='';sbox.classList.remove('has');render();};

function matchCh(c){ return partFilter==='all'||c.partname===partFilter; }

// ---- chapter cards ----
function chapterCard(c){
  const tops=c.headings.filter(b=>b.level===1||b.kind==='core'||b.kind==='casehead').slice(0,5);
  const ol=tops.map(b=>`<div class="ol"><span class="dot">${b.kind==='core'?'★':'·'}</span><span>${esc(b.kr)}</span></div>`).join('');
  const cc=c.caseCount>0?`<span class="cc">★ 서울의 경험 ${c.caseCount}선</span>`:'<span class="cc"></span>';
  return `<div class="card" data-ch="${c.order}">
    <span class="num">${esc(c.label)}</span>
    <h3>${esc(c.titleKR)}</h3><div class="en">${esc(c.titleEN)}</div>
    <div class="outline">${ol}</div>
    <div class="foot">${cc}<span class="read">본문 읽기 ›</span></div></div>`;
}

// ---- keyword table ----
function tableView(){
  let rows='';
  PARTS.filter(p=>partFilter==='all'||p===partFilter).forEach(p=>{
    const chs=CH.filter(c=>c.partname===p && c.caseCount>0);
    if(!chs.length) return;
    rows+=`<tr class="part-sep"><td colspan="4">${esc(p)}</td></tr>`;
    chs.forEach(c=>c.cases.forEach((cs,i)=>{
      rows+=`<tr class="crow" data-ch="${c.order}">
        <td class="tnum">${i===0?esc(c.label):''}</td>
        <td class="tcase">${esc(cs.kr)}${cs.en?`<div class="tpart" style="font-style:italic;margin-top:2px">${esc(cs.en)}</div>`:''}</td>
        <td>${cs.keywords.map(k=>`<span class="kw">${esc(k)}</span>`).join('')}</td>
        <td class="tpart">${i===0?esc(c.titleKR):''}</td></tr>`;
    }));
  });
  return `<div class="part-group"><div class="part-h"><span class="pt">서울의 경험으로 선택한 사례 — 키워드 정리</span><span class="pc">총 ${CH.reduce((s,c)=>s+c.caseCount,0)}개 사례</span></div>
    <div class="tbl-wrap"><table class="cases"><thead><tr><th style="width:64px">장</th><th>사례 (핵심 정책·경험)</th><th style="width:32%">키워드</th><th style="width:150px">체계</th></tr></thead><tbody>${rows}</tbody></table></div></div>`;
}

// ---- full-text search ----
function searchAll(q){
  const ql=q.toLowerCase(); const res=[];
  CH.forEach(c=>{ if(partFilter!=='all'&&c.partname!==partFilter) return;
    c.content.forEach((b,bi)=>{
      const txt=b.t==='h'?(b.kr+' '+(b.en||'')):(b.text||'');
      if(txt.toLowerCase().includes(ql)){
        const kind=b.t==='h'?(b.kind==='core'?'core':'h'):'p';
        res.push({c,bi,kind,label:b.t==='h'?(b.kind==='core'?'사례':'소제목'):'본문',text:txt});
      }
    });
  });
  return res;
}
function searchView(){
  const res=searchAll(query);
  if(!res.length) return `<div class="empty">"<b>${esc(query)}</b>" 검색 결과가 없습니다.</div>`;
  const byCh={}; res.forEach(r=>{(byCh[r.c.order]=byCh[r.c.order]||[]).push(r);});
  let html=`<div class="sr-head"><b>"${esc(query)}"</b> — ${res.length}건 (장 ${Object.keys(byCh).length}개)</div>`;
  Object.values(byCh).forEach(items=>{
    items.slice(0,6).forEach(r=>{
      const t=r.text; const idx=t.toLowerCase().indexOf(query.toLowerCase());
      const st=Math.max(0,idx-45); const snip=(st>0?'… ':'')+t.slice(st,idx+query.length+90)+(t.length>idx+query.length+90?' …':'');
      const kc=r.kind==='core'?'k-core':r.kind==='h'?'k-h':'k-p';
      html+=`<div class="sr-item" data-ch="${r.c.order}" data-bi="${r.bi}">
        <div class="sr-src"><span class="chip-sm">${esc(r.c.label)}</span>${esc(r.c.titleKR)} <span class="sr-kind ${kc}">${r.label}</span></div>
        <div class="sr-snip">${hl(snip,query)}</div></div>`;
    });
    if(items.length>6) html+=`<div class="sr-head" style="margin:-2px 0 12px 4px;color:var(--ink3)">… 외 ${items.length-6}건 더 (본문에서 확인)</div>`;
  });
  return html;
}

// ---- reading view ----
function openReader(order,scrollBi){
  const c=CH.find(x=>x.order===order); if(!c) return; curRead=order;
  let toc='', body='', refs=[];
  c.content.forEach((b,bi)=>{
    const id=`b${order}_${bi}`;
    if(b.t==='h'){
      if(b.kind==='refs'){ body+=`<h2 id="${id}" class="refs-h">${esc(b.kr)}${b.en?`<span class="en">${esc(b.en)}</span>`:''}</h2>`; return; }
      if(b.kind==='core'){
        const cs=c.cases.find(x=>x.kr===b.kr);
        const kws=cs?cs.keywords.map(k=>`<span class="kw">${esc(k)}</span>`).join(''):'';
        body+=`<div class="case-h" id="${id}"><span class="cbadge">서울의 경험</span><h2>${esc(b.kr)}${b.en?`<span class="en">${esc(b.en)}</span>`:''}</h2>${kws?`<div class="kws">${kws}</div>`:''}</div>`;
        toc+=`<a href="#${id}" class="t${b.level===1?1:2} core" data-id="${id}">★ ${esc(b.kr)}</a>`;
        return;
      }
      const tag=b.level===1?'h2':b.level===2?'h3':'h4';
      body+=`<${tag} id="${id}">${esc(b.kr)}${b.en?`<span class="en">${esc(b.en)}</span>`:''}</${tag}>`;
      if(b.level<=2) toc+=`<a href="#${id}" class="t${b.level} ${b.kind}" data-id="${id}">${esc(b.kr)}</a>`;
    } else if(b.t==='cap'){ body+=`<div class="cap" id="${id}">▣ ${esc(b.text)}</div>`; }
    else if(b.t==='ref'){ refs.push(b.text); }
    else { body+=`<p id="${id}">${esc(b.text)}</p>`; }
  });
  if(refs.length) body+=`<ul class="refs">${refs.map(r=>`<li>${esc(r)}</li>`).join('')}</ul>`;
  document.getElementById('reader').innerHTML=`
    <div class="rbar"><div class="wrap" style="padding:0"><div class="rbar-in">
      <button class="back" onclick="closeReader()">‹ 목록으로</button>
      <div class="rt">${esc(c.label)} · ${esc(c.titleKR)}<small>${esc(c.partname.replace(/ ·.*/,''))}</small></div>
    </div></div></div>
    <div class="read-layout">
      <nav class="toc">${toc}</nav>
      <article class="read"><div class="doc-h">${esc(c.label)} · ${esc(c.partname.replace(/ ·.*/,''))}</div>
        <h1>${esc(c.titleKR)}</h1><div class="den">${esc(c.titleEN)}</div>${body}</article>
    </div>`;
  document.getElementById('listView').classList.add('off');
  document.getElementById('reader').classList.add('on');
  window.scrollTo(0,0);
  setupTocSpy();
  if(scrollBi!=null){ const el=document.getElementById(`b${order}_${scrollBi}`);
    if(el){ setTimeout(()=>{el.scrollIntoView({block:'center'});el.classList.add('hl');},60); } }
}
function closeReader(){ curRead=null; document.getElementById('reader').classList.remove('on');
  document.getElementById('listView').classList.remove('off'); }
function setupTocSpy(){
  const links=[...document.querySelectorAll('.toc a')];
  const map={}; links.forEach(a=>map[a.dataset.id]=a);
  const obs=new IntersectionObserver(es=>{es.forEach(e=>{ if(e.isIntersecting){
    links.forEach(l=>l.classList.remove('active')); const a=map[e.target.id]; if(a)a.classList.add('active'); }});},
    {rootMargin:'-120px 0px -70% 0px'});
  document.querySelectorAll('article.read [id]').forEach(el=>{ if(map[el.id]) obs.observe(el); });
  links.forEach(a=>a.addEventListener('click',ev=>{ev.preventDefault();
    const el=document.getElementById(a.dataset.id); if(el)el.scrollIntoView({behavior:'smooth',block:'start'});}));
}

// ---- main render ----
function render(){
  const lv=document.getElementById('listView');
  if(query){ lv.innerHTML=searchView();
    lv.querySelectorAll('.sr-item').forEach(it=>it.onclick=()=>openReader(+it.dataset.ch,+it.dataset.bi));
    return; }
  if(view==='table'){ lv.innerHTML=tableView();
    lv.querySelectorAll('tr.crow').forEach(r=>r.onclick=()=>openReader(+r.dataset.ch));
    return; }
  // chapters
  let html='',any=false;
  PARTS.filter(p=>partFilter==='all'||p===partFilter).forEach(p=>{
    const list=CH.filter(c=>c.partname===p&&matchCh(c)); if(!list.length)return; any=true;
    html+=`<div class="part-group"><div class="part-h"><span class="pt">${esc(p)}</span><span class="pc">${list.length}개 장</span></div>
      <div class="grid">${list.map(chapterCard).join('')}</div></div>`;
  });
  lv.innerHTML=any?html:'<div class="empty">결과가 없습니다.</div>';
  lv.querySelectorAll('.card').forEach(c=>c.onclick=()=>openReader(+c.dataset.ch));
}
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&curRead!==null)closeReader();});
buildFilters(); render();
</script>
</body>
</html>'''

out = HTML.replace('__DATA__', DATA_JSON)
with open(os.path.join(HERE, 'index.html'), 'w', encoding='utf-8') as f:
    f.write(out)
print('wrote index.html', round(len(out)/1024), 'KB')
