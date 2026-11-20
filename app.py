from pathlib import Path
import json, subprocess, uuid, threading, shutil
import sys
import time
import os
import yt_dlp
from standalone import attach
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
import uvicorn
import math
from layouts import CATALOG, geometry, render_graph, text_positions
from captions import transcribe, large_v3, write as write_captions
ROOT=Path(__file__).resolve().parent
DATA=ROOT/'data';DATA.mkdir(exist_ok=True)
app=FastAPI()
state={}
def probe(p):
 r=subprocess.run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(p)],capture_output=True,text=True,check=True)
 j=json.loads(r.stdout);v=next(x for x in j['streams'] if x['codec_type']=='video')
 return {'w':v['width'],'h':v['height'],'duration':float(j['format']['duration'])}
@app.get('/')
def home():return HTMLResponse((ROOT/'index.html').read_text(encoding='utf-8'))
attach(app,DATA,state,probe)
@app.get('/layouts')
def native_layouts(top:float=.32):
 try:return [{'id':key,'name':name,'description':description,**geometry(key,top),**text_positions(key,top)} for key,name,description in CATALOG]
 except ValueError as e:raise HTTPException(400,str(e))

@app.post('/upload')
async def upload(file:UploadFile=File(...)):
 id=uuid.uuid4().hex;p=DATA/(id+'.mp4')
 with p.open('wb') as out:
  while b:=await file.read(4*1024*1024):out.write(b)
 try:m=probe(p)
 except Exception:
  p.unlink(missing_ok=True);raise HTTPException(400,'Choose a playable video file.')
 return {'id':id,**m}
@app.get('/media/{id}')
def media(id:str):
 if not id.isalnum():raise HTTPException(404)
 p=DATA/(id+'.mp4')
 if not p.exists():raise HTTPException(404)
 return FileResponse(p,media_type='video/mp4')
@app.get('/assets/{name}')
def assets(name:str):
 if name not in ('app.js','style.css'):raise HTTPException(404)
 return FileResponse(ROOT/name)
@app.get('/text/{id}/{kind}')
def text_file(id:str,kind:str):
 if not id.isalnum() or kind not in ('srt','ass'):raise HTTPException(404)
 p=DATA/(id+'.'+kind)
 if not p.exists():raise HTTPException(404)
 return FileResponse(p,filename='neonclipping-'+id+'.'+kind)
@app.get('/library')
def library():
 records=[]
 groups=app.reedit_groups()
 for f in DATA.glob('*.json'):
  if f.name.endswith(('.state.json','.request.json','.words.json')):continue
  try:
   j=json.loads(f.read_text());result=j.get('result',{})
   if result.get('status')=='done' and not j.get('superseded_by') and (DATA/(f.stem+'.mp4')).exists():
    records.append({'id':f.stem,'title':j.get('settings',{}).get('title') or 'NeonClipping clip','created':f.stat().st_mtime,'meta':result.get('meta',{}),'settings':j.get('settings',{}),'srt':bool(result.get('srt')) and (DATA/(f.stem+'.srt')).exists(),**app.reedit_metadata(f.stem,j,groups)})
  except (ValueError,OSError):pass
 return sorted(records,key=lambda j:j['created'],reverse=True)

def source_range(b):
 id=str(b.get('id',''))
 if not id.isalnum() or not (DATA/(id+'.mp4')).exists():raise HTTPException(400,'Wait for source download, or upload a video.')
 src=DATA/(id+'.mp4');m=probe(src)
 try:start=float(b.get('start',0));end=float(b.get('end',min(30,m['duration'])))
 except (TypeError,ValueError):raise HTTPException(400,'Invalid time range.')
 if not all(map(math.isfinite,(start,end))) or not 0<=start<end<=m['duration']+.1:raise HTTPException(400,'Check start and end times.')
 if end-start>600:raise HTTPException(400,'Choose a clip shorter than 10 minutes.')
 return id,src,m,start,end

