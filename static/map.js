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
 el.innerHTML=`<article class="map-place"><div class="map-place-heading"><div><span class="badge">${active?'主动为你发现':'附近候选'} · ${mapEsc(p.category)}</span><h2>${mapEsc(p.name)}</h2></div><span class="place-glyph">${p.category.includes('公园')?'♧':p.category.includes('书')?'▤':'⌂'}</span></div><p>${mapEsc(p.note)}</p><div class="map-meta"><span>${m!==null?'单程粗估 '+m+' 分钟':'距离待定位'}</span><span>营业待确认 · 坐标为近似点位</span><button data-map-details="${p.id}">依据 ↗</button></div><div class="map-card-actions"><button data-go="${p.id}" data-map-start="${p.id}">就去这里 ↗</button><button data-feedback="later" data-id="${p.id}">下次再去</button></div></article>`;
}
function drawMapMarkers(s){
 if(!explorationMap)return;
 placeLayer.clearLayers();userLayer.clearLayers();
 if(s.location){const loc=s.location;L.circle([loc.lat,loc.lon],{radius:loc.accuracy,color:'#348cff',weight:1,fillOpacity:.1}).addTo(userLayer);L.marker([loc.lat,loc.lon],{icon:L.divIcon({className:'you-marker',html:'<span></span>',iconSize:[22,22],iconAnchor:[11,11]}),title:loc.simulated?'模拟位置：新天地附近':'最近位置'}).addTo(userLayer).bindTooltip(loc.simulated?'你在这里 · 模拟位置':'最近位置',{permanent:true,direction:'bottom',offset:[0,13],className:'you-label'})}
 mapCandidates.forEach(p=>{const selected=p.id===mapSelectedId;const symbol=p.category.includes('公园')?'♧':p.category.includes('书')?'▤':'⌂';L.marker([p.lat,p.lon],{icon:L.divIcon({className:'place-map-marker'+(selected?' selected':''),html:`<button aria-label="查看${mapEsc(p.name)}"><span>${symbol}</span>${mapEsc(p.name)}</button>`,iconSize:[122,40],iconAnchor:[61,40]}),keyboard:false,title:p.name,zIndexOffset:selected?200:0}).addTo(placeLayer).on('click',()=>{mapSelectedId=p.id;drawSelectedPlace(s);drawMapMarkers(s)})});
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
 document.addEventListener('click',e=>{const filterButton=e.target.closest('[data-map-filter]');if(filterButton){mapFilter=filterButton.dataset.mapFilter;document.querySelectorAll('[data-map-filter]').forEach(b=>b.classList.toggle('selected',b===filterButton));renderExplorationMap(state)}const start=e.target.closest('[data-map-start]');if(start)setMapPanel(true);const details=e.target.closest('[data-map-details]');if(details){const p=state.places.find(p=>p.id===Number(details.dataset.mapDetails));if(p)sheet(p.name+' · 推荐依据',`<p>${p.wanted?'你明确加入了想去清单。':'依据附近位置提出，尚未推断你的个人偏好。'}</p><p>${mapEsc(p.note)}</p><p>信息来源：${mapEsc(p.source)}</p><p>地图点位为近似坐标，距离是直线粗估，不是导航路线。营业状态尚未实时核实。</p>`,'知道了',async()=>{})}})
});
