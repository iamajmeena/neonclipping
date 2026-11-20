const $=id=>document.getElementById(id),v=$('video'),c=$('source'),ctx=c.getContext('2d'),pc=$('preview').getContext('2d');
let id=null,still=null,sourceW=0,sourceH=0,sourceDuration=0,mode='cam',layout='stack',style='gta',drag=null,highlights=[],words=null,wordRange='',pendingImport=null,importToken=0,selectedTime=0;
let rectEdited=false,layoutClicked=false,layoutSpecs={},editingClip=null;
let rect={cam:{x:0,y:0,w:.25,h:.3},game:{x:.25,y:0,w:.75,h:1}};
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const status=t=>$('status').textContent=t;
async function request(path,body){const response=await fetch(path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const data=await response.json();if(!response.ok)throw Error(data.detail||'Request failed');return data;}
function signature(){return [id,Number($('start').value),Number($('end').value),$('language').value].join(':');}
function clearWords(){words=null;wordRange='';$('words').replaceChildren();}
function setRange(start,end){$('start').value=start;$('end').value=end;clearWords();}
function setSource(j,seek=0){editingClip=null;$('saved-edit').hidden=true;id=j.id;sourceW=j.w;sourceH=j.h;sourceDuration=j.duration;still=null;v.onloadeddata=()=>{if(seek>0&&seek<v.duration)v.currentTime=seek;};v.src='/media/'+id;c.width=j.w;c.height=j.h;$('empty-source').hidden=true;$('source-mode').textContent='SOURCE READY';}
async function requireSource(){if(pendingImport&&!id){status('Source is downloading. Your layout is saved; this step will continue when ready.');await pendingImport;}if(!id)throw Error('Add a video link or upload a file first.');}
function showFrame(frame,meta,button){const image=new Image();image.onload=()=>{still=image;sourceW=image.naturalWidth;sourceH=image.naturalHeight;c.width=sourceW;c.height=sourceH;sourceDuration=meta.duration;selectedTime=frame.time;$('empty-source').hidden=true;$('source-mode').textContent=frame.kind.includes('storyboard')?'EARLY FRAME · LOW RES':'PREVIEW FRAME';v.pause();document.querySelectorAll('.frame-btn').forEach(b=>b.classList.remove('active'));button.classList.add('active');};image.src=frame.url;}
function addFrames(frames,meta){const current=$('frames').children.length;frames.slice(current).forEach((frame,index)=>{const button=document.createElement('button');button.className='frame-btn';const image=document.createElement('img');image.src=frame.url;image.alt='Source frame at '+frame.time+' seconds';const label=document.createElement('small');label.textContent=frame.time+'s';button.append(image,label);button.onclick=()=>showFrame(frame,meta,button);$('frames').append(button);if(current===0&&index===0&&!id){showFrame(frame,meta,button);if(Number($('end').value)>meta.duration)$('end').value=meta.duration;}});}
$('link').onclick=async()=>{
 const url=$('url').value.trim();if(!url){status('Paste a video link first.');return;}
 const token=++importToken;id=null;still=null;clearWords();$('frames').replaceChildren();$('link').disabled=true;$('progress-wrap').hidden=false;$('progress').style.width='2%';$('link-status').textContent='Getting early source frames…';
 const operation=(async()=>{const {job}=await request('/link',{url});let completed=false;
  for(;;){const s=await request('/status/'+job);if(token!==importToken)return;if(s.preview_frames)addFrames(s.preview_frames,s.preview_meta);
   $('link-status').textContent=s.status==='done'?'Source ready. Your selected areas are preserved.':(s.message||s.stage||'Importing source');$('progress').style.width=(s.status==='done'?100:Math.min(95,(s.progress||.05)*300))+'%';
   if(s.status==='error')throw Error(s.error);
   if(s.status==='done'&&!completed){completed=true;setSource(s,selectedTime);if(!Number($('end').value)||Number($('end').value)>s.duration)$('end').value=Math.min(30,s.duration);$('link-status').textContent='Source ready. Your selected areas are preserved.';status('Source ready. Find highlights or export your selected range.');}
   if(completed&&(s.preview_status!=='loading'||s.preview_frames?.length>=4))break;
   await sleep(700);
  }
 })();pendingImport=operation;
 try{await operation;}catch(e){$('link-status').textContent=e.message;status(e.message);}finally{if(token===importToken){pendingImport=null;$('link').disabled=false;}}
 if(token===importToken&&id&&$('auto-analyze').checked&&!$('analyze').disabled)await $('analyze').onclick();
};
$('file').onchange=async()=>{try{if(!$('file').files[0])return;++importToken;pendingImport=null;id=null;still=null;$('link').disabled=false;$('frames').replaceChildren();status('Uploading source…');const form=new FormData();form.append('file',$('file').files[0]);const response=await fetch('/upload',{method:'POST',body:form});const j=await response.json();if(!response.ok)throw Error(j.detail);$('url').value='';setSource(j);setRange(0,Math.min(30,j.duration));$('link-status').textContent='File ready';status('Draw the facecam and gameplay areas.');}catch(e){status(e.message);}};
function showHighlights(jobs){highlights=jobs.flatMap(job=>(job.clips||[]).map(clip=>({...clip,job:job.job||job.id,video:job.title})));const select=$('recent');select.replaceChildren();if(!highlights.length){const option=document.createElement('option');option.textContent='No highlights yet — add a video and Find highlights';select.append(option);}highlights.forEach((h,index)=>{const option=document.createElement('option');option.value=index;option.textContent=h.start.toFixed(1)+'–'+h.end.toFixed(1)+'s · '+h.title+(h.score!==undefined?' · activity '+h.score:'');select.append(option);});}
async function openHighlight(){const h=highlights[Number($('recent').value)];if(!h)return;const j=await request('/highlight-source',{job:h.job});setSource(j,h.start);setRange(h.start,h.end);status('Moment loaded. Review the source and selected areas.');}
$('import').onclick=()=>openHighlight().catch(e=>status(e.message));
$('analyze').onclick=async()=>{const button=$('analyze');button.disabled=true;try{if(!id&&!pendingImport&&$('url').value.trim()){await $('link').onclick();}await requireSource();status('Finding activity highlights locally…');const {job}=await request('/analyze',{id,count:Number($('count').value),length:Number($('length').value),min_len:Number($('minlen').value)});for(;;){const s=await request('/analysis/'+job);status((s.stage||s.status)+' · '+Math.round((s.progress||0)*100)+'%');if(s.status==='error')throw Error(s.error);if(s.status==='done'){showHighlights([s]);await openHighlight();status('Highlights ready. Choose a moment, review it and export.');break;}await sleep(900);}}catch(e){status(e.message);}finally{button.disabled=false;}};
['cam','game'].forEach(k=>$(k).onclick=()=>{mode=k;['cam','game'].forEach(x=>$(x).classList.toggle('active',x===k));});
function point(e){const b=c.getBoundingClientRect();return{x:Math.max(0,Math.min(1,(e.clientX-b.left)/b.width)),y:Math.max(0,Math.min(1,(e.clientY-b.top)/b.height))};}
c.onpointerdown=e=>{if(!still&&v.readyState<2)return;drag=point(e);c.setPointerCapture(e.pointerId);};c.onpointermove=e=>{if(!drag)return;rectEdited=true;const p=point(e);rect[mode]={x:Math.min(p.x,drag.x),y:Math.min(p.y,drag.y),w:Math.max(.01,Math.abs(p.x-drag.x)),h:Math.max(.01,Math.abs(p.y-drag.y))};};c.onpointerup=()=>drag=null;c.onpointercancel=()=>drag=null;
$('save').onclick=()=>{localStorage.setItem('ajay-crop',JSON.stringify({rect,top:$('top').value,layout}));status('Layout saved in this browser.');};$('load').onclick=()=>{try{const j=JSON.parse(localStorage.getItem('ajay-crop')||'null');if(j){rect=j.rect;rectEdited=true;$('top').value=j.top;setLayout(j.layout||'stack');status('Saved layout loaded.');}else status('No saved layout yet.');}catch(e){status('Saved layout could not be read.');}};
function setLayout(value){layout=value;if($('edit-top'))$('edit-top').value=$('top').value;document.querySelectorAll('[data-layout]').forEach(b=>b.classList.toggle('active',b.dataset.layout===layout));$('height-control').hidden=['blur','fill','game'].includes(layout);}
document.querySelectorAll('[data-layout]').forEach(b=>b.onclick=()=>{layoutClicked=true;setLayout(b.dataset.layout);});document.querySelectorAll('[data-style]').forEach(b=>b.onclick=()=>{style=b.dataset.style;document.querySelectorAll('[data-style]').forEach(x=>x.classList.toggle('active',x===b));});
v.onplay=()=>still=null;v.ontimeupdate=()=>{const end=Number($('end').value);if(end>Number($('start').value)&&v.currentTime>end&&end<v.duration)v.pause();};
['start','end','language'].forEach(key=>$(key).addEventListener('change',()=>{clearWords();if(key==='start'&&id)v.currentTime=Math.max(0,Math.min(v.duration||Infinity,Number($('start').value)));}));
function cover(source,r,x,y,w,h){const sw=r.w*sourceW,sh=r.h*sourceH,ratio=Math.max(w/sw,h/sh),cw=w/ratio,ch=h/ratio;pc.drawImage(source,r.x*sourceW+(sw-cw)/2,r.y*sourceH+(sh-ch)/2,cw,ch,x,y,w,h);}
function captionPreview(){if(!$('captions').checked)return;let line='YOUR NEXT BIG MOMENT';if(words&&wordRange===signature()&&words.length){const time=Math.max(0,v.currentTime-Number($('start').value));let index=words.findIndex(w=>time>=w.start&&time<=w.end);if(index<0)index=0;line=words.slice(Math.floor(index/3)*3,Math.floor(index/3)*3+3).map(w=>w.text).join(' ');}pc.save();pc.textAlign='center';pc.textBaseline='middle';pc.font=(style==='clean'?'500 28px':'900 36px')+' Arial';const max=480;while(pc.measureText(line).width>max){const size=parseFloat(pc.font.match(/(\d+)px/)[1]);pc.font='900 '+Math.max(12,size-1)+'px Arial';if(size<=12)break;}const y=(Number($('caption-y').value)===1450?(layoutSpecs[layout]?.caption_y||1450):Number($('caption-y').value))/2;pc.lineWidth=5;pc.strokeStyle='#160b22';pc.shadowBlur=style==='gta'?10:0;pc.shadowColor='#ff4ba5';pc.strokeText(line,270,y);pc.fillStyle=style==='gta'?'#58e8f7':style==='bold'?'#d4fb58':'white';pc.fillText(line,270,y);pc.restore();}
function paint(){const source=still||(v.readyState>=2?v:null);if(source){if(!still){sourceW=v.videoWidth;sourceH=v.videoHeight;}if(sourceW&&sourceH){ctx.drawImage(source,0,0,c.width,c.height);['cam','game'].forEach(k=>{const r=rect[k];ctx.strokeStyle=k==='cam'?'#ff4ba5':'#58e8f7';ctx.lineWidth=Math.max(2,c.width/350);ctx.strokeRect(r.x*c.width,r.y*c.height,r.w*c.width,r.h*c.height);});pc.clearRect(0,0,540,960);drawNativeLayout(source);captionPreview();}}$('height-value').textContent=$('top').value+'%';requestAnimationFrame(paint);}paint();
function collectWords(){if(words&&wordRange===signature())return words;return null;}
function renderWords(){const editor=$('words');editor.replaceChildren();for(const word of words||[]){const input=document.createElement('input');input.value=word.text;input.title=word.start.toFixed(2)+'–'+word.end.toFixed(2)+'s';input.oninput=()=>word.text=input.value;editor.append(input);}}
async function generateSubtitles(){await requireSource();status('Starting local subtitles…');const range=signature();const {job}=await request('/transcribe',{id,start:Number($('start').value),end:Number($('end').value),language:$('language').value});for(;;){const s=await request('/status/'+job);status(s.message||s.status);if(s.status==='error')throw Error(s.error);if(s.status==='done'){if(signature()!==range)throw Error('Selected range changed. Generate subtitles for the current range.');words=s.words;wordRange=range;renderWords();const text=words.map(w=>w.text).join(' ');if(!$('clip-title').value)$('clip-title').value=text.split(/\s+/).slice(0,9).join(' ');if(!$('post-caption').value)$('post-caption').value=text.slice(0,220)+(text.length>220?'…':'')+'\n\n#Gaming #Clips';status(words.length?'Subtitles ready. Edit any word before exporting.':'No speech detected in this range.');return;}await sleep(1100);}}
$('transcribe').onclick=async()=>{$('transcribe').disabled=true;try{await generateSubtitles();}catch(e){status(e.message);}finally{$('transcribe').disabled=false;}};
function exportSettings(source,start,end){const b={id:source,...rect,layout,top:Number($('top').value)/100,start,end,captions:$('captions').checked,caption_style:style,caption_y:Number($('caption-y').value),language:$('language').value,hook:$('hook').value,title:$('clip-title').value,post_caption:$('post-caption').value,facecam_enhance:$('facecam-enhance')?.value||'smart',filters:getFacecamFilters()};if(source===id&&start===Number($('start').value)&&end===Number($('end').value)){const edited=collectWords();if(edited!==null)b.words=edited;}return b;}
async function runExport(body,prefix=''){const {job}=await request('/export',body);for(;;){const s=await request('/status/'+job);status(prefix+(s.message||'Rendering…'));if(s.status==='error')throw Error(s.error);if(s.status==='done')return s;await sleep(1000);}}
function showDownload(s){$('download').href='/media/'+s.file;$('download').hidden=false;$('srt').hidden=!s.srt;if(s.srt)$('srt').href=s.srt;}
$('export').onclick=async()=>{const button=$('export');button.disabled=true;$('download').hidden=true;$('srt').hidden=true;try{await requireSource();const s=await runExport(exportSettings(id,Number($('start').value),Number($('end').value)));showDownload(s);status('Ready · 1080 × 1920 · '+s.encoder+' · '+s.caption_words+' caption words');await refreshLibrary();}catch(e){status(e.message);}finally{button.disabled=false;}};
$('batch').onclick=async()=>{const button=$('batch');button.disabled=true;$('export').disabled=true;try{await requireSource();const selected=highlights[Number($('recent').value)];if(!selected)throw Error('Find highlights first.');const candidates=highlights.filter(h=>h.job===selected.job);const source=await request('/highlight-source',{job:selected.job});for(let i=0;i<candidates.length;i++){const h=candidates[i],body=exportSettings(source.id,h.start,h.end);body.title=($('clip-title').value||'Highlight')+' '+(i+1);const s=await runExport(body,'Clip '+(i+1)+' / '+candidates.length+' · ');showDownload(s);await refreshLibrary();}status(candidates.length+' clips exported. Open My clips to preview and download.');}catch(e){status(e.message);}finally{button.disabled=false;$('export').disabled=false;}};
// Library with many clips: only fetch a video's metadata once it scrolls near the screen.
const lazyObserver=('IntersectionObserver' in window)?new IntersectionObserver(es=>es.forEach(e=>{if(e.isIntersecting){e.target.preload='metadata';e.target.load();lazyObserver.unobserve(e.target);}}),{rootMargin:'400px'}):null;
function lazyVideo(v){if(lazyObserver){v.preload='none';lazyObserver.observe(v);}else v.preload='metadata';}
async function refreshLibrary(){const clips=await request('/library');$('library-count').textContent=clips.length;const host=$('library');host.replaceChildren();if(!clips.length){const empty=document.createElement('div');empty.className='empty-library';empty.textContent='Your first clip belongs here. Export a moment to start your library.';host.append(empty);}for(const clip of clips){const card=document.createElement('article');card.className='clip-card';const video=document.createElement('video');video.src='/media/'+clip.id;video.controls=true;lazyVideo(video);const title=document.createElement('h3');title.textContent=clip.title;const meta=document.createElement('p');meta.textContent=(clip.meta.duration||0).toFixed(1)+' seconds · '+(clip.settings.layout||'stack')+' · '+new Date(clip.created*1000).toLocaleDateString();const links=document.createElement('div');links.className='card-links';const download=document.createElement('a');download.href='/media/'+clip.id;download.download='neonclipping-'+clip.id+'.mp4';download.textContent='↓ MP4';links.append(download);if(clip.srt){const sub=document.createElement('a');sub.href='/text/'+clip.id+'/srt';sub.textContent='↓ SRT';links.append(sub);}const edit=document.createElement('button');edit.textContent='Edit clip';edit.onclick=()=>openSavedClip(clip.id).catch(e=>status(e.message));links.append(edit);card.append(video,title,meta,links);host.append(card);}}
document.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>{document.querySelectorAll('[data-view]').forEach(x=>x.classList.toggle('active',x===b));$('editor-view').hidden=b.dataset.view!=='editor';$('library-view').hidden=b.dataset.view!=='library';if(b.dataset.view==='library')refreshLibrary().catch(e=>status(e.message));});$('refresh-library').onclick=()=>refreshLibrary().catch(e=>status(e.message));
request('/highlights').then(showHighlights).catch(e=>status(e.message));refreshLibrary().catch(e=>status(e.message));