@app.post('/transcribe')
def caption_job(b:dict):
 id,src,m,start,end=source_range(b);job=uuid.uuid4().hex
 state[job]={'status':'running','message':'Starting local captions'}
 language=b.get('language') or None
 if language not in (None,'hi','en','hinglish'):raise HTTPException(400,'Choose Auto, Hinglish, Hindi or English.')
 def work():
  try:
   result=transcribe(src,start,end,DATA,lambda msg:state[job].update(message=msg),language)
   state[job]={'status':'done',**result,'source_id':id,'start':start,'end':end}
  except Exception as e:state[job]={'status':'error','error':'Caption generation failed: '+str(e)[-500:]}
 threading.Thread(target=work,daemon=True).start();return {'job':job}

@app.post('/export')
def export(b:dict):
 id,src,m,start,end=source_range(b)
 layout=b.get('layout','stack')
 if layout not in {x[0] for x in CATALOG}:raise HTTPException(400,'Choose a valid layout.')
 style=b.get('caption_style','gta')
 if style not in ('gta','bold','clean','hormozi','mrbeast'):raise HTTPException(400,'Choose a valid caption style.')
 try:
  top=float(b.get('top',.32));position=int(b.get('caption_y',1450))
  if not math.isfinite(top) or not .2<=top<=.5 or not 400<=position<=1750:raise ValueError()
  rects=[]
  for key in ['cam','game']:
   r=b[key];values=[float(r[k]) for k in ('x','y','w','h')]
   if not all(map(math.isfinite,values)) or min(values)<0 or values[2]<.01 or values[3]<.01:raise ValueError()
   x=max(0,min(m['w']-2,int(values[0]*m['w'])));y=max(0,min(m['h']-2,int(values[1]*m['h'])))
   w=max(2,min(m['w']-x,int(values[2]*m['w'])));h=max(2,min(m['h']-y,int(values[3]*m['h'])))
   rects.append((x,y,w,h))
 except (KeyError,ValueError,TypeError,OverflowError):raise HTTPException(400,'Check crop regions, face height and caption position.')
 graph=render_graph(layout,rects,top,enhance=b.get('facecam_enhance','smart'),filters=b.get('filters'))
 job=uuid.uuid4().hex;out=DATA/(job+'.mp4');state[job]={'status':'running','message':'Preparing export'}
 def work():
  try:
   words=[]
   if b.get('captions',False):
    if isinstance(b.get('words'),list):
     for word in b['words'][:2000]:
      a=float(word['start']);z=float(word['end']);text=str(word['text'])[:100]
      if math.isfinite(a) and math.isfinite(z) and 0<=a<z<=end-start+.1:words.append({'start':a,'end':z,'text':text})
    else:words=transcribe(src,start,end,DATA,lambda msg:state[job].update(message=msg),b.get('language') or None)['words']
   placement=text_positions(layout,top,position);hook_y=placement['hook_y'];caption_pos=placement['caption_y']
   ass,srt=write_captions(words,style,DATA,job,str(b.get('hook','')),caption_pos,hook_y)
   fc=graph+f';[base]ass={ass}[v]'
   state[job].update(message='Rendering vertical clip with '+style+' captions' if words else 'Rendering vertical clip')
   base=['ffmpeg','-y','-v','error','-ss',str(start),'-t',str(end-start),'-i',str(src),'-filter_complex',fc,'-map','[v]','-map','0:a?','-c:a','aac','-b:a','160k','-movflags','+faststart']
   for encoder in [['-c:v','h264_nvenc','-preset','p5','-cq','20'],['-c:v','libx264','-crf','20','-preset','fast']]:
    r=subprocess.run(base+encoder+['-pix_fmt','yuv420p',str(out)],capture_output=True,text=True,cwd=str(DATA))
    if r.returncode==0:break
   if r.returncode:raise RuntimeError(r.stderr[-900:])
   finished={'status':'done','file':job,'meta':probe(out),'encoder':encoder[1],'caption_words':len(words),'srt':f'/text/{job}/srt' if words else None}
   (DATA/(job+'.json')).write_text(json.dumps({'source':id,'settings':{**b,'words':words,'caption_y':caption_pos},'result':finished},indent=2),encoding='utf-8')
   state[job]=finished
  except Exception as e:state[job]={'status':'error','error':str(e)}
 threading.Thread(target=work,daemon=True).start();return {'job':job}
