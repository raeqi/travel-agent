/* Playful animation layer. All pedestrians, vehicles and density are synthetic.
   Real geographic markers remain separate. Nothing here is a traffic measurement. */
function demoCrowd(p){return p.category.includes('公园')?{count:13,label:'三三两两'}:p.category.includes('书')?{count:5,label:'慢慢逛逛'}:{count:20,label:'热热闹闹'}}
function landmarkArt(category){
 const park=category.includes('公园'),book=category.includes('书');
 const art=park?`<ellipse cx="60" cy="75" rx="47" ry="17" fill="#92d9c9"/><path d="M18 70 60 47 105 70 60 94Z" fill="#b9e9d4"/><path d="M18 70v8l42 24V94Zm42 24 45-24v8l-45 24" fill="#73c9b3"/><path d="m30 73 30-17 30 17-30 15z" fill="#dff6e9"/><path d="M55 87 74 73 66 66" fill="none" stroke="#fff" stroke-width="7"/><g stroke="#5489a0" stroke-width="3"><path d="M30 67V44m58 26V42m-40 9V29"/></g><g fill="#5db8b2" stroke="#fff" stroke-width="2"><path d="m17 48 13-27 13 27-13 10Z"/><path d="m75 47 13-30 13 30-13 11Z"/><path d="m36 34 12-25 12 25-12 10Z"/></g><path d="m47 69 14-8 12 7-14 8z" fill="#ffad8c"/><path d="M48 70v6m23-7v6" stroke="#ba7c70" stroke-width="2"/>`:
 book?`<ellipse cx="60" cy="87" rx="48" ry="12" fill="#ccd9f2"/><path d="m20 44 40-21 40 23-40 22z" fill="#7189d5"/><path d="m20 44 40 23v28L20 73Z" fill="#fcf8ff"/><path d="m60 67 40-21v28L60 95Z" fill="#bccaf2"/><path d="m14 43 46-29 46 28-46 26Z" fill="#ff9a97"/><path d="m14 43 46 25v7L14 50Z" fill="#de777e"/><path d="m60 68 46-26v7L60 75Z" fill="#c96978"/><path d="m30 58 10 6v12l-10-6zm17 10 8 5v16l-8-5Z" fill="#83b7e4"/><path d="m69 72 9-5v13l-9 5zm15-8 9-5v13l-9 5Z" fill="#edf6ff"/><path d="m46 24 13-5 15 9-14 5z" fill="#fff"/><path d="m59 20v11" stroke="#ef989c" stroke-width="2"/>`:
 `<ellipse cx="60" cy="88" rx="49" ry="11" fill="#cbd9ed"/><path d="m15 70 46-24 46 25-46 26Z" fill="#cedcf3"/><path d="m24 41 23-13 24 15-24 14Z" fill="#e58d7b"/><path d="m24 41 23 16v30L24 71Z" fill="#fff5e9"/><path d="m47 57 24-14v30L47 87Z" fill="#ead5c7"/><path d="m65 44 19-12 21 13-21 13Z" fill="#7f9bd1"/><path d="m65 44 19 14v28L65 73Z" fill="#fff"/><path d="m84 58 21-13v28L84 86Z" fill="#b6cbea"/><g fill="#81b9dd"><path d="m30 50 7 4v9l-7-4zm11 7 4 3v9l-4-3zm30-4 6 4v8l-6-4zm17 11 7-4v9l-7 4Z"/></g><path d="m48 46 8-5v12l-8 5Z" fill="#84b7db"/>`;
 return `<svg viewBox="0 0 120 110" aria-hidden="true"><defs><filter id="shadow"><feDropShadow dx="0" dy="3" stdDeviation="2" flood-color="#426eaa" flood-opacity=".12"/></filter></defs><g stroke-linejoin="round" filter="url(#shadow)">${art}</g></svg>`;
}
let miniWorld=null;
function updateMiniWorld(map,places){
 if(!miniWorld){const canvas=document.createElement('canvas');canvas.className='mini-world-canvas';canvas.setAttribute('aria-hidden','true');map.getContainer().append(canvas);miniWorld={map,canvas,places:[],paused:matchMedia('(prefers-reduced-motion: reduce)').matches,last:0,time:0};
 const button=document.querySelector('#toggle-world-animation');button.textContent=miniWorld.paused?'播放动画':'暂停动画';button.setAttribute('aria-pressed',String(!miniWorld.paused));button.onclick=()=>{miniWorld.paused=!miniWorld.paused;button.textContent=miniWorld.paused?'播放动画':'暂停动画';button.setAttribute('aria-pressed',String(!miniWorld.paused))};
 requestAnimationFrame(drawMiniWorld)}miniWorld.places=places;
}
function drawMiniWorld(stamp){
 const w=miniWorld;if(!w)return;
 requestAnimationFrame(drawMiniWorld);
 if(document.hidden||document.querySelector('#explore').hidden){w.last=stamp;return}
 if(stamp-w.last<33)return;
 const delta=Math.min(100,stamp-w.last);w.last=stamp;if(!w.paused)w.time+=delta/1000;
 const {canvas,map}=w,size=map.getSize(),scale=Math.min(devicePixelRatio||1,2);if(canvas.width!==size.x*scale||canvas.height!==size.y*scale){canvas.width=size.x*scale;canvas.height=size.y*scale;canvas.style.width=size.x+'px';canvas.style.height=size.y+'px'}
 const c=canvas.getContext('2d');c.setTransform(scale,0,0,scale,0,0);c.clearRect(0,0,size.x,size.y);
 const t=w.time;
 w.places.forEach((p,index)=>{
 const pt=map.latLngToContainerPoint([p.lat,p.lon]),density=demoCrowd(p);if(pt.x<-130||pt.y<-130||pt.x>size.x+130||pt.y>size.y+130)return;
 // Elliptic gathering zones are illustrative, not observed footfall.
 const radius=42+Math.min(density.count,20);const gradient=c.createRadialGradient(pt.x,pt.y,8,pt.x,pt.y,radius);gradient.addColorStop(0,index%2?'#ffab942b':'#6baaff30');gradient.addColorStop(1,'#ffffff00');c.fillStyle=gradient;c.beginPath();c.ellipse(pt.x,pt.y+4,radius,radius*.68,0,0,Math.PI*2);c.fill();
 for(let i=0;i<density.count;i++){const phase=i*2.399+index,angle=phase+t*(i%2?1:-1)*.075,rx=29+(i%4)*11,ry=18+(i%3)*8;const x=pt.x+Math.cos(angle)*rx,y=pt.y+Math.sin(angle)*ry+8,bob=w.paused?0:Math.sin(t*6+i)*.8;drawPerson(c,x,y,bob,['#ff8d81','#5c9af0','#a394df','#63bcb7'][i%4],t+i)}
 });
 // Small cars move around short decorative loops near the demo neighborhood.
 if(w.places.length){const center=map.latLngToContainerPoint([31.217,121.470]);if(Math.abs(center.x)<size.x+250&&Math.abs(center.y)<size.y+250){for(let i=0;i<4;i++){const a=t*.11+i*Math.PI/2,x=center.x+Math.cos(a)*102,y=center.y+Math.sin(a)*77;drawCar(c,x,y,a+Math.PI/2,['#ffb18f','#83aff6','#b2a2e8','#88d6cf'][i])}}}
}
function drawPerson(c,x,y,bob,color,t){c.save();c.translate(x,y);c.fillStyle='#47648420';c.beginPath();c.ellipse(0,4,4,2,0,0,Math.PI*2);c.fill();c.translate(0,bob);c.strokeStyle='#617e9e';c.lineWidth=1.7;c.lineCap='round';c.beginPath();c.moveTo(-1,1);c.lineTo(-2+Math.sin(t*5),4);c.moveTo(1,1);c.lineTo(2-Math.sin(t*5),4);c.stroke();c.fillStyle=color;c.beginPath();c.roundRect(-3,-6,6,8,3);c.fill();c.fillStyle='#ffdfc9';c.beginPath();c.arc(0,-8,2.6,0,Math.PI*2);c.fill();c.fillStyle='#5c6d8e';c.beginPath();c.arc(0,-9,2.5,Math.PI,Math.PI*2);c.fill();c.restore()}
function drawCar(c,x,y,angle,color){c.save();c.translate(x,y);c.rotate(angle);c.fillStyle='#32547822';c.beginPath();c.ellipse(1,3,7,11,0,0,Math.PI*2);c.fill();c.fillStyle='#68829c';c.fillRect(-7,-5,3,4);c.fillRect(4,-5,3,4);c.fillRect(-7,5,3,4);c.fillRect(4,5,3,4);c.fillStyle=color;c.strokeStyle='#fff';c.lineWidth=1.5;c.beginPath();c.roundRect(-6,-11,12,23,4);c.fill();c.stroke();c.fillStyle='#f4fbff';c.beginPath();c.roundRect(-4,-5,8,9,2);c.fill();c.fillStyle='#ffffffaa';c.fillRect(-4,-9,3,2);c.fillRect(1,-9,3,2);c.restore()}