$('make').onclick=async()=>{const url=$('url').value.trim();if(!url&&!id){status('Paste a video link or upload a file first.');return;}
 const b=$('make');b.disabled=true;$('make-results').hidden=false;$('make-grid').replaceChildren();$('make-progress').style.width='2%';
 try{const {job}=await request('/make',{...(url?{url}:{id}),count:Number($('count').value),mode:$('mode').value,accurate:$('accurate').value,min_len:Number($('minlen').value),max_len:Number($('length').value),layout:makeLayout(),cam:rect.cam,game:rect.game,top:Number($('top').value)/100,caption_style:style,language:$('language').value==='auto'?'':$('language').value,facecam_enhance:$('facecam-enhance')?.value||'smart',filters:getFacecamFilters()});
  const shown=new Set();
  for(;;){const s=await request('/make/'+job);$('make-status').textContent=(s.stage||s.status)+' · '+Math.round((s.progress||0)*100)+'%';$('make-progress').style.width=Math.max(2,(s.progress||0)*100)+'%';
   (s.clips||[]).forEach(c=>{if(shown.has(c.file))return;shown.add(c.file);const d=document.createElement('div');d.className='mk';d.dataset.file=c.file;
    if(c.error){d.textContent='Failed: '+c.error.slice(0,120);}else{const vid=document.createElement('video');vid.src='/media/'+c.file;vid.controls=true;vid.preload='metadata';const t=document.createElement('b');t.textContent=c.title;const m=document.createElement('small');m.textContent=Math.round(c.start)+'–'+Math.round(c.end)+'s · score '+c.score+(c.hook?' · "'+c.hook+'"':'');const a=document.createElement('a');a.href='/media/'+c.file;a.download='neonclipping-'+c.file+'.mp4';a.textContent='Download MP4';const rs=document.createElement('small');rs.textContent=c.reason||'';const vb=document.createElement('div');vb.className='viral';const ax=c.axes||{};const fmt=v=>v==null?'–':v;vb.title='Viral score is a heuristic: loudness, shouting, what is said, on-screen action and a local AI read. Your star ratings tune it.';vb.innerHTML='<b>🔥 Viral '+(c.viral??'–')+'</b><span>Energy '+fmt(ax.energy)+'</span><span>Action '+fmt(ax.action)+'</span><span>Words '+fmt(ax.words)+'</span><span>AI '+fmt(ax.ai)+'</span>';const stars=document.createElement('div');stars.className='stars';stars.title='Rate this clip: it teaches NeonClipping what a good clip is';
    for(let n=1;n<=5;n++){const sb=document.createElement('button');sb.textContent='★';sb.onclick=async()=>{try{const r=await request('/feedback',{file:c.file,rating:n});[...stars.children].forEach((x,i)=>x.classList.toggle('on',i<n));fb.textContent='Thanks! Learning from '+r.ratings+' rating'+(r.ratings===1?'':'s')+(r.fitted?' · '+(r.insight[0]||''):' (needs 8 to start adapting)');}catch(e){fb.textContent=e.message;}};stars.append(sb);}
    const fb=document.createElement('small');fb.className='fb';fb.textContent='Rate this clip ↑';const edit=document.createElement('button');edit.textContent='Edit clip';edit.onclick=()=>openSavedClip(d.dataset.file).catch(e=>status(e.message));d.append(vid,t,vb,m,rs,a,edit,stars,fb);}
    $('make-grid').append(d);});
   if(s.status==='error')throw Error(s.error);if(s.status==='done'){$('make-status').textContent='Done · '+(s.clips||[]).length+' clips in '+s.elapsed_seconds+'s · also in My clips ('+(s.engine||'')+')';if(!$('make-results').querySelector('.star-ask')){const q=document.createElement('div');q.className='star-ask';q.innerHTML='Free and open-source. If these clips saved you time, <a href="https://github.com/iamajmeena/neonclipping" target="_blank" rel="noopener">★ star NeonClipping on GitHub</a> and follow <a href="https://www.instagram.com/iamajmeena/" target="_blank" rel="noopener">@iamajmeena</a> for more tools.';$('make-results').append(q);}break;}
   await sleep(1000);}}catch(e){$('make-status').textContent=e.message;}finally{b.disabled=false;}};

