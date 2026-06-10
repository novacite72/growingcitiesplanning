'use strict';
// ---------- state ----------
let ME=null, ROLES={}, BOOK=null, CH=[], M={}, PARTS=[];
let view='chapters', query='', partFilter='all', curRead=null;
let comments=[], canSeeAll=false, memoMode=true, editMode=false;

const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
function esc(s){return (s||'').replace(/[&<>]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[m]));}
function api(url,opts){return fetch(url,Object.assign({headers:{'Content-Type':'application/json'}},opts)).then(async r=>{const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.error||'오류');return j;});}
function hl(s,q){if(!q)return esc(s);const i=s.toLowerCase().indexOf(q.toLowerCase());if(i<0)return esc(s);return esc(s.slice(0,i))+'<mark>'+esc(s.slice(i,i+q.length))+'</mark>'+esc(s.slice(i+q.length));}
function fmtTime(iso){const d=new Date(iso);const p=n=>String(n).padStart(2,'0');return `${d.getFullYear()}.${p(d.getMonth()+1)}.${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;}

// ---------- auth ----------
$('#loginForm').addEventListener('submit',async e=>{
  e.preventDefault(); $('#li-err').textContent='';
  try{
    await api('/api/login',{method:'POST',body:JSON.stringify({email:$('#li-email').value,password:$('#li-pw').value})});
    await boot();
  }catch(err){$('#li-err').textContent=err.message;}
});
$('#toReg').addEventListener('click',e=>{e.preventDefault();$('#loginForm').classList.add('hidden');$('#regForm').classList.remove('hidden');});
$('#toLogin').addEventListener('click',e=>{e.preventDefault();$('#regForm').classList.add('hidden');$('#loginForm').classList.remove('hidden');});
$('#regForm').addEventListener('submit',async e=>{
  e.preventDefault(); $('#rg-err').textContent='';
  try{
    await api('/api/register',{method:'POST',body:JSON.stringify({email:$('#rg-email').value,name:$('#rg-name').value,role:$('#rg-role').value,password:$('#rg-pw').value})});
    await boot();
  }catch(err){$('#rg-err').textContent=err.message;}
});
async function boot(){
  const r=await api('/api/me'); if(!r.user){showLogin();return;}
  ME=r.user; ROLES=r.roles;
  const d=await api('/api/data'); BOOK=d; CH=d.chapters; M=d.meta; PARTS=[...new Set(CH.map(c=>c.partname))];
  $('#login').classList.add('hidden'); $('#app').classList.remove('hidden');
  $('#h-pub').textContent='발간 · '+M.publisher; $('#h-kr').textContent=M.titleKR; $('#h-en').textContent=M.titleEN;
  $('#st-ch').textContent=CH.length;
  $('#st-case').textContent=CH.reduce((s,c)=>s+c.caseCount,0);
  $('#st-img').textContent=CH.reduce((s,c)=>s+(c.images||0),0);
  $('#foot').innerHTML=M.titleKR+' · '+M.titleEN+' &nbsp;|&nbsp; '+M.publisher+' &nbsp;|&nbsp; 원고 검수 시스템';
  renderUserChip(); buildFilters(); loadAllMemoCount(); render();
}
function showLogin(){$('#app').classList.add('hidden');$('#login').classList.remove('hidden');}
function renderUserChip(){
  const ini=(ME.name||ME.email)[0].toUpperCase();
  $('#userchip').innerHTML=`<div class="ui"><div class="un">${esc(ME.name)}</div><div class="ur">${esc(ME.roleName)} · ${esc(ME.email)}</div></div>
    <div class="uav">${esc(ini)}</div><button class="menu-btn" id="menuBtn">▾</button>`;
  $('#menuBtn').onclick=e=>{e.stopPropagation();$('#umenu').classList.toggle('open');};
  let menu=`<button id="m-pw">비밀번호 변경</button>`;
  if(ME.role==='admin') menu=`<button id="m-users">사용자 관리</button>`+menu;
  menu+=`<button class="sep" id="m-out">로그아웃</button>`;
  $('#umenu').innerHTML=menu;
  $('#m-out').onclick=async()=>{await api('/api/logout',{method:'POST'});location.reload();};
  $('#m-pw').onclick=()=>{$('#umenu').classList.remove('open');openPwModal();};
  if($('#m-users'))$('#m-users').onclick=()=>{$('#umenu').classList.remove('open');openUsers();};
}
document.addEventListener('click',()=>$('#umenu')&&$('#umenu').classList.remove('open'));

// ---------- filters / tabs ----------
function buildFilters(){
  const items=[['all','전체']].concat(PARTS.map(p=>[p,p.replace(/ ·.*$/,'').replace(/^Part \d+\. /,'')]));
  $('#filters').innerHTML=items.map(([v,l])=>`<button class="chip ${v===partFilter?'active':''}" data-f="${v}">${esc(l)}</button>`).join('');
  $$('#filters .chip').forEach(b=>b.onclick=()=>{
    partFilter=b.dataset.f;
    // when reading a chapter, clicking a Part returns to that part's chapter list
    if(curRead!==null) closeReader();
    if(view!=='chapters'){view='chapters';$$('.tab').forEach(x=>x.classList.toggle('active',x.dataset.view==='chapters'));}
    if(query){query='';$('#q').value='';$('#searchBox').classList.remove('has');}
    buildFilters();render();window.scrollTo(0,0);
  });
}
$$('.tab').forEach(t=>t.onclick=()=>{$$('.tab').forEach(x=>x.classList.remove('active'));t.classList.add('active');view=t.dataset.view;closeReader();render();});
$('#q').addEventListener('input',e=>{query=e.target.value.trim();$('#searchBox').classList.toggle('has',!!query);if(curRead===null)render();else if(query){closeReader();render();}});
$('#clrBtn').onclick=()=>{query='';$('#q').value='';$('#searchBox').classList.remove('has');render();};

// ---------- memo counts (header stat) ----------
async function loadAllMemoCount(){
  try{const r=await api('/api/comments');$('#st-memo').textContent=r.comments.length;}catch(e){}
}

// ---------- list / table / search ----------
function chapterCard(c){
  const tops=c.headings.filter(b=>b.level===1||b.kind==='core'||b.kind==='casehead').slice(0,5);
  const ol=tops.map(b=>`<div class="ol"><span class="dot">${b.kind==='core'?'★':'·'}</span><span>${esc(b.kr)}</span></div>`).join('');
  return `<div class="card" data-ch="${c.order}"><span class="num">${esc(c.label)}</span>
    <h3>${esc(c.titleKR)}</h3><div class="cen">${esc(c.titleEN)}</div>
    <div class="outline">${ol}</div>
    <div class="foot"><span class="cc">${c.caseCount?('★ 사례 '+c.caseCount+'선'):''}</span>
      <span class="meta">🖼 ${c.images||0}</span><span class="read">본문 읽기 ›</span></div></div>`;
}
function tableView(){
  let rows='';
  PARTS.filter(p=>partFilter==='all'||p===partFilter).forEach(p=>{
    const chs=CH.filter(c=>c.partname===p&&c.caseCount>0); if(!chs.length)return;
    rows+=`<tr class="part-sep"><td colspan="4">${esc(p)}</td></tr>`;
    chs.forEach(c=>c.cases.forEach((cs,i)=>{
      rows+=`<tr class="crow" data-ch="${c.order}"><td class="tnum">${i===0?esc(c.label):''}</td>
        <td class="tpart">${i===0?esc(c.titleKR):''}</td>
        <td class="tcase">${esc(cs.kr)}${cs.en?`<div class="tpart" style="font-style:italic;margin-top:2px">${esc(cs.en)}</div>`:''}</td>
        <td>${cs.keywords.map(k=>`<span class="kw">${esc(k)}</span>`).join('')}</td></tr>`;
    }));
  });
  return `<div class="part-group"><div class="part-h"><span class="pt">서울의 경험으로 선택한 사례 — 키워드 정리</span><span class="pc">총 ${CH.reduce((s,c)=>s+c.caseCount,0)}개</span></div>
    <div class="tbl-wrap"><table class="cases"><thead><tr><th style="width:60px">장</th><th style="width:130px">체계</th><th>사례 (핵심 정책·경험)</th><th style="width:28%">키워드</th></tr></thead><tbody>${rows}</tbody></table></div></div>`;
}
function searchView(){
  const ql=query.toLowerCase(),res=[];
  CH.forEach(c=>{if(partFilter!=='all'&&c.partname!==partFilter)return;
    c.content.forEach((b,bi)=>{const txt=b.t==='h'?(b.kr+' '+(b.en||'')):(b.text||'');
      if(txt&&txt.toLowerCase().includes(ql))res.push({c,bi,kind:b.t==='h'?(b.kind==='core'?'core':'h'):'p',label:b.t==='h'?(b.kind==='core'?'사례':'소제목'):'본문',text:txt});});});
  if(!res.length)return `<div class="empty">"<b>${esc(query)}</b>" 검색 결과가 없습니다.</div>`;
  const byCh={};res.forEach(r=>{(byCh[r.c.order]=byCh[r.c.order]||[]).push(r);});
  let html=`<div class="sr-head"><b>"${esc(query)}"</b> — ${res.length}건 (장 ${Object.keys(byCh).length}개)</div>`;
  Object.values(byCh).forEach(items=>{items.slice(0,6).forEach(r=>{
    const t=r.text,idx=t.toLowerCase().indexOf(ql),st=Math.max(0,idx-45);
    const snip=(st>0?'… ':'')+t.slice(st,idx+query.length+90)+(t.length>idx+query.length+90?' …':'');
    const kc=r.kind==='core'?'k-core':r.kind==='h'?'k-h':'k-p';
    html+=`<div class="sr-item" data-ch="${r.c.order}" data-bi="${r.bi}"><div class="sr-src"><span class="chip-sm">${esc(r.c.label)}</span>${esc(r.c.titleKR)} <span class="sr-kind ${kc}">${r.label}</span></div><div class="sr-snip">${hl(snip,query)}</div></div>`;
  });
  if(items.length>6)html+=`<div class="sr-head" style="margin:-2px 0 12px 4px;color:var(--ink3)">… 외 ${items.length-6}건 더</div>`;});
  return html;
}

function render(){
  const lv=$('#listView');
  if(query){lv.innerHTML=searchView();$$('#listView .sr-item').forEach(it=>it.onclick=()=>openReader(+it.dataset.ch,+it.dataset.bi));return;}
  if(view==='table'){lv.innerHTML=tableView();$$('#listView tr.crow').forEach(r=>r.onclick=()=>openReader(+r.dataset.ch));return;}
  let html='',any=false;
  PARTS.filter(p=>partFilter==='all'||p===partFilter).forEach(p=>{
    const list=CH.filter(c=>c.partname===p);if(!list.length)return;any=true;
    html+=`<div class="part-group"><div class="part-h"><span class="pt">${esc(p)}</span><span class="pc">${list.length}개 장</span></div><div class="grid">${list.map(chapterCard).join('')}</div></div>`;
  });
  lv.innerHTML=any?html:'<div class="empty">결과가 없습니다.</div>';
  $$('#listView .card').forEach(c=>c.onclick=()=>openReader(+c.dataset.ch));
}

// ---------- reader ----------
async function openReader(order,scrollBi){
  const c=CH.find(x=>x.order===order);if(!c)return;curRead=order;
  try{const r=await api('/api/comments?chapter='+order);comments=r.comments;canSeeAll=r.canSeeAll;}catch(e){comments=[];}
  let toc='',body='',refs=[];
  c.content.forEach((b,bi)=>{
    const id=`b${order}_${bi}`;
    if(b.t==='h'){
      if(b.kind==='refs'){body+=`<h2 class="read-h figs-h" id="${id}">${esc(b.kr)}${b.en?`<span class="en">${esc(b.en)}</span>`:''}</h2>`;return;}
      if(b.kind==='figs'){body+=`<h2 class="read-h figs-h" id="${id}">${esc(b.kr)} · ${esc(b.en||'')}</h2>`;return;}
      if(b.kind==='core'){
        const cs=c.cases.find(x=>x.kr===b.kr);const kws=cs?cs.kws||cs.keywords:null;
        const kw=kws?kws.map(k=>`<span class="kw">${esc(k)}</span>`).join(''):'';
        body+=`<div class="case-h blk" id="${id}" data-bi="${bi}"><span class="cbd">서울의 경험</span><h2>${esc(b.kr)}${b.en?`<span class="en" style="display:block;font-size:14px;font-style:italic;color:#a07b3a;font-weight:500">${esc(b.en)}</span>`:''}</h2>${kw?`<div class="kws">${kw}</div>`:''}${memoUI(id,b.kr)}</div>`;
        toc+=`<a href="#${id}" class="t${b.level===1?1:2} core" data-id="${id}">★ ${esc(b.kr)}</a>`;return;
      }
      const tag=b.level===1?'h2':b.level===2?'h3':'h4';
      body+=`<${tag} class="read-h blk" id="${id}" data-bi="${bi}">${esc(b.kr)}${b.en?`<span class="en">${esc(b.en)}</span>`:''}${memoUI(id,b.kr)}</${tag}>`;
      if(b.level<=2)toc+=`<a href="#${id}" class="t${b.level} ${b.kind}" data-id="${id}">${esc(b.kr)}</a>`;
    }else if(b.t==='img'){
      body+=`<figure id="${id}" class="blk figblk" data-bi="${bi}"><img src="/static/${esc(b.src)}" loading="lazy" alt="그림">${memoUI(id,'그림/사진')}</figure>`;
    }else if(b.t==='table'){
      const rows=b.rows.map((r,ri)=>{const tag=ri===0?'th':'td';return '<tr>'+r.map(c=>`<${tag}>${esc(c).replace(/\n/g,'<br>')}</${tag}>`).join('')+'</tr>';}).join('');
      body+=`<div class="tbl-scroll blk" id="${id}" data-bi="${bi}"><table class="doc-tbl">${rows}</table>${memoUI(id,'표')}</div>`;
    }else if(b.t==='cap'){body+=`<div class="cap blk" id="${id}" data-bi="${bi}">▣ ${esc(b.text)}${memoUI(id,b.text)}</div>`;}
    else if(b.t==='note'){body+=`<div class="docnote" id="${id}">${esc(b.text)}</div>`;}
    else if(b.t==='ref'){refs.push(b.text);}
    else{body+=`<p class="txt blk" id="${id}" data-bi="${bi}">${esc(b.text)}${memoUI(id,b.text)}</p>`;}
  });
  if(refs.length)body+=`<ul class="refs">${refs.map(r=>`<li>${esc(r)}</li>`).join('')}</ul>`;
  const memoN=comments.length;
  $('#reader').innerHTML=`<div class="rbar"><div class="wrap" style="padding:0"><div class="rbar-in">
      <button class="back" onclick="closeReader()">‹ 목록</button>
      <div class="rt">${esc(c.label)} · ${esc(c.titleKR)}<small>${esc(c.partname.replace(/ ·.*/,''))}</small></div>
      ${c.canEdit?`<button class="rbtn" id="editToggle" title="본문 편집">✏️ 편집</button>`:''}
      <button class="rbtn" id="btnDoc" title="Word(.doc) 저장">⬇ DOC</button>
      <button class="rbtn" id="btnPdf" title="PDF 저장(인쇄)">⬇ PDF</button>
      <button class="memo-toggle ${memoMode?'on':''}" id="memoToggle">📝 ${memoN}</button>
    </div></div></div>
    <div class="read-layout"><nav class="toc">${toc}</nav>
      <article class="read"><div class="doc-h">${esc(c.label)} · ${esc(c.partname.replace(/ ·.*/,''))}</div>
        <h1>${esc(c.titleKR)}</h1><div class="den">${esc(c.titleEN)}</div>${body}</article>
      <div class="crail" id="crail"></div></div>`;
  $('#listView').classList.add('off');$('#reader').classList.add('on');window.scrollTo(0,0);
  editMode=false;
  setupReader(order);renderNotes();
  $('#memoToggle').onclick=()=>openMemoPanel(order);
  $('#btnDoc').onclick=()=>exportDoc(c);
  $('#btnPdf').onclick=()=>exportPdf(c);
  if($('#editToggle'))$('#editToggle').onclick=()=>toggleEdit(order);
  if(scrollBi!=null){const el=$('#b'+order+'_'+scrollBi);if(el)setTimeout(()=>{el.scrollIntoView({block:'center'});el.classList.add('hl');},60);}
}
function memoUI(id,anchor){
  return `<button class="addmemo" data-id="${id}" data-anchor="${esc((anchor||'').slice(0,120))}" title="메모 추가">＋</button>`;
}
function closeReader(){curRead=null;$('#reader').classList.remove('on');$('#listView').classList.remove('off');closeMemoPanel();}
window.closeReader=closeReader;

function setupReader(order){
  // image zoom + reposition margin comments once each image settles (height changes)
  $$('article.read figure img').forEach(im=>{
    im.onclick=()=>{$('#zoomImg').src=im.src;$('#imgzoom').classList.add('open');};
    im.addEventListener('load',()=>positionComments());
  });
  // add-memo buttons
  $$('.addmemo').forEach(btn=>btn.onclick=e=>{e.stopPropagation();openComposer(btn.dataset.id,btn.dataset.anchor,order);});
  // toc spy + smooth scroll
  const links=$$('.toc a'),map={};links.forEach(a=>map[a.dataset.id]=a);
  const obs=new IntersectionObserver(es=>{es.forEach(e=>{if(e.isIntersecting){links.forEach(l=>l.classList.remove('active'));const a=map[e.target.id];if(a)a.classList.add('active');}});},{rootMargin:'-120px 0px -70% 0px'});
  $$('article.read [id]').forEach(el=>{if(map[el.id])obs.observe(el);});
  links.forEach(a=>a.onclick=ev=>{ev.preventDefault();gotoBlock(a.dataset.id);});
}
function gotoBlock(id){
  const el=document.getElementById(id);if(!el)return;
  const y=el.getBoundingClientRect().top+window.pageYOffset-118, y0=window.pageYOffset;
  try{window.scrollTo({top:y,behavior:'smooth'});}catch(e){window.scrollTo(0,y);}
  setTimeout(()=>{if(Math.abs(window.pageYOffset-y0)<4)window.scrollTo(0,y);},130);  // smooth 미지원 폴백
  el.classList.add('hl');setTimeout(()=>el.classList.remove('hl'),1700);
}

// ---------- export: .doc / .pdf ----------
function blockExportHTML(b){
  if(b.t==='h'){const tag=b.level===1?'h2':b.level===2?'h3':'h4';return `<${tag}>${esc(b.kr)}${b.en?` <span style="font-weight:400;color:#777;font-style:italic">${esc(b.en)}</span>`:''}</${tag}>`;}
  if(b.t==='img')return `<p style="text-align:center"><img src="${location.origin}/static/${esc(b.src)}" style="max-width:520px;border:1px solid #ccc"></p>`;
  if(b.t==='cap')return `<p style="font-size:10pt;color:#555;font-style:italic;margin:2px 0 12px">${esc(b.text)}</p>`;
  if(b.t==='table')return '<table border="1" cellpadding="5" style="border-collapse:collapse;margin:10px 0;font-size:10pt">'+b.rows.map((r,ri)=>'<tr>'+r.map(c=>`<${ri===0?'th':'td'} style="text-align:left">${esc(c).replace(/\n/g,'<br>')}</${ri===0?'th':'td'}>`).join('')+'</tr>').join('')+'</table>';
  if(b.t==='note')return '';
  if(b.t==='ref')return `<p style="font-size:9pt;color:#666">${esc(b.text)}</p>`;
  return `<p>${esc(b.text)}</p>`;
}
function chapterExportHTML(c){
  return `<h1>${esc(c.label)} · ${esc(c.titleKR)}</h1><p style="color:#666;font-style:italic">${esc(c.titleEN)}</p><hr>`+c.content.map(blockExportHTML).join('');
}
function exportDoc(c){
  const html=`<html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:w="urn:schemas-microsoft-com:office:word" xmlns="http://www.w3.org/TR/REC-html40"><head><meta charset="utf-8"><title>${esc(c.titleKR)}</title></head><body style="font-family:'Malgun Gothic','맑은 고딕',sans-serif;line-height:1.7;font-size:11pt">${chapterExportHTML(c)}</body></html>`;
  const blob=new Blob(['﻿'+html],{type:'application/msword'});
  const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=`${c.label}_${c.titleKR}.doc`;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(a.href),1000);
  toast('Word 문서(.doc)를 저장했습니다.');
}
function exportPdf(c){
  const wasEdit=editMode;if(editMode)toggleEdit(curRead);
  document.body.classList.add('printing');
  toast('인쇄 대화상자에서 "PDF로 저장"을 선택하세요.');
  setTimeout(()=>{window.print();document.body.classList.remove('printing');},250);
}

// ---------- edit mode (관리자=전체, 집필자=배정 장) ----------
function toggleEdit(order){
  editMode=!editMode;
  const art=$('article.read');if(art)art.classList.toggle('editing',editMode);
  const btn=$('#editToggle');if(btn){btn.classList.toggle('on',editMode);btn.textContent=editMode?'✓ 편집 종료':'✏️ 편집';}
  if(editMode){
    $$('article.read .txt.blk, article.read .cap.blk').forEach(el=>el.onclick=ev=>{
      if(ev.target.closest('.addmemo, .blk-editor'))return; openEditor(order,el);});
    toast('편집 모드 — 문단/캡션을 클릭하면 수정창이 열립니다.');
  }else{
    $$('.blk-editor').forEach(e=>e.remove());
    $$('article.read .blk').forEach(el=>el.onclick=null);
  }
}
function openEditor(order,el){
  $$('.blk-editor').forEach(e=>e.remove());
  const idx=+el.id.split('_')[1];
  const ch=CH.find(c=>c.order===order);const b=ch.content[idx];if(!b)return;
  const cur=b.text||'';
  const ed=document.createElement('div');ed.className='blk-editor';
  ed.innerHTML=`<textarea spellcheck="false"></textarea><div class="cb"><button class="cancel">취소</button><button class="save">저장</button></div>`;
  ed.querySelector('textarea').value=cur;
  el.after(ed);const ta=ed.querySelector('textarea');ta.style.height=Math.max(64,ta.scrollHeight+8)+'px';ta.focus();
  ed.querySelector('.cancel').onclick=()=>ed.remove();
  ed.querySelector('.save').onclick=async()=>{
    const val=ta.value;
    try{
      const r=await api('/api/edit',{method:'POST',body:JSON.stringify({chapter:order,blk:idx,value:val})});
      b.text=val;const btn=el.querySelector('.addmemo');
      el.textContent=(b.t==='cap'?'▣ ':'')+val;if(btn){el.appendChild(btn);btn.onclick=e=>{e.stopPropagation();openComposer(btn.dataset.id,btn.dataset.anchor,order);};}
      el.classList.add('edited');ed.remove();toast(r.unchanged?'변경 없음':'저장되었습니다.');positionComments();
    }catch(e){alert(e.message);}
  };
}
let _toastT=null;
function toast(msg){
  let t=$('#toast');if(!t){t=document.createElement('div');t.id='toast';document.body.appendChild(t);}
  t.textContent=msg;t.classList.add('show');clearTimeout(_toastT);_toastT=setTimeout(()=>t.classList.remove('show'),2600);
}

// ---------- threaded comments (메모 · 댓글 · 대댓글 · 대대댓글…) ----------
function roleBadge(role){const cls={admin:'rb-admin',author:'rb-author',reviewer:'rb-reviewer'}[role]||'';return `<span class="rb ${cls}">${esc(ROLES[role]||role)}</span>`;}
function threadMaps(){
  const kids={},roots={};
  comments.forEach(c=>{
    if(c.parent_id){(kids[c.parent_id]=kids[c.parent_id]||[]).push(c);}
    else{(roots[c.block]=roots[c.block]||[]).push(c);}
  });
  return {kids,roots};
}
function renderThread(c,depth,kids){
  const ch=(kids[c.id]||[]).slice().sort((a,b)=>a.id-b.id);
  const acts=[`<button data-reply="${c.id}">↩ 답글</button>`];
  if(depth===0&&(ME.role==='admin'||ME.role==='author'))
    acts.push(`<button data-resolve="${c.id}" data-v="${c.resolved?0:1}">${c.resolved?'미해결로':'✔ 해결'}</button>`);
  if(c.canDelete)acts.push(`<button data-del="${c.id}">삭제</button>`);
  const ind=Math.min(depth,6)*16;
  return `<div class="note ${c.resolved?'resolved':''} ${depth?'reply':''}" id="note${c.id}" ${depth?`style="margin-left:${ind}px"`:''}>
    <div class="nh"><span class="who">${esc(c.name)} ${roleBadge(c.role)}</span><span class="tm">${fmtTime(c.created)}${c.resolved?' · ✔ 해결':''}</span></div>
    <div class="body">${esc(c.body)}</div>
    <div class="acts">${acts.join('')}</div>
    <div class="replies">${ch.map(k=>renderThread(k,depth+1,kids)).join('')}</div>
  </div>`;
}
function marginMode(){return window.innerWidth>1080;}   // 데스크탑=여백 레일 / 모바일=인라인
function renderNotes(){
  const rail=$('#crail');if(!rail)return;
  const margin=marginMode();
  rail.innerHTML='';
  $$('#reader .notes').forEach(n=>n.remove());          // clear inline note blocks
  $$('.blk').forEach(b=>b.classList.remove('hascom'));
  if(!memoMode){positionComments();return;}
  const {kids,roots}=threadMaps();
  const total={};comments.forEach(c=>{total[c.block]=(total[c.block]||0)+1;});
  $$('article.read .blk').forEach(b=>{
    const bid=b.id;if(!roots[bid])return;
    b.classList.add('hascom');
    const inner=`<div class="ccard-h">💬 메모 ${total[bid]}개</div>`+
      roots[bid].slice().sort((a,b)=>a.id-b.id).map(r=>renderThread(r,0,kids)).join('');
    if(margin){   // 데스크탑: 본문 옆 여백 레일
      const card=document.createElement('div');card.className='ccard';card.dataset.block=bid;card.innerHTML=inner;
      card.addEventListener('mouseenter',()=>{b.classList.add('blk-focus');card.classList.add('focus');});
      card.addEventListener('mouseleave',()=>{b.classList.remove('blk-focus');card.classList.remove('focus');});
      rail.appendChild(card);
    }else{        // 모바일: 해당 블록 바로 아래 인라인
      const wrap=document.createElement('div');wrap.className='notes';wrap.dataset.block=bid;wrap.innerHTML=inner;
      b.after(wrap);
    }
  });
  bindNoteActions();
  positionComments();
}
function positionComments(){
  const rail=$('#crail'),art=$('article.read');if(!rail||!art)return;
  if(!marginMode()){rail.style.height='';$$('#crail > *').forEach(c=>{c.style.top='';});return;}
  const artTop=art.getBoundingClientRect().top;
  const items=$$('#crail > *').map(card=>{
    const b=card.dataset.block?document.getElementById(card.dataset.block):null;
    return {card,y:b?(b.getBoundingClientRect().top-artTop):1e9};
  }).sort((a,b)=>a.y-b.y);
  let last=0;
  items.forEach(({card,y})=>{const top=Math.max(y,last+8);card.style.top=top+'px';last=top+card.offsetHeight;});
  rail.style.height=Math.max(art.offsetHeight,last+20)+'px';
}
let _rzTimer=null,_lastMargin=null;
window.addEventListener('resize',()=>{
  if(curRead===null)return;
  clearTimeout(_rzTimer);
  _rzTimer=setTimeout(()=>{
    const m=marginMode();
    if(m!==_lastMargin){_lastMargin=m;renderNotes();}   // 모드 전환 시 재구성
    else positionComments();
  },120);
});
function bindNoteActions(){
  $$('.note [data-del]').forEach(b=>b.onclick=async()=>{if(!confirm('이 메모와 하위 답글을 모두 삭제할까요?'))return;await api('/api/comments/'+b.dataset.del,{method:'DELETE'});await reloadComments();});
  $$('.note [data-resolve]').forEach(b=>b.onclick=async()=>{await api('/api/comments/'+b.dataset.resolve+'/resolve',{method:'POST',body:JSON.stringify({resolved:+b.dataset.v})});await reloadComments();});
  $$('.note [data-reply]').forEach(b=>b.onclick=()=>openReplyComposer(+b.dataset.reply));
}
async function reloadComments(){
  if(curRead===null)return;
  try{const r=await api('/api/comments?chapter='+curRead);comments=r.comments;}catch(e){comments=[];}
  renderNotes();
  const mt=$('#memoToggle');if(mt){mt.textContent='📝 메모 '+comments.length;mt.classList.toggle('on',comments.length>0);}
  loadAllMemoCount();
}
function composerHTML(label,ph){
  return `<textarea placeholder="${ph}"></textarea><div class="cb"><button class="cancel">취소</button><button class="save">${label}</button></div>`;
}
function openComposer(bid,anchor,order){   // 새 메모(뿌리)
  $$('.composer').forEach(c=>c.remove());
  const host=$('#'+CSS.escape(bid));if(!host)return;host.classList.add('blk-focus');
  const cm=document.createElement('div');cm.className='composer';cm.dataset.block=bid;
  const ph=anchor==='그림/사진'?'이 그림에 대한 메모를 입력하세요…':'이 문단에 대한 메모를 입력하세요…';
  cm.innerHTML=`<div class="ccard-h">💬 새 메모</div>`+composerHTML('메모 저장',ph);
  if(marginMode()){$('#crail').appendChild(cm);positionComments();}
  else{host.after(cm);}   // 모바일: 블록 바로 아래
  const ta=cm.querySelector('textarea');ta.focus();ta.scrollIntoView({block:'center'});
  cm.querySelector('.cancel').onclick=()=>{cm.remove();host.classList.remove('blk-focus');positionComments();};
  cm.querySelector('.save').onclick=async()=>{
    const body=ta.value.trim();if(!body)return;
    await api('/api/comments',{method:'POST',body:JSON.stringify({chapter:order,block:bid,anchor,body})});
    host.classList.remove('blk-focus');memoMode=true;await reloadComments();
  };
}
function openReplyComposer(pid){           // 답글(댓글·대댓글·대대댓글…)
  $$('.composer').forEach(c=>c.remove());
  const note=$('#note'+pid);if(!note)return;
  const rep=note.querySelector(':scope > .replies');
  const cm=document.createElement('div');cm.className='composer reply';
  cm.innerHTML=composerHTML('답글 저장','답글을 입력하세요…');
  rep.prepend(cm);positionComments();const ta=cm.querySelector('textarea');ta.focus();
  cm.querySelector('.cancel').onclick=()=>{cm.remove();positionComments();};
  cm.querySelector('.save').onclick=async()=>{
    const body=ta.value.trim();if(!body)return;
    await api('/api/comments',{method:'POST',body:JSON.stringify({parent_id:pid,body})});
    await reloadComments();
  };
}
function refreshMemoCounts(){loadAllMemoCount();}

// ---------- memo panel ----------
function openMemoPanel(order){
  const c=CH.find(x=>x.order===order);
  $('#mp-title').textContent=`메모 · ${c.label} ${c.titleKR}`;
  const body=$('#mp-body');
  const roots=comments.filter(n=>!n.parent_id);
  const replyCount={};comments.forEach(n=>{if(n.parent_id)replyCount[n.parent_id]=(replyCount[n.parent_id]||0)+1;});
  if(!roots.length){body.innerHTML='<div class="mp-empty">아직 메모가 없습니다.<br>본문 문단 오른쪽 ＋ 버튼으로 메모를 남겨보세요.</div>';}
  else{body.innerHTML=`<div style="font-size:12.5px;color:var(--ink3);margin-bottom:10px">메모 ${roots.length}건 · 답글 포함 총 ${comments.length}건</div>`+
    roots.map(n=>{const rc=replyCount[n.id]||0;return `<div class="mp-note" data-b="${esc(n.block)}">
    ${n.anchor?`<div class="anchor">"${esc(n.anchor)}"</div>`:''}
    <div style="font-size:12px;font-weight:700">${esc(n.name)} ${roleBadge(n.role)} <span style="color:var(--ink3);font-weight:400">· ${fmtTime(n.created)}${n.resolved?' · ✔ 해결':''}</span></div>
    <div class="body">${esc(n.body)}</div>${rc?`<div style="font-size:11.5px;color:var(--han);font-weight:600;margin-top:4px">↩ 답글 ${rc}개</div>`:''}</div>`;}).join('');
    $$('#mp-body .mp-note').forEach(el=>el.onclick=()=>{const t=$('#'+CSS.escape(el.dataset.b));if(t){closeMemoPanel();t.scrollIntoView({block:'center'});t.classList.add('hl');setTimeout(()=>t.classList.remove('hl'),2600);}});
  }
  $('#memoPanel').classList.add('open');$('#overlay').classList.add('open');
}
function closeMemoPanel(){$('#memoPanel').classList.remove('open');$('#overlay').classList.remove('open');}
$('#mp-close').onclick=closeMemoPanel;$('#overlay').onclick=closeMemoPanel;
$('#imgzoom').onclick=()=>$('#imgzoom').classList.remove('open');

// ---------- password modal ----------
function openModal(html){$('#modalCard').innerHTML=html;$('#modalBg').classList.add('open');}
function closeModal(){$('#modalBg').classList.remove('open');}
$('#modalBg').onclick=e=>{if(e.target.id==='modalBg')closeModal();};
function openPwModal(){
  openModal(`<div class="modal-head"><h2>비밀번호 변경</h2><button class="x" onclick="closeModal()">×</button></div>
  <div class="modal-body"><div class="adduser" style="grid-template-columns:1fr">
    <input type="password" id="pw-old" placeholder="현재 비밀번호">
    <input type="password" id="pw-new" placeholder="새 비밀번호 (6자 이상)">
    <div class="msg" id="pw-msg"></div>
    <button class="btn btn-primary" id="pw-save" style="margin-top:0">변경</button></div></div>`);
  $('#pw-save').onclick=async()=>{try{await api('/api/password',{method:'POST',body:JSON.stringify({old:$('#pw-old').value,new:$('#pw-new').value})});$('#pw-msg').style.color='var(--green)';$('#pw-msg').textContent='변경되었습니다.';setTimeout(closeModal,900);}catch(e){$('#pw-msg').style.color='var(--red)';$('#pw-msg').textContent=e.message;}};
}
window.closeModal=closeModal;

// ---------- admin: users ----------
async function openUsers(){
  const r=await api('/api/users');ADMIN_CHAPTERS=r.chapters;
  const chapName=o=>{const c=r.chapters.find(x=>x.order===o);return c?c.label:o;};
  const rows=r.users.map(u=>{
    const chips=(u.chapters||[]).map(o=>`<span class="chipmini">${esc(chapName(o))}</span>`).join('')||'<span class="tpart">없음</span>';
    return `<tr><td><b>${esc(u.name)}</b><div class="tpart">${esc(u.email)}</div></td>
    <td><select data-role="${esc(u.email)}">${Object.entries(r.roles).map(([k,v])=>`<option value="${k}" ${u.role===k?'selected':''}>${v}</option>`).join('')}</select></td>
    <td>${u.role==='admin'?'<span class="tpart">전체</span>':`<div class="asgn">${chips}</div><button class="back asgnbtn" style="padding:3px 8px;font-size:11px;margin-top:4px" data-asgn="${esc(u.email)}">장 배정 수정</button>`}</td>
    <td class="tpart">${u.comments}</td>
    <td><button class="back" style="padding:4px 9px;font-size:12px" data-save="${esc(u.email)}">저장</button>
    ${u.email===ME.email?'':`<button class="back" style="padding:4px 9px;font-size:12px;color:var(--red);margin-left:4px" data-deluser="${esc(u.email)}">삭제</button>`}</td></tr>`;}).join('');
  openModal(`<div class="modal-head"><h2>사용자 · 권한 관리</h2>
     <div style="display:flex;gap:8px"><button class="rbtn" id="btnLog" style="background:rgba(255,255,255,.2);color:#fff">📝 편집 로그</button><button class="x" onclick="closeModal()">×</button></div></div>
   <div class="modal-body">
    <p class="tpart" style="margin:0 0 12px">집필자=배정 장 <b>편집</b>, 감수자=배정 장 <b>열람·메모</b>, 관리자=전체. 역할 변경 후 <b>저장</b>.</p>
    <table class="users"><thead><tr><th>이름 / ID</th><th>역할</th><th>배정 장</th><th>메모</th><th></th></tr></thead><tbody>${rows}</tbody></table>
    <div class="adduser"><h4>＋ 사용자 추가</h4>
      <input id="nu-name" placeholder="이름"><input id="nu-email" placeholder="이메일">
      <select id="nu-role">${Object.entries(r.roles).map(([k,v])=>`<option value="${k}" ${k==='reviewer'?'selected':''}>${v}</option>`).join('')}</select>
      <input id="nu-pw" placeholder="초기 비밀번호 (6자+)">
      <div class="msg" id="nu-msg"></div>
      <button class="btn btn-primary full" id="nu-add" style="margin-top:0">추가</button></div></div>`);
  $('#btnLog').onclick=openEditLog;
  $$('[data-save]').forEach(b=>b.onclick=async()=>{const em=b.dataset.save;
    await api('/api/users/'+encodeURIComponent(em),{method:'PUT',body:JSON.stringify({role:$(`select[data-role="${em}"]`).value})});b.textContent='✓';setTimeout(()=>b.textContent='저장',1000);});
  $$('[data-deluser]').forEach(b=>b.onclick=async()=>{if(!confirm(b.dataset.deluser+' 계정을 삭제할까요?'))return;await api('/api/users/'+encodeURIComponent(b.dataset.deluser),{method:'DELETE'});openUsers();});
  $$('[data-asgn]').forEach(b=>b.onclick=()=>openAssign(b.dataset.asgn,r.users.find(u=>u.email===b.dataset.asgn).chapters||[]));
  $('#nu-add').onclick=async()=>{try{await api('/api/users',{method:'POST',body:JSON.stringify({name:$('#nu-name').value,email:$('#nu-email').value,role:$('#nu-role').value,password:$('#nu-pw').value})});openUsers();}catch(e){$('#nu-msg').style.color='var(--red)';$('#nu-msg').textContent=e.message;}};
}
let ADMIN_CHAPTERS=[];
function openAssign(email,current){
  const set=new Set(current);
  const boxes=ADMIN_CHAPTERS.map(c=>`<label class="asgnchk"><input type="checkbox" value="${c.order}" ${set.has(c.order)?'checked':''}> ${esc(c.label)} <span class="tpart">${esc(c.titleKR)}</span></label>`).join('');
  openModal(`<div class="modal-head"><h2>장 배정 · ${esc(email)}</h2><button class="x" onclick="closeModal()">×</button></div>
    <div class="modal-body"><div class="asgngrid">${boxes}</div>
    <div class="msg" id="as-msg"></div>
    <div style="display:flex;gap:8px;margin-top:14px"><button class="btn btn-primary" id="as-save" style="margin-top:0">저장</button>
      <button class="back" onclick="openUsers()">← 목록</button></div></div>`);
  $('#as-save').onclick=async()=>{
    const chs=$$('.asgngrid input:checked').map(i=>+i.value);
    await api('/api/assignments/'+encodeURIComponent(email),{method:'PUT',body:JSON.stringify({chapters:chs})});
    $('#as-msg').style.color='var(--green)';$('#as-msg').textContent='저장되었습니다.';setTimeout(openUsers,700);
  };
}
async function openEditLog(){
  const r=await api('/api/editlog');
  const rows=r.log.map(e=>`<tr><td class="tpart" style="white-space:nowrap">${fmtTime(e.ts)}</td><td><b>${esc(e.name)}</b> ${roleBadge(e.role)}</td>
    <td class="tnum">${esc(e.chapterLabel)}</td><td style="font-size:12px"><span style="color:var(--red);text-decoration:line-through">${esc((e.oldv||'').slice(0,40))}</span> → <span style="color:var(--green)">${esc((e.newv||'').slice(0,40))}</span></td></tr>`).join('')||'<tr><td colspan="4" class="tpart" style="padding:20px;text-align:center">편집 기록이 없습니다.</td></tr>';
  openModal(`<div class="modal-head"><h2>편집 로그 (${r.log.length})</h2><button class="x" onclick="closeModal()">×</button></div>
    <div class="modal-body"><table class="users"><thead><tr><th>시각</th><th>편집자</th><th>장</th><th>변경(이전→이후)</th></tr></thead><tbody>${rows}</tbody></table>
    <button class="back" style="margin-top:14px" onclick="openUsers()">← 사용자 관리</button></div>`);
}

document.addEventListener('keydown',e=>{if(e.key==='Escape'){if($('#imgzoom').classList.contains('open'))$('#imgzoom').classList.remove('open');else if($('#memoPanel').classList.contains('open'))closeMemoPanel();else if($('#modalBg').classList.contains('open'))closeModal();else if(curRead!==null)closeReader();}});

boot();
