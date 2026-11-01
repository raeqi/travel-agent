/* WGS84 map view. Markers are approximate; no route is implied. */
let explorationMap,placeLayer,userLayer,mapSelectedId=null,mapFilter='all',mapLastLocation='',mapCandidates=[];
const mapEsc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function refreshMapSize(){if(explorationMap)explorationMap.invalidateSize()}
function setMapPanel(open){document.querySelector('#map-detail-panel').hidden=!open;document.querySelector('#map-more').setAttribute('aria-expanded',String(open))}
function mapMeters(a,b){const r=Math.PI/180;return 6371000*2*Math.asin(Math.min(1,Math.sqrt(Math.sin((b.lat-a.lat)*r/2)**2+Math.cos(a.lat*r)*Math.cos(b.lat*r)*Math.sin((b.lon-a.lon)*r/2)**2)))}
function drawSelectedPlace(s){
 const p=mapCandidates.find(p=>p.id===mapSelectedId)||mapCandidates[0];mapSelectedId=p?.id||null;
 const el=document.querySelector('#map-card');
 if(!p){el.innerHTML='<div class="map-empty"><strong>这片地图，还在等一个好去处</strong><p>可以换个类别，或更新位置继续探索。</p><button data-tab="profile">查看位置与设置 ↗</button></div>';return}
 const m=s.location?Math.ceil(mapMeters(s.location,p)/65):null;
 const active=s.messages.some(x=>x.place_id===p.id&&x.status==='new');
 el.innerHTML=`<article class="map-place"><div class="map-place-heading"><div><span class="badge">${active?'主动为你发现':'附近候选'} · ${mapEsc(p.category)}</span><h2>${mapEsc(p.name)}</h2></div><span class="place-glyph landmark-preview">${landmarkArt(p.category)}</span></div><p>${mapEsc(p.experience_preview?.summary||p.note)}</p><button class="experience-entry" data-map-details="${p.id}">${p.public_sample_count?'公开体验 · '+p.public_sample_count+' 篇历史样本 ↗':'查看地点信息与体验来源 ↗'}</button><div class="map-meta"><span>${m!==null?'单程粗估 '+m+' 分钟':'距离待定位'}</span><span>营业待确认 · 点位近似</span><button data-map-details="${p.id}">依据 ↗</button></div><div class="crowd-preview"><span class="crowd-dots">● ● ●</span> ${demoCrowd(p).label} <small>热度演示 · 非实时客流</small></div><div class="map-card-actions"><button data-go="${p.id}" data-map-start="${p.id}">就去这里 ↗</button><button data-feedback="later" data-id="${p.id}">下次再去</button></div></article>`;
}
function drawMapMarkers(s){
 if(!explorationMap)return;
 placeLayer.clearLayers();userLayer.clearLayers();
 if(s.location){const loc=s.location;L.circle([loc.lat,loc.lon],{radius:loc.accuracy,color:'#348cff',weight:1,fillOpacity:.1}).addTo(userLayer);L.marker([loc.lat,loc.lon],{icon:L.divIcon({className:'you-marker',html:'<span class="you-avatar">☺</span>',iconSize:[22,22],iconAnchor:[11,11]}),title:loc.simulated?'模拟位置：新天地附近':'最近位置'}).addTo(userLayer).bindTooltip(loc.simulated?'你在这里 · 模拟位置':'最近位置',{permanent:true,direction:'bottom',offset:[0,13],className:'you-label'})}
 mapCandidates.forEach(p=>{const selected=p.id===mapSelectedId;L.marker([p.lat,p.lon],{icon:L.divIcon({className:'place-map-marker world-landmark'+(selected?' selected':''),html:`<button aria-label="查看${mapEsc(p.name)}"><span class="landmark-art">${landmarkArt(p.category)}</span><span class="landmark-caption">${mapEsc(p.name)}<small>${demoCrowd(p).label} · 演示</small></span></button>`,iconSize:[112,105],iconAnchor:[56,77]}),keyboard:false,title:p.name,zIndexOffset:selected?200:0}).addTo(placeLayer).on('click',()=>{mapSelectedId=p.id;drawSelectedPlace(s);drawMapMarkers(s)})});
 if(typeof updateMiniWorld==='function')updateMiniWorld(explorationMap,mapCandidates);

}
function renderExplorationMap(s){
 const simulated=!!s.location?.simulated;
 document.querySelector('#map-location-label').textContent=s.location?(simulated?'上海 · 新天地附近 / 模拟位置':'最近位置 · '+new Date(s.location.observed*1000).toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'})):'尚无位置 · 请先设置起点';
 mapCandidates=s.places.filter(p=>!p.visited&&p.expires>Date.now()/1000&&!s.evidence.some(e=>e.place_id===p.id&&e.kind==='dislike')&&(p.wanted||p.origin==='nearby')&&(mapFilter==='all'||p.category.includes(mapFilter))&&(!s.location||mapMeters(s.location,p)<=2000));
 mapCandidates.sort((a,b)=>{const ai=s.messages.some(m=>m.place_id===a.id&&m.status==='new')?0:1,bi=s.messages.some(m=>m.place_id===b.id&&m.status==='new')?0:1;return ai-bi||(s.location?mapMeters(s.location,a)-mapMeters(s.location,b):a.id-b.id)});
 drawSelectedPlace(s);
 if(!window.L){const e=document.querySelector('#map-load-status');e.hidden=false;e.textContent='地图组件未能加载，请联网后刷新。附近地点仍可在下方查看。';return}
 if(!explorationMap){explorationMap=L.map('exploration-map',{zoomControl:false,attributionControl:true}).setView([31.217,121.471],15);placeLayer=L.layerGroup().addTo(explorationMap);userLayer=L.layerGroup().addTo(explorationMap);
 const tiles=L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>'});let successfulTiles=0;
 tiles.on('tileload',()=>{successfulTiles++;document.querySelector('#map-load-status').hidden=true});tiles.on('tileerror',()=>{if(!successfulTiles){const e=document.querySelector('#map-load-status');e.hidden=false;e.textContent='地图底图暂时无法加载，标记为近似位置；可联网后重试。'}});tiles.addTo(explorationMap)}
 drawMapMarkers(s);
 const key=JSON.stringify(s.location?[s.location.lat,s.location.lon]:null);
 if(key!==mapLastLocation){mapLastLocation=key;fitExplorationMap(s)}
}
function fitExplorationMap(s){if(!explorationMap)return;refreshMapSize();const points=mapCandidates.map(p=>[p.lat,p.lon]);if(s.location)points.push([s.location.lat,s.location.lon]);if(points.length)explorationMap.fitBounds(points,{paddingTopLeft:[65,160],paddingBottomRight:[65,365],maxZoom:16,animate:false})}
document.addEventListener('DOMContentLoaded',()=>{
 document.querySelector('#map-more').onclick=()=>setMapPanel(document.querySelector('#map-detail-panel').hidden);
 document.querySelector('#close-map-panel').onclick=()=>setMapPanel(false);
 document.querySelector('#map-recenter').onclick=()=>{if(typeof state!=='undefined')fitExplorationMap(state)};
 document.querySelector('#map-zoom-in').onclick=()=>explorationMap?.zoomIn();document.querySelector('#map-zoom-out').onclick=()=>explorationMap?.zoomOut();
 document.addEventListener('click',e=>{const filterButton=e.target.closest('[data-map-filter]');if(filterButton){mapFilter=filterButton.dataset.mapFilter;document.querySelectorAll('[data-map-filter]').forEach(b=>b.classList.toggle('selected',b===filterButton));renderExplorationMap(state)}const start=e.target.closest('[data-map-start]');if(start)setMapPanel(true);const details=e.target.closest('[data-map-details]');if(details){const p=state.places.find(p=>p.id===Number(details.dataset.mapDetails));if(p)openPlaceContext(p)}})
});

async function openPlaceContext(p){
 sheet(p.name+' · 事实与体验','<p>正在获取来源…</p>','关闭',async()=>{});
 const body=document.querySelector('#sheet-fields');
 try{const r=await api('/api/place-context',{place_id:p.id});if(!document.querySelector('#sheet').open||document.querySelector('#sheet-title').textContent!==p.name+' · 事实与体验')return;
 const f=r.facts,items=[...r.public_experiences,...r.user_experiences];
 body.innerHTML=`<div class="source-section"><h3>地点事实 <small>高德地图</small></h3>${f.status==='ok'?`<p>${mapEsc(f.name)} · ${mapEsc(f.address)}</p><div class="fact-chips"><span>评分 ${mapEsc(f.rating??'暂无')}</span><span>人均 ${f.cost?mapEsc(f.cost)+' 元':'暂无'}</span></div><p>营业描述：${mapEsc(f.opening_description||'暂无；出发前请确认')}</p><p>查询于 ${date(f.retrieved_at)} · 平台评分不是个性化判断</p><a href="${safeSourceLink(f.source_url)}" target="_blank" rel="noopener noreferrer">在高德查看 ↗</a>`:`<p>${mapEsc(f.message)}</p>`}</div>
 <div class="source-section"><h3>体验证据 <small>${items.length} 条样本</small></h3>${items.map(item=>`<article class="source-observation"><span>${mapEsc(item.platform)} · ${item.source_type==='user_supplied'?'用户提供，未核实原文':'公开游记，人工核对'}</span><p>${mapEsc(item.summary)}</p><small>${mapEsc(item.author)} · 发布于 ${mapEsc(item.published)}${item.checked_on?' · 核对于 '+mapEsc(item.checked_on):''}</small><p class="source-limit">${mapEsc(item.limitation)}</p><a href="${safeSourceLink(item.url)}" target="_blank" rel="noopener noreferrer">查看原文 ↗</a></article>`).join('')||'<p>还没有可追溯的体验样本，不生成口碑总结。</p>'}<button type="button" class="secondary" id="add-experience">＋ 补充一条有来源的体验</button></div>
 <div class="source-section"><h3>实时人流</h3><p>未接入。评论中的“人多／安静”属于历史体验；地图上的人车和热度都是演示。</p></div>`;
 document.querySelector('#add-experience').onclick=()=>{sheet(p.name+' · 补充体验',`<label>体验摘要<textarea name="summary" maxlength="500" required placeholder="简短转述，不整篇复制评论"></textarea></label><label>原文链接<input type="url" name="url" required placeholder="https://…"></label><label>作者<input name="author" maxlength="120" required></label><label>来源平台<input name="platform" maxlength="80" required></label><label>发布日期<input type="date" name="published" required></label><p>仅记录你提供的来源，不自动抓取页面；显示为“未核实原文”。</p>`,'保存来源',async d=>{await api('/api/experiences',{place_id:p.id,...d});notice('已记录来源与摘要，未将其当成个人偏好或实时客流。')})};
 }catch(e){body.textContent='获取失败：'+e.message}
}
function safeSourceLink(value){try{const u=new URL(value);return u.protocol==='https:'?mapEsc(u.href):'#'}catch{return '#'}}