const PRESETS={tl:{cam:{x:0,y:0,w:.24,h:.32},game:{x:.24,y:0,w:.76,h:1}},tr:{cam:{x:.76,y:0,w:.24,h:.32},game:{x:0,y:0,w:.76,h:1}},
 bl:{cam:{x:0,y:.68,w:.24,h:.32},game:{x:.24,y:0,w:.76,h:1}},br:{cam:{x:.76,y:.68,w:.24,h:.32},game:{x:0,y:0,w:.76,h:1}},bc:{cam:{x:.37,y:.68,w:.26,h:.32},game:{x:0,y:0,w:1,h:.68}}};
let preset=null;
function applyPreset(k,save=true){preset=k;document.querySelectorAll('[data-preset]').forEach(b=>b.classList.toggle('on',b.dataset.preset===k));
 if(k==='none'){$('preset-note').textContent='Blurred full frame, no separate facecam.';document.querySelector('[data-layout=blur]')?.click();}
 else{rectEdited=true;rect={cam:{...PRESETS[k].cam},game:{...PRESETS[k].game}};$('preset-note').textContent='Preset set. Fine-tune by drawing in step 03 if your cam sits a bit differently.';document.querySelector('[data-layout=stack]')?.click();}
 if(save)try{localStorage.setItem('neonclipping-preset',k);}catch(e){}}
