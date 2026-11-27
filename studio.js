// Project-scoped edit decisions are stored locally. The review player opens the actual export.
(() => {
  const el = name => document.getElementById('studio-' + name);
  const key = 'neon-timeline-draft-v1';
  const note = text => { el('note').textContent = text; };
  let rows = [], selected = 0, undo = [], redo = [], revision = 0;
  try { const saved = JSON.parse(localStorage.getItem(key)); if (Array.isArray(saved)) rows = saved; } catch {}
  function replace(next, index = selected) {
    undo.push(rows); if (undo.length > 60) undo.shift();
    redo = []; rows = next; selected = index; save();
  }
  function save() {
    revision++; selected = Math.max(0, Math.min(selected, rows.length - 1));
    localStorage.setItem(key, JSON.stringify(rows)); draw();
  }
  function button(label, action) {
    const b = document.createElement('button'); b.type = 'button'; b.textContent = label;
    b.onclick = () => Promise.resolve().then(action).catch(e => note(e.message)); return b;
  }
  function patch(i, values) { replace(rows.map((r,n) => n === i ? {...r,...values} : r), i); }
  function field(label, value, change, step = '.01') {
    const node = document.createElement('label'), input = document.createElement('input');
    node.textContent = label; input.type = 'number'; input.step = step; input.value = value;
    input.onchange = () => { if (input.value && Number.isFinite(input.valueAsNumber)) change(input.valueAsNumber); };
    node.append(input); return node;
  }
  const player=el('player'), overlay=el('overlay'), seek=el('seek');
  const imported=new Map();
  let music=null;
  let monitored=null;
  function position(video,r){
    if(!video.videoWidth || !el('monitor').clientWidth)return;
    const width=el('monitor').clientWidth, height=el('monitor').clientHeight;
    const scale=Math.max(width/video.videoWidth,height/video.videoHeight)*(r.zoom??1);
    const w=video.videoWidth*scale,h=video.videoHeight*scale;
    Object.assign(video.style,{width:w+'px',height:h+'px',top:(height-h)/2+'px',
      left:-Math.max(0,Math.min(w-width,w*(r.center??.5)-width/2))+'px'});
  }
  function preview(){
    const r=rows[selected];
    if(!r){player.pause();overlay.pause();el('monitor').hidden=true;monitored=null;return;}
    el('monitor').hidden=false;
    if(monitored!==r){
      player.pause();overlay.pause();monitored=r;
      if(player.getAttribute('src')!=='/media/'+r.id)player.src='/media/'+r.id;
      overlay.hidden=!r.broll;
      if(r.broll && overlay.getAttribute('src')!=='/media/'+r.broll)overlay.src='/media/'+r.broll;
      seek.min=r.start;seek.max=r.end;seek.value=r.start;
      if(player.readyState>=1)player.currentTime=r.start;
      if(r.broll && overlay.readyState>=1)overlay.currentTime=0;
    }
    position(player,r);position(overlay,r);
  }
  player.onloadedmetadata=()=>{if(monitored){player.currentTime=monitored.start;position(player,monitored);}};
  overlay.onloadedmetadata=()=>{if(monitored){overlay.currentTime=0;position(overlay,monitored);}};
  player.ontimeupdate=()=>{if(!monitored)return;seek.value=player.currentTime;
    if(player.currentTime>=monitored.end){player.pause();overlay.pause();}};
  seek.oninput=()=>{player.currentTime=Number(seek.value);if(monitored?.broll&&overlay.duration)overlay.currentTime=(player.currentTime-monitored.start)%overlay.duration;};
  el('play').onclick=async()=>{if(!monitored)return;if(!player.paused){player.pause();overlay.pause();return;}
    if(player.currentTime>=monitored.end-.05)player.currentTime=monitored.start;
    try{player.playbackRate=monitored.speed??1;overlay.playbackRate=player.playbackRate;await player.play();if(monitored.broll){overlay.loop=true;if(overlay.duration)overlay.currentTime=(player.currentTime-monitored.start)%overlay.duration;await overlay.play();}}
    catch(e){note(e.message);}};
  el('split').onclick=()=>{const r=rows[selected],at=player.currentTime;if(!r||at-r.start<.08||r.end-at<.08)return note('Move the playhead inside the segment.');
    replace([...rows.slice(0,selected),{...r,end:at},{...r,start:at},...rows.slice(selected+1)],selected);};
  new ResizeObserver(()=>{if(monitored){position(player,monitored);position(overlay,monitored);}}).observe(el('monitor'));
  el('search').onclick=async()=>{try{const results=await request('/studio/stock?q='+encodeURIComponent(el('stock-query').value));const host=el('stock');host.replaceChildren();
    for(const stock of results){const line=document.createElement('div'),link=document.createElement('a');link.href=stock.page;link.target='_blank';link.rel='noopener noreferrer';
      link.textContent='View on Pexels · '+stock.author+' · '+stock.duration+'s';line.append(link,button('Import footage',async()=>{
        const r=await request('/studio/stock/'+stock.id,{});imported.set(r.id,'Pexels · '+r.credit);await sources();el('source').value=r.id;note('B-roll ready. Apply it to a segment.');}));
      host.append(line);}
    if(!results.length)note('No matching footage.');
  }catch(e){note(e.message);}};
  el('file').onchange=async()=>{const file=el('file').files[0];if(!file)return;
    try{const form=new FormData();form.append('file',file);note('Importing local file…');
      const response=await fetch('/upload',{method:'POST',body:form});const info=await response.json();
      if(!response.ok)throw Error(info.detail||'Import failed.');
      imported.set(info.id,file.name);await sources();el('source').value=info.id;note('Source ready.');
    }catch(e){note(e.message);}finally{el('file').value='';}};
  function draw() {
    const host = el('cuts'); host.replaceChildren();
    rows.forEach((r,i) => {
      const line = document.createElement('div'); line.className = 'controls';
      const pick = button((selected===i?'● ':'○ ') + (i+1) + '. ' + (r.label || r.id.slice(0,8)), () => { selected=i; draw(); });
      pick.setAttribute('aria-pressed', String(selected===i)); line.append(pick);
      line.append(field('In (s)',r.start,v=>patch(i,{start:v})),field('Out (s)',r.end,v=>patch(i,{end:v})),
                  field('Centre (0–1)',r.center??.5,v=>patch(i,{center:v})),field('Zoom (1–2)',r.zoom??1,v=>patch(i,{zoom:v})),field('Speed',r.speed??1,v=>patch(i,{speed:v})),field('Freeze at end (s)',r.freeze??0,v=>patch(i,{freeze:v})));
      line.append(button('Split at midpoint',()=>{ const mid=(r.start+r.end)/2;
        if(mid-r.start<.08) throw Error('Segment is too short to split.');
        replace([...rows.slice(0,i),{...r,end:mid},{...r,start:mid},...rows.slice(i+1)],i); }),
        button('Move up',()=>{if(i){const next=rows.slice(); [next[i],next[i-1]]=[next[i-1],next[i]]; replace(next,i-1);}}),
        button(r.cue?'Remove sound cue':'Add sound cue',()=>patch(i,{cue:!r.cue})),
        button(r.broll?'Remove B-roll':'Use selected source as B-roll',()=>{
          const value=el('source').value;if(!r.broll&&(!value||value===r.id))throw Error('Select another source for the B-roll.');
          patch(i,{broll:r.broll?null:value});}),button('Remove',()=>replace(rows.filter((_,n)=>n!==i),i)));
      host.append(line);
    });
    preview(); el('undo').disabled=!undo.length; el('redo').disabled=!redo.length;
  }
  async function sources(){
    const list=await request('/library'); const picker=el('source'); const current=picker.value; picker.replaceChildren();
    if(typeof id==='string' && id) picker.add(new Option('Current source video',id));
    for(const [key,label] of imported) picker.add(new Option(label,key));
    for(const row of list) if(!Array.from(picker.options).some(o=>o.value===row.id)) picker.add(new Option(row.title,row.id));
    if(Array.from(picker.options).some(o=>o.value===current))picker.value=current;
  }
  el('add').onclick=async()=>{try{
    const opt=el('source').selectedOptions[0];if(!opt)throw Error('Upload a source or generate a clip first.');
    const info=await request('/studio/source/'+opt.value);
    replace([...rows,{id:opt.value,start:0,end:info.duration,label:opt.textContent}],rows.length);
  }catch(e){note(e.message);}};
  el('undo').onclick=()=>{if(undo.length){redo.push(rows);rows=undo.pop();save();}};
  el('redo').onclick=()=>{if(redo.length){undo.push(rows);rows=redo.pop();save();}};
  el('refresh').onclick=()=>sources().catch(e=>note(e.message));
  document.getElementById('timeline-studio').ontoggle=e=>{if(e.target.open)sources().catch(err=>note(err.message));};
  el('transcript').onclick=async()=>{const r=rows[selected];if(!r)return note('Select a segment first.');
    el('transcript').disabled=true;
    try{const info=await request('/transcripts/load',{id:r.id,language:document.getElementById('language').value.replace(/^auto$/,'')});
      if(info.job){for(;;){const status=await request('/status/'+info.job);note(status.message||status.status);
        if(status.status==='error')throw Error(status.error);if(status.status==='done')break;await sleep(1000);}}
      note('Transcript ready.');
    }catch(e){note(e.message);}finally{el('transcript').disabled=false;}};
  el('plan').onclick=async()=>{const r=rows[selected], index=selected, before=revision;
    if(!r)return note('Select a segment first.');el('plan').disabled=true;
    try{note('Planning cuts…');const result=await request('/studio/plan',{...r,mode:el('mode').value,broll_source:el('source').value!==r.id?el('source').value:null,prompt:el('prompt').value,language:document.getElementById('language').value.replace(/^auto$/,'')});
      if(revision!==before)throw Error('Draft changed while planning. Run the plan again.');
      if(!result.segments.length)throw Error('No matching cuts. Your draft is preserved.');
      replace([...rows.slice(0,index),...result.segments.map(s=>({...r,...s})),...rows.slice(index+1)],index);note('Review the cuts or undo the plan.');
    }catch(e){note(e.message);}finally{el('plan').disabled=false;}};
  async function render(parts){
    if(!rows.length)return note('Add a segment first.');
    const batches=parts?rows.map(r=>[r]):[rows]; const title=el('title').value;
    el('parts').disabled=el('export').disabled=true;
    try{const host=el('results');host.replaceChildren();
      for(const [i,segments] of batches.entries()){
        const name=parts?title+' · Part '+(i+1):title;
        const {job}=await request('/studio/render',{title:name,segments,music});
        for(;;){const result=await request('/status/'+job);note(result.stage||result.status);
          if(result.status==='error')throw Error(result.error);
          if(result.status==='done')break; await sleep(700);}
        const video=document.createElement('video');video.controls=true;video.preload='metadata';video.style.maxHeight='360px';video.src='/media/'+job;
        const a=document.createElement('a');a.href=video.src;a.download=job+'.mp4';a.textContent='Download '+name;host.append(video,a);
      }note('Export ready.');await refreshLibrary();
    }catch(e){note(e.message);}finally{el('export').disabled=el('parts').disabled=false;}
  }
  el('music').onchange=async()=>{const file=el('music').files[0];if(!file)return;
    try{const form=new FormData();form.append('file',file);const response=await fetch('/upload-asset?kind=audio',{method:'POST',body:form});const asset=await response.json();
      if(!response.ok)throw Error(asset.detail||'Could not import music.');music=asset.id;note('Music ready: '+file.name);
    }catch(e){music=null;note(e.message);}};
  el('clear-music').onclick=()=>{music=null;el('music').value='';note('Music bed removed.');};
  el('export').onclick=()=>render(false);el('parts').onclick=()=>render(true);draw();
})();