PAD=4.0         # seconds fetched before a section: yt-dlp cuts on a keyframe, export trims exactly
FAST_OVER=600   # seconds: longer videos go audio-first, short ones are downloaded whole
def _yt(opts):
 return yt_dlp.YoutubeDL({'noplaylist':True,'quiet':True,'no_warnings':True,'socket_timeout':20,'retries':3,'fragment_retries':3,'concurrent_fragment_downloads':6,**opts})
def _dur(p):
 r=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',str(p)],capture_output=True,text=True,check=True);return float(r.stdout.strip())

def _pcm(path,start=None,length=None):
 import numpy as np
 cmd=['ffmpeg','-v','error']+(['-ss',f'{max(0,start):.2f}'] if start is not None else [])+(['-t',f'{length:.2f}'] if length else [])+['-i',str(path),'-vn','-ac','1','-ar','8000','-f','s16le','pipe:1']
 return np.frombuffer(subprocess.run(cmd,capture_output=True).stdout,dtype=np.int16).astype('float32')
def section_start(audio_file,section_file,expected):
 """Where the downloaded section really begins in the source (it is cut on a keyframe), found by matching its sound to the audio track."""
 import numpy as np
 needle=_pcm(section_file,0,25)
 if len(needle)<8000*5 or float(np.abs(needle).mean())<20:return expected
 a0=max(0,expected-20);hay=_pcm(audio_file,a0,20+20+len(needle)/8000+2)
 if len(hay)<len(needle):return expected
 size=1<<(len(hay)+len(needle)).bit_length()
 corr=np.fft.irfft(np.fft.rfft(hay,size)*np.conj(np.fft.rfft(needle,size)),size)[:len(hay)-len(needle)+1]
 return a0+int(np.argmax(corr))/8000

def axes(f):
 """Four readable 0-100 axes from the scoring features (None = not measured for this clip)."""
 def mean(keys):
  v=[f[k] for k in keys if f.get(k) is not None]
  return round(100*sum(v)/len(v)) if v else None
 return {'energy':mean(('loud','shout')),'action':mean(('motion','flash','strobe')),'words':mean(('words',)),'ai':mean(('llm',)),'chat':mean(('chat',))}

