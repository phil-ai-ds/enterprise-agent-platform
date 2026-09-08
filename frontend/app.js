/* ============ Enterprise Agent Platform · App ============ */
const $=id=>document.getElementById(id);
let TOKEN=localStorage.getItem('eap_tok')||'';
let ME=JSON.parse(localStorage.getItem('eap_me')||'null');
let C={}; // page state

/* ---------- API ---------- */
async function api(path,opts={}){
  const h={'Content-Type':'application/json'};
  if(TOKEN)h['Authorization']='Bearer '+TOKEN;
  const r=await fetch('/api'+path,{...opts,headers:{...h,...(opts.headers||{})}});
  const txt=await r.text();
  let j={};try{j=txt?JSON.parse(txt):{};}catch(e){j={detail:txt.slice(0,200)};}
  if(!r.ok)throw new Error(j.detail||('HTTP '+r.status));
  return j;
}
function esc(s){return (s==null?'':String(s)).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function fill(u){$('lu').value=u;$('lp').value='demo123';}
function isAdmin(){return ME&&ME.role==='platform_admin';}
function setTitle(t){$('title').textContent=t;}
function setSub(t){$('subtitle').textContent=t||'';}
function toast(msg,type){
  const el=$('toast');el.textContent=msg;el.className='toast '+(type||'');
  el.style.display='block';clearTimeout(el._t);el._t=setTimeout(()=>el.style.display='none',3400);
}
function scopePill(x){return '<span class="pill '+esc(x)+'">'+esc(x)+'</span>';}
function stPill(x){return '<span class="pill '+esc(x)+'">'+esc(x)+'</span>';}
function fmtSize(n){if(n==null)return '';if(n<1024)return n+' B';if(n<1048576)return (n/1024).toFixed(1)+' KB';return (n/1048576).toFixed(1)+' MB';}
function fmtTime(iso){if(!iso)return '-';const d=new Date(iso);if(isNaN(d))return iso.slice(0,16).replace('T',' ');const p=n=>String(n).padStart(2,'0');return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;}
function btnSpin(btn,on,text){if(on){btn.dataset.txt=btn.innerHTML;btn.disabled=true;btn.innerHTML='<span class="spin"></span> '+(text||'处理中…');}else{btn.disabled=false;if(btn.dataset.txt)btn.innerHTML=btn.dataset.txt;}}

async function login(){
  try{const r=await api('/login',{method:'POST',body:JSON.stringify({username:$('lu').value,password:$('lp').value})});
    TOKEN=r.token;ME=r.user;localStorage.setItem('eap_tok',TOKEN);localStorage.setItem('eap_me',JSON.stringify(ME));
    $('login').style.display='none';$('app').style.display='flex';boot();}
  catch(e){$('lerr').textContent=e.message;}
}
function logout(){TOKEN='';localStorage.removeItem('eap_tok');localStorage.removeItem('eap_me');location.reload();}

/* ---------- Modal ---------- */
function openModal(html,w){
  $('modalBox').innerHTML=html;
  $('modalBox').style.maxWidth=w||'680px';
  $('modal-mask').style.display='flex';
}
function closeModal(){$('modal-mask').style.display='none';}

/* ---------- Boot & Nav ---------- */
const ICO={dash:'◈',chat:'✉',agents:'◉',skills:'◇',workflows:'⇄',ws:'▤',mem:'♆',usage:'∷',ref:'↻',flows:'⧉',
  ov:'◈','admin-usage':'∷',prov:'⌁',aagents:'◉',askill:'◇',users:'☺'};
const PAGES={dash:vc_dash,chat:vc_chat,agents:vc_agents,skills:vc_skills,workflows:vc_workflows,flows:vc_flows,mem:vc_mem,usage:vc_usage,ref:vc_ref,
  ov:vc_ov,'admin-usage':vc_admin_usage,prov:vc_prov,aagents:vc_aagents,askill:vc_askill,users:vc_users};
function boot(){
  $('app').style.display='flex';
  const nm=ME.display_name||ME.username; $('sideName').textContent=nm;
  $('sideTeam').textContent=ME.team||(isAdmin()?'平台管理员':'无团队');
  $('myAvatar').textContent=(nm||'?').slice(0,1).toUpperCase();
  const groups=[
    ['使用',[['dash','总览'],['chat','Agent 工作台'],['flows','流程演示']]],
    ['构建',[['agents','Agents'],['skills','技能工作室'],['workflows','工作流']]],
    ['数据',[['mem','记忆'],['ref','反思日志'],['usage','用量']]],
  ];
  if(isAdmin())groups.push(['平台管理',[['ov','总览'],['admin-usage','全局用量'],['prov','Providers'],['aagents','Agent 管理'],['askill','技能治理'],['users','用户']]]);
  $('nav').innerHTML=groups.map(g=>'<div class="grp">'+g[0]+'</div>'+g[1].map(i=>{
    const [id,label]=i;return `<a data-v="${id}"><span class="nav-ico">${ICO[id]||'·'}</span><span class="txt">${label}</span></a>`;}).join('')).join('');
  $('nav').querySelectorAll('a').forEach(a=>a.onclick=e=>{e.preventDefault();show(a.dataset.v);});
  show('dash');
}
async function show(v){
  $('nav').querySelectorAll('a').forEach(a=>a.classList.toggle('active',a.dataset.v===v));
  C.page=v;
  try{await PAGES[v]();}catch(e){$('view').innerHTML='<div class="card" style="color:var(--red)">'+esc(e.message)+'</div>';}
}
function loader(){return '<div class="loader">加载中…</div>';}

/* ================= Dashboard ================= */
async function vc_dash(){
  setTitle('总览');setSub('你的 Agent 与技能构建工作台');
  $('view').innerHTML='<div class="stat-grid" id="dstat"></div><div class="grid2" style="margin-top:12px"><div><div class="card"><div class="spread"><b>最近对话</b><span class="mut small">去对话页体验工作区/搜索/代码</span></div><div id="dchats"></div></div></div><div><div class="card"><div class="spread"><b>最近用量</b></div><div id="dusage"></div></div></div></div>';
  const [agents,skills,wss,usage]=await Promise.all([
    api('/agents').catch(()=>[]),api('/skills').catch(()=>[]),api('/workspaces').catch(()=>[]),api('/usage/me/recent?limit=6').catch(()=>[])]);
  const nMy=(agents||[]).filter(a=>a.workspace&&a.workspace.kind==='personal').length;
  $('dstat').innerHTML=
    stat('我的 Agents',agents.length,'◉')+stat('可见技能',skills.length,'◇')+
    stat('工作区',wss.length,'▤')+stat('个人 Agent',nMy,'◈');
  const el=$('dchats');
  if(agents.length){el.innerHTML=agents.slice(0,4).map(a=>`<div class="file-item"><span class="file-ico">◉</span><div style="flex:1;min-width:0"><div class="file-name">${esc(a.name)}</div><div class="file-meta">${esc((a.workspace||{}).label||'')} · ${esc((a.skills||[]).length||0)} 技能</div></div><button class="btn btn-sm btn-ghost" onclick="goChat(${a.id})">对话</button></div>`).join('')||'<div class="empty">还没有 Agent —— 试试「Agents」页用一句话创建</div>';}
  $('dusage').innerHTML='<table class="tbl"><tr><th>时间</th><th>对象</th><th>kind</th><th>成本$</th></tr>'+(usage||[]).map(u=>`<tr><td class="small mut">${fmtTime(u.ts)}</td><td>${esc(u.agent)}</td><td><span class="pill">${esc(u.kind)}</span></td><td>${u.cost_usd}</td></tr>`).join('')+'</table>'||'<div class="empty">暂无用量</div>';
}
function stat(k,v,ico){return `<div class="stat"><div class="mut">${ico} ${k}</div><div class="v">${v}</div></div>`;}

/* ================= Agent 工作台（工作区管理与选择 × Agent 对话 · 两 Tab 合并） ================= */
// 理念：工作区与 Agent 解耦。左边始终是「工作区管理与选择」（个人/团队/组织空间 + 文件夹树），
// 右边是 Agent（选哪个 Agent 干活）。Agent 记住上次工作的 工作区+文件夹，默认选中，可手动切换。
let curAgentSel=null;
const AG_SEL=()=>$('ag'); // 隐藏的事实来源 select（其它函数依赖 $('ag')）
let PEND_AGENT=null; // goChat 预选 Agent

async function vc_chat(){
  setTitle('Agent 工作台');setSub('左侧选工作区与文件夹 · 右侧选 Agent · Agent 会记住上次工作的文件夹，多个 Agent 可在同一文件夹协作');
  $('topActions').innerHTML=`<button class="btn btn-ghost btn-sm" id="btnRef2" onclick="showRefModal()" style="display:none">↻ 反思历史</button>
    <button class="btn btn-ghost btn-sm" onclick="goAgents()">＋ 新建 Agent</button>`;
  $('view').innerHTML=`<select id="ag" style="display:none"></select>
  <div style="display:grid;grid-template-columns:minmax(320px,36%) 1fr;gap:12px;align-items:start" class="wb-grid">
    <div class="card" style="margin:0;padding:12px">
      <div class="spread" style="margin-bottom:8px">
        <b style="font-size:13px">▤ 工作区</b>
        <div class="row" style="gap:4px">
          <label class="btn btn-ghost btn-sm" style="cursor:pointer;padding:2px 7px" title="上传文件到当前工作区">↑<input type="file" id="wbUpFile" multiple style="display:none" onchange="wbUpload(this.files)"></label>
          <button class="btn btn-ghost btn-sm" style="padding:2px 7px" onclick="wbNewDoc()" title="新建文本文档">＋</button>
          <button class="btn btn-ghost btn-sm" style="padding:2px 7px" onclick="loadWsTree(true)" title="刷新文件树">↻</button>
        </div>
      </div>
      <div id="wsTabs" class="ws-tabs2"></div>
      <div class="mut small" style="margin:6px 0">📁 点名称展开 · 点「工」=设为工作目录 · ＋=加入参考；📄 点行预览 · ＋=参考</div>
      <div id="wsTree" style="max-height:calc(100vh - 300px);overflow-y:auto;font-size:13px"></div>
    </div>
    <div style="display:flex;flex-direction:column;gap:10px;min-width:0">
      <div class="card" style="margin:0;padding:10px 12px">
        <div class="spread" style="margin-bottom:6px"><b style="font-size:13px">◉ Agents</b><span class="mut small">切换 Agent 自动恢复其上次的工作文件夹</span></div>
        <div id="agList" style="display:flex;flex-wrap:wrap;gap:6px"></div>
        <div id="agInfo" class="mut small" style="margin-top:7px;display:none"></div>
      </div>
      <div class="card" style="margin:0;display:flex;flex-direction:column;flex:1;min-height:46vh">
        <div id="ctxBar" style="display:none;border-bottom:1px solid var(--border);padding:7px 0 9px;margin-bottom:8px"></div>
        <div id="refBar" style="display:none;border-bottom:1px solid var(--border);padding:0 0 9px;margin-bottom:8px"></div>
        <div id="cb" class="chatbox" style="flex:1;min-height:30vh"></div>
        <div class="chat-input-row"><input id="msg" class="inp" placeholder="输入任务… Enter 发送（在当前工作目录执行，参考材料随消息注入）" style="flex:1">
        <button class="btn btn-primary" onclick="send()">发送</button></div>
        <div class="mut small" style="margin-top:6px">👍/👎 反馈让 Agent 反思迭代 · Agent 的读写工具只在「当前工作目录」内（.. 可回工作区上层），产出默认落到该目录</div>
      </div>
    </div>
  </div>`;
  C.wsTree={}; C.refs=[]; C.expanded={}; C.folder=''; C.wsFiles=[];
  const [agents,wss]=await Promise.all([api('/agents'),api('/workspaces').catch(()=>[])]);
  C.agents=agents; C.wss=wss;
  $('ag').onchange=()=>{onAgentChange();};
  $('msg').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send();}});
  renderAgentList();
  if(!C.agents.length){$('agList').innerHTML='<div class="empty">还没有 Agent</div>';$('cb').innerHTML='';addMsg('agent','还没有可用 Agent。去「Agents」页用一句话创建一个吧。');return;}
  // 选择：goChat 预选 or 默认第一个
  const want=PEND_AGENT&&C.agents.some(a=>a.id==PEND_AGENT)?PEND_AGENT:C.agents[0].id;
  PEND_AGENT=null;
  AG_SEL().value=want; onAgentChange();
}
function renderAgentList(){
  const el=$('agList'); if(!el) return;
  const sel=AG_SEL();
  const prev=sel?sel.value:'';   // 重建 options 会重置 selection，先保存
  if(sel) sel.innerHTML=C.agents.map(a=>`<option value="${a.id}">${esc(a.name)}</option>`).join('');
  if(sel&&prev) sel.value=prev;
  const cur=sel?sel.value:'';
  el.innerHTML=C.agents.map(a=>{
    const on=a.id==cur;
    return `<button class="ag-chip ${on?'on':''}" data-id="${a.id}" onclick="pickAgent(${a.id})" title="${esc(a.description||'')}">
      ${esc(a.name)} ${scopePill(a.scope)}</button>`;
  }).join('');
  const a=C.agents.find(x=>x.id==cur);
  const info=$('agInfo');
  if(info&&a){
    const wsLab=(a.workspace&&a.workspace.label)||'';
    const folder=(a.pref&&a.pref.folder)?(' · 📁 /'+a.pref.folder):'';
    info.style.display='block';
    info.innerHTML=`<b style="color:var(--fg)">${esc(a.name)}</b> · ${esc(a.description||'')}
      ${(a.skills||[]).length?` · 🧩 ${esc((a.skills||[]).join('、'))}`:''}
      <span style="opacity:.85"> · 上次位置：▤ ${esc(wsLab)}${folder}</span>`;
  }
}
function pickAgent(id){AG_SEL().value=id;onAgentChange();}
function curAgent(){return C.agents.find(x=>x.id==AG_SEL().value);}
async function onAgentChange(){
  const a=curAgent(); if(!a) return;
  document.querySelectorAll('.ag-chip').forEach(c=>c.classList.toggle('on',+c.dataset.id==a.id));
  renderAgentList();
  $('btnRef2').style.display='inline-flex';
  clearChat();
  C.refs=[]; C.expanded={};
  // 恢复该 Agent 上次的工作位置：pref > Agent 默认空间
  const pref=a.pref||{};
  let wsId=pref.workspace_id||(a.workspace&&a.workspace.id);
  const inWss=(C.wss||[]).some(w=>w.id==wsId);
  if(!inWss) wsId=(C.wss&&C.wss[0])?C.wss[0].id:null;
  C.wsId=wsId; C.folder=(wsId==pref.workspace_id)?(pref.folder||''):'';
  renderWsTabs(); renderCtxBar(); renderRefBar();
  if(wsId) await loadWsTree(); else $('wsTree').innerHTML='<div class="empty">没有可见工作区</div>';
}
/* ---------- 左栏：工作区管理与选择 ---------- */
function renderWsTabs(){
  const el=$('wsTabs'); if(!el) return;
  el.innerHTML=(C.wss||[]).map(w=>`<button class="ws-tab ${C.wsId==w.id?'active':''}" data-id="${w.id}" onclick="pickWs(${w.id})" title="${esc(w.label)} · ${w.can_write?'可读写':'只读'} · ${w.file_count} 文件">${esc(w.kind==='personal'?'👤':w.kind==='team'?'👥':'🏢')} ${esc(w.label)}</button>`).join('')
    ||'<div class="empty">无可见工作区</div>';
}
async function pickWs(id){
  if(C.wsId==id) return;
  C.wsId=id; C.folder=''; C.refs=[]; C.expanded={};
  renderWsTabs(); renderCtxBar(); renderRefBar(); saveWsPref();
  await loadWsTree();
}
function curWsObj(){return (C.wss||[]).find(w=>w.id==C.wsId);}
async function loadWsTree(silent){
  const treeEl=$('wsTree'); if(!treeEl||!C.wsId) return;
  if(!silent) treeEl.innerHTML='<div class="mut small" style="padding:8px">加载中…</div>';
  try{
    const d=await api(`/workspaces/${C.wsId}/files`);
    C.wsFiles=d.files||[]; C.wsCanWrite=d.workspace&&d.workspace.can_write;
    renderWsTree();
  }catch(e){treeEl.innerHTML='<div class="mut small" style="color:var(--red)">'+esc(e.message)+'</div>';}
}
function iconFor(p){const e=(p||'').split('.').pop().toLowerCase();if(['md','txt','csv','json','yaml','yml','py','js','html'].includes(e))return '📄';if(['png','jpg','jpeg','gif','webp','pdf'].includes(e))return '🖼';if(['xlsx','xls','doc','docx','ppt','pptx'].includes(e))return '📊';return '📎';}
function renderWsTree(){
  const el=$('wsTree'); if(!el) return;
  const files=C.wsFiles||[];
  const root={name:'',children:{}};
  files.forEach(f=>{
    const segs=f.path.split('/');
    let node=root;
    segs.forEach((sg,i)=>{
      const isLast=i===segs.length-1;
      if(!node.children[sg])node.children[sg]={name:sg,kind:isLast?f.kind:'dir',children:{},path:segs.slice(0,i+1).join('/'),size:f.size||0};
      node=node.children[sg];
    });
  });
  const isOpen=p=>C.expanded[p]!==false;
  const isRef=p=>C.refs.some(r=>r.path===p);
  const isWork=p=>C.folder===p;
  function rowBtn(kind,path,label,title,on){
    const cls=on?'wt-ib on':'wt-ib';
    return `<span class="${cls}" title="${title}" onclick="event.stopPropagation();${kind}('${esc(path)}')">${label}</span>`;
  }
  function renderChildren(node,depth){
    let html='';
    const names=Object.keys(node.children).sort((a,b)=>{
      const ka=node.children[a].kind==='dir'?0:1,kb=node.children[b].kind==='dir'?0:1;
      return ka-kb||a.localeCompare(b);
    });
    names.forEach(nm=>{
      const ch=node.children[nm];
      const pad=`padding-left:${depth*14}px`;
      if(ch.kind==='dir'){
        const open=isOpen(ch.path); const refOn=isRef(ch.path); const workOn=isWork(ch.path);
        html+=`<div style="${pad}">
          <div class="wt-row ${workOn?'work':''}" style="display:flex;align-items:center;gap:3px;padding:2.5px 4px;border-radius:6px;cursor:pointer" onclick="toggleDir('${esc(ch.path)}')">
            <span style="width:13px;font-size:10px;color:var(--fg4)">${open?'▾':'▸'}</span>
            <span title="设为工作目录" style="cursor:pointer;font-size:12px;${workOn?'color:var(--brand)':'color:var(--fg4)'}" onclick="event.stopPropagation();setWorkFolder('${esc(ch.path)}')">${workOn?'●':'○'}</span>
            <span>📁</span><span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;${workOn?'color:var(--brand);font-weight:600':''}">${esc(nm)}</span>
            ${rowBtn('toggleRef',ch.path,refOn?'✓':'＋',refOn?'移除参考':'加入参考',refOn)}
          </div>
          ${open?renderChildren(ch,depth+1):''}</div>`;
      }else{
        const refOn=isRef(ch.path);
        html+=`<div style="${pad}">
          <div class="wt-row" style="display:flex;align-items:center;gap:3px;padding:2.5px 4px;border-radius:6px;cursor:pointer" onclick="wbPreview('${esc(ch.path)}')" title="预览 /${esc(ch.path)}">
            <span style="width:13px"></span><span style="width:13px"></span>
            <span>${iconFor(ch.path)}</span>
            <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;${refOn?'color:var(--brand);font-weight:500':''}">${esc(nm)}</span>
            ${refOn?'<span style="color:var(--brand);font-size:11px">✓</span>':''}
            ${rowBtn('toggleRef',ch.path,'＋','加入参考',refOn)}
          </div></div>`;
      }
    });
    return html;
  }
  el.innerHTML=files.length?renderChildren(root,0):'<div class="empty">工作区为空 · 点 ↑ 上传或 ＋ 新建文档</div>';
}
function toggleDir(p){C.expanded[p]=!(C.expanded[p]!==false);renderWsTree();}
function toggleRef(path,kind){
  const i=C.refs.findIndex(r=>r.path===path);
  if(i>=0)C.refs.splice(i,1);else C.refs.push({path,kind});
  renderWsTree();renderRefBar();
}
function removeRef(i){C.refs.splice(i,1);renderWsTree();renderRefBar();}
function renderRefBar(){
  const bar=$('refBar'); if(!bar) return;
  const refs=C.refs||[];
  if(!refs.length){bar.style.display='none';bar.innerHTML='';return;}
  bar.style.display='block';
  bar.innerHTML=`<div class="row" style="gap:5px;flex-wrap:wrap"><span class="mut small">📎 参考：</span>
    ${refs.map((r,i)=>`<span class="pill api" style="cursor:pointer" title="点击移除" onclick="removeRef(${i})">${r.kind==='dir'?'📁':'📄'} ${esc(r.path)} ✕</span>`).join('')}
    <button class="btn btn-ghost btn-sm" style="padding:0 6px" onclick="C.refs=[];renderWsTree();renderRefBar();">清空</button></div>`;
}
/* ---------- 当前工作目录（右侧上下文条） ---------- */
function renderCtxBar(){
  const bar=$('ctxBar'); if(!bar) return;
  if(!C.wsId){bar.style.display='none';bar.innerHTML='';return;}
  const ws=curWsObj(); if(!ws){bar.style.display='none';bar.innerHTML='';return;}
  bar.style.display='flex';
  const a=curAgent();
  const folder=C.folder||'(根目录)';
  bar.innerHTML=`<div style="flex:1;min-width:0">
    <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">
      <b style="font-size:12.5px">📍 工作目录</b>
      <span class="pill on" style="max-width:100%">▤ ${esc(ws.label)}${C.folder?' / '+esc(C.folder):''}</span>
      ${C.folder?`<button class="btn btn-ghost btn-sm" style="padding:0 6px" onclick="setWorkFolder('')" title="回到工作区根">回根目录</button>`:''}
      <button class="btn btn-ghost btn-sm" style="padding:0 6px" onclick="saveWsPref();toast('已记住：该 Agent 下次默认在此文件夹工作','ok')" title="记住当前文件夹为默认">💾 记住</button>
    </div>
    <div class="mut small" style="margin-top:2px">发送任务后，${esc(a?a.name:'Agent')} 的读写在此文件夹内执行（可用 .. 访问同工作区其它位置），产出默认写到这里</div></div>`;
}
async function saveWsPref(){
  const a=curAgent(); if(!a||!C.wsId) return;
  try{await api(`/agents/${a.id}/ws-pref`,{method:'PUT',body:JSON.stringify({workspace_id:C.wsId,folder:C.folder||''})});
    // 同步本地 pref，便于切走再切回时立即恢复
    a.pref={workspace_id:C.wsId,folder:C.folder||''}; a.workspace=(curWsObj()&&{id:curWsObj().id,name:curWsObj().name,kind:curWsObj().kind,label:curWsObj().label})||a.workspace;
  }catch(e){/* 静默：仅记忆失败不影响对话 */}}
