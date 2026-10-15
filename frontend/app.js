'use strict';
const $ = s => document.querySelector(s);
const app = $('#app');
const MODS = ['常识判断', '言语理解与表达', '判断推理', '数量关系', '资料分析'];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const NATIVE = !!(window.Capacitor && window.Capacitor.isNativePlatform && window.Capacitor.isNativePlatform());
let BASE = NATIVE ? (localStorage.getItem('tj_server') || '').replace(/\/+$/, '') : '';
const abs = u => (BASE && typeof u === 'string' && u.startsWith('/')) ? BASE + u : u;
let TOKEN = localStorage.getItem('tj_token');
let ME = JSON.parse(localStorage.getItem('tj_user') || 'null');

async function api(path, opt = {}) {
  const h = opt.headers || {};
  if (TOKEN) h.Authorization = 'Bearer ' + TOKEN;
  if (opt.body && !(opt.body instanceof FormData)) { h['Content-Type'] = 'application/json'; opt.body = JSON.stringify(opt.body); }
  if (NATIVE && !BASE) { location.hash = '#/server'; throw new Error('请先设置服务器地址'); }
  const r = await fetch(abs(path), {...opt, headers: h});
  if (r.status === 401) { logout(); throw new Error('请先登录'); }
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.detail || ('请求失败 ' + r.status));
  return j;
}
function toast(m) { const t = $('#toast'); t.textContent = m; t.classList.add('show'); clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove('show'), 2200); }
function logout() { TOKEN = null; ME = null; localStorage.removeItem('tj_token'); localStorage.removeItem('tj_user'); location.hash = '#/login'; }

function ring(pct, size, stroke, color, inner) {
  const r = (size - stroke) / 2, c = 2 * Math.PI * r, off = c * (1 - Math.max(0, Math.min(1, pct)));
  return `<div class="ring" style="width:${size}px;height:${size}px"><svg width="${size}" height="${size}"><circle cx="${size/2}" cy="${size/2}" r="${r}" stroke="#2c3346" stroke-width="${stroke}" fill="none"/><circle cx="${size/2}" cy="${size/2}" r="${r}" stroke="${color}" stroke-width="${stroke}" fill="none" stroke-linecap="round" stroke-dasharray="${c}" stroke-dashoffset="${off}"/></svg><div class="c">${inner}</div></div>`;
}
const icons = {
  flag: '<svg viewBox="0 0 48 48"><path d="M6 40 20 20l6 8 4-5 12 17z"/><path d="M24 26V8l10 4-10 4"/></svg>',
  clock: '<svg viewBox="0 0 48 48"><circle cx="24" cy="24" r="17"/><path d="M24 14v10l6 5"/></svg>',
  book: '<svg viewBox="0 0 48 48"><path d="M6 12c6-2 12-2 18 2 6-4 12-4 18-2v24c-6-2-12-2-18 2-6-4-12-4-18-2z"/><path d="M24 14v24"/></svg>',
  doc: '<svg viewBox="0 0 48 48"><path d="M12 6h16l8 8v28H12z"/><path d="M28 6v8h8M18 22h12M18 28h8M30 30v8m-4-4 4 4 4-4"/></svg>',
};