@app.post('/make')
def make(b:dict):
 """One click. Short video: download, smart highlights, export. Long video (PeakCut-style): download AUDIO only, pick moments from
 audio + transcript, then fetch just those video sections. Clips stream into state[job]['clips']."""
 url,src0=app.neon['new_source'](b);save=app.neon['save']
 try:
  count=max(1,min(12,int(b.get('count',4))));raw_max=float(b.get('max_len',b.get('length',60)));raw_min=float(b.get('min_len',30))
  if not (math.isfinite(raw_max) and math.isfinite(raw_min)):raise ValueError()
  max_len=max(10,min(180,raw_max));min_len=max(5,min(max_len,raw_min))
 except (TypeError,ValueError,OverflowError):raise HTTPException(400,'Choose a valid clip count and length range.')
 if raw_min>raw_max:raise HTTPException(400,'Minimum clip length is longer than the maximum. Make the minimum smaller or the maximum bigger.')
 mode='deep' if b.get('mode')=='deep' else 'fast'
 acc=b.get('accurate','fast');acc='best' if acc=='best' else 'accurate' if acc in (True,'accurate') else 'fast'
 layout=b.get('layout','blur');style=b.get('caption_style','gta');language=b.get('language') or None
 from translit import to_hinglish
 top_h=b.get('top');cam=b.get('cam') or {'x':0,'y':0,'w':.25,'h':.3};game=b.get('game') or {'x':.25,'y':0,'w':.75,'h':1}
 job=uuid.uuid4().hex;save(job,{'id':job,'status':'running','stage':'Starting','progress':0,'clips':[],'source':{'url':url}})
 def work():
  began=time.monotonic()
  try:
   from smart import find
   fast=False;title='';yt_words=None;video_lang=''
   if url:
    save(job,{'stage':'Reading video info','progress':.01})
    with _yt({'skip_download':True}) as y:info=y.extract_info(url,download=False)
    if info.get('is_live') or info.get('live_status') in ('is_live','is_upcoming'):
     raise RuntimeError('This stream is live right now. Use the Live clipping panel to clip it while it is on, or wait until it ends and use Make clips on the finished video.')
    video_lang=str(info.get('language') or '')
    fast=float(info.get('duration') or 0)>FAST_OVER and not info.get('is_live') and mode=='fast';title=info.get('title') or ''
    try:
     from captions_yt import from_info
     yt_words=from_info(info);save(job,{'transcript_source':'YouTube captions' if yt_words else 'speech model'})
    except Exception:yt_words=None
   save(job,{'fast_path':fast,'title':title})
   import learn, action
   from concurrent.futures import ThreadPoolExecutor as _TP
   W=learn.load_weights(DATA)
   def lowres_section(u,c):
    """A tiny 144p copy of just this candidate, only for looking at the action (motion, flashes, light strobes)."""
    from yt_dlp.utils import download_range_func
    name='lr_'+uuid.uuid4().hex
    with _yt({'format':'worst[ext=mp4]/bv*[height<=240][ext=mp4]/worst','outtmpl':str(DATA/(name+'.%(ext)s')),'merge_output_format':'mp4',
              'download_ranges':download_range_func(None,[(max(0,c['start']),c['end'])])}) as y:y.download([u])
    f=next(x for x in DATA.glob(name+'.*') if x.suffix not in ('.part','.ytdl'))
    return f,0.0
   def choose(pool_clips,locate):
    """Look at the action in the best candidates, re-rank with the learned weights, keep `count`."""
    K=min(len(pool_clips),count*2)
    top=pool_clips[:K];save(job,{'stage':'Checking action in the best moments','progress':.5})
    def one(c):
     tmp=None
     try:
      f,off=locate(c)
      tmp=f if str(f).startswith(str(DATA)) and Path(f).name.startswith('lr_') else None
      c['_act']=action.analyze(f,off,c['end']-c['start'])
     except Exception as e:c['_act']=None;c['reason']=c.get('reason','')+' (no action check)'
     finally:
      if tmp:Path(tmp).unlink(missing_ok=True)
    with _TP(max_workers=4) as ex:list(ex.map(one,top))
    for key in ('motion','flash','strobe','cuts'):
     vals=[c['_act'][key] for c in top if c.get('_act')]
     if not vals:continue
     lo,hi=min(vals),max(vals)
     for c in top:
      if c.get('_act'):
       v=c['_act'][key];c['features'][key]=round(.5*v+.5*((v-lo)/(hi-lo) if hi>lo else v),3)
    for c in top:
     c['rank']=learn.score(c['features'],W);c['score']=round(c['rank']*100)
     cues=[n for n,k,t in (('shouting','shout',.6),('loud jump','loud',.6),('exclamations','words',.5),('fast motion','motion',.7),('explosion/flash','flash',.5),('police-light flicker','strobe',.5)) if (c['features'].get(k) or 0)>=t]
     c['reason']=(('Cues: '+', '.join(cues)) if cues else 'Steady energy')+(f" · AI {c['llm']:g}/10" if c.get('llm') else '')
     c.pop('_act',None)
    top.sort(key=lambda c:-c['rank'])
    return top[:count]
   sections=None
   if fast:
    def hook(d):
     t=d.get('total_bytes') or d.get('total_bytes_estimate')
     if t and d.get('status')=='downloading':save(job,{'stage':f"Downloading audio {d['downloaded_bytes']/1048576:.0f}/{t/1048576:.0f} MB",'progress':.02+.1*d['downloaded_bytes']/t})
    with _yt({'format':'ba[ext=m4a]/ba/worst','outtmpl':str(DATA/(job+'.audio.%(ext)s')),'progress_hooks':[hook]}) as y:y.download([url])
    p=next(f for f in DATA.glob(job+'.audio.*') if f.suffix not in ('.part','.ytdl'));duration=_dur(p);sid=job
    save(job,{'meta':{'duration':duration},'stage':'Finding moments in audio','progress':.12})
    found,engine=find(p,duration,count,max_len,lambda f,m:save(job,{'stage':m,'progress':.12+.4*f}),language,DATA,min_len,False,yt_words,False,W,False)
    found=choose(found,lambda c:lowres_section(url,c))
    save(job,{'engine':engine+' (audio-first)','stage':'Fetching only the chosen sections','progress':.58,'candidates':len(found)})
    from concurrent.futures import ThreadPoolExecutor
    from yt_dlp.utils import download_range_func
    def section(i,c):
     name=uuid.uuid4().hex
     with _yt({'format':'bv*[height<=1080][vcodec^=avc1]+ba[ext=m4a]/bv*[height<=1080]+ba/b[height<=1080]/bv*[height<=720]+ba/b[height<=720]','merge_output_format':'mp4','outtmpl':str(DATA/(name+'.%(ext)s')),
               'download_ranges':download_range_func(None,[(max(0,c['start']-PAD),c['end']+1)])}) as y:y.download([url])
     return name
    pool=ThreadPoolExecutor(max_workers=3);sections=[pool.submit(section,i,c) for i,c in enumerate(found)]
   else:
    if url:
     save(job,{'stage':'Downloading source','progress':.02});sid,p=app.neon['download'](url,job)
    else:sid,p=src0.stem,src0
    meta=probe(p);duration=meta['duration'];save(job,{'source_id':sid,'meta':meta,'stage':'Finding moments','progress':.1})
    found,engine=find(p,duration,count,max_len,lambda f,m:save(job,{'stage':m,'progress':.1+.5*f}),language,DATA,min_len,True,yt_words,mode=='deep',W,False)
    found=choose(found,lambda c:(p,c['start']))
    save(job,{'engine':engine,'stage':'Rendering clips','progress':.6,'candidates':len(found)})
   done=[]
   for i,c in enumerate(found):
    if sections:
     sid2=sections[i].result();real=section_start(p,DATA/(sid2+'.mp4'),max(0,c['start']-PAD));start=max(0,c['start']-real);end=min(_dur(DATA/(sid2+'.mp4')),start+c['end']-c['start']);words=c.get('words')
    else:sid2=sid;start=c['start'];end=c['end'];words=c.get('words')
    lang=language or ('hinglish' if (video_lang.startswith('hi') or c.get('language')=='hi') else None)
    body={'id':sid2,'start':start,'end':end,'layout':layout,'top':(top_h if isinstance(top_h,(int,float)) and .2<=top_h<=.5 else .32),'captions':True,'caption_style':style,'language':language,'hook':(' '.join(to_hinglish(w) for w in c.get('hook','').split()) if lang=='hinglish' else c.get('hook','')),
          'title':c.get('title',''),'post_caption':c.get('title',''),'batch_id':job,'source_url':url,'cam':cam,'game':game,'features':c.get('features'),'weights_used':W,'facecam_enhance':b.get('facecam_enhance','smart'),'filters':b.get('filters')}
    if acc!='fast' or lang in ('hinglish','hi') or not c.get('words'):
     save(job,{'stage':f'Accurate captions {i+1}/{len(found)}'})
     body['words']=transcribe(DATA/(sid2+'.mp4'),start,end,DATA,lambda m:None,lang,(large_v3() if acc=='best' else None))['words']
    else:body['words']=c['words']
    ej=export(body)['job']
    while state.get(ej,{}).get('status')=='running':time.sleep(.7)
    r=state[ej]
    done.append({'viral':min(99,c['score']),'axes':axes(c.get('features') or {}),'file':ej,'start':c['start'],'end':c['end'],'title':c.get('title') or 'Clip %d'%(i+1),'hook':c.get('hook',''),'score':c['score'],'reason':c.get('reason',''),
                 'error':r.get('error'),'srt':r.get('srt')})
    save(job,{'clips':list(done),'stage':f'Rendered {i+1}/{len(found)}','progress':.6+.4*(i+1)/len(found)})
   save(job,{'status':'done','stage':'Clips ready','progress':1,'elapsed_seconds':round(time.monotonic()-began,1)})
  except Exception as e:save(job,{'status':'error','error':str(e)[-600:]})
 threading.Thread(target=work,daemon=True).start();return {'job':job}