document.querySelectorAll('[data-preset]').forEach(b=>b.onclick=()=>applyPreset(b.dataset.preset));
try{const k=localStorage.getItem('neonclipping-preset');if(k)applyPreset(k,false);}catch(e){}

// Make clips uses what the user set up: preset or drawn boxes -> that layout; else the layout they clicked; else blurred full frame.
function makeLayout(){return (layoutClicked||rectEdited)?layout:'blur';}

async function loadNativeLayouts(){
 const entries=await request('/layouts?top='+Number($('top').value)/100);
 layoutSpecs=Object.fromEntries(entries.map(x=>[x.id,x]));
 for(const host of [$('layouts'),$('edit-layouts')].filter(Boolean)){host.replaceChildren();
 for(const entry of entries){const button=document.createElement('button');button.className='choice';button.dataset.layout=entry.id;
 const icon=document.createElement('span');icon.className='mini native-layout-mini';icon.setAttribute('aria-hidden','true');
 if(entry.mode==='blur'){const backdrop=document.createElement('i');backdrop.className='layout-backdrop';const inset=document.createElement('i');inset.className='layout-inset';icon.append(backdrop,inset);}
 else for(const layer of entry.layers){const shape=document.createElement('i');shape.className='layout-'+layer.source+(layer.circle?' layout-circle':'');Object.assign(shape.style,{left:(layer.x/1080*100)+'%',top:(layer.y/1920*100)+'%',width:(layer.w/1080*100)+'%',height:(layer.h/1920*100)+'%'});icon.append(shape);}
 const name=document.createElement('b');name.textContent=entry.name;const desc=document.createElement('small');desc.textContent=entry.description;
 button.append(icon,name,desc);button.onclick=()=>{layoutClicked=true;setLayout(entry.id);};host.append(button);}}
 setLayout(layout);
}
function drawNativeLayout(source){
 const spec=layoutSpecs[layout];if(!spec)return;
 if(spec.mode==='blur'){pc.save();pc.filter='blur(16px)';cover(source,{x:0,y:0,w:1,h:1},-15,-15,570,990);pc.restore();const ratio=Math.min(540/sourceW,960/sourceH),w=sourceW*ratio,h=sourceH*ratio;pc.drawImage(source,0,0,sourceW,sourceH,(540-w)/2,(960-h)/2,w,h);}
 else{pc.fillStyle='#000';pc.fillRect(0,0,540,960);for(const layer of spec.layers){pc.save();if(layer.source==='cam'&&$('facecam-enhance')?.value!=='off'){const c=Number($('filter-contrast')?.value||100),b=Number($('filter-brightness')?.value||0),s=Number($('filter-saturation')?.value||100),h=Number($('filter-hue')?.value||0);pc.filter=`contrast(${c}%) brightness(${100+b}%) saturate(${s}%) hue-rotate(${h}deg)`}if(layer.circle){pc.beginPath();pc.arc((layer.x+layer.w/2)/2,(layer.y+layer.h/2)/2,Math.min(layer.w,layer.h)/4,0,Math.PI*2);pc.clip();}cover(source,layer.source==='full'?{x:0,y:0,w:1,h:1}:rect[layer.source],layer.x/2,layer.y/2,layer.w/2,layer.h/2);pc.restore();}}
 if($('safe-zones')?.checked){pc.save();pc.fillStyle='#ff4ba52b';pc.fillRect(0,0,540,48);pc.fillRect(0,840,540,120);pc.fillRect(470,250,70,590);pc.fillStyle='#fff';pc.font='14px sans-serif';pc.fillText('Platform controls — preview only',12,927);pc.restore();}
}
$('top').addEventListener('input',()=>loadNativeLayouts().catch(e=>status(e.message)));
loadNativeLayouts().catch(e=>status(e.message));

