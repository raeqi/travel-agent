const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const date = t => new Date(t * 1000).toLocaleString('zh-CN', {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});
let state, filter = 'wanted', toastTimer, sheetAction, showRecommendations = false;
let tripId = Number(sessionStorage.getItem('wander-trip')) || null;
async function api(path, data) {
  const r = await fetch(path, data ? {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)} : {});
  const result = await r.json();
  if (!r.ok) throw Error(result.error || '请求失败');
  return result;
}
function notice(s) { clearTimeout(toastTimer); $('#notice').textContent = s; $('#notice').hidden = false; toastTimer = setTimeout(() => $('#notice').hidden = true, 6500); }
async function run(fn) { try { await fn(); } catch (e) { notice(e.message); } }
function tab(name) {
  if (!['explore','saved','journal','profile'].includes(name)) name = 'explore';
  document.querySelectorAll('.screen').forEach(s => s.hidden = s.id !== name);
  document.querySelectorAll('.tabbar button').forEach(b => { b.classList.toggle('active', b.dataset.tab === name); b.setAttribute('aria-current', b.dataset.tab === name ? 'page' : 'false'); });
  $('.app').classList.toggle('map-mode', name === 'explore'); $('#composer').hidden = name !== 'explore';
  if (name === 'explore') requestAnimationFrame(refreshMapSize);
  history.replaceState(null, '', '#' + name); window.scrollTo(0, 0);
}
function sheet(title, fields, submit, fn) { $('#sheet-title').textContent = title; $('#sheet-fields').innerHTML = fields; $('#sheet-submit').textContent = submit; sheetAction = fn; if (!$('#sheet').open) $('#sheet').showModal(); }
$('#close-sheet').onclick = () => $('#sheet').close();
$('#sheet-form').onsubmit = e => { e.preventDefault(); run(async () => { const b = $('#sheet-submit'); b.disabled = true; try { await sheetAction(Object.fromEntries(new FormData(e.target))); $('#sheet').close(); await render(); } finally { b.disabled = false; } }); };
function isSnoozed(p) { return p.snoozed_until != null && p.snoozed_until > state.exploration.evaluated_at; }
function feedbackButtons(p) {
  if (p.interest_state === 'disliked') return `<button data-feedback="undo-dislike" data-id="${p.id}">撤销不感兴趣</button>`;
  return `<div class="actions"><button data-feedback="visited" data-id="${p.id}">✓ 去过了</button>${isSnoozed(p) ? `<button data-feedback="undo-later" data-id="${p.id}">提前结束暂缓</button>` : `<button data-feedback="later" data-id="${p.id}">稍后</button>`}<button data-feedback="dislike" data-id="${p.id}">不感兴趣</button><button data-feedback="correction" data-id="${p.id}">写点感受</button></div>`;
}
const empty = (title, text, button = '') => `<div class="empty"><span class="empty-icon">⌁</span><strong>${title}</strong>${text}${button}</div>`;
function setSavedFilter(value) {
  filter = value;
  document.querySelectorAll('[data-filter]').forEach(button => button.classList.toggle('selected', button.dataset.filter === value));
}
const labels = {'explicit-interest':'心动收藏',visited:'一段新足迹',dislike:'明确不感兴趣','undo-dislike':'撤销不感兴趣',later:'单次暂缓','undo-later':'结束暂缓',correction:'你的真实感受',refresh:'地点信息更新','location-confirmed':'已确认位置'};
function mapLink(p) { return `https://www.openstreetmap.org/?mlat=${p.lat}&mlon=${p.lon}#map=17/${p.lat}/${p.lon}`; }
function renderPlaces() {
  const items = state.places.filter(p => {
    if (filter === 'paused') return isSnoozed(p) || p.interest_state === 'disliked';
    if (filter === 'all') return p.origin !== 'nearby' || p.wanted || p.visited || p.interest_state === 'disliked' || isSnoozed(p);
    if (filter === 'visited') return !!p.visited;
    return p.wanted && !p.visited && p.interest_state !== 'disliked';
  });
  $('#places').innerHTML = items.map(p => `<article class="card"><div class="card-top"><span class="place-symbol">${p.category.includes('咖啡') ? '☕' : p.category.includes('书') ? '▤' : '⌖'}</span><span class="badge">${esc(p.category)} · ${p.interest_state === 'disliked' ? '不感兴趣' : p.visited ? '已去过' : p.wanted ? '心愿清单' : '附近发现'}</span></div><h3>${esc(p.name)}</h3><p>${esc(p.note) || '把这个地方留给下一次出发。'}</p>${isSnoozed(p) ? `<p class="snooze-status">暂缓到 ${date(p.snoozed_until)}；到期前不推荐，不改变兴趣。</p>` : ''}${p.lat == null || p.lon == null ? `<p>尚未定位 · 只在清单保存，不进入地图或推荐。</p><button class="secondary" data-locate-place="${p.id}">补充位置</button>` : `<a class="map-link" target="_blank" rel="noopener noreferrer" href="${mapLink(p)}">看看它在哪里 ↗</a>`}${feedbackButtons(p)}<details><summary>${p.expires < state.exploration.evaluated_at ? '信息需要更新' : '地点信息与来源'}</summary><p>${esc(p.source)}<br>记录于 ${date(p.verified)} · 出发前请确认营业</p><button class="secondary" data-refresh="${p.id}">更新信息来源</button></details></article>`).join('') || empty(filter === 'paused' ? '没有暂缓或不感兴趣的地点' : filter === 'visited' ? '你的下一段足迹，还在路上' : '把心动的地方，先收下来', '可以先只记下名字和原因，稍后补位置。', '<button data-add>＋ 收藏一个地方</button>');
}
async function render() {
  state = await api('/api/state');
  $('#proactive').checked = !!state.settings.proactive;
  $('#data-connections').innerHTML = '<strong>地点与体验数据</strong><p>高德：' + (state.providers?.amap.configured ? '已配置密钥，查询时获取已定位地点信息' : '尚未配置密钥；没有在线地点搜索结果') + '</p><p>大众点评／Google 评论：未接入</p><p>实时客流：未接入 · 地图动画为演示</p>';
  $('#location-title').textContent = state.location?.label || (state.location ? '在你附近，发现新风景' : '从你所在的地方开始');
  $('#location').textContent = state.location ? `${state.location.lat.toFixed(4)}, ${state.location.lon.toFixed(4)} · ${date(state.location.observed)} 更新${state.location.simulated ? ' · 模拟位置，非 GPS' : ''}` : '还不知道你在哪里。定位后，一起看看附近。';
  renderAgent(); renderPlaces();
  $('#evidence').innerHTML = state.evidence.map(e => { const p = state.places.find(p => p.id === e.place_id); return `<article class="log"><small>${date(e.created)} · ${esc(labels[e.kind] || e.kind)}</small><strong>${esc(p?.name || '地点记录')}</strong>${esc(e.text)}${e.snoozed_until ? '<p>本次暂缓到：' + date(e.snoozed_until) + '</p>' : ''}${e.kind === 'later' && !e.snoozed_until ? '<p>此条历史记录未包含到期时间；未自动猜测暂缓期限。</p>' : ''}</article>`; }).join('') || empty('走过的路，慢慢记下来', '当你收藏、到访或分享感受，它们会留在这里。');
  $('#runs').innerHTML = state.runs.map(r => `<div class="log"><small>${date(r.created)}</small>${esc(r.decision)}</div>`).join('') || '<p>漫游还在等待你的第一次出发。</p>';
}
function addPlace() {
  sheet('收下一个想去的地方', `<label>地点名称<input name="name" required maxlength="200" placeholder="例如，一家想去很久的书店"></label><label>它是什么地方<input name="category" required maxlength="100" placeholder="书店、咖啡馆、公园…"></label><label>为什么让你心动<textarea name="note" maxlength="1000"></textarea></label><label>信息来源<input name="source" required maxlength="500" placeholder="店铺链接、朋友推荐或你亲自确认的信息"></label><details><summary>补充位置（可选）</summary><p>可先不填。未定位地点不会进入地图或推荐。目前没有在线搜索；补充时请确认 WGS84 坐标，不混用高德或百度坐标。</p><div class="coordinate-row"><label>纬度<input name="lat" type="number" step="any" min="-90" max="90"></label><label>经度<input name="lon" type="number" step="any" min="-180" max="180"></label></div></details>`, '加入我的想去', async d => { await api('/api/places', d); setSavedFilter('wanted'); tab('saved'); notice('收好了。未填位置的地点会留在清单，确认位置后再推荐。'); });
}
$('#add-place').onclick = addPlace;
async function locate() {
  if (!navigator.geolocation) throw Error('当前浏览器不支持定位，请在「我的」中手动设置。');
  notice('正在寻找你的位置…');
  navigator.geolocation.getCurrentPosition(p => run(async () => { const r = await api('/api/location', {lat:p.coords.latitude,lon:p.coords.longitude,accuracy:p.coords.accuracy}); await render(); notice(r.recommendations.length ? '发现了一个适合你的去处。' : '位置已更新。' + r.decision); }), () => notice('暂时无法定位。你可以在「我的」中手动设置位置。'), {enableHighAccuracy:true,maximumAge:0,timeout:15000});
}
$('#locate').onclick = () => run(locate); $('#update-location').onclick = () => run(locate);
$('#manual-location').onclick = () => sheet('从哪里开始漫游？', '<p>请输入当前位置的 WGS84 坐标。</p><label>纬度<input name="lat" type="number" step="any" min="-90" max="90" required></label><label>经度<input name="lon" type="number" step="any" min="-180" max="180" required></label>', '从这里出发', async d => { await api('/api/location', {...d,accuracy:50}); notice('起点已更新。'); });
$('#proactive').onchange = () => run(async () => { const enabled = $('#proactive').checked; try { await api('/api/settings', {proactive:enabled,minutes:state.settings.minutes}); notice(enabled ? '漫游会把适合的机会留在探索页。' : '已暂停主动建议。'); } finally { await render(); } });
$('#check').onclick = () => run(async () => { const r = await api('/api/check', {}); await render(); notice(r.decision); });
async function findSuggestions() { const r = await api('/api/evaluate', {}); showRecommendations = true; await render(); return r; }
$('#ask').onclick = () => run(async () => { const b = $('#ask'); b.disabled = true; try { const r = await findSuggestions(); if (!r.recommendations.length) addConversation('agent', r.decision); } finally { b.disabled = false; } });
function feedbackSheet(kind, id) {
  const p = state.places.find(p => p.id === id); if (!p) return;
  const defaults = {visited:'我去过这里了',dislike:'我不想再收到这个地点的推荐',later:'这次不方便，稍后再考虑',correction:'','undo-dislike':'撤销之前的不感兴趣；保留历史原话','undo-later':'提前结束这次暂缓'};
  const titles = {visited:'这一站，感觉怎么样？',dislike:'不再推荐这个地点',later:'暂缓到什么时候？',correction:'记下真实的感受','undo-dislike':'恢复这个地点的推荐资格？','undo-later':'提前结束暂缓？'};
  const snoozeBase = state.exploration.evaluated_at;
  let fields = '';
  if (kind === 'later') fields += '<label>暂缓时长<select name="snooze_duration" required><option value="3600">1 小时</option><option value="86400" selected>24 小时</option><option value="604800">7 天</option></select></label><p id="snooze-preview"></p><p>仅暂缓本地点；不记录为不喜欢。到期后重新按位置、时间和冷却判断，不保证立即提醒。</p>';
  if (kind === 'dislike') fields += '<p>只针对这个地点，直到你撤销；不会推断你不喜欢整个类别。可在「记忆 → 暂缓与不感兴趣」恢复。</p>';
  fields += `<label>想和漫游说的话<textarea name="text" required maxlength="1000">${esc(defaults[kind])}</textarea></label>`;
  sheet(titles[kind], fields, kind === 'later' ? '确认暂缓' : '记下来', async d => {
    const duration = Number(d.snooze_duration);
    await api('/api/feedback', {place_id:id,kind,text:d.text,...(kind === 'later' ? {snoozed_until:snoozeBase + duration} : {})});
    if (tripId === id && ['later','dislike','visited'].includes(kind)) { tripId = null; sessionStorage.removeItem('wander-trip'); }
    await render();
    notice(kind === 'later' ? `已暂缓到 ${date(state.places.find(p => p.id === id).snoozed_until)}` : '已更新。历史原话会保留。');
  });
  if (kind === 'later') { const update = () => $('#snooze-preview').textContent = '预计到期：' + date(snoozeBase + Number($('#sheet-fields select').value)); $('#sheet-fields select').onchange = update; update(); }
}
document.addEventListener('click', e => run(async () => {
  const b = e.target.closest('button'); if (!b) return;
  if (b.hasAttribute('data-demo')) { sheet('启用新天地模拟探索？', '<p>这会把本地起点设为上海新天地附近的模拟位置，并开启应用内主动建议。非实时 GPS，有效期 30 分钟；只加载带来源的演示候选，不写成你的兴趣。</p>', '启用模拟探索', async () => { const r = await api('/api/demo-xintiandi', {}); showRecommendations = false; notice('已启用模拟位置。' + r.decision); tab('explore'); }); return; }
  if (b.dataset.go) {
    const id = Number(b.dataset.go); if (!state.exploration.recommendations.some(x => x.place.id === id)) { await render(); notice('条件已变化，请重新选择当前候选。'); return; }
    await api('/api/start-exploration', {place_id:id}); await render();
    tripId = id; sessionStorage.setItem('wander-trip', tripId); renderAgent(); notice('已放到这次探索中。出发前请确认实际路线和营业。'); return;
  }
  if (b.hasAttribute('data-finish')) { feedbackSheet('visited', tripId); return; }
  if (b.hasAttribute('data-cancel-trip')) { tripId = null; sessionStorage.removeItem('wander-trip'); renderAgent(); return; }
  if (b.dataset.compose) { $('#chat-text').value = b.dataset.compose; $('#chat-text').focus(); return; }
  if (b.dataset.tab) { tab(b.dataset.tab); return; }
  if (b.hasAttribute('data-add')) { addPlace(); return; }
  if (b.dataset.filter) { setSavedFilter(b.dataset.filter); renderPlaces(); return; }
  if (b.dataset.locatePlace) { sheet('确认地点位置', '<p>请确认 WGS84 坐标。未确认前只在清单保存，不会自动匹配同名地点。</p><label>纬度<input name="lat" type="number" step="any" min="-90" max="90" required></label><label>经度<input name="lon" type="number" step="any" min="-180" max="180" required></label><label>位置来源<input name="source" required maxlength="500"></label>', '确认位置', async d => { await api('/api/place-location', {place_id:Number(b.dataset.locatePlace),...d}); notice('已确认位置；会重新检查时间与地点信息。'); }); return; }
  if (b.dataset.refresh) { sheet('更新地点信息', '<label>新的信息来源<input name="source" required maxlength="500"></label>', '更新记忆', async d => { await api('/api/refresh', {place_id:Number(b.dataset.refresh),...d}); notice('地点信息已更新。'); }); return; }
  if (b.dataset.feedback) { feedbackSheet(b.dataset.feedback, Number(b.dataset.id)); return; }
  if (b.hasAttribute('data-agent-location')) await locate();
}));
$('#delete').onclick = () => sheet('清除漫游记忆？', '<p>这会删除所有地点、位置与感受，且无法恢复。主动建议也会关闭。</p>', '确认清除全部数据', async () => { await api('/api/delete-data', {}); showRecommendations = false; tripId = null; sessionStorage.removeItem('wander-trip'); $('#conversation').replaceChildren(); notice('已清除所有个人数据。'); });
function addConversation(role, text) { setMapPanel(true); const item = document.createElement('div'); item.className = 'utterance ' + role; const label = document.createElement('small'); label.textContent = role === 'user' ? '你' : '漫游'; const content = document.createElement('p'); content.textContent = text; item.append(label, content); $('#conversation').append(item); item.scrollIntoView({behavior:'smooth',block:'nearest'}); }
function budgetText(r) { return `往返粗估 ${r.round_trip_minutes_estimate} 分钟 + 停留 ${r.stop_minutes_assumption} 分钟 = 合计 ${r.total_minutes_estimate} 分钟`; }
function proposal(r) {
  const p = state.places.find(p => p.id === r.place.id);
  return `<article class="proposal"><span class="badge">✧ 一个值得考虑的去处</span><h2>${esc(p.name)}</h2><p>${esc(p.note)}</p><div class="proposal-evidence"><span>${p.wanted ? '♡ 你明确想去' : '⌖ 附近发现 · 尚未了解你的偏好'}</span><span>单程粗估 ${r.walking_minutes_estimate} 分钟</span></div><p class="time-budget">${budgetText(r)}</p><details><summary>为什么提出这个建议？</summary><p>${esc(r.text)}</p><p>来源：${esc(p.source)} · ${date(p.verified)} 记录。</p></details><div class="proposal-actions"><button data-go="${p.id}">就去这里 ↗</button><button data-feedback="later" data-id="${p.id}">稍后</button><button data-feedback="dislike" data-id="${p.id}">不感兴趣</button></div></article>`;
}
function renderAgent() {
  renderExplorationMap(state);
  const current = state.exploration.recommendations;
  const eligible = new Set(current.map(r => r.place.id));
  $('.app').classList.toggle('simulated', !!state.location?.simulated); $('#simulation').hidden = !state.location?.simulated;
  $('#adjust-time').textContent = `约 ${state.settings.minutes} 分钟 ⌄`;
  $('#status').textContent = state.settings.proactive ? '已开启应用内主动留意' : '主动留意未开启';
  $('#agent-context').innerHTML = `<article class="agent-note"><span class="note-dot">✧</span><div><h2>${current.length ? '下一站，值得期待' : '现在先不出发'}</h2><p>${current.length ? '已按本次时间、起点和反馈筛选。到访不等于喜欢。' : esc(state.exploration.decision)}</p>${!state.location ? '<button data-agent-location>更新位置 ↗</button><button data-demo>试用新天地模拟探索</button>' : ''}</div></article>`;
  $('#answers').innerHTML = showRecommendations ? current.slice(0,3).map(proposal).join('') : '';
  // Inbox entries are historical delivery records. Re-use current server results
  // before showing any action, rather than activating an old message's payload.
  $('#messages').innerHTML = state.messages.filter(m => m.status === 'new' && eligible.has(m.place_id)).slice(0,3).filter(m => !showRecommendations || !current.slice(0,3).some(r => r.place.id === m.place_id)).map(m => `<div class="past-opportunity"><small>主动为你留意 · ${date(m.created)} · 已按当前条件重验</small>${proposal(current.find(r => r.place.id === m.place_id))}</div>`).join('');
  $('#agent-context').hidden = !!($('#messages').textContent.trim() || $('#answers').textContent.trim());
  if (tripId && !eligible.has(tripId)) { tripId = null; sessionStorage.removeItem('wander-trip'); }
  const trip = state.places.find(p => p.id === tripId);
  $('#active-trip').innerHTML = trip ? `<article class="trip-card"><span class="badge">↗ 这次的探索</span><h2>${esc(trip.name)}</h2><p>${budgetText(current.find(r => r.place.id === tripId))}。尚未确认到达；请确认实际路线和营业。</p><a href="${mapLink(trip)}" target="_blank" rel="noopener noreferrer">打开地图 ↗</a><button data-finish>去过了，聊聊感受</button><button data-cancel-trip>取消这次探索</button></article>` : '';
  $('#memory-preview').innerHTML = state.evidence.slice(0,2).map(e => `<div class="memory-fragment"><span>♡</span><div><small>${esc(labels[e.kind] || e.kind)} · ${esc(state.places.find(p => p.id === e.place_id)?.name || '你的记录')}</small><p>${esc(e.text)}</p></div></div>`).join('') || '<p class="memory-empty">明确兴趣、暂缓和不感兴趣分开保存。</p>';
}
$('#adjust-time').onclick = () => sheet('这次有多少时间？', `<label>可探索的分钟数<input name="minutes" type="number" min="20" max="480" value="${state.settings.minutes}" required></label><p>按直线距离每分钟65米、往返步行及停留20分钟粗估；不是导航，不计等候。</p>`, '调整这次提议', async d => { await api('/api/settings', {proactive:!!state.settings.proactive,minutes:Number(d.minutes)}); const r = await findSuggestions(); addConversation('agent', `已按 ${d.minutes} 分钟更新所有候选。${r.decision}`); });
$('#chat-form').onsubmit = e => { e.preventDefault(); run(async () => {
  const b = e.target.querySelector('button'), text = $('#chat-text').value.trim(); if (!text) return;
  b.disabled = true; addConversation('user', text); $('#chat-text').value = '';
  try {
    const match = text.match(/(?:只有|有|约)?\s*(\d+)\s*分钟/), half = text.includes('半小时');
    if (match || half) { const minutes = half ? 30 : Number(match[1]); await api('/api/settings', {proactive:!!state.settings.proactive,minutes}); const r = await findSuggestions(); addConversation('agent', `按 ${minutes} 分钟重新考虑了这次探索。${r.recommendations.length ? '地图与下方候选已同步。' : r.decision}`); }
    else if (/附近|去哪|去处/.test(text)) { const r = await findSuggestions(); addConversation('agent', r.recommendations.length ? '按当前起点、可用时间和反馈找到了这些候选。' : r.decision); }
    else { const r = await api('/api/chat', {text}); if (r.recommendations) showRecommendations = true; await render(); addConversation('agent', r.decision); }
  } catch (error) { addConversation('agent', error.message + '。无需模型也可在地点卡片选择稍后或不感兴趣。'); }
  finally { b.disabled = false; }
}); };
window.addEventListener('hashchange', () => tab(location.hash.slice(1)));
tab(location.hash.slice(1) || 'explore'); run(async () => { await api('/api/pulse', {}); await render(); }); setInterval(() => run(render), 10000);