LIVE={}

def live_render(sess,start,dur,why,chat_feature):
 """Cut the backdated window out of the growing recording, caption it, write a hook, export with the user's layout."""
 import learn,excite
 from translit import to_hinglish
 o=sess.opts;name=uuid.uuid4().hex;out=DATA/(name+'.mp4');T={};_t=time.time()
 def lap(k):
  nonlocal _t;T[k]=round(time.time()-_t,1);_t=time.time()
 for enc in (['-c:v','h264_nvenc','-preset','p4','-cq','21'],['-c:v','libx264','-preset','veryfast','-crf','21']):
  r=subprocess.run(['ffmpeg','-y','-v','error','-ss',f'{start:.2f}','-i',str(sess.rec),'-t',f'{dur:.2f}',*enc,'-c:a','aac','-b:a','160k',str(out)],capture_output=True,text=True)
  if r.returncode==0 and out.exists() and out.stat().st_size>10000:break
 else:raise RuntimeError('Could not cut the clip from the recording: '+r.stderr[-150:])
 real=_dur(out);lap('cut')
 lang=o.get('language') or None
 res=transcribe(out,0,real,DATA,lambda m:None,('hinglish' if lang=='hinglish' else lang),'base')
 words=res['words']
 if res.get('language')=='hi' and lang in (None,'hinglish'):
  words=[dict(w,text=to_hinglish(w['text'])) for w in words]
 text=' '.join(w['text'] for w in words);lap('captions')
 title,hook,llm='Live clip','',None
 try:
  import smart
  m=smart._model()
  if m and len(text.split())>=4:
   sc,t,h=smart._ask(m,text);title,hook,llm=t or title,h,sc/10
 except Exception:pass
 loud=None
 try:
  import numpy as np
  from highlights import _audio
  rms,hf=_audio(out)
  if len(rms)>4:
   base=float(np.median(rms))+1e-4;loud=float(min(1.0,max(0.0,(float(np.percentile(rms,95))/base-1.0)/3.0)))
 except Exception:pass
 feats={'chat':chat_feature,'words':excite.window_score(words,real),'llm':llm,'loud':loud}
 W=learn.load_weights(DATA);viral=min(99,round(100*learn.score(feats,W)))
 body={'id':name,'start':0,'end':real,'layout':o.get('layout','blur'),'captions':True,'caption_style':o.get('caption_style','gta'),'language':None,'hook':hook,
       'title':title,'post_caption':title,'cam':o['cam'],'game':o['game'],'top':o.get('top',.32),'words':words,'features':feats,'weights_used':W,'creator':o.get('creator')}
 lap('score')
 ej=export(body)['job']
 while state.get(ej,{}).get('status')=='running':time.sleep(.3)
 r=state[ej]
 if r.get('error'):raise RuntimeError(r['error'])
 lap('render')
 return {'secs':T,'file':ej,'title':title,'hook':hook,'why':why,'viral':viral,'axes':axes(feats),'at':int(sess.now()),'reason':why,'start':round(start),'end':round(start+real)}