async function setWorkFolder(p){C.folder=p||'';renderWsTree();renderCtxBar();await saveWsPref();}
/* ---------- 左栏文件管理（上传/新建/预览/编辑/删除） ---------- */
async function wbUpload(files){
  if(!files.length||!C.wsId)return;
  try{
    for(const f of files){const fd=new FormData();fd.append('file',f);
      await api(`/workspaces/${C.wsId}/files`,{method:'POST',body:fd});}
    toast(`已上传 ${files.length} 个文件`,'ok');loadWsTree(true);
  }catch(e){toast('上传失败: '+e.message,'err');}
}
function wbNewDoc(){
  const ws=curWsObj(); if(!ws) return;
  if(ws.can_write===false){toast('该工作区只读','err');return;}
  openModal(`<h3>新建文档</h3><div class="m-sub">工作区：${esc(ws.label)} ${C.folder?('· 当前目录 /'+esc(C.folder)):''}</div>
    <div class="field"><label>文件名（留空则存到当前工作目录）</label><input id="ndocname" class="inp mono" placeholder="如 Q4-总结.md"></div>
    <div class="field"><label>内容</label><textarea id="ndoccontent" class="inp code" style="min-height:200px"></textarea></div>
    <div class="row" style="justify-content:flex-end"><button class="btn btn-ghost" onclick="closeModal()">取消</button>
    <button class="btn btn-primary" onclick="wbSaveDoc()">保存</button></div>`);
}
async function wbSaveDoc(){
  const nm=$('ndocname').value.trim();
  let p=nm; if(!p.includes('/')&&C.folder)p=C.folder+'/'+p; else if(!p&&C.folder)p=C.folder+'/untitled.md'; else if(!p)p='untitled.md';
  try{await api(`/workspaces/${C.wsId}/text`,{method:'POST',body:JSON.stringify({path:p,content:$('ndoccontent').value})});
    closeModal();toast('已保存','ok');loadWsTree(true);}
  catch(e){toast(e.message,'err');}
}
async function wbPreview(path){
  const ws=curWsObj(); if(!ws) return;
  try{
    const d=await api(`/workspaces/${C.wsId}/text?path=${encodeURIComponent(path)}`);
    const name=path.split('/').pop();
    const canW=C.wsCanWrite!==false;
    openModal(`<h3>${esc(name)}</h3><div class="m-sub">▤ ${esc(ws.label)} · /${esc(path)} · ${d.size} B</div>
      <pre class="codeblock" style="max-height:52vh">${esc(d.content)}</pre>
      <div class="row" style="justify-content:flex-end;margin-top:10px;flex-wrap:wrap">
      <button class="btn btn-ghost btn-sm" onclick="toggleRef('${esc(path)}','file');closeModal()">📎 加入参考</button>
      ${canW?`<button class="btn btn-ghost btn-sm" onclick="wbEditText('${esc(path)}')">编辑</button>`:''}
      <a class="btn btn-ghost btn-sm" href="/api/workspaces/${C.wsId}/download?path=${encodeURIComponent(path)}" target="_blank">下载</a>
      ${canW?`<button class="btn btn-danger btn-sm" onclick="wbDelFile('${esc(path)}')">删除</button>`:''}
      <button class="btn btn-primary btn-sm" onclick="closeModal()">关闭</button></div>`);
  }catch(e){toast('该文件无法预览（可能非文本或过大）','err');}
}
async function wbEditText(path){
  const d=await api(`/workspaces/${C.wsId}/text?path=${encodeURIComponent(path)}`);
  openModal(`<h3>编辑 ${esc(path.split('/').pop())}</h3>
    <textarea id="ndoccontent" class="inp code" style="min-height:300px">${esc(d.content)}</textarea>
    <div class="row" style="justify-content:flex-end;margin-top:8px"><button class="btn btn-ghost" onclick="wbPreview('${esc(path)}')">返回预览</button>
    <button class="btn btn-primary" onclick="wbSaveEdited('${esc(path)}')">保存</button></div>`,'760px');
}
async function wbSaveEdited(path){
  try{await api(`/workspaces/${C.wsId}/text`,{method:'POST',body:JSON.stringify({path,content:$('ndoccontent').value})});
    closeModal();toast('已保存','ok');loadWsTree(true);}
  catch(e){toast(e.message,'err');}
}
async function wbDelFile(path){
  if(!confirm(`删除 ${path}？`))return;
  try{await api(`/workspaces/${C.wsId}/files?path=${encodeURIComponent(path)}`,{method:'DELETE'});
    closeModal();toast('已删除','ok');
    const i=C.refs.findIndex(r=>r.path===path);if(i>=0){C.refs.splice(i,1);renderRefBar();}
    loadWsTree(true);}catch(e){toast(e.message,'err');}
}
/* ---------- 对话 ---------- */
function addMsg(who,text,html){
  const d=document.createElement('div');d.className='msg '+who;
  if(html)d.innerHTML=html;else d.textContent=text;
  $('cb').appendChild(d);$('cb').scrollTop=1e9;return d;
}
async function send(){
  const inp=$('msg');const m=inp.value.trim();if(!m){toast('输入任务内容','err');return;}
  const aid=AG_SEL().value;if(!aid){toast('没有可用 Agent','err');return;}
  if(!C.wsId){toast('没有可用工作区','err');return;}
  const refs=(C.refs||[]).map(r=>r.path);
  inp.value='';
  const ws=curWsObj();
  const locNote='▤ '+(ws?ws.label:'')+(C.folder?' /'+C.folder:'');
  const refNote=refs.length?('\n\n📎 参考：'+refs.map(r=>'「'+r+'」').join('、')):'';
  addMsg('user',`${m}\n\n📍 工作目录：${locNote}${refNote}`);
  const d=addMsg('agent','思考中…',false);d.style.color='var(--fg3)';
  try{
    const r=await api('/agents/'+aid+'/chat',{method:'POST',body:JSON.stringify({message:m,refs,workspace_id:C.wsId,folder:C.folder||''})});
    d.className='msg agent';d.style.color='';
    const tools=(r.tools_used||[]).filter(t=>!['now'].includes(t));
    const toolHtml=tools.length?('<div style="margin-bottom:4px">'+tools.map(t=>'<span class="tooltag">'+esc(t)+'</span>').join('')+'</div>'):'';
    d.innerHTML=toolHtml+esc(r.reply)+
      `<div class="msg-actions"><button class="rate-btn" onclick="rate(this,${aid},1)">👍 有用</button><button class="rate-btn" onclick="rate(this,${aid},0)">👎 需改进</button></div>`;
    d.dataset.agent=aid;
    // 对话成功 → 后端已记忆位置，本地同步 + 刷新树（Agent 可能写了新文件）
    const a=curAgent(); if(a){a.pref={workspace_id:C.wsId,folder:C.folder||''};}
    loadWsTree(true);
  }catch(e){d.className='msg agent';d.style.color='';d.textContent='错误: '+e.message;}
}
async function rate(btn,aid,good){
  btn.classList.toggle(good?'liked':'disliked',true);
  const val=good?5:1;
  const box=document.createElement('div');box.className='card feedback';
  box.innerHTML=`<b style="font-size:13px">${good?'这个回复有帮助 👍':'哪里不对？请告诉 Agent 帮你改进'}</b>
    ${good?'<div class="mut small" style="margin:4px 0 6px">可留一句话说明，Agent 会把它沉淀为记忆/偏好</div>':'<textarea id="fbx" class="inp" style="margin-top:6px;min-height:70px" placeholder="例如：简报要有来源链接；结论先于数据；以后都用英文缩写…"></textarea>'}
    <div class="row" style="margin-top:8px"><button class="btn btn-ghost btn-sm" onclick="this.closest('.card').remove()">取消</button>
    <button class="btn btn-sm ${good?'btn-green':'btn-primary'}" onclick="sendFeedback(this,${aid},${val})">${good?'仅点赞':'提交反馈并反思'}</button></div>`;
  const msg=btn.closest('.msg');msg.insertAdjacentElement('afterend',box);
  if(!good)$('fbx')&&$('fbx').focus();
}
async function sendFeedback(btn,aid,val){
  const txt=$('fbx')?$('fbx').value:'';
  btnSpin(btn,true,'反思中…');
  const card=btn.closest('.card');
  try{
    const r=await api(`/agents/${aid}/reflect`,{method:'POST',body:JSON.stringify({rating:val,feedback:txt})});
    card.innerHTML='';
    let h=`<div style="font-size:13px"><span class="pill on">✅ 已反思并迭代</span></div>`;
    h+=`<div class="mut small" style="margin:6px 0">${esc(r.analysis)}</div>`;
    if(r.applied_memory&&r.applied_memory.length)h+=`<div class="small" style="margin-top:4px">🧠 记忆更新：<b>${esc(r.applied_memory.join('、'))}</b></div>`;
    if(r.applied_skill_drafts&&r.applied_skill_drafts.length)h+=`<div class="small" style="margin-top:2px">🧩 技能草稿：<b>${esc(r.applied_skill_drafts.map(s=>s.name+' v'+s.version).join('、'))}</b>（在技能工作室中可继续编辑/发布）</div>`;
    if(r.system_prompt_suggestion)h+=`<div class="small" style="margin-top:2px">📝 提示词建议已生成（可到 Agent 详情采纳）</div>`;
    card.innerHTML='<div style="border:1px solid rgba(63,185,80,.4);background:var(--green-dim);border-radius:8px;padding:10px 12px">'+h+'</div>';
    toast('Agent 反思完成：技能/记忆已迭代','ok');
  }catch(e){card.innerHTML='<div style="color:var(--red);font-size:13px">'+esc(e.message)+'</div>';btnSpin(btn,false);}
}
function clearChat(){const cb=$('cb');if(!cb)return;cb.innerHTML='';addMsg('agent','已切换 Agent，可在此工作台开始新任务。工作目录见上方 📍 条，可在左侧文件树调整。');}
async function goChat(id){PEND_AGENT=id;await show('chat');}
async function showRefModal(){
  const aid=AG_SEL()?AG_SEL().value:'';if(!aid)return;
  const rows=await api(`/agents/${aid}/reflections`);
  const a=C.agents.find(x=>x.id==aid);
  openModal(`<h3>反思日志 · ${esc(a?a.name:'')}</h3><div class="m-sub">Agent 根据你的反馈迭代技能/记忆的记录</div>
    <div style="max-height:60vh;overflow-y:auto">`+
    (rows.length?rows.map(r=>`<div class="card" style="margin-bottom:8px">
      <div class="row"><span class="pill ${r.rating>=4?'published':'draft'}">${'★'.repeat(r.rating)}${'☆'.repeat(5-r.rating)}</span><span class="mut small">${fmtTime(r.created_at)}</span></div>
      <div class="mut" style="margin:4px 0">反馈：${esc(r.feedback||'(仅点赞)')}</div>
      <div class="small" style="margin:4px 0">${esc(r.analysis)}</div>
      ${JSON.stringify(r.actions||[]).includes('memory')?`<div class="pg-meta">🧠 含记忆更新</div>`:''}
      ${(r.actions||[]).some(a=>a.type==='skill_draft'&&(a.items||[]).length)?`<div class="pg-meta">🧩 含技能草稿</div>`:''}
      </div>`).join(''):'<div class="empty">还没有反思记录。在对话页对回复点 👍/👎 并留言即可触发。</div>')+
    `</div><div class="row" style="justify-content:flex-end;margin-top:14px"><button class="btn btn-ghost" onclick="closeModal()">关闭</button></div>`);
}
function goAgents(){show('agents');}