// ---------- question rendering ----------
function imgs(list, cls = '') { return (list || []).map(u => { const w = +(new URL(u, location.href).searchParams.get('w') || 0); return `<img class="qimg ${cls}" loading="lazy" src="${abs(u)}" ${w ? `style="width:${Math.round(w * 1.55)}px"` : ''}>`; }).join(''); }
function renderQ(q, state = {}) {
  // state: {chosen:Set, reveal:{answer}, readonly}
  let h = '';
  if (q.material) {
    const m = q.material;
    h += `<details class="mat" ${state.matOpen !== false ? 'open' : ''}><summary class="mut sm">资料 / 材料</summary>${m.full.length ? imgs(m.full, 'inl') : esc(m.text)}${imgs(m.images)}</details>`;
  }
  h += `<div class="stem">${q.stem_full.length ? imgs(q.stem_full, 'inl') : esc(q.stem)}</div>${imgs(q.stem_images)}${imgs(q.option_images)}`;
  if (q.qtype === 'subjective') return h;
  h += `<div class="opts">`;
  const ans = state.reveal ? state.reveal.answer || '' : null;
  for (const o of q.options) {
    let cls = '';
    const sel = state.chosen && state.chosen.has(o.label);
    if (ans != null) { if (ans.includes(o.label)) cls = 'right'; else if (sel) cls = 'wrong'; }
    else if (sel) cls = 'sel';
    const body = o.images.length ? imgs(o.images, 'inl') : esc(o.text);
    h += `<button class="opt ${cls}" data-l="${o.label}" ${state.readonly ? 'disabled' : ''}><span class="lb">${o.label}</span><span class="ot">${body || '<span class="dim">见上图</span>'}</span></button>`;
  }
  return h + `</div>${q.qtype === 'multi' ? '<p class="mut sm">多选题：可选择多个选项</p>' : ''}`;
}
function bindOpts(q, chosen, onChange) {
  app.querySelectorAll('.opt').forEach(b => b.onclick = () => {
    const l = b.dataset.l;
    if (q.qtype === 'multi') chosen.has(l) ? chosen.delete(l) : chosen.add(l);
    else { chosen.clear(); chosen.add(l); }
    app.querySelectorAll('.opt').forEach(x => x.classList.toggle('sel', chosen.has(x.dataset.l)));
    onChange && onChange();
  });
}
function analysisCard(r) {
  const body = r.analysis_full && r.analysis_full.length ? imgs(r.analysis_full, 'inl') : `<div class="ana">${esc(r.analysis || '暂无解析')}</div>`;
  return `<div class="card" style="margin-top:14px"><h2>解析</h2>${body}${imgs(r.analysis_images)}</div>`;
}

// ---------- pages ----------
const routes = {};
function route(p, f) { routes[p] = f; }
async function go() {
  const hash = location.hash.slice(1) || '/';
  const [path, qs] = hash.split('?');
  const params = new URLSearchParams(qs || '');
  const parts = path.split('/').filter(Boolean);
  if (NATIVE && !BASE && parts[0] !== 'server') { location.hash = '#/server'; return; }
  if (!TOKEN && parts[0] !== 'server' && parts[0] !== 'login' && parts[0] !== 'register') { location.hash = '#/login'; return; }
  const key = '/' + (parts[0] || '');
  const tab = {'/': 'home', '/chapters': 'chapters', '/papers': 'papers', '/wrong': 'wrong', '/me': 'me', '/admin': 'me'}[key];
  const full = ['/server', '/practice', '/exam', '/login', '/register', '/wpractice'].includes(key);
  $('#tabbar').classList.toggle('hidden', full);
  document.querySelectorAll('#tabbar a').forEach(a => a.classList.toggle('on', a.dataset.tab === tab));
  clearInterval(window._timer);
  window.scrollTo(0, 0);
  try { await (routes[key] || routes['/'])(parts.slice(1).map(decodeURIComponent), params); }
  catch (e) { app.innerHTML = `<div class="card"><p class="co">${esc(e.message)}</p><a class="btn" href="#/">返回首页</a></div>`; }
}
window.addEventListener('hashchange', go);