(() => {
  const get = id => document.getElementById('social-'+id);
  let account=null, pending=null, platformsInfo=[];
  const note=t=>{get('note').textContent=t;};
  function syncPlatformFields(){
    const p=get('platform').value;
    account=null;get('name').textContent='';get('privacy').replaceChildren();get('send').disabled=true;
    get('ig').hidden=!['instagram','threads'].includes(p);
    get('tt').hidden=p!=='tiktok';
    if(get('custom-box'))get('custom-box').hidden=p!=='custom';
    if(get('connect'))get('connect').hidden=p==='custom';
  }
  function renderPlatformCheckboxes(host,selected,prefix){
    if(!host)return;
    host.replaceChildren();
    const list=platformsInfo.length?platformsInfo:[
      {id:'youtube',label:'YouTube'},{id:'x',label:'X (Twitter)'},{id:'instagram',label:'Instagram'},
      {id:'facebook',label:'Facebook'},{id:'tiktok',label:'TikTok'},{id:'linkedin',label:'LinkedIn'},
      {id:'threads',label:'Threads'},{id:'custom',label:'More (Custom)'}];
    for(const item of list){
      const lbl=document.createElement('label');lbl.className='check';
      const box=document.createElement('input');box.type='checkbox';box.value=item.id;
      box.id=prefix+'-'+item.id;
      if(Array.isArray(selected)&&selected.includes(item.id))box.checked=true;
      lbl.append(box,document.createTextNode(item.label+(item.configured?' ✓':'')));
      host.append(lbl);
    }
  }
  async function loadAuto(){
    try{
      const cfg=await request('/social/auto');
      platformsInfo=cfg.platforms_info||[];
      if(get('auto-on'))get('auto-on').checked=!!cfg.enabled;
      if(get('auto-draft'))get('auto-draft').value=cfg.draft_only?'1':'0';
      if(get('auto-score'))get('auto-score').value=cfg.min_score??0;
      if(get('auto-gap'))get('auto-gap').value=cfg.gap_minutes??30;
      if(get('auto-cap'))get('auto-cap').value=cfg.daily_cap??4;
      if(get('auto-skip-flagged'))get('auto-skip-flagged').checked=cfg.skip_flagged!==false;
      if(get('auto-tags'))get('auto-tags').checked=cfg.include_hashtags!==false;
      if(get('auto-media-url'))get('auto-media-url').value=cfg.media_base_url||'';
      if(get('auto-custom-url'))get('auto-custom-url').value=cfg.custom_url||'';
      if(get('custom-url'))get('custom-url').value=cfg.custom_url||'';
      if(get('auto-custom-token'))get('auto-custom-token').placeholder=cfg.has_custom_token?'token saved (leave blank to keep)':'leave blank to keep existing';
      if(get('custom-token'))get('custom-token').placeholder=cfg.has_custom_token?'token saved':'kept local';
      renderPlatformCheckboxes(get('auto-platforms'),cfg.platforms||[],'social-auto-plat');
      const existingMulti=[...document.querySelectorAll('#social-multi input:checked')].map(x=>x.value);
      renderPlatformCheckboxes(get('multi'),existingMulti.length?existingMulti:(cfg.platforms||[]),'social-multi-plat');
      const srcs=cfg.sources||['make','live'];
      document.querySelectorAll('#social-auto-sources input[type=checkbox]').forEach(box=>{box.checked=srcs.includes(box.value);});
    }catch{}
  }
  async function history(){
    const host=get('history');host.replaceChildren();
    const rows=await request('/social/posts');
    const today=new Date().toDateString(),todayAt=t=>t&&new Date(t*1000).toDateString()===today;
    get('summary').textContent=rows.filter(row=>row.status==='submitted'&&todayAt(row.submitted_at)).length+' submitted today · '+
      rows.filter(row=>['queued','running'].includes(row.status)&&todayAt(row.scheduled_at)).length+' queued today';
    for(const row of rows){
      const line=document.createElement('p');line.textContent=row.platform+' · '+row.title+' · '+row.status+(row.error?' · '+row.error:'');
      if(['draft','retryable'].includes(row.status)){
        const review=document.createElement('small');review.textContent=' · '+row.name+' · '+row.privacy;
        if(row.when)review.textContent+=' · '+new Date(row.when*1000).toLocaleString();
        const approve=document.createElement('button');approve.textContent=row.status==='retryable'?'Retry and queue':'Approve and queue';
        approve.onclick=async()=>{approve.disabled=true;try{
          const result=await request('/social/posts/'+row.id+'/approve',{});
          note('Approved for '+new Date(result.scheduled_at*1000).toLocaleString()+'.');await history();
        }catch(e){note(e.message);approve.disabled=false;}};
        line.append(review,approve);
      }
      if(row.status==='queued' && row.job){const cancel=document.createElement('button');cancel.textContent='Cancel scheduled post';
        cancel.onclick=async()=>{try{await request('/queue/'+row.job+'/cancel',{});await history();}catch(e){note(e.message);}};line.append(cancel);}
      if(row.external){const metrics=document.createElement('span');const show=v=>{metrics.textContent=Object.entries(v).map(([k,n])=>' · '+k+' '+n).join('');};
        show(row.metrics);const b=document.createElement('button');b.textContent='Refresh metrics';
        b.onclick=async()=>{try{show(await request('/social/posts/'+row.id+'/metrics',{}));}catch(e){note(e.message);}};line.append(b,metrics);}
      host.append(line);
    }
  }
  async function init(){const list=await request('/library');get('clip').replaceChildren();
    for(const row of list)get('clip').add(new Option(row.title,row.id));await Promise.all([history(),loadAuto()]);}
  document.getElementById('social-panel').ontoggle=e=>{if(e.target.open)init().catch(err=>note(err.message));};
  get('platform').onchange=syncPlatformFields;
  syncPlatformFields();
  if(get('custom-save'))get('custom-save').onclick=async()=>{try{
    await request('/social/auto',{custom_url:get('custom-url').value.trim(),custom_token:get('custom-token').value.trim()});
    get('custom-token').value='';note('Custom upload endpoint saved. Press Check account to verify.');await loadAuto();
  }catch(e){note(e.message);}};
  if(get('auto-save'))get('auto-save').onclick=async()=>{
    const anote=get('auto-note');anote.textContent='Saving…';
    try{
      const plats=[...document.querySelectorAll('#social-auto-platforms input:checked')].map(x=>x.value);
      const srcs=[...document.querySelectorAll('#social-auto-sources input:checked')].map(x=>x.value);
      const body={enabled:get('auto-on').checked,platforms:plats,sources:srcs,draft_only:get('auto-draft').value==='1',
        min_score:Number(get('auto-score').value)||0,gap_minutes:Number(get('auto-gap').value)||0,
        daily_cap:Number(get('auto-cap').value)||0,offset_minutes:-new Date().getTimezoneOffset(),
        skip_flagged:get('auto-skip-flagged').checked,
        include_hashtags:get('auto-tags').checked,media_base_url:get('auto-media-url').value.trim(),
        custom_url:get('auto-custom-url').value.trim()};
      const tok=get('auto-custom-token').value.trim();if(tok)body.custom_token=tok;
      const saved=await request('/social/auto',body);
      get('auto-custom-token').value='';
      anote.textContent=saved.enabled?'✓ Auto-upload ON ('+saved.platforms.join(', ')+')':'✓ Saved (auto-upload off)';
      await loadAuto();
    }catch(e){anote.textContent='✗ '+e.message;}
  };
  get('connect').onclick=async()=>{try{const r=await request('/social/connect/'+get('platform').value,{});
    const a=document.createElement('a');a.href=r.url;a.target='_blank';a.rel='noopener noreferrer';a.textContent='Continue on the platform';
    get('note').replaceChildren(a);}catch(e){note(e.message);}};
  get('finish').onclick=async()=>{const redirect=get('callback').value;get('callback').value='';
    try{await request('/social/authorize',{redirect});note('Account connected. Check the account before posting.');await loadAuto();}catch(e){note(e.message);}};
  get('disconnect').onclick=async()=>{try{await request('/social/disconnect/'+get('platform').value,{});syncPlatformFields();note('Saved local connection cleared. Environment-supplied tokens are managed outside the app.');await loadAuto();}
    catch(e){note(e.message);}};
  get('account').onclick=async()=>{syncPlatformFields();const p=get('platform').value;
    try{const found=await request('/social/account/'+p);if(get('platform').value!==p)return;account=found;
      get('name').textContent=account.name+' ('+account.id+')';get('privacy').add(new Option('Choose visibility',''));
      for(const choice of account.privacy)get('privacy').add(new Option(choice,choice));
      get('send').disabled=false;note('Review the selected clip, destination and visibility.');
    }catch(e){note(e.message);}};
  get('send').onclick=async()=>{if(!account)return;get('send').disabled=true;
    try{const date=get('when').value;const payload={account:account.id,platform:get('platform').value,privacy:get('privacy').value,
      clip:get('clip').value,title:get('title').value,media_url:get('url').value,when:date?new Date(date).getTime()/1000:0,
      own_brand:get('brand').checked,paid:get('paid').checked,draft:true,
      gap_minutes:Number(get('gap').value)||0,daily_cap:Number(get('cap').value)||0,offset_minutes:-new Date().getTimezoneOffset()};
      const signature=JSON.stringify(payload);
      if(!pending || pending.signature!==signature)pending={signature,id:crypto.randomUUID()};
      await request('/social/posts',{...payload,request_id:pending.id});pending=null;note('Draft saved. Approve it below to queue publishing.');await history();
    }catch(e){note(e.message);}finally{get('send').disabled=!account;}};
  if(get('send-multi'))get('send-multi').onclick=async()=>{
    const selected=[...document.querySelectorAll('#social-multi input:checked')].map(x=>x.value);
    if(!selected.length)return note('Check at least one platform below to publish.');
    get('send-multi').disabled=true;
    try{
      const date=get('when').value;
      const res=await request('/social/posts/batch',{platforms:selected,clip:get('clip').value,title:get('title').value,
        media_url:get('url').value,when:date?new Date(date).getTime()/1000:0,own_brand:get('brand').checked,paid:get('paid').checked,
        draft:false,gap_minutes:Number(get('gap').value)||0,daily_cap:Number(get('cap').value)||0,
        offset_minutes:-new Date().getTimezoneOffset(),request_id:crypto.randomUUID()});
      const ok=res.results.filter(r=>r.ok).map(r=>r.platform), fail=res.results.filter(r=>!r.ok).map(r=>r.platform+': '+r.error);
      note((ok.length?'Queued for '+ok.join(', ')+'. ':'')+(fail.length?'Skipped: '+fail.join(' · '):''));
      await history();
    }catch(e){note(e.message);}finally{get('send-multi').disabled=false;}
  };
})();