async function openSavedClip(file){
 const saved=await request('/clips/'+file+'/edit'),s=saved.settings;
 if(saved.file&&saved.file!==file){swapEditedCards([{previous:file,file:saved.file}]);file=saved.file;}
 document.querySelector('[data-view=editor]').click();
 setSource(saved.source,Number(s.start));setRange(s.start,s.end);rect={cam:{...s.cam},game:{...s.game}};rectEdited=true;layoutClicked=true;
 $('top').value=Math.round((s.top||.32)*100);$('edit-top').value=$('top').value;await loadNativeLayouts();setLayout(s.layout||'stack');
 style=s.caption_style||'gta';document.querySelectorAll('[data-style]').forEach(b=>b.classList.toggle('active',b.dataset.style===style));
 $('language').value=s.language||'';$('captions').checked=s.captions!==false;$('caption-y').value=s.caption_y||1450;
 $('hook').value=s.hook||'';$('clip-title').value=s.title||'';$('post-caption').value=s.post_caption||'';
 words=s.words||[];wordRange=signature();renderWords();editingClip=file;$('saved-edit').hidden=false;const n=Number(saved.video_clips)||1;$('apply-video').textContent=n>1?'Apply to all '+n+' clips of this video':'Apply to this clip';$('apply-one').hidden=n<=1;
 status(n>1?'Saved clip loaded. Your change will apply to all '+n+' clips of this video (each keeps its own words and title).':'Saved clip loaded. Change framing or captions; saved source and words are reused.');
}
function swapEditedCards(edited){
 for(const e of edited||[]){const olds=[e.previous,...(e.was||[])];const card=[...document.querySelectorAll('.mk')].find(x=>olds.includes(x.dataset.file));if(!card)continue;
  card.dataset.file=e.file;const v=card.querySelector('video');if(v){v.src='/media/'+e.file;v.load();}
  const dl=card.querySelector('a[download]');if(dl){dl.href='/media/'+e.file;dl.download='neonclipping-'+e.file+'.mp4';}
  const t=card.querySelector('b');if(t&&e.title&&!t.parentElement.classList.contains('viral'))t.textContent=e.title;}
}
async function applySavedEdit(scope){
 if(!editingClip)throw Error('Open Edit clip from My clips first.');
 const settings=exportSettings(id,Number($('start').value),Number($('end').value));
 const changes={};for(const k of ['layout','top','cam','game','caption_style','caption_y','captions','hook','title','post_caption'])changes[k]=settings[k];
 const body={file:editingClip,scope,changes};const edited=collectWords();if(edited!==null)body.words=edited;
 $('apply-one').disabled=true;$('apply-video').disabled=true;
 try{const {job,clips}=await request('/clips/reedit',body);status('Updating '+clips+' saved clip(s) — no download, AI picking or transcription.');
 for(;;){const result=await request('/status/'+job);status(result.stage||result.status);if(result.status==='error')throw Error(result.error);if(result.status==='done'){swapEditedCards(result.clips);if(result.clips?.length){const changed=result.clips.find(c=>c.previous===editingClip)||result.clips[0];editingClip=changed.file;showDownload({file:changed.file,srt:changed.srt});}await refreshLibrary();status(clips+' clip(s) updated in '+result.elapsed_seconds+'s. Source, moments and subtitles reused.');break;}await sleep(500);}}
 finally{$('apply-one').disabled=false;$('apply-video').disabled=false;}
}
$('apply-one').onclick=()=>applySavedEdit('one').catch(e=>status(e.message));
$('apply-video').onclick=()=>applySavedEdit('video').catch(e=>status(e.message));

