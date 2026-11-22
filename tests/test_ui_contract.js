/* Dependency-free render contract. HTTP/Python tests decide eligibility; these
   assertions ensure both surfaces actually consume that result, including after
   a budget change or a historical inbox entry. Browser layout is checked apart. */
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
const nodes = new Map();
let serverState, postedPlace;
const filterButtons = ['wanted','visited','paused','all'].map(value => ({dataset:{filter:value},selected:false,classList:{toggle(name,selected){filterButtons.find(b=>b.dataset.filter===value).selected=selected}}}));
function node(selector) {
  if (!nodes.has(selector)) {
    const el = {textContent:'',hidden:false,checked:false,value:'',classList:{toggle(){}},setAttribute(){},append(){},replaceChildren(){},showModal(){this.open=true}};
    Object.defineProperty(el, 'innerHTML', {get(){return this.html||''},set(value){this.html=value;this.textContent=value.replace(/<[^>]*>/g,'')}});
    nodes.set(selector,el);
  }
  return nodes.get(selector);
}
const context = vm.createContext({
  document:{querySelector:node,querySelectorAll(selector){return selector==='[data-filter]'?filterButtons:[]},addEventListener(){}},
  window:{addEventListener(){},scrollTo(){}}, history:{replaceState(){}},
  fetch:async (url,options)=>{if(url==='/api/places')postedPlace=JSON.parse(options.body);return {ok:true,json:async()=>url==='/api/state'?serverState:{ok:true}}}, sessionStorage:{getItem(){return null},removeItem(){},setItem(){}},
  setTimeout(){},clearTimeout(){},setInterval(){},requestAnimationFrame(){},
  landmarkArt(){return ''},demoCrowd(){return {label:'演示'}},console,
});
const map = fs.readFileSync(path.join(root,'static/map.js'),'utf8');
const app = fs.readFileSync(path.join(root,'static/app.js'),'utf8').replace(/^tab\(location\.hash[\s\S]*$/m,'');
vm.runInContext(map+'\n'+app+`\nthis.harness={update(s,active=null){state=s;tripId=active;showRecommendations=true;renderAgent()},html(selector){return document.querySelector(selector).innerHTML},async addWishFromPaused(){setSavedFilter('paused');addPlace();await sheetAction({name:'新增未定位愿望',category:'书店',source:'合成来源',lat:'',lon:''});await render();}};`,context);
const p={id:1,name:'合成店',category:'咖啡',origin:'user',wanted:1,lat:31.223,lon:121.4752,note:'说明',source:'合成来源',interest_state:'active'};
const r={place:p,walking_minutes_estimate:6,round_trip_minutes_estimate:12,stop_minutes_assumption:20,total_minutes_estimate:32,text:'合计粗估32分钟，非导航'};
function state(recommendations,minutes=35) {return {places:[p],messages:[{place_id:1,status:'new',created:10}],evidence:[],location:{lat:31.2197,lon:121.4752,observed:10,accuracy:10,simulated:1,label:'模拟起点'},settings:{minutes,proactive:true},exploration:{recommendations,evaluated_at:10,decision:'没有时间内地点'}}}
context.harness.update(state([r]));
assert.match(context.harness.html('#map-card'),/data-go="1"/);
assert.match(context.harness.html('#answers'),/data-go="1"/);
assert.match(context.harness.html('#map-card'),/往返粗估 12 分钟 \+ 停留 20 分钟 = 合计 32 分钟/);
assert.match(context.harness.html('#answers'),/往返粗估 12 分钟 \+ 停留 20 分钟 = 合计 32 分钟/);
context.harness.update(state([],30),1);
for (const selector of ['#map-card','#answers','#messages','#active-trip']) {
  assert.doesNotMatch(context.harness.html(selector),/data-go|打开地图/,selector+' must clear obsolete actions');
}
assert.match(context.harness.html('#map-card'),/当前没有可出发的地点/);
// A rejected/snoozed item may still be retained in memory, never in current UI.
context.harness.update({...state([],60),places:[{...p,interest_state:'disliked',snoozed_until:100}]});
assert.doesNotMatch(context.harness.html('#map-card'),/data-go/);
const noLocation=state([],60);noLocation.location=null;context.harness.update(noLocation);
assert.match(context.harness.html('#map-card'),/data-demo/);
// Saving from the paused list must switch both state and selected control back
// to wanted, otherwise the newly-created wish is invisible after success.
serverState={...state([],60),runs:[],places:[{...p,id:2,name:'新增未定位愿望',category:'书店',lat:null,lon:null,expires:1000}],messages:[]};
context.harness.addWishFromPaused().then(()=>{
  assert.equal(postedPlace.name,'新增未定位愿望');
  assert.deepEqual(filterButtons.filter(b=>b.selected).map(b=>b.dataset.filter),['wanted']);
  assert.match(context.harness.html('#places'),/新增未定位愿望/);
  assert.match(context.harness.html('#places'),/尚未定位/);
  assert.doesNotMatch(context.harness.html('#places'),/class="map-link"/);
  console.log('UI render contract: budget, historical inbox, active trip, feedback exclusion, demo and saved-wish filter reset passed');
}).catch(error=>{console.error(error);process.exitCode=1});