/* ================= Agents ================= */
async function vc_agents(){
  setTitle('Agents');setSub('自建 Agent · 绑定技能 · 设置默认空间（对话时可按需切到任意可见工作区） · 对话测试即迭代');
  $('view').innerHTML=`<div class="card" style="border-color:rgba(113,112,255,.35);background:linear-gradient(120deg,rgba(94,106,210,.14),rgba(255,255,255,.02))">
    <div class="spread"><div><b style="font-size:14px">✨ 用一句话创建 Agent</b>
    <div class="mut small" style="margin-top:3px">描述你要的 Agent，平台自动生成 agent.md、推荐/编写技能并装配好工作区</div></div>
    <button class="btn btn-primary" onclick="nlAgent()">开始创建</button></div></div>
    <div id="aglist">${loader()}</div>`;
  refreshAgList();
}
async function refreshAgList(){
  const list=await api('/agents');C.agents=list;
  $('aglist').innerHTML=list.map(a=>`<div class="card card-hover">
    <div class="spread"><div style="flex:1;min-width:0"><div class="row">
      <b style="font-size:14.5px">${esc(a.name)}</b> ${scopePill(a.scope)} <span class="pill">v${a.version}</span></div>
      <div class="mut" style="margin-top:3px">${esc(a.description)}</div>
      <div class="pg-meta" style="margin-top:6px">${esc(a.provider)}/${esc(a.model)}
        ${a.workspace?` · ▤ ${esc(a.workspace.label||'')}`:''}
        ${(a.skills||[]).length?` · 🧩 ${esc((a.skills||[]).join('、'))}`:''}</div></div>
      <div class="row" style="flex-shrink:0"><button class="btn btn-sm btn-ghost" onclick="agentEdit(${a.id})">编辑</button>
      <button class="btn btn-sm btn-primary" onclick="goChat(${a.id})">对话</button></div></div></div>`).join('')
    ||'<div class="empty">还没有可见 Agent —— 点上方「用一句话创建」</div>';
}
async function nlAgent(){
  openModal(`<h3>✨ 用一句话创建 Agent</h3><div class="m-sub">描述你想要的 Agent 的职责、使用场景与要求，平台会设计 agent.md 与技能</div>
    <div class="field"><label>一句话需求</label><textarea id="nlprompt" class="inp code" style="min-height:120px" placeholder="例如：帮我建一个奢侈品行业舆情监测助手，每天汇总品牌相关新闻与社媒讨论，输出结构化简报并存档到工作区…"></textarea></div>
    <div class="row" style="margin:6px 0 12px"><span class="lbl" style="margin:0">范围</span>
    <select id="nlscope" class="inp"><option value="user">user（仅我，个人空间）</option><option value="team">team（我所在团队）</option><option value="org">org（全员）</option></select>
    <span class="lbl" style="margin:0">工作区</span><select id="nlws" class="inp"><option value="">按范围自动</option></select></div>
    <div id="nlres"></div>
    <div class="row" style="justify-content:flex-end;gap:8px"><button class="btn btn-ghost" onclick="closeModal()">取消</button>
    <button class="btn btn-primary" id="nlgo" onclick="genPlan()">生成蓝图 →</button></div>`);
  C.wss=await api('/workspaces').catch(()=>[]);
  const sel=$('nlws');
  sel.innerHTML='<option value="">按范围自动</option>'+C.wss.map(w=>`<option value="${w.id}">${esc(w.label)}</option>`).join('');
  $('nlscope').onchange=()=>{const v=$('nlscope').value;sel.innerHTML='<option value="">按范围自动</option>'+C.wss.filter(w=>v==='team'?w.kind==='team':v==='org'?w.kind==='org':w.kind==='personal').map(w=>`<option value="${w.id}">${esc(w.label)}</option>`).join('');};
}
async function genPlan(){
  const prompt=$('nlprompt').value.trim();if(!prompt){toast('请先描述需求','err');return;}
  const btn=$('nlgo');btnSpin(btn,true,'AI 设计中…');
  $('nlres').innerHTML='<div class="loader"><span class="spin"></span> 正在生成 Agent 蓝图（会评估现有技能并给出装配方案）…</div>';
  try{
    const r=await api('/agents/generate-plan',{method:'POST',body:JSON.stringify({prompt,scope:$('nlscope').value,workspace_id:$('nlws').value?+$('nlws').value:null})});
    C.plan=r.plan;C.nlPrompt=prompt;
    renderPlan();
  }catch(e){$('nlres').innerHTML='<div style="color:var(--red)">'+esc(e.message)+'</div>';btnSpin(btn,false);}
}
function renderPlan(){
  const p=C.plan;
  $('nlres').innerHTML=`<div style="border:1px solid var(--border2);border-radius:10px;padding:14px">
    <div class="row"><b style="font-size:16px">${esc(p.name||'未命名 Agent')}</b><button class="btn btn-sm btn-ghost" onclick="regenPlan()">↻ 重新生成</button></div>
    <div class="mut small" style="margin-top:2px">${esc(p.description||'')}</div>
    ${p.notes?`<div class="small" style="margin-top:8px;color:var(--brand3)">💡 ${esc(p.notes)}</div>`:''}
    <div class="divider"></div>
    <h3 class="sec" style="margin-top:0">技能装配方案</h3>
    ${(p.skills||[]).map((s,i)=>`<div class="file-item"><span class="file-ico">${s.action==='existing'?'✓':'＋'}</span>
      <div style="flex:1"><div class="file-name">${esc(s.name)} ${s.action==='existing'?'<span class="pill on">复用已有</span>':'<span class="pill api">新建草稿</span>'}</div>
      <div class="file-meta">${esc((s.reason||'').slice(0,120))}</div></div></div>`).join('')||'<div class="empty">无技能需求</div>'}
    <div class="divider"></div>
    <div class="row" style="justify-content:space-between"><button class="btn btn-ghost" onclick="togglePrompt()" id="togglePromptBtn">📄 查看 agent.md / 系统提示词</button>
    <button class="btn btn-primary" onclick="applyPlan()">确认创建 Agent</button></div>
    <div id="planDetail" style="display:none;margin-top:10px">
      ${p.system_prompt?`<div class="lbl" style="margin-top:8px">系统提示词</div><pre class="codeblock" style="max-height:200px">${esc(p.system_prompt)}</pre>`:''}
      ${p.agent_md?`<div class="lbl" style="margin-top:8px">agent.md</div><pre class="codeblock">${esc(p.agent_md)}</pre>`:''}
    </div></div>`;
  btnSpin($('nlgo'),false);
}
function togglePrompt(){const el=$('planDetail');el.style.display=el.style.display==='none'?'block':'none';$('togglePromptBtn').textContent=el.style.display==='none'?'📄 查看 agent.md / 系统提示词':'📄 收起';}
async function regenPlan(){const prompt=$('nlprompt').value.trim()||C.nlPrompt;$('nlres').innerHTML='<div class="loader"><span class="spin"></span> 重新生成中…</div>';try{const r=await api('/agents/generate-plan',{method:'POST',body:JSON.stringify({prompt,scope:$('nlscope').value,workspace_id:$('nlws').value?+$('nlws').value:null})});C.plan=r.plan;renderPlan();}catch(e){$('nlres').innerHTML='<div style="color:var(--red)">'+esc(e.message)+'</div>';}}
async function applyPlan(){
  const btn=event.target;btnSpin(btn,true,'创建中…');
  try{
    const r=await api('/agents/generate-plan/apply',{method:'POST',body:JSON.stringify({prompt:C.nlPrompt||'',plan:C.plan,scope:$('nlscope').value,workspace_id:$('nlws').value?+$('nlws').value:null})});
    $('nlres').innerHTML=`<div style="border:1px solid rgba(63,185,80,.4);background:var(--green-dim);border-radius:10px;padding:14px">
      <b>✅ Agent 已创建</b>
      <div class="small" style="margin-top:6px">${esc(r.bound_skills||[]).length?`已绑定技能：${esc((r.bound_skills||[]).join('、'))}<br>`:''}${esc(r.created_skills||[]).length?`已新建技能草稿：${esc((r.created_skills||[]).join('、'))}（可到技能工作室编辑发布）<br>`:''}工作区：${esc((r.workspace||{}).name||'按范围自动')}</div>
      <div class="row" style="margin-top:12px"><button class="btn btn-primary btn-sm" onclick="closeModal();goChat(${r.agent_id})">去对话测试</button>
      <button class="btn btn-ghost btn-sm" onclick="closeModal();vc_agents()">返回列表</button></div></div>`;
    toast('Agent 创建成功','ok');
  }catch(e){toast(e.message,'err');btnSpin(btn,false);}
}
async function agentEdit(id){
  const a=await api('/agents/'+id);
  if(!a.can_edit){toast('无权编辑','err');return;}
  const provs=await api('/admin/providers').catch(()=>[]);
  const skills=await api('/skills');
  const wss=await api('/workspaces').catch(()=>[]);
  const pubSkills=skills.filter(s=>s.versions.some(v=>v.status==='published')||s.can_edit);
  openModal(`<h3>编辑 Agent · ${esc(a.name)}</h3><div class="m-sub">修改配置后保存；在对话页测试即迭代（v${a.version}→v${a.version+1}）</div>
    <div class="row"><div class="field" style="flex:1"><label>名称</label><input id="an" class="inp" value="${esc(a.name)}"></div>
    <div class="field"><label>范围</label><select id="ascope" class="inp"><option value="user" ${a.scope==='user'?'selected':''}>user</option><option value="team" ${a.scope==='team'?'selected':''}>team</option><option value="org" ${a.scope==='org'?'selected':''}>org</option></select></div></div>
    <div class="field"><label>描述</label><input id="adesc" class="inp" value="${esc(a.description)}"></div>
    <div class="row"><div class="field" style="flex:1"><label>模型 Provider</label><select id="aprov" class="inp">${provs.filter(p=>p.enabled).map(p=>`<option value="${p.id}" ${a.provider_id===p.id?'selected':''}>${esc(p.name)}</option>`).join('')}</select></div>
    <div class="field" style="flex:1"><label>模型</label><input id="amodel" class="inp" value="${esc(a.model)}"></div>
    <div class="field"><label>默认空间（可空=按范围自动；对话时可切任意可见工作区）</label><select id="aws" class="inp"><option value="">按范围自动</option>${wss.map(w=>`<option value="${w.id}" ${a.workspace&&a.workspace.id===w.id?'selected':''}>${esc(w.label)}</option>`).join('')}</select></div></div>
    <div class="field"><label>系统提示词</label><textarea id="aprompt" class="inp code" style="min-height:150px">${esc(a.system_prompt)}</textarea></div>
    <div class="lbl">绑定技能</div><div id="binds"></div>
    <div class="row" style="margin-top:8px"><button class="btn btn-ghost btn-sm" onclick="addBindRow()">＋ 技能</button>
      <span style="flex:1"></span><button class="btn btn-danger btn-sm" onclick="agentDel(${a.id})">删除</button>
      <button class="btn btn-primary" onclick="agentSave(${a.id})">保存</button></div>`,'860px');
  C.skillPool=pubSkills;C.editAgent=a;
  (a.skill_bindings||[]).forEach(b=>addBindRow(b));
  if(!(a.skill_bindings||[]).length)addBindRow();
  // scope 联动工作区默认
}
function addBindRow(b){
  const d=document.createElement('div');d.className='row bind';d.style.cssText='margin:3px 0';
  const pool=C.skillPool||[];
  const opts=pool.map(s=>{
    const pub=s.versions.filter(v=>v.status==='published');
    const drafts=s.can_edit?s.versions.filter(v=>v.status==='draft'):[];
    const pair=[...pub,...drafts];
    return `<option value="${s.id}__">${esc(s.name)}（跟随最新）</option>`+
      pair.map(v=>`<option value="${s.id}:${v.id}" ${b&&b.skill_id===s.id&&b.version_id===v.id?'selected':''}>${esc(s.name)} v${v.version}(${v.status})</option>`).join('');
  }).join('');
  d.innerHTML=`<select class="inp" style="flex:1">${opts||'<option value="">（无技能）</option>'}</select>
    <button class="btn btn-ghost btn-sm" onclick="this.parentNode.remove()">✕</button>`;
  $('binds').appendChild(d);
}
async function agentSave(id){
  const binds=[...document.querySelectorAll('#binds .bind select')].map(s=>{const v=s.value;if(!v)return null;const [sid,vid]=v.split(':');return {skill_id:+sid,version_id:vid&&vid!=='__'?+vid:null};}).filter(Boolean);
  const body={name:$('an').value,description:$('adesc').value,system_prompt:$('aprompt').value,
    scope:$('ascope').value,provider_id:+$('aprov').value,model:$('amodel').value||'',
    workspace_id:$('aws').value?+$('aws').value:null,skill_bindings:binds};
  try{await api('/agents/'+id,{method:'PATCH',body:JSON.stringify(body)});closeModal();toast('已保存（版本 +1，可在对话页测试）','ok');refreshAgList();}
  catch(e){toast(e.message,'err');}
}
async function agentDel(id){if(!confirm('确认删除该 Agent？'))return;await api('/agents/'+id,{method:'DELETE'});closeModal();toast('已删除','ok');refreshAgList();}