$('edit-top').addEventListener('input',()=>{$('top').value=$('edit-top').value;loadNativeLayouts().catch(e=>status(e.message));});

// Optional donate button: only shown when donate.json (or env vars) has https links.
(async()=>{try{const d=await request('/donate');if(!d.razorpay&&!d.paypal)return;if(d.razorpay){$('don-rzp').href=d.razorpay;$('don-rzp').hidden=false;}if(d.paypal){$('don-pp').href=d.paypal;$('don-pp').hidden=false;}
 $('donate').hidden=false;$('donate').onclick=()=>$('donate-dialog').showModal();$('don-close').onclick=()=>$('donate-dialog').close();}catch(e){}})();

// ---- Live clipping (record + chat spikes + backdated clips)
let liveId=null,liveTimer=null;const liveShown=new Set();
function liveStars(d,file){const stars=document.createElement('div');stars.className='stars';const fb=document.createElement('small');fb.className='fb';fb.textContent='Rate this clip ↑';
 for(let n=1;n<=5;n++){const sb=document.createElement('button');sb.textContent='★';sb.onclick=async()=>{try{const r=await request('/feedback',{file,rating:n});[...stars.children].forEach((x,i)=>x.classList.toggle('on',i<n));fb.textContent='Thanks! Learning from '+r.ratings+' rating'+(r.ratings===1?'':'s');}catch(e){fb.textContent=e.message;}};stars.append(sb);}
 d.append(stars,fb);}
function liveCard(c){const d=document.createElement('div');d.className='mk';d.dataset.file=c.file;
 if(c.error){d.textContent='Clip failed: '+c.error;return d;}
 const vid=document.createElement('video');vid.src='/media/'+c.file;vid.controls=true;vid.preload='metadata';
 const t=document.createElement('b');t.textContent=c.title;
 const ax=c.axes||{},f=v=>v==null?'–':v;const vb=document.createElement('div');vb.className='viral';vb.innerHTML='<b>🔥 Viral '+(c.viral??'–')+'</b><span>Chat '+f(ax.chat)+'</span><span>Energy '+f(ax.energy)+'</span><span>Words '+f(ax.words)+'</span><span>AI '+f(ax.ai)+'</span>';
 const m=document.createElement('small');m.textContent=(c.why||'')+(c.hook?' · "'+c.hook+'"':'');
 const a=document.createElement('a');a.href='/media/'+c.file;a.download='neonclipping-live-'+c.file+'.mp4';a.textContent='Download MP4';
 const edit=document.createElement('button');edit.textContent='Edit clip';edit.onclick=()=>openSavedClip(d.dataset.file).catch(e=>status(e.message));
 d.append(vid,t,vb,m,a,edit);liveStars(d,c.file);return d;}
