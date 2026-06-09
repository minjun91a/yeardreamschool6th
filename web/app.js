/* 학습 올인원 — 하이브리드 웹 UI 로직 (pywebview 브릿지) */
'use strict';
const $  = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));
let API = null;

const GEM_URL = 'https://aistudio.google.com/apikey';
const CLAUDE_URL = 'https://console.anthropic.com/settings/keys';
const ANSWER_DELAY = 90, KOREAN_MIN = 8;
const THEMES = ['pastel','light','dark'];
const THEME_LABEL = { pastel:'파스텔', light:'라이트', dark:'다크' };
let curTheme = 'pastel';

/* ── 유틸 ── */
function esc(s){ return (s == null ? '' : String(s)).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function codeBlock(s){ return '<pre><code>' + esc(s) + '</code></pre>'; }
function toast(msg, kind){
  const t = document.createElement('div'); t.className = 'toast ' + (kind||''); t.textContent = msg;
  $('#toasts').appendChild(t); setTimeout(()=>t.remove(), 3200);
}
function ready(){ return !!API; }
function showModal(title, html){
  const ov = document.createElement('div'); ov.className = 'overlay on';
  ov.innerHTML = '<div class="sheet"><h2>'+esc(title)+'</h2><div class="md" style="overflow:auto;margin-top:10px;">'+html+
                 '</div><button class="btn ghost sm" style="margin-top:14px;align-self:flex-end;">닫기</button></div>';
  ov.querySelector('button').onclick = ()=>ov.remove();
  ov.addEventListener('click', e=>{ if(e.target===ov) ov.remove(); });
  document.body.appendChild(ov);
}

/* ── 첫 방문 사용 가이드(웰컴) ── */
function showWelcome(force){
  if(!force && localStorage.getItem('welcomed')) return;   // 첫 방문에만 자동 표시
  const ov = document.createElement('div'); ov.className = 'overlay on';
  ov.innerHTML =
    '<div class="sheet">'+
      '<h2>🎓 학습 올인원에 오신 걸 환영해요!</h2>'+
      '<div class="sub">Jupyter 노트 변환 · 스스로 코딩 연습 · 모르는 코드 질문을 한 곳에서.</div>'+
      '<div class="md" style="overflow:auto; flex:1 1 auto; min-height:0;">'+
        '<div class="banner">⚡ 시작 전 딱 한 가지 (1분·무료) — AI 기능을 쓰려면 무료 키가 필요해요.</div>'+
        '<ol>'+
          '<li><b>무료 Gemini 키 만들기</b> → <a href="#" id="wlkGem">AI Studio에서 발급 ↗</a></li>'+
          '<li><b>설정 ⚙️</b> 에 붙여넣고 <b>저장</b> → 끝!</li>'+
        '</ol>'+
        '<p class="placeholder">그러면 노트 변환·요점정리·AI 도우미·도움말이 모두 열려요. (Claude 키가 있으면 요점정리가 더 고품질)</p>'+
        '<h3>무엇을 할 수 있나요?</h3>'+
        '<ul>'+
          '<li>📄 <b>노트 변환</b> — Jupyter(.ipynb)를 깔끔한 학습노트로</li>'+
          '<li>🧠 <b>코딩 연습</b> — 예시 없이 스스로 코딩하고 자동 채점(키 없이도 가능)</li>'+
          '<li>💬 <b>AI 도우미</b> — 모르는 코드를 붙여넣고 질문</li>'+
          '<li>🎧 <b>도움말</b> — 사용법이 궁금하면 여기서 물어보세요</li>'+
        '</ul>'+
      '</div>'+
      '<div class="actions" style="margin-top:14px;">'+
        '<button class="btn" id="wlkKey">🔑 무료 키 등록하러 가기</button>'+
        '<button class="btn ghost sm" id="wlkClose">먼저 둘러볼게요</button>'+
      '</div>'+
    '</div>';
  const close = ()=>{ try{ localStorage.setItem('welcomed','1'); }catch(e){} ov.remove(); };
  ov.querySelector('#wlkClose').onclick = close;
  ov.querySelector('#wlkKey').onclick = ()=>{ close(); navTo('settings'); const i=$('#inGem'); if(i) i.focus(); };
  ov.querySelector('#wlkGem').onclick = (e)=>{ e.preventDefault(); if(ready()) API.open_url(GEM_URL); };
  ov.addEventListener('click', e=>{ if(e.target===ov) close(); });
  document.body.appendChild(ov);
}
function insertAt(ta, t){
  const s = ta.selectionStart, e = ta.selectionEnd;
  ta.value = ta.value.slice(0,s) + t + ta.value.slice(e);
  ta.selectionStart = ta.selectionEnd = s + t.length;
}
function attachEditor(ta, onCtrlEnter){
  ta.addEventListener('keydown', (e)=>{
    if(e.key === 'Tab'){ e.preventDefault(); insertAt(ta,'    '); return; }
    if(e.key === 'Enter' && (e.ctrlKey||e.metaKey)){ e.preventDefault(); if(onCtrlEnter) onCtrlEnter(); return; }
    if(e.key === 'Enter'){
      e.preventDefault();
      const before = ta.value.slice(0, ta.selectionStart);
      const line = before.slice(before.lastIndexOf('\n')+1);
      let indent = (line.match(/^[ \t]*/) || [''])[0];
      if(line.replace(/\s+$/,'').endsWith(':')) indent += '    ';
      insertAt(ta, '\n'+indent);
    }
  });
}

/* ── 내비게이션 ── */
function navTo(v){
  $$('.nav button').forEach(b=>b.classList.toggle('on', b.dataset.view===v));
  $$('.view').forEach(s=>s.classList.toggle('on', s.id==='view-'+v));
  if(v==='trainer' && T.phase==='idle') trOpenChooser();
  if(v==='notice') openNotices();
}

/* ── 공지사항 ── */
let noticeData = null, noticeLatest = 0;
async function loadNotices(){
  try { const r = await API.get_notices(); noticeData = (r && r.items) || []; }
  catch(e){ noticeData = []; }
  noticeLatest = noticeData.reduce((m,n)=>Math.max(m, n.id||0), 0);
  refreshNoticeBadge();
}
function refreshNoticeBadge(){
  const btn = $('.nav button[data-view="notice"]'); if(!btn) return;
  let seen = 0; try { seen = +(localStorage.getItem('notices_seen')||0); } catch(e){}
  let dot = btn.querySelector('.badge');
  if(noticeLatest > seen){ if(!dot){ dot = document.createElement('span'); dot.className='badge'; btn.appendChild(dot); } }
  else if(dot){ dot.remove(); }
}
function renderNotices(){
  const box = $('#noticeList'); if(!box) return;
  if(!noticeData || !noticeData.length){ box.innerHTML = '<div class="placeholder">아직 공지가 없어요.</div>'; return; }
  // body 는 운영자가 저장소에 직접 쓴 신뢰 콘텐츠(사용자 입력 아님) → HTML 그대로 렌더. 제목·날짜는 이스케이프.
  box.innerHTML = noticeData.map(n =>
    '<div class="notice-item"><div class="notice-h"><b>'+esc(n.title)+'</b>'+
    '<span class="notice-date">'+esc(n.date)+'</span></div>'+
    '<div class="md">'+(n.body||'')+'</div></div>').join('');
}
async function openNotices(){
  if(noticeData === null) await loadNotices();
  renderNotices();
  try { localStorage.setItem('notices_seen', String(noticeLatest)); } catch(e){}
  refreshNoticeBadge();
}

/* ── 테마 ── */
function applyTheme(t, save){
  if(THEMES.indexOf(t) < 0) t = 'pastel';
  curTheme = t;
  document.documentElement.setAttribute('data-theme', t);
  const tc = $('#themeCycle'); if(tc) tc.textContent = '🎨 테마 · ' + THEME_LABEL[t];
  $$('#themeOpts .theme-opt').forEach(b => b.classList.toggle('on', b.dataset.theme === t));
  if(save && ready()) API.save_theme(t);
}
function cycleTheme(){ const i = THEMES.indexOf(curTheme); applyTheme(THEMES[(i+1)%THEMES.length], true); }

/* ── 키 상태 ── */
async function refreshKeys(){
  if(!ready()) return;
  const k = await API.keys_status();
  const side = $('#sideStatus');
  if(k.claude){ side.className='foot'; side.innerHTML='<b>✨ Claude 연결됨 (요점정리 우선)</b>고품질 요약 · AI 도우미는 Gemini'; }
  else if(k.gemini){ side.className='foot gem'; side.innerHTML='<b>● Gemini 연결됨 (무료)</b>요점정리·AI 도우미'; }
  else { side.className='foot none'; side.innerHTML='<b>● 키 미설정</b>설정에서 무료 Gemini 키를 등록하세요'; }
  const cp = $('#convPill');
  if(k.claude){ cp.className='pill'; cp.innerHTML='<span class="dot"></span> Claude (우선)'; }
  else if(k.gemini){ cp.className='pill gem'; cp.innerHTML='<span class="dot"></span> Gemini (무료)'; }
  else { cp.className='pill none'; cp.innerHTML='<span class="dot"></span> 무료 Gemini 키 필요'; }
  const hp = $('#helpPill');
  if(k.gemini){ hp.className='pill gem'; hp.innerHTML='<span class="dot"></span> Gemini 연결됨'; }
  else { hp.className='pill none'; hp.innerHTML='<span class="dot"></span> Gemini 미설정'; }
  const sp = $('#supPill');
  if(sp){
    if(k.gemini){ sp.className='pill gem'; sp.innerHTML='<span class="dot"></span> Gemini 연결됨'; }
    else if(k.claude){ sp.className='pill'; sp.innerHTML='<span class="dot"></span> Claude 연결됨'; }
    else { sp.className='pill none'; sp.innerHTML='<span class="dot"></span> 키 미설정'; }
  }
  $('#stClaude').textContent = k.claude?'✓ 설정됨':'미설정'; $('#stClaude').className='kstat '+(k.claude?'on':'off');
  $('#stGem').textContent    = k.gemini?'✓ 설정됨':'미설정'; $('#stGem').className='kstat '+(k.gemini?'on':'off');
}

/* ── 변환 탭 ── */
const conv = { view:'raw', level:'concise', cache:{}, hasFile:false };
function placeholderConv(){ return '<div class="placeholder">먼저 파일을 여세요.</div>'; }
function levelLabel(l){ return ({concise:'핵심 요약', standard:'표준', cheatsheet:'치트시트'})[l] || l; }
function setSegUI(v){ $$('#viewSeg button').forEach(b=>b.classList.toggle('on', b.dataset.v===v)); }

async function convOpen(){
  if(!ready()) return;
  const r = await API.pick_notebook();
  if(!r.ok){ if(r.error) toast(r.error,'err'); return; }
  conv.hasFile = true; conv.cache = { raw: r.html };
  $('#fileChip').textContent = '📄 ' + r.name;
  await setView('raw');
  const s = $('#convStatus');
  s.textContent = '원본 변환 완료 · ' + r.chars.toLocaleString() + '자' + (r.images? ' · 이미지 '+r.images+'개':'') + '  — [✨ AI 요점정리]로 핵심만!';
  s.className = 'status ok';
}
async function setView(v){
  conv.view = v; setSegUI(v);
  if(v==='raw'){
    $('#convPreview').innerHTML = conv.cache.raw || placeholderConv();
    return;
  }
  if(!conv.hasFile){ conv.view='raw'; setSegUI('raw'); toast('먼저 파일을 여세요.','err'); return; }
  if(conv.cache[conv.level]){ $('#convPreview').innerHTML = conv.cache[conv.level]; return; }
  await summarize();
}
async function summarize(){
  if(!ready() || !conv.hasFile) return;
  $('#convPreview').innerHTML = '<div class="loading"><div class="spin"></div> AI가 ‘'+levelLabel(conv.level)+'’ 요점정리 중입니다… (십여 초~수십 초)</div>';
  const s = $('#convStatus'); s.textContent = '요약 중…'; s.className = 'status work';
  const r = await API.summarize(conv.level);
  if(r.nokey){ toast('AI 요점정리엔 키가 필요해요. 설정에서 무료 Gemini 키를 등록하세요.','err'); conv.view='raw'; setSegUI('raw'); $('#convPreview').innerHTML=conv.cache.raw||placeholderConv(); navTo('settings'); return; }
  if(!r.ok){ toast(r.error||'요약 실패','err'); conv.view='raw'; setSegUI('raw'); $('#convPreview').innerHTML=conv.cache.raw||placeholderConv(); return; }
  conv.cache[conv.level] = r.html; $('#convPreview').innerHTML = r.html;
  const m = r.provider==='claude' ? 'Claude' : 'Gemini';
  s.textContent = '✅ '+m+'로 요점정리 완료 — '+levelLabel(conv.level)+'. [💾 저장]으로 저장하세요.'; s.className='status ok';
}
async function convSave(){
  if(!ready()) return;
  const r = await API.save_md(conv.view, conv.level);
  if(r.ok) toast('저장됨 · ' + r.path, 'ok');
  else if(r.error) toast(r.error,'err');
}

/* ── 코드연습 상태머신 ── */
const T = { items:[], count:0, idx:0, scope:'', phase:'idle',
  elapsed:0, attempts:0, hint:0, kHint:0, sawAns:false, sawKEx:false, solvedOnce:false,
  fbRun:'', fbHints:[], fbAnswer:'', busy:false, timer:null };

function renderFB(){
  const fb = $('#trFeedback');
  let h = '';
  if(T.fbRun) h += T.fbRun;
  T.fbHints.forEach(x => h += x);
  if(T.fbAnswer) h += T.fbAnswer;
  fb.innerHTML = h || '<div class="placeholder">여기에 실행 결과와 힌트가 표시돼요.</div>';
  fb.scrollTop = fb.scrollHeight;
}
function applyPhase(ph){
  T.phase = ph;
  const code=$('#trCode'), run=$('#trRun'), hint=$('#trHint'), ans=$('#trAnswer'), gate=$('#trGate'), next=$('#trNext'), banner=$('#trBanner');
  if(ph==='korean'){
    banner.textContent='1단계 · 한국어로 풀이 설계 (코드칸 잠김). 막히면 [💡 단계 힌트] → [한국어 예시]';
    gate.classList.remove('hidden'); gate.disabled=false;
    code.disabled=true; run.disabled=true;
    hint.textContent='💡 단계 힌트'; hint.disabled=false;
    ans.textContent='한국어 예시'; ans.disabled=false;
    next.disabled=true;
  } else if(ph==='coding'){
    banner.textContent='2단계 · 코드 작성 → [▶ 실행]으로 채점. 막히면 [💡 힌트]부터!';
    gate.classList.add('hidden');
    code.disabled=false; code.focus();
    run.textContent='▶ 실행'; run.disabled=false;
    hint.textContent='💡 힌트'; hint.disabled=false;
    next.disabled=true;
    refreshAnswerBtn();
  } else if(ph==='solved'){
    banner.textContent='✅ 정답! 3단계 백지 복원으로 완전히 내 것으로 만들어요.';
    run.textContent='🧠 백지 복원'; run.disabled=false;
    hint.disabled=true; ans.disabled=true; next.disabled=false;
  } else if(ph==='reconstruct'){
    banner.textContent='3단계 · 백지 복원 — 안 보고 처음부터 다시! (힌트·정답 잠금)';
    gate.classList.add('hidden');
    run.textContent='▶ 복원 채점'; run.disabled=false;
    code.disabled=false; code.focus();
    hint.disabled=true; ans.disabled=true; next.disabled=false;
  }
}
function refreshAnswerBtn(){
  if(T.phase!=='coding') return;
  const ans=$('#trAnswer');
  const unlocked = T.elapsed>=ANSWER_DELAY || T.attempts>=5;
  if(T.sawAns){ ans.textContent='정답 다시'; ans.disabled=false; }
  else if(unlocked){ ans.textContent='정답 🔑'; ans.disabled=false; }
  else { const r=Math.max(0,ANSWER_DELAY-T.elapsed); ans.textContent='정답 🔒 '+Math.floor(r/60)+':'+String(r%60).padStart(2,'0'); ans.disabled=true; }
}
function startTick(){
  if(T.timer) return;
  T.timer = setInterval(()=>{
    if(T.phase==='coding' || T.phase==='reconstruct'){
      T.elapsed++;
      $('#trTimer').textContent='⏱ '+Math.floor(T.elapsed/60)+':'+String(T.elapsed%60).padStart(2,'0');
      refreshAnswerBtn();
    }
  }, 1000);
}
// 입력칸 안내문: SQL 단원은 '--'(SQL 주석), 파이썬은 '#'(파이썬 주석)으로 맞춘다.
function _codePH(){ return T.kind === 'sql' ? '-- 여기에 SQL을 작성하고 [▶ 실행]을 누르세요' : '# 여기에 코드를 작성하고 [▶ 실행]을 누르세요'; }
function _reconPH(){ return T.kind === 'sql' ? '-- 안 보고 처음부터 다시 쳐보세요' : '# 안 보고 처음부터 다시 쳐보세요'; }
async function trOpenChooser(){
  if(!ready()) return;
  const r = await API.trainer_topics();
  const list = $('#trTopicList'); list.innerHTML='';
  r.topics.forEach(t=>{
    const sub = t.seen===0 ? '아직 안 풂' : ('습득 '+t.mastered+' · 정답열람 '+t.needed+' · 풀이 '+t.seen);
    const b = document.createElement('button'); b.className='t-item';
    b.innerHTML = '<span class="ic">'+(t.bank?'📘':'🧩')+'</span><span><span class="big">단계 '+t.stage+'. '+esc(t.topic)+'</span><span class="meta">'+sub+'</span></span>'+(t.weakest?'<span class="star">⭐ 약점</span>':'');
    b.onclick = ()=>{ $('#trChooser').classList.remove('on'); trBegin(t.topic); };
    list.appendChild(b);
  });
  $('#trChooser').classList.add('on');
}
async function trBegin(sel){
  const r = await API.trainer_start(sel || null, 5);
  T.items=r.items; T.count=r.count; T.scope=r.scope; T.phase='loading';
  $('#trScope').textContent = '집중 단원: ' + r.scope;
  trLoad(0);
}
function trLoad(i){
  if(i>=T.count){ return trSummary(); }
  T.idx=i; T.elapsed=0; T.attempts=0; T.hint=0; T.kHint=0; T.sawAns=false; T.sawKEx=false; T.solvedOnce=false;
  T.fbRun=''; T.fbHints=[]; T.fbAnswer='';
  const it = T.items[i];
  T.kind = it.kind || 'python';
  $('#trProblem').innerHTML = it.q_html;
  $('#trKorean').value=''; $('#trCode').value=_codePH();
  $('#trCode').disabled=true; $('#trTimer').textContent='';
  $('#trProgress').textContent = '〔'+T.scope+'〕 '+(i+1)+'/'+T.count+' · '+it.topic;
  ['trRun','trHint','trAnswer'].forEach(id=>$('#'+id).disabled=false);
  renderFB();
  applyPhase('korean');
  $('#trKorean').focus();
}
function trGate(){
  const t = $('#trKorean').value.replace(/\s/g,'');
  if(t.length < KOREAN_MIN){ toast('무엇을 어떤 순서로 할지 한국어로 더 적어 주세요 (예: total을 0으로, 1~n 더하기, 출력)','err'); $('#trKorean').focus(); return; }
  $('#trCode').value=_codePH();
  applyPhase('coding');
}
async function trPrimary(){
  if(T.busy) return;
  if(T.phase==='coding') return trRun(false);
  if(T.phase==='solved') return enterReconstruct();
  if(T.phase==='reconstruct') return trRun(true);
}
async function trRun(recon){
  const code = $('#trCode').value;
  T.busy=true; $('#trRun').disabled=true; T.attempts++;
  let r;
  try { r = await API.trainer_run(T.idx, code, recon); }
  finally { T.busy=false; $('#trRun').disabled=false; }
  if(r.kind==='empty'){ T.fbRun='<p>❌ 코드가 비어 있어요. 한국어 단계를 한 줄씩 코드로 옮겨 보세요.</p>'; return renderFB(); }
  if(r.kind==='timeout'){ T.fbRun='<h3>❌ 시간 초과</h3><p>무한 루프일 수 있어요. while 조건이 언젠가 거짓이 되는지 확인하세요.</p>'; return renderFB(); }
  if(r.kind==='launch'){ T.fbRun='<h3>❌ 실행 실패</h3>'+codeBlock(r.err); return renderFB(); }
  const shown = r.got || '(아무것도 출력되지 않음)';
  if(r.match){
    if(recon){ T.fbRun='<h3>✅ 백지 복원 성공!</h3><p>안 보고 다시 만들었어요 — 완전 습득 🎉</p>'; renderFB(); return trFinish(true,true); }
    T.solvedOnce=true; T.fbRun='<h3>✅ 정답!</h3>'+codeBlock(shown); applyPhase('solved'); renderFB();
  } else {
    let h='<h3>❌ 아직 안 맞아요</h3><p><strong>기대한 출력</strong></p>'+codeBlock(r.expected)+'<p><strong>내 코드 출력</strong></p>'+codeBlock(shown);
    if(r.err) h += '<blockquote>'+esc(r.err)+'</blockquote>';
    h += recon ? '<p class="placeholder">괜찮아요. 기억을 더듬어 다시! (복원 단계는 힌트 잠금)</p>'
               : '<p class="placeholder">막히면 [💡 힌트]를 눌러 의도→도구부터 확인하세요.</p>';
    T.fbRun=h; renderFB();
  }
}
async function trHint(){
  if(T.phase==='korean'){
    if(T.kHint===0){ T.kHint=1; const r=await API.trainer_hint(T.idx,'k1'); T.fbHints.push('<h3>💡 한국어 힌트 ① 단계 나누는 법</h3><p>'+esc(r.text)+'</p>'); }
    else if(T.kHint===1){ T.kHint=2; const r=await API.trainer_hint(T.idx,'k2'); T.fbHints.push('<h3>💡 한국어 힌트 ② 의도 → 도구</h3><p>'+esc(r.text)+'</p>'); $('#trHint').disabled=true; }
    return renderFB();
  }
  if(T.phase!=='coding') return;
  if(T.hint===0){ T.hint=1; const r=await API.trainer_hint(T.idx,'c1'); T.fbHints.push('<h3>💡 힌트 ① 의도 → 도구</h3><p>'+esc(r.text)+'</p>'); }
  else if(T.hint===1){ T.hint=2; const r=await API.trainer_hint(T.idx,'c2'); T.fbHints.push('<h3>💡 힌트 ② 뼈대 — 여기서 출발해 채워 보세요</h3>'+codeBlock(r.code)); $('#trHint').disabled=true; }
  renderFB();
}
async function trAnswer(){
  if(T.phase==='korean'){
    T.sawKEx=true;
    const r = await API.trainer_korean_example(T.idx);
    T.fbAnswer='<h3>🧭 예시 설계 (한 가지 방법일 뿐 · 코드 아님)</h3>'+codeBlock(r.text)+'<p class="placeholder">위를 참고해 네 말로 ① 칸에 단계를 적고 [코드 시작 ▶].</p>';
    return renderFB();
  }
  if(T.phase!=='coding') return;
  T.sawAns=true;
  const r = await API.trainer_answer(T.idx);
  T.fbAnswer='<h3>🔑 정답 예시</h3>'+codeBlock(r.ans)+'<p><strong>출력</strong></p>'+codeBlock(r.out)+'<p class="placeholder">이해했으면 [🧠 백지 복원]으로 안 보고 다시 쳐보세요.</p>';
  applyPhase('solved'); renderFB();
}
function enterReconstruct(){
  T.elapsed=0; T.fbRun=''; T.fbHints=[]; T.fbAnswer=''; renderFB();
  $('#trCode').value=_reconPH();
  applyPhase('reconstruct');
}
function trNext(){
  if(T.phase==='solved' || T.phase==='reconstruct') trFinish(T.solvedOnce, false);
  else trFinish(false, false);  // 코딩 중 건너뛰기
}
async function trFinish(solved, mastered){
  const it = T.items[T.idx];
  await API.trainer_finish({ topic:it.topic, seconds:T.elapsed, attempts:T.attempts,
    hint_level:T.hint, saw_answer:T.sawAns, solved:!!solved, mastered:!!mastered });
  trLoad(T.idx+1);
}
async function trSummary(){
  T.phase='done'; $('#trTimer').textContent=''; $('#trBanner').textContent='🎉 이번 세션 완료!';
  $('#trProblem').innerHTML='<h1>오늘 훈련 끝!</h1><p class="placeholder">수고했어요. 아래 약점 주제를 확인하세요.</p>';
  $('#trKorean').value=''; $('#trCode').value=''; $('#trCode').disabled=true;
  ['trRun','trHint','trAnswer'].forEach(id=>$('#'+id).disabled=true);
  $('#trGate').classList.add('hidden');
  $('#trProgress').textContent='세션 요약';
  const r = await API.trainer_summary();
  T.fbRun='<h3>세션 완료</h3><p>다음에 집중하면 좋은 약점 주제: <strong>'+esc(r.weak)+'</strong></p>'+
          '<p class="placeholder">[🔄 주제 선택]으로 다른 단원을 이어서 연습하세요. 진행상황은 자동 저장됐어요.</p>';
  T.fbHints=[]; T.fbAnswer=''; renderFB();
}
async function trCheat(){ if(!ready()) return; const r = await API.cheatsheet(); showModal('의도 → 도구 치트시트', r.html); }

/* ── 코드도우미 ── */
let hpBusy = false;
async function hpAsk(){
  if(!ready() || hpBusy) return;
  const code = $('#hpCode').value.trim(), q = $('#hpQ').value.trim();
  if(!code && !q){ toast('코드나 질문 중 하나는 입력해 주세요','err'); return; }
  hpBusy=true; $('#hpAsk').disabled=true;
  $('#hpStatus').textContent='Gemini에게 물어보는 중…'; $('#hpStatus').className='status work';
  $('#hpAnswer').innerHTML='<div class="loading"><div class="spin"></div> 답변 생성 중…</div>';
  let r;
  try { r = await API.helper_ask(code, q); }
  finally { hpBusy=false; $('#hpAsk').disabled=false; }
  if(r.nokey){ toast('AI 도우미엔 무료 Gemini 키가 필요해요. 설정에서 등록하세요.','err'); $('#hpStatus').textContent=''; $('#hpAnswer').innerHTML='<div class="placeholder">설정에서 Gemini 키를 먼저 등록해 주세요.</div>'; navTo('settings'); return; }
  if(!r.ok){ $('#hpAnswer').innerHTML='<h3>오류가 발생했어요</h3><p>'+esc(r.error||'')+'</p>'; $('#hpStatus').textContent='오류'; $('#hpStatus').className='status err'; return; }
  $('#hpAnswer').innerHTML = r.html;
  $('#hpStatus').textContent = '✓ 완료' + (r.saved? ' · 저장됨 '+r.saved : ''); $('#hpStatus').className='status ok';
}
function hpClear(){ $('#hpCode').value=''; $('#hpQ').value=''; $('#hpAnswer').innerHTML='<div class="placeholder">코드와 질문을 넣고 <b>물어보기 ▶</b>를 눌러보세요.</div>'; $('#hpStatus').textContent=''; }

/* ── 고객센터(챗봇) ── */
const supHistory = [];     // 멀티턴 대화: {role:'user'|'assistant', content}
let supBusy = false;
function supBubble(role, html){
  const d = document.createElement('div');
  d.className = 'msg ' + (role==='user' ? 'user' : 'bot md');
  if(role==='user') d.textContent = html;     // 사용자 입력은 평문(이스케이프)으로
  else d.innerHTML = html;                     // 봇 답변은 서버가 만든 안전한 HTML
  const box = $('#supChat'); box.appendChild(d); box.scrollTop = box.scrollHeight;
  return d;
}
async function supSend(text){
  if(!ready() || supBusy) return;
  const q = (text != null ? text : $('#supInput').value).trim();
  if(!q) return;
  supBubble('user', q);
  supHistory.push({ role:'user', content:q });
  $('#supInput').value='';
  supBusy = true; $('#supSend').disabled = true;
  const loading = supBubble('bot', '<div class="loading"><div class="spin"></div> 답변 작성 중…</div>');
  let r;
  try { r = await API.support_ask(supHistory); }
  catch(e){ r = { ok:false, error:String(e) }; }
  finally { supBusy = false; $('#supSend').disabled = false; }
  loading.remove();
  if(r.nokey){
    supHistory.pop();   // 보내지 못한 질문은 히스토리에서 제거
    supBubble('bot', '<p>도움말을 이용하려면 <b>무료 Gemini 키</b>가 필요해요. 설정에서 등록해 주세요. 🙂</p>');
    toast('설정에서 무료 Gemini 키를 등록하세요.','err'); navTo('settings'); return;
  }
  if(!r.ok){
    supHistory.pop();
    supBubble('bot', '<p>죄송해요, 답변 중 문제가 생겼어요.<br>'+esc(r.error||'')+'</p>');
    return;
  }
  supBubble('bot', r.html);
  // 다음 턴 맥락용으로 봇 답변을 평문으로 보관(태그 제거)
  supHistory.push({ role:'assistant', content:(r.html||'').replace(/<[^>]+>/g,' ').replace(/\s+/g,' ').trim() });
  if(supHistory.length > 12) supHistory.splice(0, supHistory.length - 12);  // 토큰 과다 방지
}

/* 빠른 질문 4개는 AI 호출 없이 '고정 답변'으로 즉시 응답(키 불필요·오류 없음). 키 텍스트는 칩 글자와 일치. */
const SUPPORT_FIXED = {
  '노트 변환은 어떻게 쓰나요?':
    '<p><b>노트 변환 📄</b> 탭에서 <b>[📂 파일 열기]</b>로 Jupyter 노트북(.ipynb)을 고르면 학습노트로 바뀝니다.</p>'+
    '<ul><li><b>원본 변환</b> — 내용을 그대로</li>'+
    '<li><b>✨ AI 요점정리</b> — 핵심만 추려서(핵심요약·표준·치트시트 선택). <b>API 키가 필요</b>해요.</li></ul>'+
    '<p><b>[💾 .md 로 저장]</b> 으로 저장합니다.</p>',
  'API 키는 어디서 등록하나요?':
    '<p><b>설정 ⚙️</b> 탭에서 등록합니다.</p>'+
    '<ul><li><b>무료 Gemini 키</b> — Google AI Studio에서 무료로 발급 → 설정에 붙여넣고 <b>저장</b></li>'+
    '<li><b>Claude 키</b>(선택·유료 소액) — 요점정리를 더 고품질로</li></ul>'+
    '<p class="placeholder">키는 이 브라우저에만 저장되고 서버에는 저장되지 않아요(안전).</p>',
  '코딩 연습은 어떻게 하나요?':
    '<p><b>코딩 연습 🧠</b> 탭에서:</p>'+
    '<ol><li>주제 선택(파이썬 기초~클래스, <b>SQL</b> 단원도 있어요)</li>'+
    '<li>① 한국어로 풀이 설계 → ② 코드 작성 후 <b>[▶ 실행]</b> 으로 자동 채점</li>'+
    '<li>맞으면 <b>백지 복원</b>으로 한 번 더!</li></ol>'+
    '<p>막히면 <b>[💡 힌트]·[정답]</b> 을 단계적으로 볼 수 있어요. <b>키 없이도</b> 됩니다.</p>'+
    '<p class="placeholder">첫 실행은 실행 환경 준비로 몇 초 걸릴 수 있어요.</p>',
  '답변이 안 오거나 한도 초과래요':
    '<p>AI 답변(요점정리·AI 도우미·도움말)은 <b>무료 Gemini</b>를 쓰는데, 무료는 <b>분당·하루 요청 횟수 한도</b>가 있어요. 한도에 걸리면 이렇게 해보세요:</p>'+
    '<ol><li><b>잠시 후 다시</b> 시도 — 분당 한도면 1~2분 뒤 풀려요. (앱이 자동으로 몇 번 재시도도 해요)</li>'+
    '<li>하루 한도면 <b>다음 날</b> 초기화돼요(태평양 시간 자정 기준).</li>'+
    '<li><b>Claude 키</b>를 설정에 등록하면, Gemini가 한도일 때 <b>도움말이 Claude로 자동 전환</b>돼 답해요.</li>'+
    '<li>많이 쓰신다면 본인 Gemini 키에 <b>결제 등록</b>(매우 저렴)으로 한도를 크게 올릴 수 있어요.</li></ol>'+
    '<p class="placeholder">💡 키를 여러 개 만들어도 한도는 합쳐지지 않아요(프로젝트 단위).</p>',
  '버튼이 안 눌려요':
    '<ul><li>주소가 <b>https://…onrender.com</b> 인지 확인</li>'+
    '<li><b>Ctrl+F5</b> 로 새로고침(옛 캐시 제거)</li>'+
    '<li>AI 기능이면 <b>설정에서 무료 Gemini 키</b> 등록이 필요해요</li>'+
    '<li>한동안 방문이 없었다면 서버가 깨어나는 중일 수 있어요 — <b>최대 1분 뒤 다시 시도</b></li></ul>',
};
function supFixed(q){
  const key = (q || '').trim();
  const ans = SUPPORT_FIXED[key];
  if(!ans){ return supSend(key); }   // 매핑 없으면 AI로 폴백(안전)
  supBubble('user', key);
  supBubble('bot', ans);
  // 후속 AI 질문 맥락용으로 히스토리에도 평문으로 남김(서버 호출은 안 함)
  supHistory.push({ role:'user', content:key });
  supHistory.push({ role:'assistant', content: ans.replace(/<[^>]+>/g,' ').replace(/\s+/g,' ').trim() });
  if(supHistory.length > 12) supHistory.splice(0, supHistory.length - 12);
}

/* ── 설정 ── */
async function saveKey(which){
  if(!ready()) return;
  const val = (which==='claude'? $('#inClaude').value : $('#inGem').value).trim();
  if(!val){ toast('키를 입력해 주세요','err'); return; }
  const r = which==='claude' ? await API.save_claude_key(val) : await API.save_gemini_key(val);
  if(r.ok){ toast((which==='claude'?'Claude':'Gemini')+' 키 저장됨','ok'); conv.cache={ raw: conv.cache.raw }; await refreshKeys(); }
  else toast(r.error||'저장 실패','err');
}

/* ── 배선 ── */
function wire(){
  $$('.nav button').forEach(b => b.addEventListener('click', ()=>navTo(b.dataset.view)));
  // 변환
  $('#btnOpen').addEventListener('click', convOpen);
  $$('#viewSeg button').forEach(b => b.addEventListener('click', ()=>setView(b.dataset.v)));
  $$('#levelRow .tag').forEach(b => b.addEventListener('click', ()=>{
    conv.level=b.dataset.lvl; $$('#levelRow .tag').forEach(x=>x.classList.toggle('on', x===b));
    if(conv.view==='note') setView('note');
  }));
  $('#btnSave').addEventListener('click', convSave);
  $('#btnGeminiKey').addEventListener('click', ()=>{ navTo('settings'); $('#inGem').focus(); });
  // 코드연습
  $('#trGate').addEventListener('click', trGate);
  $('#trRun').addEventListener('click', trPrimary);
  $('#trHint').addEventListener('click', trHint);
  $('#trAnswer').addEventListener('click', trAnswer);
  $('#trNext').addEventListener('click', trNext);
  $('#btnCheat').addEventListener('click', trCheat);
  $('#btnReChoose').addEventListener('click', trOpenChooser);
  $('#trWeakAll').addEventListener('click', ()=>{ $('#trChooser').classList.remove('on'); trBegin(null); });
  attachEditor($('#trCode'), trPrimary);
  // 코드도우미
  $('#hpAsk').addEventListener('click', hpAsk);
  $('#hpClear').addEventListener('click', hpClear);
  attachEditor($('#hpCode'), hpAsk);
  $('#hpQ').addEventListener('keydown', e=>{ if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){ e.preventDefault(); hpAsk(); } });
  // 고객센터
  $('#supSend').addEventListener('click', ()=>supSend());
  $('#supInput').addEventListener('keydown', e=>{ if(e.key==='Enter' && !e.shiftKey){ e.preventDefault(); supSend(); } });
  $$('#supChips .chip-q').forEach(b => b.addEventListener('click', ()=>supFixed(b.textContent)));
  // 설정
  $('#saveClaude').addEventListener('click', ()=>saveKey('claude'));
  $('#saveGem').addEventListener('click', ()=>saveKey('gemini'));
  $('#lnkClaude').addEventListener('click', e=>{ e.preventDefault(); if(ready()) API.open_url(CLAUDE_URL); });
  $('#lnkGem').addEventListener('click', e=>{ e.preventDefault(); if(ready()) API.open_url(GEM_URL); });
  // 사용 가이드(웰컴 다시 보기)
  $('#btnGuide').addEventListener('click', ()=>showWelcome(true));
  // 테마
  $('#themeCycle').addEventListener('click', cycleTheme);
  $$('#themeOpts .theme-opt').forEach(b => b.addEventListener('click', ()=>applyTheme(b.dataset.theme, true)));
  applyTheme(document.documentElement.getAttribute('data-theme') || 'pastel', false);
  startTick();
}
/* ── 웹(서버) 모드 어댑터 ──
   데스크톱은 window.pywebview.api(네이티브 다리)를 쓰고, 브라우저(웹 서버)에는
   그 다리가 없으므로 같은 메서드 계약을 fetch 로 구현해 서버를 호출한다.
   이 함수는 웹 모드에서만 실행된다(아래 부트스트랩의 http/https 분기). */