/* ================= Skills ================= */
async function vc_skills(){
  setTitle('技能工作室');setSub('创建 → 迭代草稿 → 测试 → 发布 → API 化 → 分享/复制');
  $('view').innerHTML=`<div class="card"><div class="row">
    <input id="sn" class="inp" placeholder="技能名" style="flex:1;min-width:130px">
    <input id="sd" class="inp" placeholder="一句话描述" style="flex:2">
    <select id="nscope" class="inp"><option value="private">private</option><option value="team">team</option><option value="org">org</option></select>
    <button class="btn btn-primary" onclick="skillCreate()">＋ 创建技能</button></div>
    <div class="mut small" style="margin-top:8px">提示：Agent 反思会自动生成技能草稿（状态=草稿），在这里编辑、测试、发布。</div></div>
    <div id="sktab">${loader()}</div>`;
  refreshSkills();
}
async function refreshSkills(){
  const list=await api('/skills');C.skills=list;
  $('sktab').innerHTML=list.map(s=>`<div class="card card-hover">
    <div class="spread"><div style="flex:1;min-width:0"><div class="row">
      <b style="font-size:14px">${esc(s.name)}</b> ${scopePill(s.scope)} ${s.api_enabled?'<span class="pill api">API</span>':''}
      ${s.can_edit?'<span class="pill on">可编辑</span>':''}
      ${s.versions.filter(v=>v.status==='draft').length?'<span class="pill draft">有草稿</span>':''}</div>
      <div class="mut small" style="margin-top:3px">${esc(s.description)}</div>
      <div class="pg-meta" style="margin-top:5px">by ${esc(s.owner)} · ${s.versions.map(v=>`v${v.version}(${v.status})`).join(' ')}</div></div>
      <button class="btn btn-sm btn-ghost" onclick="skillOpen(${s.id})">打开 / 编辑</button></div></div>`).join('')
    ||'<div class="empty"><div class="big">◇</div>还没有技能，创建一个或让 Agent 反思自动生成</div>';
}
async function skillCreate(){
  const n=$('sn').value.trim();if(!n){toast('填技能名','err');return;}
  await api('/skills',{method:'POST',body:JSON.stringify({name:n,description:$('sd').value||'',content:'# '+n+'\n（在此写清技能的方法/规则/示例…）',scope:$('nscope').value})});
  await refreshSkills();
  const s=C.skills.find(x=>x.name===n);if(s)skillOpen(s.id);
}
async function skillOpen(id){
  const d=await api('/skills/'+id);
  setTitle('技能 · '+d.name);
  const latest=d.versions[0]||{content:'',id:null};
  const canFork=!d.can_edit;
  const verRows=d.versions.map(v=>`<tr><td><b class="mono">v${v.version}</b></td><td>${stPill(v.status)}</td>
    <td class="mut">${esc(v.change_note||'-')}</td><td class="mut small">${(v.published_at||'').slice(0,10)||'-'}</td>
    <td style="white-space:nowrap">${v.status==='draft'&&d.can_edit?`<button class="btn btn-sm btn-green" onclick="publishVer(${d.id},${v.id})">发布</button> <button class="btn btn-sm btn-ghost" onclick="editDraft(${d.id},${v.id})">编辑</button>`:''}</td></tr>`).join('');
  $('view').innerHTML=`<div style="max-width:1060px">
  <div class="card"><div class="spread"><b style="font-size:16px">${esc(d.name)}</b>
    <div class="row">${scopePill(d.scope)} ${d.api_enabled?'<span class="pill api">API 已开放</span>':''}
      ${d.can_edit?`<select id="kscope" class="inp" style="width:110px"><option value="private" ${d.scope==='private'?'selected':''}>private</option><option value="team" ${d.scope==='team'?'selected':''}>team</option><option value="org" ${d.scope==='org'?'selected':''}>org</option></select>
      <button class="btn btn-sm btn-ghost" onclick="skillScope(${d.id})">改范围</button>`:''}
      ${canFork?`<button class="btn btn-sm" onclick="skillFork(${d.id})">复制到我(Fork)</button>`:''}
      ${d.can_edit?`<button class="btn btn-sm btn-danger" onclick="skillDel(${d.id})">删除</button>`:''}
    </div></div>
    <div class="mut small" style="margin:6px 0">${esc(d.description)} · by ${esc(d.owner)} · 被 ${d.used_by_agents} 个 Agent 引用</div>
    <div class="row" style="margin-top:10px">
      ${d.can_edit?`<button class="btn btn-sm" onclick="newDraftForm(${d.id})">＋ 新建草稿版本</button>`:''}
      ${d.can_edit?`<button class="btn btn-sm ${d.api_enabled?'btn-warn':'btn-green'}" onclick="toggleApi(${d.id})">${d.api_enabled?'关闭 API':'发布为 API'}</button>`:''}
      <span style="flex:1"></span>
      <button class="btn btn-sm btn-ghost" onclick="history.back()">返回</button>
    </div>
    ${d.api_enabled?`<div class="card" style="margin:10px 0 0;background:rgba(255,255,255,.015)">
      <b class="small">🔌 Skill API</b><pre class="codeblock" style="margin-top:6px">POST /api/skills/${d.id}/invoke
Authorization: Bearer &lt;token&gt;
{"input":"你的输入"}

curl -X POST http://localhost:8000/api/skills/${d.id}/invoke \\
  -H "Authorization: Bearer ***" \\
  -H "Content-Type: application/json" \\
  -d '{"input":"..."}'</pre></div>`:''}
  </div>
  <div class="card"><h3 class="sec" style="margin-top:0">版本历史</h3>
    <table class="tbl"><tr><th>版本</th><th>状态</th><th>变更说明</th><th>发布时间</th><th></th></tr>${verRows||'<tr><td colspan=5 class="mut">暂无版本</td></tr>'}</table>
    <div class="lbl" style="margin-top:12px">内容（最新版本）</div>
    <pre class="codeblock">${esc(latest.content)}</pre>
    ${d.can_edit?`<button class="btn btn-sm" style="margin-top:8px" onclick="newDraftForm(${d.id})">以此为基础新建草稿 →</button>`:''}
  </div>
  <div class="card"><h3 class="sec" style="margin-top:0">🧪 测试运行</h3>
    <div class="row"><span class="lbl" style="margin:0">版本</span><select id="tver" class="inp">${d.versions.map(v=>`<option value="${v.id}">v${v.version} (${v.status})</option>`).join('')||'<option value="">（无）</option>'}</select>
    <button class="btn btn-primary" onclick="testSkill(${d.id})">运行测试</button></div>
    <textarea id="tin" class="inp code" style="margin-top:8px;min-height:70px" placeholder="测试输入…"></textarea>
    <div id="tres" style="margin-top:8px"></div></div></div>`;
  C.curSkill=d;
}
async function skillScope(id){await api('/skills/'+id,{method:'PATCH',body:JSON.stringify({scope:$('kscope').value})});toast('范围已更新','ok');skillOpen(id);}
async function skillFork(id){const r=await api('/skills/'+id+'/fork',{method:'POST'});toast('已复制到你的私有空间','ok');await refreshSkills();skillOpen(r.id);}
async function skillDel(id){if(!confirm('删除技能？(被引用时会拒绝)'))return;try{await api('/skills/'+id,{method:'DELETE'});toast('已删除','ok');await vc_skills();}catch(e){toast(e.message,'err');}}
function newDraftForm(id){editDraft(id,null);}
function editDraft(id,vid){
  const d=C.curSkill;
  const base=vid?d.versions.find(v=>v.id===vid):d.versions[0];
  openModal(`<h3>迭代草稿 · ${esc(d.name)}</h3><div class="m-sub">基于 v${base?base.version:'?'} 编辑（已发布版本不可改 → 建草稿迭代）</div>
    <div class="field"><label>变更说明</label><input id="cnote" class="inp" placeholder="这次改了什么？"></div>
    <div class="field"><label>技能内容（SKILL.md 风格）</label><textarea id="ccont" class="inp code" style="min-height:320px">${esc(base?base.content:'')}</textarea></div>
    <div class="row" style="justify-content:flex-end"><button class="btn btn-ghost" onclick="closeModal()">取消</button>
    <button class="btn btn-primary" onclick="saveDraft(${d.id},${vid||'null'})">保存草稿</button></div>`,'820px');
}
async function saveDraft(id,vid){
  const body={content:$('ccont').value,change_note:$('cnote').value||''};
  try{if(vid)await api('/skills/'+id+'/versions/'+vid,{method:'PATCH',body:JSON.stringify(body)});
    else await api('/skills/'+id+'/versions',{method:'POST',body:JSON.stringify(body)});
    closeModal();toast('草稿已保存（可测试/发布）','ok');skillOpen(id);}catch(e){toast(e.message,'err');}
}
async function publishVer(id,vid){await api(`/skills/${id}/versions/${vid}/publish`,{method:'POST'});toast('已发布','ok');skillOpen(id);}
async function toggleApi(id){await api('/skills/'+id+'/api',{method:'POST'});skillOpen(id);}
async function testSkill(id){
  $('tres').innerHTML='<div class="loader"><span class="spin"></span> 运行中…</div>';
  try{const r=await api('/skills/'+id+'/invoke',{method:'POST',body:JSON.stringify({input:$('tin').value,version_id:$('tver').value?+$('tver').value:null})});
    $('tres').innerHTML=`<pre class="codeblock">${esc(r.result)}</pre><div class="pg-meta" style="margin-top:4px">skill ${esc(r.skill)} v${r.version} · ${esc(r.run_ref)}</div>`;}
  catch(e){$('tres').innerHTML='<div style="color:var(--red)">'+esc(e.message)+'</div>';}
}