def start_live(target,opts,creator=None,before=24,after=14):
 """Start one live-clipping session (used by the Live panel and by the creator watcher). Only one runs at a time."""
 import live_session
 for s_ in LIVE.values():
  if s_.state['status'] in ('starting','recording'):raise RuntimeError('A live session is already running. Stop it first.')
 sess=live_session.LiveSession(target,DATA,live_render,before,after)
 sess.creator=creator;sess.auto=bool(creator);sess.max_seconds=3*3600 if creator else None
 sess.opts={'layout':opts.get('layout','blur'),'caption_style':opts.get('caption_style','gta'),'language':opts.get('language') or None,
            'cam':opts.get('cam') or {'x':0,'y':0,'w':.25,'h':.3},'game':opts.get('game') or {'x':.25,'y':0,'w':.75,'h':1},
            'top':opts.get('top') if isinstance(opts.get('top'),(int,float)) else .32,'creator':creator}
 LIVE[sess.id]=sess;sess.start();return sess.id

@app.post('/live/start')
def live_start(b:dict):
 import live_session
 try:target=live_session.parse_target(str(b.get('url','')))
 except ValueError as e:raise HTTPException(400,str(e))
 before=max(10,min(60,float(b.get('before',24))));after=max(5,min(40,float(b.get('after',14))))
 try:sid=start_live(target,b,None,before,after)
 except RuntimeError as e:raise HTTPException(400,str(e))
 return {'live':sid}