function makeWebApi(){
  const notYet = (msg) => ({ ok:false, error: msg });
  let lastMd = '', lastTitle = '';     // 마지막 변환 결과(요점정리에 재사용)
  let trainerPack = null, trainerKoreanStep = '';  // 코드연습 세션(문제+정답+힌트) — 단계적 공개
  const readKeys = () => ({
    claude: localStorage.getItem('claude_key') || '',
    gemini: localStorage.getItem('gemini_key') || '',
  });

  /* ── 코드연습 실행(Pyodide) — 서버 대신 브라우저 워커에서 실행 ──
     데스크톱은 core.run_user_code(파이썬 subprocess)로 돌리지만, 웹에서는 서버가
     사용자 코드를 실행하면 위험(RCE)하므로 분리된 Web Worker 안 Pyodide 로 실행한다.
     채점 규칙(normalize_output/outputs_match)·friendly_error 는 core 와 동일하게 이식. */
  const PY_RUN_TIMEOUT_MS = 6000;   // core.RUN_TIMEOUT=6초 (실행 시간 한도; 첫 다운로드 시간은 별도)
  let _pyWorker = null;   // 현재 워커
  let _pyWarm = null;     // 워밍업(로딩) Promise. resolve(true)=준비완료 / resolve(false)=실패
  let _pyReqSeq = 0;      // 실행 요청 일련번호
  let _pyPending = null;  // { id, resolve, timer } — 진행 중 1건(코드연습은 한 번에 한 문제만 실행)

  // 워커 생성 + Pyodide 로딩 시작. 같은 Promise 를 캐시해 중복 로딩을 막는다.
  function _ensurePyReady(){
    if(_pyWarm) return _pyWarm;
    _pyWarm = new Promise((resolve) => {
      let settled = false;
      let w;
      try { w = new Worker('pyodide-worker.js'); }
      catch(e){ resolve(false); return; }
      _pyWorker = w;
      w.onmessage = (e) => {
        const m = e.data || {};
        if(m.type === 'ready'){ if(!settled){ settled = true; resolve(true); } return; }
        if(m.type === 'error'){ if(!settled){ settled = true; resolve(false); } return; }
        // 실행 응답
        if(_pyPending && m.id === _pyPending.id){
          clearTimeout(_pyPending.timer);
          const d = _pyPending; _pyPending = null;
          d.resolve(m);
        }
      };
      w.onerror = () => {
        if(!settled){ settled = true; resolve(false); }
        if(_pyPending){ const d = _pyPending; _pyPending = null; clearTimeout(d.timer);
          d.resolve({ kind:'launch', stdout:'', stderr:'실행 워커 오류' }); }
      };
      w.postMessage({ type:'warmup' });
    });
    return _pyWarm;
  }

  // 워커 폐기(무한 루프 강제 종료 등). 다음 실행 때 새로 로딩한다(WASM 은 브라우저 캐시 → 빠름).
  function _resetPyWorker(){
    try { if(_pyWorker) _pyWorker.terminate(); } catch(e){}
    _pyWorker = null; _pyWarm = null;
    if(_pyPending){ clearTimeout(_pyPending.timer); _pyPending = null; }
  }

  const DB_LOAD_TIMEOUT_MS = 30000; // 데이터셋(.db) 다운로드는 실행 제한과 분리(첫 1회만 큼)

  // 워커에 한 건 보내고 응답(또는 타임아웃)을 받는 공용 함수. 로딩 시간과 제한시간을 분리:
  // 준비될 때까지 기다린 뒤 타이머 시작. payload 에 따라 파이썬 실행·데이터로드·SQL 실행을 모두 처리.
  async function _callWorker(payload, timeoutMs){
    let ok = false;
    try { ok = await _ensurePyReady(); } catch(e){ ok = false; }
    if(!ok || !_pyWorker){
      _resetPyWorker();
      return { kind:'launch', stdout:'', stderr:'코드 실행 환경(Pyodide)을 불러오지 못했어요. 인터넷 연결을 확인해 주세요.' };
    }
    return new Promise((resolve) => {
      const id = ++_pyReqSeq;
      const timer = setTimeout(() => {
        // 제한시간 내 무응답 = 무한 루프/지연 추정 → 워커 강제 종료(유일한 탈출구) 후 폐기
        if(_pyPending && _pyPending.id === id) _pyPending = null;
        _resetPyWorker();
        resolve({ kind:'timeout', stdout:'', stderr:'' });
      }, timeoutMs);
      _pyPending = { id, resolve, timer };
      _pyWorker.postMessage(Object.assign({ id }, payload));
    });
  }
  async function _runInPyodide(code){ return _callWorker({ code }, PY_RUN_TIMEOUT_MS); }
  async function _loadDatasetInWorker(dataset){ return _callWorker({ kind:'loaddb', dataset }, DB_LOAD_TIMEOUT_MS); }
  // SQL: 데이터셋을 먼저 적재(다운로드 지연을 6초 실행제한과 분리)한 뒤, 쿼리를 6초 제한으로 실행.
  async function _runSqlInPyodide(sql, dataset, ordered){
    const load = await _loadDatasetInWorker(dataset);
    if(load.kind === 'launch') return load;
    if(load.kind === 'timeout') return { kind:'launch', stdout:'', stderr:'데이터 파일 로딩이 너무 오래 걸려요. 연결을 확인해 주세요.' };
    return _callWorker({ kind:'sql', sql, dataset, ordered }, PY_RUN_TIMEOUT_MS);
  }

  // ── 채점 규칙 이식(core.normalize_output/outputs_match/friendly_error 와 동일 동작) ──
  function _normalizeOutput(s){
    s = (s == null ? '' : String(s)).replace(/\r\n/g, '\n').replace(/\r/g, '\n');
    return s.split('\n').map(line => line.replace(/\s+$/, '')).join('\n').trim();
  }
  function _outputsMatch(got, expected){ return _normalizeOutput(got) === _normalizeOutput(expected); }
  const _ERR_TIPS = {
    SyntaxError: '문법 오류예요. 콜론(:) 빠짐, 괄호/따옴표 짝, 오타를 확인해 보세요.',
    IndentationError: '들여쓰기 문제예요. for/if 아래 줄은 보통 공백 4칸 들여써야 해요.',
    NameError: '정의하지 않은 이름을 썼어요. 변수 철자나 따옴표 누락을 확인해 보세요.',
    TypeError: '자료형이 안 맞아요. 숫자+글자는 str() 로 바꿔서 합쳐야 해요.',
    IndexError: '리스트 범위를 벗어났어요. 번호는 0부터, 길이보다 작아야 해요.',
    KeyError: '딕셔너리에 없는 이름표(key)를 꺼냈어요.',
    ZeroDivisionError: '0으로 나눴어요. 나누는 값이 0이 아닌지 확인해 보세요.',
    ValueError: '값이 함수가 기대하는 형태가 아니에요(예: 숫자 변환 실패).',
  };
  function _friendlyError(stderr){
    const lines = (stderr || '').trim().split('\n').filter(ln => ln.trim());
    if(!lines.length) return '';
    const last = lines[lines.length - 1].trim();
    for(const key in _ERR_TIPS){ if(last.indexOf(key) >= 0) return last + '\n   → ' + _ERR_TIPS[key]; }
    return last;
  }
  // SQL 오류 친절 설명(SQLite 메시지 → 초보자 힌트)
  function _sqlFriendly(stderr){
    const s = (stderr || '').trim();
    if(!s) return '';
    if(/no such table/i.test(s))            return s + '\n   → 테이블 이름을 확인하세요(철자·대소문자). 예: albums, tracks, customers, invoices.';
    if(/no such column/i.test(s))           return s + '\n   → 열 이름을 확인하세요. 문자열 값은 작은따옴표 \'USA\' 로, 열 이름엔 따옴표를 쓰지 않아요.';
    if(/syntax error/i.test(s))             return s + '\n   → 문법을 확인하세요: SELECT 열 FROM 테이블 [WHERE …] [ORDER BY …]; 끝에 세미콜론(;).';
    if(/one statement/i.test(s))            return s + '\n   → 한 번에 한 문장만 실행돼요. 쿼리 하나만 남겨 주세요.';
    return s;
  }

  // 브라우저용 파일 선택 → /api/convert/upload 업로드 변환
  function pickAndUpload(){
    return new Promise((resolve) => {
      let input = document.getElementById('webFileInput');
      if(!input){
        input = document.createElement('input');
        input.type = 'file'; input.accept = '.ipynb';
        input.id = 'webFileInput'; input.style.display = 'none';
        document.body.appendChild(input);
      }
      input.value = '';
      input.onchange = async () => {
        const f = input.files && input.files[0];
        if(!f){ resolve({ ok:false, cancel:true }); return; }
        try{
          const fd = new FormData(); fd.append('file', f, f.name);
          const res = await fetch('/api/convert/upload', { method:'POST', body:fd });
          const j = await res.json();
          if(j && j.ok){ lastMd = j.md || ''; lastTitle = (f.name || '').replace(/\.ipynb$/i, ''); }
          resolve(j);
        }catch(e){ resolve({ ok:false, error:'서버 연결 실패: ' + e }); }
      };
      input.click();   // 사용자 클릭 제스처 안에서 호출되어 파일창이 열린다
    });
  }

  // 코드연습 진행상황 — 이 브라우저(localStorage)에만 저장(서버 무상태·멀티유저 분리). 키·테마와 같은 방식.
  const PROG_KEY = 'trainer_progress';
  const readProg = () => { try { return JSON.parse(localStorage.getItem(PROG_KEY) || 'null'); } catch(e){ return null; } };
  const writeProg = (p) => { try { if(p) localStorage.setItem(PROG_KEY, JSON.stringify(p)); } catch(e){} };

  return {
    // ✅ 서버에 연결된 기능
    pick_notebook: () => pickAndUpload(),
    open_url: (u) => { window.open(u, '_blank'); return { ok:true }; },
    // 테마는 브라우저 로컬에 저장(서버 불필요)
    get_theme: () => ({ theme: localStorage.getItem('theme') || 'pastel' }),
    save_theme: (t) => { try{ localStorage.setItem('theme', t); }catch(e){} return { ok:true, theme:t }; },
    // 키는 브라우저 로컬에 보관(BYOK) — 요청마다 서버로 전송, 서버는 저장 안 함
    keys_status: () => { const k = readKeys(); return { claude: !!k.claude, gemini: !!k.gemini }; },
    save_claude_key: (k) => { localStorage.setItem('claude_key', (k || '').trim()); return { ok:true }; },
    save_gemini_key: (k) => { localStorage.setItem('gemini_key', (k || '').trim()); return { ok:true }; },

    // ✅ AI 요점정리 — 변환된 원본(md) + 키를 서버로 보내 호출
    summarize: async (level) => {
      if(!lastMd) return { ok:false, error:'먼저 Jupyter 파일을 여세요.' };
      const k = readKeys();
      if(!k.claude && !k.gemini) return { ok:false, nokey:true };
      try{
        const res = await fetch('/api/convert/summarize', {
          method:'POST', headers:{ 'Content-Type':'application/json' },
          body: JSON.stringify({ md:lastMd, level, title:lastTitle,
                                 anthropic_key:k.claude, gemini_key:k.gemini }),
        });
        return await res.json();
      }catch(e){ return { ok:false, error:'서버 연결 실패: ' + e }; }
    },

    // ⏳ 아직 서버 미연결: UI가 깨지지 않도록 안전/안내 응답
    save_md: () => notYet('저장은 다음 단계에서 연결돼요. 지금은 변환·요점정리 미리보기까지 가능해요.'),
    clear_notes: () => ({ ok:true }),
    helper_ask: async (code, question) => {
      const k = readKeys();
      if(!k.gemini) return { ok:false, nokey:true };
      try{
        const res = await fetch('/api/helper', {
          method:'POST', headers:{ 'Content-Type':'application/json' },
          body: JSON.stringify({ code, question, gemini_key:k.gemini }),
        });
        return await res.json();
      }catch(e){ return { ok:false, error:'서버 연결 실패: ' + e }; }
    },
    // ✅ 고객센터(앱 사용법 챗봇) — 대화 히스토리 + 키를 서버로 보내 멀티턴 응답
    support_ask: async (messages) => {
      const k = readKeys();
      if(!k.gemini && !k.claude) return { ok:false, nokey:true };
      try{
        const res = await fetch('/api/support', {
          method:'POST', headers:{ 'Content-Type':'application/json' },
          body: JSON.stringify({ messages, gemini_key:k.gemini, anthropic_key:k.claude }),
        });
        return await res.json();
      }catch(e){ return { ok:false, error:'서버 연결 실패: ' + e }; }
    },
    trainer_topics: async () => {
      _ensurePyReady().catch(()=>{});   // 코드연습 진입 시 Pyodide 미리 로딩 → 첫 [▶ 실행] 지연 최소화
      try{ return await (await fetch('/api/trainer/topics', {
        method:'POST', headers:{ 'Content-Type':'application/json' },
        body: JSON.stringify({ progress: readProg() }) })).json(); }
      catch(e){ return { topics: [] }; }
    },
    trainer_start: async (topic, count) => {
      const r = await (await fetch('/api/trainer/start', {
        method:'POST', headers:{ 'Content-Type':'application/json' },
        body: JSON.stringify({ topic: topic || null, count: count || 5, progress: readProg() }),
      })).json();
      trainerPack = r.items || [];
      trainerKoreanStep = r.korean_step || '';
      // q_html·topic·kind 등 '보여도 되는 것'만 노출. 정답/힌트는 trainerPack 에만 보관(단계적 공개).
      return { count: r.count, scope: r.scope,
               items: trainerPack.map(p => ({ idx:p.idx, topic:p.topic, stage:p.stage, q_html:p.q_html, kind:p.kind || 'python' })) };
    },
    trainer_hint: (idx, which) => {
      const p = (trainerPack || [])[idx] || {};
      if(which === 'k1') return { text: trainerKoreanStep };
      if(which === 'k2' || which === 'c1') return { text: p.intent || '' };
      if(which === 'c2') return { code: p.skeleton || '' };
      return { text: '' };
    },
    trainer_korean_example: (idx) => ({ text: ((trainerPack || [])[idx] || {}).korean_example || '' }),
    trainer_answer: (idx) => { const p = (trainerPack || [])[idx] || {}; return { ans: p.ans || '', out: p.out || '' }; },
    // 코드 실행·채점: 브라우저 워커(Pyodide)에서 실행 → core 와 같은 규칙으로 채점.
    // 응답 형태는 데스크톱 trainer_run 과 동일하게 유지({kind, match, expected, got, err}).
    trainer_run: async (idx, code, recon) => {
      const p = (trainerPack || [])[idx] || {};
      if(!(code || '').trim()) return { kind:'empty' };
      const isSql = p.kind === 'sql';
      let r;
      try { r = isSql ? await _runSqlInPyodide(code, p.dataset || '', !!p.ordered) : await _runInPyodide(code); }
      catch(e){ return { kind:'launch', err:'실행 환경 오류: ' + e }; }
      if(r.kind === 'timeout') return { kind:'timeout', err:'' };
      if(r.kind === 'launch')  return { kind:'launch', err: r.stderr || '코드 실행 환경을 불러오지 못했어요.' };
      const expected = p.out || '';
      const match = _outputsMatch(r.stdout, expected);
      return { kind:'ok', match,
               expected: expected.trim(),
               got: (r.stdout || '').trim(),
               err: match ? '' : (isSql ? _sqlFriendly(r.stderr) : _friendlyError(r.stderr)) };
    },
    trainer_finish: async (rec) => {
      try{
        const r = await (await fetch('/api/trainer/finish', {
          method:'POST', headers:{ 'Content-Type':'application/json' },
          body: JSON.stringify({ rec, progress: readProg() }) })).json();
        if(r && r.progress) writeProg(r.progress);   // 서버가 갱신한 진행상황을 이 브라우저에 저장
        return r;
      }
      catch(e){ return { ok:false }; }
    },
    trainer_summary: async () => {
      try{ return await (await fetch('/api/trainer/summary', {
        method:'POST', headers:{ 'Content-Type':'application/json' },
        body: JSON.stringify({ progress: readProg() }) })).json(); }
      catch(e){ return { weak:'(불러오기 실패)' }; }
    },
    cheatsheet: async () => {
      try{ return await (await fetch('/api/trainer/cheatsheet')).json(); }
      catch(e){ return { html:'<p class="placeholder">불러오기 실패</p>' }; }
    },
    // 공지사항 — 정적 파일(서버 StaticFiles). 운영자가 notices.json 한 줄 추가 후 배포하면 반영.
    get_notices: async () => {
      try{ return await (await fetch('notices.json', { cache:'no-store' })).json(); }
      catch(e){ return { items: [] }; }
    },
  };
}

async function initApi(api){
  API = api;
  try { const r = await API.get_theme(); applyTheme(r.theme, false); } catch(e){}
  refreshKeys();
  loadNotices();        // 공지 불러와서 새 공지 배지 표시
  showWelcome(false);   // 첫 방문이면 사용 가이드 자동 표시
}

wire();
if(location.protocol === 'http:' || location.protocol === 'https:'){
  initApi(makeWebApi());                                                  // 브라우저(웹 서버) 모드
} else if(window.pywebview && window.pywebview.api){
  initApi(window.pywebview.api);                                          // 데스크톱: 즉시 준비됨
} else {
  window.addEventListener('pywebviewready', ()=> initApi(window.pywebview.api));  // 데스크톱: 준비 대기
}

// 진단용: 지금 어떤 모드로 떴는지 콘솔에 한 줄. (F12 → Console 에서 확인)
console.log('[학습올인원] UI 모드:',
  (location.protocol === 'http:' || location.protocol === 'https:')
    ? 'web (fetch · 서버 연결됨)' : 'desktop/file (' + location.protocol + ')');