/* ================= Workflows ================= */
async function vc_workflows(){
  setTitle('工作流');setSub('有序串联多个已发布技能，逐步加工（上一步输出喂下一步）');
  $('view').innerHTML=`<div class="card"><div class="row">
    <input id="wfname" class="inp" placeholder="工作流名称" style="flex:1">
    <input id="wfdesc" class="inp" placeholder="描述" style="flex:2">
    <select id="wfscope" class="inp"><option value="private">private</option><option value="team">team</option><option value="org">org</option></select>
    <button class="btn btn-primary" onclick="wfCreate()">＋ 创建工作流</button></div></div><div id="wflist">${loader()}</div>`;
  refreshWf();
}
async function refreshWf(){
  const [list,skills]=await Promise.all([api('/workflows'),api('/skills')]);
  C.pubSkills=skills.filter(s=>s.versions.some(v=>v.status==='published'));
  $('wflist').innerHTML=list.map(w=>`<div class="card card-hover"><div class="spread">
    <div style="flex:1"><b style="font-size:14px">${esc(w.name)}</b> ${scopePill(w.scope)}
    <div class="mut small" style="margin-top:3px">${esc(w.description)}</div>
    <div class="pg-meta" style="margin-top:4px">${w.steps} 个技能步骤 · by ${esc(w.owner)}</div></div>
    <button class="btn btn-sm btn-ghost" onclick="wfOpen(${w.id})">打开 / 运行</button></div></div>`).join('')||'<div class="empty">暂无工作流</div>';
}
async function wfCreate(){
  const n=$('wfname').value.trim();if(!n){toast('填名称','err');return;}
  await api('/workflows',{method:'POST',body:JSON.stringify({name:n,description:$('wfdesc').value||'',scope:$('wfscope').value,steps:[]})});
  await refreshWf();const list=await api('/workflows');const w=list.find(x=>x.name===n);if(w)wfOpen(w.id);
}
async function wfOpen(id){
  const w=await api('/workflows/'+id);
  setTitle('工作流 · '+w.name);
  const stepEditors=(w.steps||[]).map((s,i)=>`<div class="row" style="margin:5px 0;background:rgba(255,255,255,.02);border:1px solid var(--border);border-radius:6px;padding:6px 10px">
    <span class="pill">#${i+1}</span><b style="font-size:13px">${esc(s.skill_name)}</b>
    <span class="pill ${s.status}">v${s.version}(${s.status})</span><span class="mut small">${esc(s.note||'')}</span>
    <span style="flex:1"></span><button class="btn btn-ghost btn-sm" onclick="wfMoveUp(${w.id},${i})">↑</button>
    <button class="btn btn-ghost btn-sm" onclick="wfDelStep(${w.id},${i})">✕</button></div>`).join('')||'<div class="mut">还没有步骤——从右侧添加技能</div>';
  const addOpts=(C.pubSkills||[]).map(s=>`<option value="${s.id}">${esc(s.name)}</option>`).join('');
  $('view').innerHTML=`<div style="max-width:1060px"><div class="card"><div class="spread"><b style="font-size:16px">${esc(w.name)}</b> ${scopePill(w.scope)}
    <div><button class="btn btn-sm btn-ghost" onclick="vc_workflows()">返回</button>
    <button class="btn btn-sm btn-danger" onclick="wfDel(${w.id})">删除</button></div></div>
    <div class="mut small">${esc(w.description)}</div>
    <h3 class="sec">步骤（顺序执行）</h3><div id="wsteps">${stepEditors}</div>
    <div class="row" style="margin-top:10px"><select id="addskill" class="inp" style="flex:1">${addOpts||'<option value="">（没有已发布技能）</option>'}</select>
    <input id="addnote" class="inp" placeholder="本步说明(可选)" style="flex:1.5">
    <button class="btn" onclick="wfAddStep(${w.id})">＋ 添加步骤</button></div>
  </div>
  <div class="card"><h3 class="sec" style="margin-top:0">▶ 运行</h3>
    <textarea id="win" class="inp code" style="min-height:80px" placeholder="任务输入…"></textarea>
    <button class="btn btn-primary" style="margin-top:8px" onclick="wfRun(${w.id})">运行</button>
    <div id="wres" style="margin-top:10px"></div></div>
  <div class="card"><h3 class="sec" style="margin-top:0">最近运行</h3><div id="wrruns"></div></div></div>`;
  C.curWf=w;wfRuns();
}
async function wfAddStep(id){
  const sid=$('addskill').value;if(!sid)return;
  const w=await api('/workflows/'+id);
  w.steps.push({skill_id:+sid,note:$('addnote').value||''});
  await api('/workflows/'+id,{method:'PATCH',body:JSON.stringify({name:w.name,description:w.description,scope:w.scope,steps:w.steps})});
  wfOpen(id);
}
async function wfDelStep(id,i){
  const w=await api('/workflows/'+id);w.steps.splice(i,1);
  await api('/workflows/'+id,{method:'PATCH',body:JSON.stringify({name:w.name,description:w.description,scope:w.scope,steps:w.steps})});
  wfOpen(id);
}
async function wfMoveUp(id,i){if(i===0)return;const w=await api('/workflows/'+id);const [it]=w.steps.splice(i,1);w.steps.splice(i-1,0,it);
  await api('/workflows/'+id,{method:'PATCH',body:JSON.stringify({name:w.name,description:w.description,scope:w.scope,steps:w.steps})});wfOpen(id);}