@app.get('/live-active')
def live_active():
 """The running live session, if any, so the page can re-attach to it after a reload."""
 for s_ in LIVE.values():
  if s_.state['status'] in ('starting','recording'):return {'live':s_.id}
 return {'live':None}

@app.get('/live/{lid}')
def live_state(lid:str):
 if lid not in LIVE:raise HTTPException(404,'Live session not found (the app was restarted).')
 return LIVE[lid].state

@app.post('/live/{lid}/clip-now')
def live_clip_now(lid:str):
 if lid not in LIVE:raise HTTPException(404,'Live session not found.')
 try:LIVE[lid].clip_now(30)
 except RuntimeError as e:raise HTTPException(400,str(e))
 return {'ok':True}

@app.post('/live/{lid}/stop')
def live_stop(lid:str):
 if lid not in LIVE:raise HTTPException(404,'Live session not found.')
 LIVE[lid].stop();return {'ok':True}

@app.get('/donate')
def donate():
 """Optional donate links (donate.json or NEONCLIPPING_DONATE_RAZORPAY / NEONCLIPPING_DONATE_PAYPAL). Only https links are served; nothing is unlocked by donating."""
 cfg={}
 try:cfg=json.loads((ROOT/'donate.json').read_text(encoding='utf-8'))
 except (OSError,ValueError):pass
 out={}
 for k in ('razorpay','paypal'):
  v=str(os.environ.get('NEONCLIPPING_DONATE_'+k.upper()) or cfg.get(k) or '').strip()
  if v.startswith('https://') and len(v)<300 and ' ' not in v:out[k]=v
 return out

@app.post('/feedback')
def feedback(b:dict):
 """A star rating (1-5) for a finished clip. Stored locally; the scoring weights are refitted from the ratings (learn.py)."""
 import learn
 file=str(b.get('file',''))
 try:rating=int(b.get('rating',0))
 except (TypeError,ValueError):rating=0
 if not file.isalnum() or not 1<=rating<=5:raise HTTPException(400,'Choose 1 to 5 stars for a finished clip.')
 f=DATA/(file+'.json')
 if not f.exists():raise HTTPException(404,'Clip not found.')
 m=json.loads(f.read_text(encoding='utf-8')).get('settings',{})
 if not m.get('features'):raise HTTPException(400,'This clip has no scoring data (made before ratings existed).')
 return learn.record(DATA,file,rating,m['features'],{'layout':m.get('layout'),'style':m.get('caption_style')})

@app.get('/feedback/summary')
def feedback_summary():
 import learn
 return learn.refit(DATA)

@app.get('/make/{job}')
def make_status(job:str):
 if job not in state:raise HTTPException(404,'Job unavailable after restart. Please retry.')
 return state[job]
@app.get('/status/{id}')
def status(id:str):return state.get(id,{'status':'error','error':'Server restarted. Paste the link again to retry.'})
from reedit import attach as attach_reedit
attach_reedit(app,DATA,state,probe,export,app.neon['save'])

import creators
creators.attach(app,DATA,LIVE,lambda target,opts,cid:start_live(target,opts,cid))

if __name__=='__main__':uvicorn.run(app,host='127.0.0.1',port=int(os.environ.get('NEONCLIPPING_PORT','8770')))