function liveStatus(s){const mm=String(Math.floor((s.elapsed||0)/60)).padStart(2,'0')+':'+String((s.elapsed||0)%60).padStart(2,'0');
 if(s.status==='error')return '⚠ '+(s.error||'Could not start');
 if(s.status==='starting')return s.stage;
 if(s.status==='recording')return '● Recording '+mm+' · chat '+s.chat_now+' msgs/10 s (normal '+s.baseline+') · chat '+s.chat+' · spikes '+s.spikes+' · clips '+s.clips.length+(s.pending?' · cutting '+s.pending+'…':'');
 return s.stage+' · clips '+s.clips.length;}
async function livePoll(){if(!liveId)return;try{const s=await request('/live/'+liveId);$('live-stats').textContent=liveStatus(s);
 s.clips.forEach((c,i)=>{if(liveShown.has(i))return;liveShown.add(i);$('live-grid').prepend(liveCard(c));});
 if(['stopped','ended','error'].includes(s.status)){clearInterval(liveTimer);liveTimer=null;$('live-start').disabled=false;}}catch(e){$('live-stats').textContent=e.message;clearInterval(liveTimer);$('live-start').disabled=false;}}
$('live-start').onclick=async()=>{const url=$('live-url').value.trim();if(!url){$('live-stats').textContent='Paste a Twitch or YouTube Live link first.';$('live-box').hidden=false;return;}
 $('live-start').disabled=true;$('live-box').hidden=false;$('live-grid').replaceChildren();liveShown.clear();$('live-stats').textContent='Starting the recorder…';
 try{const r=await request('/live/start',{url,layout:makeLayout(),cam:rect.cam,game:rect.game,top:Number($('top').value)/100,caption_style:style,language:$('language').value});liveId=r.live;liveTimer=setInterval(livePoll,2000);livePoll();}
 catch(e){$('live-stats').textContent='⚠ '+e.message;$('live-start').disabled=false;if(/already running/.test(e.message)){try{const r=await request('/live-active');if(r.live){liveId=r.live;$('live-start').disabled=true;liveTimer=setInterval(livePoll,2000);livePoll();}}catch(_){}}}};
$('live-now').onclick=async()=>{if(!liveId)return;try{await request('/live/'+liveId+'/clip-now',{});$('live-stats').textContent='Cutting the last 30 s…';}catch(e){$('live-stats').textContent='⚠ '+e.message;}};
$('live-stop').onclick=async()=>{if(!liveId)return;try{await request('/live/'+liveId+'/stop',{});}catch(e){}livePoll();};

// Re-attach to a live session that is already running (after a page reload) so Stop always works.
(async()=>{try{const r=await request('/live-active');if(r.live){liveId=r.live;$('live-box').hidden=false;$('live-start').disabled=true;liveTimer=setInterval(livePoll,2000);livePoll();}}catch(e){}})();

// ---- Creators: a list of streamers that NeonClipping watches and clips automatically when they go live.
const creatorOpts=()=>({layout:makeLayout(),cam:rect.cam,game:rect.game,top:Number($('top').value)/100,caption_style:style,language:$('language').value});
let creatorSig='';const creatorFeedOpen=new Set();
function attachLive(id){if(liveId===id)return;liveId=id;liveShown.clear();$('live-grid').replaceChildren();$('live-box').hidden=false;$('live-start').disabled=true;clearInterval(liveTimer);liveTimer=setInterval(livePoll,2000);livePoll();}
function agoText(t){if(!t)return 'never';const m=Math.round((Date.now()/1000-t)/60);return m<1?'just now':m<60?m+' min ago':Math.round(m/60)+' h ago';}
function miniCard(clip){const d=document.createElement('div');d.className='mk';d.dataset.file=clip.id;
 const v=document.createElement('video');v.src='/media/'+clip.id;v.controls=true;lazyVideo(v);
 const t=document.createElement('b');t.textContent=clip.title;const m=document.createElement('small');m.textContent=(clip.meta.duration||0).toFixed(0)+' s · '+new Date(clip.created*1000).toLocaleString();
 const a=document.createElement('a');a.href='/media/'+clip.id;a.download='neonclipping-'+clip.id+'.mp4';a.textContent='Download MP4';
 const e=document.createElement('button');e.textContent='Edit clip';e.onclick=()=>openSavedClip(d.dataset.file).catch(x=>status(x.message));
 d.append(v,t,m,a,e);return d;}
async function fillCreatorFeed(id,grid){const lib=await request('/library');grid.replaceChildren();const mine=lib.filter(c=>(c.settings||{}).creator===id);
 if(!mine.length){const p=document.createElement('small');p.textContent='No clips yet. They appear here by themselves while this creator is live.';grid.append(p);return;}
 mine.forEach(c=>grid.append(miniCard(c)));}
function chipFor(c){const s=document.createElement('span');s.className='chip';
 if(c.status==='recording'){s.classList.add('recording');s.textContent='● Recording & clipping';}
 else if(c.status==='live'&&c.paused_until){s.classList.add('wait');s.textContent='LIVE · paused for '+Math.max(1,Math.round((c.paused_until-Date.now()/1000)/60))+' min (switch Auto off and on to resume now)';}
 else if(c.status==='live'&&c.waiting){s.classList.add('live');s.textContent='LIVE · waiting for the current stream to finish';}
 else if(c.status==='live'){s.classList.add('live');s.textContent=c.auto?'LIVE · starting…':'LIVE now (auto is off)';}
 else if(c.status==='unknown'){s.textContent='Checking…';}
 else{s.textContent='Offline · checked '+agoText(c.checked);}
 return s;}