async function wfRun(id){
  $('wres').innerHTML='<div class="loader"><span class="spin"></span> 运行中…（每步一次 LLM 调用，计入用量）</div>';
  try{const r=await api('/workflows/'+id+'/run',{method:'POST',body:JSON.stringify({input:$('win').value})});
    $('wres').innerHTML=r.steps.map((s,i)=>`<div style="margin-bottom:8px"><div class="pg-meta" style="margin-bottom:3px">Step ${i+1} · ${esc(s.skill)} v${s.version}</div><pre class="codeblock" style="max-height:240px">${esc(s.output)}</pre></div>`).join('')
      +`<div class="pg-meta">最终输出</div><pre class="codeblock">${esc(r.final)}</pre>`;wfRuns();}
  catch(e){$('wres').innerHTML='<div style="color:var(--red)">'+esc(e.message)+'</div>';}
}
async function wfRuns(){
  const runs=await api('/workflows/runs/mine').catch(()=>[]);
  const el=$('wrruns');if(!el)return;
  el.innerHTML='<table class="tbl"><tr><th>工作流</th><th>输入</th><th>步骤</th><th>时间</th></tr>'+runs.slice(0,8).map(r=>`<tr><td>${esc(r.workflow)}</td><td class="mut">${esc(r.input)}</td><td>${r.steps}</td><td class="mut small">${fmtTime(r.created_at)}</td></tr>`).join('')+'</table>';
}
async function wfDel(id){if(!confirm('删除工作流？'))return;await api('/workflows/'+id,{method:'DELETE'});toast('已删除','ok');vc_workflows();}