function authPage(isReg) {
  app.innerHTML = `<div class="auth"><div class="brand">题境</div><p class="mut">福建事业单位真题 · 章节闯关 · 限时模考</p>
  <div class="card" style="margin-top:24px"><h2>${isReg ? '注册账号' : '登录'}</h2>
  <form id="f"><label>用户名</label><input name="username" autocomplete="username" required>
  <label>密码</label><input name="password" type="password" autocomplete="${isReg ? 'new-password' : 'current-password'}" required minlength="6">
  <button class="btn pri" style="width:100%;margin-top:20px">${isReg ? '注册并登录' : '登录'}</button></form>
  <p class="sm mut" style="text-align:center;margin-top:14px">${isReg ? '已有账号？<a class="ac" href="#/login">去登录</a>' : '还没有账号？<a class="ac" href="#/register">注册</a>'}</p></div></div>`;
  $('#f').onsubmit = async e => {
    e.preventDefault(); const fd = new FormData(e.target);
    try { const r = await api(isReg ? '/api/register' : '/api/login', {method: 'POST', body: {username: fd.get('username'), password: fd.get('password')}});
      TOKEN = r.token; ME = r.user; localStorage.setItem('tj_token', TOKEN); localStorage.setItem('tj_user', JSON.stringify(ME)); location.hash = '#/'; }
    catch (err) { toast(err.message); }
  };
}
route('/server', () => {
  app.innerHTML = `<div class="auth"><div class="brand">题境</div><p class="mut">连接你自己的题境服务器</p>
  <div class="card" style="margin-top:24px"><h2>服务器地址</h2>
  <form id="sf"><label>地址（如 http://192.168.1.10:8000）</label><input name="u" inputmode="url" autocapitalize="off" value="${esc(BASE || 'http://')}" required>
  <button class="btn pri" style="width:100%;margin-top:20px">测试并保存</button></form>
  <p class="sm mut" style="margin-top:12px">手机/iPad 需与服务器（Mac Mini）在同一 Wi‑Fi 下。</p></div></div>`;
  $('#sf').onsubmit = async e => {
    e.preventDefault(); let u = new FormData(e.target).get('u').trim().replace(/\/+$/, '');
    if (!/^https?:\/\//.test(u)) u = 'http://' + u;
    try { const r = await fetch(u + '/api/modules'); if (r.status >= 500 || r.status === 404) throw 0; }
    catch (_) { toast('连接失败，请检查地址和网络'); return; }
    if (u !== BASE) { TOKEN = null; localStorage.removeItem('tj_token'); localStorage.removeItem('tj_user'); }
    BASE = u; localStorage.setItem('tj_server', u); toast('已保存'); location.hash = TOKEN ? '#/' : '#/login';
  };
});
route('/login', () => authPage(false));
route('/register', () => authPage(true));

route('/', async () => {
  const d = await api('/api/home');
  const next = d.modules.find(m => m.cleared < m.levels) || d.modules[0];
  const tot = d.modules.reduce((a, m) => a + m.levels, 0), clr = d.modules.reduce((a, m) => a + m.cleared, 0);
  const dots = Math.min(8, next.levels), on = Math.min(dots, Math.round(next.cleared / Math.max(1, next.levels) * dots));
  app.innerHTML = `<div class="row between"><div class="row"><span class="brand">题境</span><span class="pill">🔥 连练 <b>${d.streak}</b> 天</span></div>
    ${ring(d.today / d.goal, 96, 7, '#2DD4BF', `<div class="sm mut">今日</div><div style="font-size:20px;font-weight:600">${d.today}/${d.goal}</div>`)}</div>
  <h1>今天练${esc(next.module)}</h1>
  <div class="grid4">
    <a class="card feat" href="#/chapters"><h3>章节闯关</h3>${icons.flag}<div class="row"><span class="ac sm">${next.cleared}/${next.levels}</span><div class="dots">${Array.from({length: dots}, (_, i) => `<i class="${i < on ? 'on' : ''}"></i>`).join('')}</div></div><span class="sm mut">按章节逐步突破</span></a>
    <a class="card feat" href="#/papers"><h3>限时模考</h3>${icons.clock}<span class="sm mut">${d.papers} 套真题整卷<br>模拟真实考试环境</span></a>
    <a class="card feat" href="#/wrong"><h3>错题回炉 ${d.wrong_open ? `<span class="badge">${d.wrong_open}</span>` : ''}</h3>${icons.book}<span class="sm mut">回顾错题，查漏补缺</span></a>
    <a class="card feat" href="${d.is_admin ? '#/admin' : '#/papers'}"><h3>导入真题</h3>${icons.doc}<span class="sm mut">${d.is_admin ? '上传试卷 + 答案 PDF' : `题库 ${d.total_questions} 题`}</span></a>
  </div>
  <div class="grid2" style="margin-top:14px">
    <div class="card"><h2>模块进度</h2>${d.modules.map(m => `<a href="#/chapters?m=${encodeURIComponent(m.module)}" class="row between" style="padding:7px 0"><span>${m.module}</span><span class="row sm mut" style="width:55%"><span class="prog"><i style="width:${m.answered / Math.max(1, m.total) * 100}%"></i></span>${m.answered}/${m.total}</span></a>`).join('')}</div>
    <div class="card"><h2>概览</h2><div class="row between"><div><div class="kpi">${clr}<span class="sm mut">/${tot}</span></div><div class="sm mut">已通关卡</div></div><div><div class="kpi">${d.today_correct}</div><div class="sm mut">今日答对</div></div><div><div class="kpi">${d.last_exam ? d.last_exam.score + '<span class="sm mut">/' + d.last_exam.total + '</span>' : '—'}</div><div class="sm mut">最近模考</div></div></div></div>
  </div>`;
});

route('/chapters', async (_, p) => {
  const ms = await api('/api/modules');
  const sel = p.get('m') || (ms.find(m => m.cleared < m.levels) || ms[0]).module;
  const m = ms.find(x => x.module === sel) || ms[0];
  app.innerHTML = `<h1>章节闯关</h1><div class="tabs">${ms.map(x => `<button class="${x.module === m.module ? 'on' : ''}" data-m="${x.module}">${x.module}</button>`).join('')}</div>
  <div class="card"><div class="row between"><div><h2 style="margin:0">${m.module}</h2><span class="sm mut">共 ${m.total} 题 · ${m.levels} 关 · 每关 10 题${m.accuracy != null ? ' · 正确率 ' + m.accuracy + '%' : ''}</span></div>
  ${ring(m.cleared / Math.max(1, m.levels), 64, 5, '#2DD4BF', `<span class="sm">${m.cleared}/${m.levels}</span>`)}</div>
  <div class="lvl">${Array.from({length: m.levels}, (_, i) => `<a href="#/practice/${encodeURIComponent(m.module)}/${i + 1}" class="${i < m.cleared ? 'clear' : i === m.cleared ? 'next' : ''}">第${i + 1}关</a>`).join('')}</div></div>`;
  app.querySelectorAll('.tabs button').forEach(b => b.onclick = () => location.hash = '#/chapters?m=' + encodeURIComponent(b.dataset.m));
});

// generic practice runner (chapter & wrong book)
function runPractice({title, questions, mode, onExit}) {
  let i = 0, stats = {ok: 0, n: 0};
  const show = () => {
    if (i >= questions.length) {
      app.innerHTML = `<div class="card" style="text-align:center;padding:40px 20px;margin-top:40px">${ring(stats.n ? stats.ok / stats.n : 0, 120, 8, '#2DD4BF', `<div style="font-size:26px;font-weight:700">${stats.ok}/${stats.n}</div><div class="sm mut">答对</div>`)}
        <h2 style="margin-top:18px">本关完成</h2><p class="mut">${stats.n - stats.ok ? '错题已自动收入错题本' : '全部答对，漂亮！'}</p><div class="row" style="justify-content:center"><a class="btn" href="${onExit}">返回</a></div></div>`;
      return;
    }
    const q = questions[i], chosen = new Set();
    app.innerHTML = `<div class="topbar"><a class="back" href="${onExit}">✕</a><span class="qtag">${esc(title)} · ${esc(q.module)}</span><span class="prog"><i style="width:${i / questions.length * 100}%"></i></span><span class="sm mut">${i + 1}/${questions.length}</span></div>
      <div class="sm dim">${esc(q.paper.title)} · 第 ${q.num} 题</div>${renderQ(q, {chosen})}
      <div class="actions"><button class="btn ghost" id="prev" ${i ? '' : 'disabled'}>上一题</button><button class="btn pri" id="sub" disabled>提交</button></div>`;
    bindOpts(q, chosen, () => $('#sub').disabled = !chosen.size);
    $('#prev').onclick = () => { i--; show(); };
    $('#sub').onclick = async () => {
      const r = await api('/api/answer', {method: 'POST', body: {question_id: q.id, chosen: [...chosen].join(''), mode}});
      stats.n++; if (r.correct) stats.ok++;
      app.innerHTML = `<div class="topbar"><a class="back" href="${onExit}">✕</a><span class="qtag">${esc(title)} · ${esc(q.module)}</span><span class="prog"><i style="width:${(i + 1) / questions.length * 100}%"></i></span><span class="sm mut">${i + 1}/${questions.length}</span></div>
      <div class="verdict ${r.correct ? 'ok' : 'no'}"><div class="ic">${r.correct ? '✓' : '✕'}</div><div><div style="font-size:22px;font-weight:700">${r.correct ? '答对了' : '答错了'}</div><div class="sm mut">${r.correct ? '继续保持' : '已自动收入错题本 · 累计错 ' + r.wrong_count + ' 次'}</div></div></div>
      <div class="cmp"><div class="card"><div class="sm mut">你的答案</div><b class="${r.correct ? 'ac' : 'co'}">${esc(r.chosen)}</b></div><div class="card"><div class="sm mut">正确答案</div><b class="ac">${esc(r.answer)}</b></div></div>
      <div style="margin-top:14px">${renderQ(q, {chosen, reveal: r, readonly: true, matOpen: false})}</div>${analysisCard(r)}
      <div class="actions">${mode === 'wrongbook' && r.correct ? `<button class="btn" id="mst">标记已掌握</button>` : `<button class="btn" id="add" ${r.in_wrongbook ? 'disabled' : ''}>${r.in_wrongbook ? '已在错题本' : '收入错题本'}</button>`}<button class="btn pri" id="nx">下一题</button></div>`;
      $('#nx').onclick = () => { i++; show(); };
      const add = $('#add'); if (add) add.onclick = async () => { await api('/api/wrongbook/' + q.id, {method: 'POST'}); add.disabled = true; add.textContent = '已在错题本'; toast('已收入错题本'); };
      const mst = $('#mst'); if (mst) mst.onclick = async () => { await api(`/api/wrongbook/${q.id}/mastered`, {method: 'POST'}); mst.disabled = true; mst.textContent = '已掌握'; toast('已标记掌握'); };
    };
  };
  show();
}
route('/practice', async ([mod, lv]) => {
  const d = await api(`/api/practice?module=${encodeURIComponent(mod)}&level=${lv}`);
  runPractice({title: `第${lv}关`, questions: d.questions, mode: 'practice', onExit: '#/chapters?m=' + encodeURIComponent(mod)});
});
route('/wpractice', async (_, p) => {
  const qs = new URLSearchParams(); if (p.get('m')) qs.set('module', p.get('m')); if (p.get('q')) qs.set('qid', p.get('q'));
  const d = await api('/api/wrongbook/practice?' + qs);
  if (!d.questions.length) { toast('没有待回炉的错题'); location.hash = '#/wrong'; return; }
  runPractice({title: '错题回炉', questions: d.questions, mode: 'wrongbook', onExit: '#/wrong'});
});

route('/wrong', async (_, p) => {
  const m = p.get('m') || '';
  const d = await api('/api/wrongbook' + (m ? '?module=' + encodeURIComponent(m) : ''));
  app.innerHTML = `<div class="row between"><h1>错题回炉</h1>${ring(d.rate / 100, 84, 6, '#2DD4BF', `<div style="font-weight:700">${d.rate}%</div><div class="sm mut">掌握率</div>`)}</div>
  <div class="tabs"><button class="${m ? '' : 'on'}" data-m="">全部</button>${MODS.map(x => `<button class="${x === m ? 'on' : ''}" data-m="${x}">${x}${d.counts[x] ? ' ' + d.counts[x] : ''}</button>`).join('')}</div>
  <div class="row between" style="margin-bottom:12px"><span class="sm mut">共 ${d.total} 题 · 已掌握 ${d.mastered}</span><a class="btn pri sm" href="#/wpractice${m ? '?m=' + encodeURIComponent(m) : ''}">全部再练</a></div>
  <div class="list">${d.items.length ? d.items.map(it => `<div class="card wcard"><div class="meta"><div class="row sm"><span class="qtag">${it.module}</span>${it.wrong_count ? `<span class="cnt">错 ${it.wrong_count} 次</span>` : '<span class="cnt">手动收藏</span>'}${it.mastered ? '<span class="ac">已掌握</span>' : ''}</div><p>${esc(it.stem)}</p><div class="sm dim">${esc(it.title)} · 第${it.num}题</div></div>
    <div class="row" style="flex-direction:column;gap:8px"><a class="btn sm" href="#/wpractice?q=${it.question_id}" ${it.mastered ? 'style="pointer-events:none;opacity:.4"' : ''}>再练</a><button class="btn sm ghost" data-ms="${it.question_id}" data-v="${it.mastered ? 0 : 1}">${it.mastered ? '取消掌握' : '已掌握'}</button></div></div>`).join('') : '<div class="card mut" style="text-align:center">还没有错题，去闯关吧</div>'}</div>`;
  app.querySelectorAll('.tabs button').forEach(b => b.onclick = () => location.hash = '#/wrong' + (b.dataset.m ? '?m=' + encodeURIComponent(b.dataset.m) : ''));
  app.querySelectorAll('[data-ms]').forEach(b => b.onclick = async () => { await api(`/api/wrongbook/${b.dataset.ms}/mastered?value=${b.dataset.v}`, {method: 'POST'}); go(); });
});

route('/papers', async () => {
  const ps = await api('/api/papers'); const ex = await api('/api/exams');
  app.innerHTML = `<h1>限时模考</h1><div class="list">${ps.map(p => `<div class="card row between wrap"><div style="flex:1;min-width:220px"><div style="font-weight:600">${esc(p.title)}</div><div class="sm mut">${p.kind === 'subjective' ? '主观题 · 仅展示参考答案' : `${p.gradable} 题 · ${p.duration_min} 分钟${p.best != null ? ' · 最佳 ' + p.best + ' 分' : ''}`}</div></div>
   ${p.kind === 'subjective' ? `<a class="btn sm" href="#/paper/${p.id}">查看</a>` : `<button class="btn pri sm" data-p="${p.id}">开始模考</button>`}</div>`).join('')}</div>
   ${ex.length ? `<h2 style="margin-top:26px">考试记录</h2><div class="card"><table><tr><th>试卷</th><th>得分</th><th></th></tr>${ex.map(e => `<tr><td>${esc(e.title)}</td><td>${e.submitted ? e.score + '/' + e.total : '<span class="co">未交卷</span>'}</td><td><a class="ac" href="#/exam/${e.id}">${e.submitted ? '报告' : '继续'}</a></td></tr>`).join('')}</table></div>` : ''}`;
  app.querySelectorAll('[data-p]').forEach(b => b.onclick = async () => { const e = await api('/api/exams', {method: 'POST', body: {paper_id: +b.dataset.p}}); location.hash = '#/exam/' + e.id; });
});

route('/paper', async ([pid]) => {
  const d = await api('/api/papers/' + pid);
  app.innerHTML = `<div class="topbar"><a class="back" href="#/papers">‹</a><span>${esc(d.paper.title)}</span></div>${d.questions.map(q => `<div class="card"><div class="stem" style="font-size:15px">${esc(q.stem)}</div></div>${analysisCard(q)}`).join('')}`;
});

route('/exam', async ([eid]) => {
  let e = await api('/api/exams/' + eid);
  if (e.submitted) return report(e);
  const qs = e.questions, ans = e.answers; let i = 0, saveT;
  const skew = Date.now() / 1000 - e.now;
  const total = e.paper.duration_min * 60;
  const save = () => { clearTimeout(saveT); saveT = setTimeout(() => api(`/api/exams/${eid}/answers`, {method: 'PUT', body: {answers: ans}}).catch(() => {}), 400); };
  const submit = async () => { clearInterval(window._timer); const r = await api(`/api/exams/${eid}/submit`, {method: 'POST', body: {answers: ans}}); report(r); };
  const fmt = s => [Math.floor(s / 3600), Math.floor(s % 3600 / 60), Math.floor(s % 60)].map(x => String(x).padStart(2, '0')).join(':');
  const tick = () => { const left = Math.max(0, e.deadline - (Date.now() / 1000 - skew)); const t = $('#tm'); if (t) t.innerHTML = ring(left / total, 92, 5, '#F87171', `<span style="font-variant-numeric:tabular-nums;color:#F87171;font-weight:600">${fmt(left)}</span>`); if (left <= 0) { toast('时间到，自动交卷'); submit(); } };
  const show = () => {
    const q = qs[i], chosen = new Set((ans[q.id] || '').split('').filter(Boolean));
    const done = qs.filter(x => ans[x.id]).length;
    app.innerHTML = `<div class="topbar"><a class="back" href="#/papers">‹</a><span class="sm mut" style="flex:1">${esc(e.paper.title)}</span></div>
    <div style="text-align:center"><div id="tm"></div><div class="mut sm">第 <span class="co">${i + 1}/${qs.length}</span> 题 · 已答 ${done}</div></div>
    <div class="card" style="margin-top:14px"><span class="qtag">${esc(q.module)}</span>${renderQ(q, {chosen})}</div>
    <div class="card" style="padding:0;margin-top:12px"><div class="sheet" id="sheet">${qs.map((x, k) => `<button data-k="${k}" class="${ans[x.id] ? 'done' : ''} ${k === i ? 'cur' : ''}">${k + 1}</button>`).join('')}</div></div>
    <div class="actions"><div class="row"><button class="btn ghost" id="prev" ${i ? '' : 'disabled'}>上一题</button><button class="btn" id="next" ${i < qs.length - 1 ? '' : 'disabled'}>下一题</button></div><button class="btn warn" id="hand">交卷</button></div>`;
    tick();
    bindOpts(q, chosen, () => { ans[q.id] = [...chosen].join(''); save(); const b = app.querySelector(`#sheet [data-k="${i}"]`); b.classList.toggle('done', !!ans[q.id]); if (q.qtype !== 'multi' && i < qs.length - 1) setTimeout(() => { i++; show(); }, 250); });
    $('#prev').onclick = () => { i--; show(); }; $('#next').onclick = () => { i++; show(); };
    app.querySelectorAll('#sheet button').forEach(b => b.onclick = () => { i = +b.dataset.k; show(); });
    const cur = app.querySelector('#sheet .cur'); if (cur) cur.scrollIntoView({inline: 'center', block: 'nearest'});
    $('#hand').onclick = () => { const left = qs.length - qs.filter(x => ans[x.id]).length; if (confirm(left ? `还有 ${left} 题未作答，确定交卷？` : '确定交卷？')) submit(); };
  };
  clearInterval(window._timer); window._timer = setInterval(tick, 1000);
  show();
});
function report(e) {
  clearInterval(window._timer);
  const r = e.report, wrong = new Set(r.wrong);
  app.innerHTML = `<div class="topbar"><a class="back" href="#/papers">‹</a><span class="sm mut">${esc(e.paper.title)}</span></div>
  <div class="card" style="text-align:center;padding:28px">${ring(r.score / Math.max(1, r.total), 140, 9, '#2DD4BF', `<div style="font-size:34px;font-weight:700">${r.score}</div><div class="sm mut">/ ${r.total} 题</div>`)}
  <p class="mut">正确率 ${Math.round(r.score / Math.max(1, r.total) * 100)}% · 作答 ${r.answered} 题 · 用时 ${Math.round(r.used_sec / 60)} 分钟</p><p class="sm co">${r.wrong.length} 道错题已收入错题本</p></div>
  <div class="card" style="margin-top:14px"><h2>模块得分</h2><table><tr><th>模块</th><th>答对</th><th>未答</th><th>正确率</th></tr>${Object.entries(r.per_module).map(([m, v]) => `<tr><td>${m}</td><td>${v.correct}/${v.total}</td><td>${v.blank}</td><td>${Math.round(v.correct / v.total * 100)}%</td></tr>`).join('')}</table></div>
  <div class="card" style="padding:0;margin-top:14px"><div class="sheet">${e.questions.map((q, k) => `<button class="${e.answers[q.id] ? (wrong.has(q.id) ? 'bad' : 'done') : ''}" data-k="${k}">${k + 1}</button>`).join('')}</div></div>
  <div id="rv" style="margin-top:14px"></div>`;
  app.querySelectorAll('.sheet button').forEach(b => b.onclick = () => {
    const q = e.questions[+b.dataset.k];
    $('#rv').innerHTML = `<div class="card"><span class="qtag">${esc(q.module)} · 第${q.num}题</span>${renderQ(q, {chosen: new Set((e.answers[q.id] || '').split('')), reveal: q, readonly: true})}</div>${analysisCard(q)}`;
    $('#rv').scrollIntoView({behavior: 'smooth'});
  });
}

route('/me', async () => {
  const me = await api('/api/me');
  app.innerHTML = `<h1>我的</h1><div class="card row between"><div><div style="font-size:20px;font-weight:600">${esc(me.username)}</div><div class="sm mut">${me.is_admin ? '管理员' : '学员'}</div></div><button class="btn" id="lo">退出登录</button></div>
  ${NATIVE ? `<a class="card row between" style="margin-top:12px" href="#/server"><span>服务器地址</span><span class="mut sm">${esc(BASE)} ›</span></a>` : ''}
  ${me.is_admin ? '<a class="card row between" style="margin-top:12px" href="#/admin"><span>题库管理 / 导入真题</span><span class="mut">›</span></a>' : ''}
  <div class="card" style="margin-top:12px"><h2>安装到手机</h2><p class="sm mut">iPhone：Safari 打开 → 分享 → 添加到主屏幕。安卓：Chrome 菜单 → 安装应用 / 添加到主屏幕。</p></div>`;
  $('#lo').onclick = logout;
});

route('/admin', async () => {
  const s = await api('/api/admin/stats');
  app.innerHTML = `<div class="topbar"><a class="back" href="#/me">‹</a><h2 style="margin:0">题库管理</h2></div>
  <div class="card"><h2>导入真题</h2><p class="sm mut">上传一份试题 PDF 和对应的答案解析 PDF。扫描版答案会自动 OCR，图形 / 公式 / 图表会自动裁图挂到题目上。重复导入同名试卷会覆盖。</p>
  <form id="imp"><label>试题 PDF</label><input type="file" name="question_pdf" accept="application/pdf" required style="padding-top:10px"><label>答案解析 PDF（可选）</label><input type="file" name="answer_pdf" accept="application/pdf" style="padding-top:10px">
  <button class="btn pri" style="margin-top:16px">开始导入</button> <span id="st" class="sm mut"></span></form></div>
  <div class="card" style="margin-top:14px;overflow-x:auto"><h2>已导入试卷（${s.papers.length}）</h2><table><tr><th>试卷</th><th>题数</th><th>有答案</th><th>含图</th><th>待核对</th></tr>${s.papers.map(p => `<tr><td>${esc(p.title)}</td><td>${p.qcount}</td><td>${p.answered}</td><td>${p.with_images}</td><td class="${p.flagged ? 'co' : ''}">${p.flagged}</td></tr>`).join('')}</table></div>`;
  $('#imp').onsubmit = async ev => {
    ev.preventDefault(); const st = $('#st');
    try { const j = await api('/api/admin/import', {method: 'POST', body: new FormData(ev.target)}); st.textContent = '导入中…';
      const poll = setInterval(async () => { const r = await api('/api/admin/import/' + j.job); st.textContent = {running: '处理中…', ocr: 'OCR 识别中（扫描版较慢）…', parsing: '解析题目…'}[r.status] || r.status;
        if (r.status === 'done') { clearInterval(poll); toast(`导入完成：${r.result.questions} 题，${r.result.with_answer} 题有答案`); go(); }
        if (r.status === 'error') { clearInterval(poll); st.textContent = '失败：' + r.error; } }, 1500);
    } catch (err) { toast(err.message); }
  };
});

if (!NATIVE && 'serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {});
go();