async function loadCreators(force){
 const r=await request('/creators');
 const sig=JSON.stringify(r.creators.map(c=>[c.id,c.status,c.auto,c.clips,c.waiting,c.session,!!c.paused_until,Math.floor((c.checked||0)/30)]));
 const act=await request('/live-active').catch(()=>({}));if(act.live&&!liveId)attachLive(act.live);
 if(!force&&sig===creatorSig)return;creatorSig=sig;
 const host=$('creator-list');host.replaceChildren();
 if(!r.creators.length){const p=document.createElement('p');p.className='muted';p.textContent='No creators yet. Add a streamer above and NeonClipping will clip them whenever they go live.';host.append(p);return;}
 for(const c of r.creators){
  const row=document.createElement('div');row.className='creator-row';
  const top=document.createElement('div');top.className='creator-top';
  const nm=document.createElement('b');nm.textContent=c.name;const pl=document.createElement('span');pl.className='plat';pl.textContent=c.platform;
  const lab=document.createElement('label');const cb=document.createElement('input');cb.type='checkbox';cb.checked=!!c.auto;
  cb.onchange=()=>request('/creators/'+c.id+'/auto',{auto:cb.checked}).then(()=>loadCreators(true)).catch(e=>status(e.message));
  lab.append(cb,document.createTextNode('Auto-clip when live'));top.append(nm,pl,chipFor(c),lab);
  const acts=document.createElement('div');acts.className='creator-actions';
  const mk=(txt,fn)=>{const b=document.createElement('button');b.className='secondary';b.textContent=txt;b.onclick=()=>fn(b).catch(e=>{$('creator-note').textContent='⚠ '+e.message;});acts.append(b);return b;};
  mk('Check now',async b=>{b.disabled=true;$('creator-note').textContent='Checking '+c.name+'…';const x=await request('/creators/'+c.id+'/check',{});$('creator-note').textContent=c.name+(x.live?' is live right now.':' is not live right now.');await loadCreators(true);});
  mk('Use my current layout',async()=>{await request('/creators/'+c.id+'/layout',creatorOpts());$('creator-note').textContent='Saved your current layout, facecam boxes and caption style for '+c.name+'.';});
  if(c.session)mk('Open live view',async()=>{attachLive(c.session);$('live-box').scrollIntoView({behavior:'smooth'});});
  mk('Remove',async()=>{if(!confirm('Remove '+c.name+' from your list? Their clips stay in My clips.'))return;await request('/creators/'+c.id+'/remove',{});await loadCreators(true);});
  const det=document.createElement('details');det.className='creator-feed';const sm=document.createElement('summary');sm.textContent='Clips from '+c.name+' ('+c.clips+')';const grid=document.createElement('div');grid.className='make-grid';
  det.append(sm,grid);det.open=creatorFeedOpen.has(c.id);if(det.open)fillCreatorFeed(c.id,grid).catch(()=>{});
  det.ontoggle=()=>{if(det.open){creatorFeedOpen.add(c.id);fillCreatorFeed(c.id,grid).catch(()=>{});}else creatorFeedOpen.delete(c.id);};
  row.append(top,acts,det);host.append(row);}
}
$('creator-add').onclick=async()=>{const url=$('creator-url').value.trim();if(!url){$('creator-note').textContent='Type a Twitch name or paste a channel link first.';return;}
 try{await request('/creators',{url,...creatorOpts()});$('creator-url').value='';$('creator-note').textContent='Added. Checking if they are live…';await loadCreators(true);}catch(e){$('creator-note').textContent='⚠ '+e.message;}};
loadCreators(true).catch(()=>{});setInterval(()=>{if(!document.hidden)loadCreators().catch(()=>{});},8000);

function getFacecamFilters(){
 return {
  contrast:Number($('filter-contrast')?.value||100)/100,
  brightness:Number($('filter-brightness')?.value||0)/100,
  saturation:Number($('filter-saturation')?.value||100)/100,
  clarity:Number($('filter-clarity')?.value||0)/100,
  hue:Number($('filter-hue')?.value||0)
 };
}
function updateFilterLabels(){
 if($('val-contrast'))$('val-contrast').textContent=$('filter-contrast').value+'%';
 if($('val-brightness'))$('val-brightness').textContent=($('filter-brightness').value>0?'+':'')+$('filter-brightness').value+'%';
 if($('val-saturation'))$('val-saturation').textContent=$('filter-saturation').value+'%';
 if($('val-clarity'))$('val-clarity').textContent=$('filter-clarity').value+'%';
 if($('val-hue'))$('val-hue').textContent=$('filter-hue').value+'°';
}
function setFilterPreset(preset){
 const p={'smart':{c:112,b:1,s:110,clr:50,h:0},'high':{c:116,b:1,s:114,clr:80,h:0},'off':{c:100,b:0,s:100,clr:0,h:0}}[preset];
 if(p){
  if($('filter-contrast'))$('filter-contrast').value=p.c;
  if($('filter-brightness'))$('filter-brightness').value=p.b;
  if($('filter-saturation'))$('filter-saturation').value=p.s;
  if($('filter-clarity'))$('filter-clarity').value=p.clr;
  if($('filter-hue'))$('filter-hue').value=p.h;
  updateFilterLabels();
 }
}
setFilterPreset('smart');
['contrast','brightness','saturation','clarity','hue'].forEach(k=>{
 $('filter-'+k)?.addEventListener('input',()=>{
  updateFilterLabels();
  if($('facecam-enhance'))$('facecam-enhance').value='custom';
 });
});
$('facecam-enhance')?.addEventListener('change',()=>{
 if($('facecam-enhance').value!=='custom')setFilterPreset($('facecam-enhance').value);
});
$('filters-reset')?.addEventListener('click',()=>{
 setFilterPreset('off');
 if($('facecam-enhance'))$('facecam-enhance').value='off';
});