/* ================= Workspace ================= */
let curWs=null;
/* ================= 记忆 / 反思 / 用量 ================= */
async function vc_mem(){
  setTitle('长期记忆');setSub('Agent 记住的关于你的事实与偏好（反思也会自动更新）');
  $('view').innerHTML='<div id="memlist">'+loader()+'</div>';
  const rows=await api('/memory');
  $('memlist').innerHTML=rows.map(m=>`<div class="card card-hover"><div class="spread">
    <div style="flex:1"><div class="row"><b style="font-size:13.5px">${esc(m.key)}</b><span class="pill">${esc(m.kind)}</span><span class="mut small">${fmtTime(m.updated_at)}</span></div>
    <div class="mut" style="margin-top:4px">${esc(m.value)}</div></div>
    <button class="btn btn-ghost btn-sm" onclick="memDel(${m.id})">删除</button></div></div>`).join('')
    ||'<div class="empty"><div class="big">♆</div>暂无记忆 —— 对话中让 Agent 记住偏好，或用反馈触发反思沉淀</div>';
  window.memDel=async id=>{await api('/memory/'+id,{method:'DELETE'});toast('已删除','ok');vc_mem();};
}
async function vc_ref(){
  setTitle('反思日志');setSub('Agent 根据你的反馈自我迭代技能与记忆的记录');
  $('view').innerHTML='<div class="card row"><select id="refagent" class="inp"><option value="">全部 Agent</option></select></div><div id="refbody">'+loader()+'</div>';
  C.agents=await api('/agents');
  const sel=$('refagent');
  sel.innerHTML='<option value="">全部 Agent</option>'+C.agents.map(a=>`<option value="${a.id}">${esc(a.name)}</option>`).join('');
  sel.onchange=loadRefs;loadRefs();
}
async function loadRefs(){
  const aid=$('refagent').value;
  const ags=aid?[await api('/agents/'+aid)]:await Promise.all(C.agents.map(a=>api('/agents/'+a.id).catch(()=>null)));
  let all=[];
  for(const a of (aid?ags:ags.filter(Boolean))){try{const r=await api(`/agents/${a.id}/reflections`);r.forEach(x=>x.agent_name=a.name);all=all.concat(r);}catch(e){}}
  all.sort((x,y)=>(y.created_at||'').localeCompare(x.created_at||''));
  $('refbody').innerHTML=all.length?all.map(r=>`<div class="card"><div class="row">
    <b style="font-size:13.5px">${esc(r.agent_name||'')}</b>
    <span class="pill ${r.rating>=4?'published':'draft'}">${'★'.repeat(r.rating)}${'☆'.repeat(5-r.rating)}</span>
    <span class="mut small">${fmtTime(r.created_at)}</span></div>
    <div class="mut small" style="margin:5px 0">反馈：${esc(r.feedback||'(仅点赞)')}</div>
    <div class="small" style="margin:4px 0;color:var(--fg2)">${esc(r.analysis)}</div>
    ${renderActions(r)}</div>`).join(''):'<div class="empty"><div class="big">↻</div>还没有反思记录。在对话页给 Agent 回复点 👍/👎 并留言即可。</div>';
}
function renderActions(r){
  let h='';
  const acts=r.actions||[];
  const memKeys=(acts.find(a=>a.type==='memory')||{}).keys||[];
  const drafts=(acts.find(a=>a.type==='skill_draft')||{}).items||[];
  const prompt=(acts.find(a=>a.type==='prompt_suggestion')||{});
  if(memKeys.length)h+=`<div class="pg-meta" style="margin-top:4px">🧠 记忆更新：${esc(memKeys.join('、'))}</div>`;
  if(drafts.length)h+=`<div class="pg-meta" style="margin-top:2px">🧩 技能草稿：${esc(drafts.map(s=>s.name+' v'+s.version).join('、'))} ${drafts.map(s=>`<button class="btn btn-ghost btn-sm" style="margin-left:6px" onclick="goSkill(${s.skill_id})">打开</button>`).join('')}</div>`;
  if(prompt.text&&!prompt.applied)h+=`<div class="pg-meta" style="margin-top:2px">📝 有提示词建议 <button class="btn btn-ghost btn-sm" onclick="applyPrompt(${r.agent_id},${r.id})">采纳为 system_prompt</button></div>`;
  if(prompt.applied)h+=`<div class="pg-meta" style="margin-top:2px">📝 提示词建议已采纳</div>`;
  return h;
}
async function applyPrompt(aid,rid){
  try{await api(`/agents/${aid}/reflect/${rid}/apply-prompt`,{method:'POST'});toast('已采纳为 system_prompt','ok');loadRefs();}catch(e){toast(e.message,'err');}
}
async function goSkill(id){await show('skills');skillOpen(id);}
async function vc_usage(){
  setTitle('用量');setSub('LLM 调用统计（对话/技能测试/API/工作流/反思）');
  $('view').innerHTML=`<div class="card row"><span class="lbl" style="margin:0">聚合</span>
    <select id="ug" class="inp"><option value="agent">按 Agent</option><option value="provider">按 Provider</option><option value="model">按模型</option><option value="day">按天</option><option value="kind">按类型</option></select>
    <button class="btn btn-primary btn-sm" onclick="renderUsage()">查询</button></div>
    <div id="utab"></div><div class="card"><h3 class="sec" style="margin-top:0">最近调用</h3><div id="urec">${loader()}</div></div>`;
  renderUsage();
  const rec=await api('/usage/me/recent?limit=15');
  $('urec').innerHTML='<table class="tbl"><tr><th>时间</th><th>对象</th><th>kind</th><th>Provider/模型</th><th>tokens</th><th>成本$</th></tr>'+
    rec.map(r=>`<tr><td class="small mut">${fmtTime(r.ts)}</td><td>${esc(r.agent)}</td><td><span class="pill">${esc(r.kind)}</span></td><td class="mut">${esc(r.provider)}/${esc(r.model)}</td><td>${r.tokens}</td><td>${r.cost_usd}</td></tr>`).join('')+'</table>';
}
window.renderUsage=async function(){
  const g=$('ug').value;const d=await api('/usage/me?group_by='+g+'&days=30');
  const mx=Math.max(...d.rows.map(r=>r.cost_usd),1e-6);
  $('utab').innerHTML=`<div class="card"><b style="font-size:13px">按 ${g}（近 30 天）</b>
    <table class="tbl" style="margin-top:8px"><tr><th>维度</th><th>调用</th><th>tokens</th><th>成本$</th><th></th></tr>
    ${d.rows.map(r=>`<tr><td>${esc(r.label)}</td><td>${r.calls}</td><td>${r.input_tokens+r.output_tokens}</td><td>${r.cost_usd}</td>
    <td><div class="barwrap"><div class="bar" style="width:${Math.max(2,r.cost_usd/mx*100)}%"></div></div></td></tr>`).join('')||'<tr><td colspan=5 class="mut">无数据</td></tr>'}
    </table></div>`;
};

/* ================= Admin ================= */
async function vc_ov(){setTitle('平台总览');const s=await api('/admin/stats');
  $('view').innerHTML=`<div class="stat-grid">${stat('用户',s.users)+stat('Agents',s.agents)+stat('技能',s.skills)+stat('Providers',s.providers)+stat('LLM 调用',s.llm_calls)+stat('总 tokens',s.total_tokens)+stat('成本 $',s.cost_usd)+stat('流程运行',s.flow_runs)}</div>`;}
async function vc_admin_usage(){setTitle('全局用量');$('view').innerHTML=`<div class="card row"><span class="lbl" style="margin:0">聚合</span>
  <select id="ug2" class="inp"><option value="user">按用户</option><option value="agent">按 Agent</option><option value="provider">按 Provider</option><option value="model">按模型</option><option value="team">按团队</option><option value="day">按天</option><option value="kind">按类型</option></select>
  <button class="btn btn-primary btn-sm" onclick="adminUsage()">查询</button></div><div id="utab2"></div>`;adminUsage();}
async function adminUsage(){const g=$('ug2').value;const d=await api('/admin/usage?group_by='+g+'&days=30');
  const mx=Math.max(...d.rows.map(r=>r.cost_usd),1e-6);
  $('utab2').innerHTML=`<div class="card"><table class="tbl"><tr><th>${g}</th><th>调用</th><th>tokens</th><th>成本$</th><th></th></tr>
    ${d.rows.map(r=>`<tr><td>${esc(r.label)}</td><td>${r.calls}</td><td>${r.input_tokens+r.output_tokens}</td><td>${r.cost_usd}</td>
    <td><div class="barwrap"><div class="bar" style="width:${Math.max(2,r.cost_usd/mx*100)}%"></div></div></td></tr>`).join('')}</table></div>`;}
async function vc_prov(){setTitle('LLM Providers');$('view').innerHTML=`<div class="card"><b>新增 OpenAI 兼容 Provider</b>
  <div class="row" style="margin-top:8px"><input id="pn" class="inp" placeholder="名称" style="flex:1"><input id="purl" class="inp mono" placeholder="Base URL" style="flex:2"><input id="pkey" class="inp mono" placeholder="API Key" style="flex:1.5"></div>
  <div class="row" style="margin-top:8px"><input id="pm" class="inp" placeholder="模型(逗号分隔)" style="flex:1.5"><input id="pdm" class="inp" placeholder="默认模型" style="flex:1"><input id="ppi" class="inp" type="number" placeholder="输入价 $/MTok" style="width:120px"><input id="ppo" class="inp" type="number" placeholder="输出价" style="width:120px">
  <button class="btn btn-primary" onclick="provAdd()">添加</button></div></div><div id="ptab">${loader()}</div>`;provList();}
async function provList(){const ps=await api('/admin/providers');
  $('ptab').innerHTML=`<div class="card"><table class="tbl"><tr><th>名称</th><th>Base URL</th><th>Key</th><th>默认模型</th><th>状态</th><th></th></tr>
  ${ps.map(p=>`<tr><td><b>${esc(p.name)}</b></td><td class="mut mono">${esc(p.base_url)}</td><td class="mono">${esc(p.api_key_masked)}</td><td>${esc(p.default_model)}</td><td><span class="badge-dot ${p.enabled?'dot-green':'dot-red'}"></span> ${p.enabled?'启用':'停用'}</td><td><button class="btn btn-sm btn-ghost" onclick="provToggle(${p.id})">启/停</button></td></tr>`).join('')}</table></div>`;}
window.provToggle=async id=>{await api('/admin/providers/'+id+'/toggle',{method:'PATCH'});provList();};
window.provAdd=async()=>{const models=$('pm').value.split(',').map(s=>s.trim()).filter(Boolean);
  await api('/admin/providers',{method:'POST',body:JSON.stringify({name:$('pn').value,base_url:$('purl').value,api_key:$('pkey').value,models,default_model:$('pdm').value||models[0],price_in_per_mtok:parseFloat($('ppi').value||0),price_out_per_mtok:parseFloat($('ppo').value||0)})});provList();};
async function vc_aagents(){setTitle('Agent 管理');const as=await api('/admin/agents');
  $('view').innerHTML=`<div class="card"><table class="tbl"><tr><th>ID</th><th>名称</th><th>范围</th><th>Provider/模型</th><th>v</th><th>状态</th></tr>
  ${as.map(a=>`<tr><td>${a.id}</td><td><b>${esc(a.name)}</b></td><td>${scopePill(a.scope)}</td><td class="mut">${esc(a.provider)}/${esc(a.model)}</td><td>${a.version}</td><td><span class="badge-dot ${a.enabled?'dot-green':'dot-red'}"></span></td></tr>`).join('')}</table></div>`;}
async function vc_askill(){setTitle('技能治理');const list=await api('/admin/skills');
  $('view').innerHTML=list.map(s=>`<div class="card card-hover"><div class="spread"><div style="flex:1">
    <div class="row"><b style="font-size:14px">${esc(s.name)}</b> ${scopePill(s.scope)} ${s.api_enabled?'<span class="pill api">API</span>':''}</div>
    <div class="pg-meta" style="margin-top:3px">owner ${esc(s.owner)} · 已发布 ${s.published} · ${s.versions.map(v=>`v${v.version}(${v.status})`).join(' ')}</div></div>
    ${s.published>0?`<button class="btn btn-sm btn-warn" onclick="deprecate(${s.id})">下架最新版</button>`:''}</div></div>`).join('')||'<div class="empty">无技能</div>';
  window.deprecate=async id=>{await api('/admin/skills/'+id+'/deprecate',{method:'POST'});toast('已下架','ok');vc_askill();};}
async function vc_users(){setTitle('用户与团队');const us=await api('/admin/users');
  $('view').innerHTML=`<div class="card"><table class="tbl"><tr><th>ID</th><th>用户名</th><th>显示名</th><th>角色</th><th>团队</th></tr>
  ${us.map(u=>`<tr><td>${u.id}</td><td>${esc(u.username)}</td><td><b>${esc(u.display_name)}</b></td><td>${u.role==='platform_admin'?'<span class="pill admin">admin</span>':'<span class="pill">user</span>'}</td><td>${esc(u.team||'-')}</td></tr>`).join('')}</table></div>`;}

/* ================= HITL flows ================= */
async function vc_flows(){setTitle('多 Agent 流程演示');setSub('draft-review：Agent A 起草 → 人工审批门 → Agent B 评审，人保留最终决定权');
  $('view').innerHTML=`<div class="card"><div class="row"><input id="ftask" class="inp" placeholder="例如：起草新品发布公告" style="flex:1">
  <button class="btn btn-primary" onclick="fstart()">启动流程</button></div><div id="fd"></div></div>
  <div class="card"><h3 class="sec" style="margin-top:0">记录</h3><div id="flist">${loader()}</div></div>`;flist();}
async function flist(){const rows=await api('/flows');
  $('flist').innerHTML=`<table class="tbl"><tr><th>run</th><th>状态</th><th>任务</th></tr>${rows.map(r=>`<tr><td class="mono">${esc(r.run_id)}</td><td>${stPill(r.status)}</td><td>${esc(r.task)}</td></tr>`).join('')}</table>`;}
async function fstart(){const t=$('ftask').value;if(!t)return;$('fd').innerHTML='<div class="loader"><span class="spin"></span> 启动中…</div>';
  try{renderFlow(await api('/flows/draft-review',{method:'POST',body:JSON.stringify({task:t})}));}catch(e){$('fd').innerHTML='<span style="color:var(--red)">'+esc(e.message)+'</span>';}flist();}
function renderFlow(r){$('fd').innerHTML=`<div class="card"><div class="row"><b class="mono">${esc(r.run_id)}</b> ${stPill(r.status)}
  <span class="mut small">${esc(r.tip||'')}</span></div>
  ${r.draft?`<div class="lbl" style="margin-top:8px">Agent A 草稿</div><pre class="codeblock">${esc(r.draft)}</pre>`:''}
  ${r.final?`<div class="lbl" style="margin-top:8px">Agent B 评审</div><pre class="codeblock">${esc(r.final)}</pre>`:''}
  ${r.status==='waiting_approval'?`<div class="row" style="margin-top:10px"><input id="ffb" class="inp" placeholder="意见/驳回理由（可选）" style="flex:1">
  <button class="btn btn-green" onclick="fapp('${r.run_id}',true)">通过 → Agent B</button>
  <button class="btn btn-danger" onclick="fapp('${r.run_id}',false)">驳回</button></div>`:''}</div>`;}
async function fapp(id,ok){try{renderFlow(await api('/flows/'+id+'/approve',{method:'POST',body:JSON.stringify({approved:ok,feedback:$('ffb')?$('ffb').value:''})}));}catch(e){toast(e.message,'err');}flist();}

/* ============ boot ============ */
$('lp').addEventListener('keydown',e=>{if(e.key==='Enter')login();});
if(TOKEN&&ME){$('login').style.display='none';$('app').style.display='flex';boot();}
