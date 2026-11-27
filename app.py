from pathlib import Path
from contextlib import asynccontextmanager
import json, re, subprocess, uuid, threading, shutil
import sys
import time
import os
import compat    # first: PyAV 19 shim and a portable FFmpeg when none is installed
import ytdl      # then: keeps yt-dlp fresh before it is imported, and handles YouTube's bot check
import report    # local error log + "Report a problem"
import encoders  # picks NVENC / VideoToolbox / x264 by what works on this computer
import languages
import yt_dlp
from standalone import attach, source_height, source_format, quality_label, LONG_SECONDS
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
import uvicorn
import math
import layouts
from layouts import CATALOG, geometry, render_graph, text_positions, output_settings
import captions
from captions import transcribe, large_v3, write as write_captions, ANIMS, ascii_fold, collapse_repeats
from translit import DEVA as DEVA_RX
import glossary
import styling
import brands
import hooks
import curation
import clip_effects
import facecam_detect
ROOT=Path(__file__).resolve().parent
DATA=Path(os.environ.get('NEONCLIPPING_DATA_DIR',str(ROOT/'data'))).resolve();DATA.mkdir(parents=True,exist_ok=True)
@asynccontextmanager
async def lifespan(application):
 try:yield
 finally:
  application.processing_queue.close()
  try:
   import share
   share.stop_tunnel()
  except Exception:pass

app=FastAPI(lifespan=lifespan)
state={}
import watchdog;watchdog.start(state,report.log_error)      # flags a job that has not moved for 15 minutes and logs where it waits
def probe(p):
 r=subprocess.run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(p)],capture_output=True,text=True,check=True)
 j=json.loads(r.stdout);v=next(x for x in j['streams'] if x['codec_type']=='video')
 return {'w':v['width'],'h':v['height'],'duration':float(j['format']['duration'])}
@app.get('/')
def home():return HTMLResponse((ROOT/'index.html').read_text(encoding='utf-8'))
attach(app,DATA,state,probe)
@app.get('/layouts')
def native_layouts(top:float=.32,aspect:str='vertical',resolution:int=1080):
 try:
  width,height,_=output_settings({'aspect':aspect,'resolution':resolution})
  return [{'id':key,'name':name,'description':description,**geometry(key,top,width,height),**text_positions(key,top,width=width,height=height)} for key,name,description in CATALOG]
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
@app.get('/cover/{id}')
def cover_image(id:str):
 """JPEG cover (a frame plus the clip title) for a finished clip."""
 if not id.isalnum():raise HTTPException(404)
 import cover
 from reedit import latest_file,read_record
 try:
  file=latest_file(DATA,id);settings=read_record(DATA,file)['settings']
  path=cover.make(DATA,file,str(settings.get('title') or ''),str(settings.get('hook') or ''),cover.hook_until(settings))
 except HTTPException:raise
 except Exception as e:raise HTTPException(404,'No cover for this clip: '+str(e)[-120:])
 return FileResponse(path,media_type='image/jpeg')
@app.get('/assets/{name}')
def assets(name:str):
 if name not in ('app.js','style.css','extras.js','transcripts.js','vision.js','report.js','studio.js','composer.js','composer.css','sidebar.js','library.js','right-bar.js','right-bar.css','editor.js','editor.css','capdraw.js','modes.js','modes.css','campaigns.js','campaigns.css','youtube-feed.js','youtube-feed.css','i18n.js'):raise HTTPException(404)
 return FileResponse(ROOT/name)
@app.get('/languages')
def list_languages():
 return {'special':languages.SPECIAL,'base':list(languages.BASE),'more':[{'code':c,'spoken':s,'english':e} for c,s,e in languages.MORE]}
@app.get('/text/{id}/{kind}')
def text_file(id:str,kind:str):
 if not id.isalnum() or kind not in ('srt','ass','vtt'):raise HTTPException(404)
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
    st_=j.get('settings',{});sc_=st_.get('viral_score')
    if sc_ is None and isinstance(st_.get('features'),dict):      # older clips: rebuild the score from the saved features
     try:
      import learn;wt_=st_.get('weights_used') if isinstance(st_.get('weights_used'),dict) else learn.DEFAULT
      sc_=min(99,round(100*learn.score(st_['features'],{k:float(wt_.get(k,learn.DEFAULT[k])) for k in learn.FEATURES})))
     except Exception:sc_=None
    records.append({'score':sc_,'score_parts':st_.get('viral_parts') or {},'id':f.stem,'title':j.get('settings',{}).get('title') or 'NeonClipping clip','created':f.stat().st_mtime,'meta':result.get('meta',{}),'settings':j.get('settings',{}),'srt':bool(result.get('srt')) and (DATA/(f.stem+'.srt')).exists(),**app.reedit_metadata(f.stem,j,groups)})
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
 state[job]={'status':'running','kind':'transcribe','message':'Starting local captions'}
 language=b.get('language') or None
 if not languages.valid(language):raise HTTPException(400,'Choose Auto, Hinglish or a language from the list.')
 def work():
  try:
   result=transcribe(src,start,end,DATA,lambda msg:state[job].update(message=msg),language)
   state[job]={'status':'done',**result,'source_id':id,'start':start,'end':end}
  except Exception as e:state[job]={'status':'error','error':'Caption generation failed: '+str(e)[-500:]}
 threading.Thread(target=work,daemon=True).start();return {'job':job}

@app.post('/export')
def export(b:dict):
 return start_export(b)

def _run_ffmpeg_export(cmd,cwd,dur,on_progress=None):
 """Run an FFmpeg export command with live `-progress pipe:1` parsing when duration is known."""
 args=cmd[:4]+['-progress','pipe:1','-nostats']+cmd[4:]
 proc=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1,cwd=str(cwd))
 err_chunks=[]
 def _drain_err():
  try:err_chunks.append(proc.stderr.read() or '')
  except Exception:pass
 err_thread=threading.Thread(target=_drain_err,daemon=True);err_thread.start()
 last_p=-1.0
 try:
  if proc.stdout:
   for line in proc.stdout:
    line=line.strip()
    if on_progress and dur>0 and line.startswith('out_time_us='):
     try:
      us=int(line.split('=',1)[1])
      if us>=0:
       p=min(.99,max(0.0,us/(dur*1_000_000.0)))
       if p-last_p>=.01:
        last_p=p;on_progress(p)
     except ValueError:pass
    elif line=='progress=end' and on_progress:
     on_progress(1.0)
 finally:
  rc=proc.wait();err_thread.join(timeout=2)
  if proc.stdout:proc.stdout.close()
  if proc.stderr:proc.stderr.close()
 return rc,''.join(err_chunks)

def start_export(b,job=None,auto_source='export'):
 id,src,m,start,end=source_range(b)
 layout=b.get('layout','stack')
 if layout not in {x[0] for x in CATALOG}:raise HTTPException(400,'Choose a valid layout.')
 style=b.get('caption_style',captions.DEFAULT_STYLE)
 if style not in captions.STYLE_NAMES:raise HTTPException(400,'Choose a valid caption style.')
 if (b.get('caption_anim') or 'highlight') not in ANIMS:raise HTTPException(400,'Choose a valid caption animation.')
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
 try:width,height,fps=output_settings(b)
 except (ValueError,TypeError,OverflowError) as e:raise HTTPException(400,str(e))
 try:censor_mode,censor_terms=clip_effects.settings(b);effect_cues=clip_effects.cues(b,end-start)
 except ValueError as e:raise HTTPException(400,str(e))
 camera_layer=next((layer for layer in geometry(layout,top,width,height)['layers'] if layer['source']=='cam'),None)
 if censor_terms and censor_mode in ('bar','blur') and (not camera_layer or b.get('template','none') not in ('none','')):
  raise HTTPException(400,'Choose a facecam layout without a social-card template for that censorship effect.')
 if (b.get('captions') or censor_mode!='off') and 'words' in b:
  try:b={**b,'words':subtitles.validate_words(b['words'],end-start)}
  except (ValueError,KeyError,TypeError,OverflowError) as e:raise HTTPException(400,str(e))
 import camfx
 try:cam_fx=camfx.filter(b)
 except (ValueError,TypeError,OverflowError) as e:raise HTTPException(400,str(e))
 graph=render_graph(layout,rects,top,width,height,cam_fx)
 try:brands.appearance(b)
 except (ValueError,TypeError,OverflowError) as e:raise HTTPException(400,str(e))
 try:hooks.settings(b)
 except (ValueError,TypeError,OverflowError) as e:raise HTTPException(400,str(e))
 try:plan=styling.plan(b,DATA)
 except ValueError as e:raise HTTPException(400,str(e))
 is_internal=bool(auto_source is None or b.get('batch_id'))
 job=job or uuid.uuid4().hex;out=DATA/(job+'.mp4')
 state[job]={'status':'running','kind':'export','internal':is_internal,'message':'Preparing export','progress':0.0}
 if b.get('batch_id'):state[job]['parent_job']=b['batch_id']
 def work():
  try:
   words=[]
   if b.get('captions',False) or censor_mode!='off' and censor_terms:
    if isinstance(b.get('words'),list):
     for word in b['words']:
      a=float(word['start']);z=float(word['end']);text=str(word['text'])[:100]
      if math.isfinite(a) and math.isfinite(z) and 0<=a<z<=end-start+.1:words.append({'start':a,'end':z,'text':text})
    else:words=transcribe(src,start,end,DATA,lambda msg:state[job].update(message=msg),b.get('language') or None)['words']
   dur=end-start;g2=graph
   placement=text_positions(layout,top,position,width,height);hook_y=placement['hook_y'];caption_pos=placement['caption_y'];hook_text=str(b.get('hook',''))
   fixes=glossary.entries()         # your words list (names, English words said in a Hindi accent): before and after Hinglish
   words=glossary.fix_words(words,fixes);hook_text=glossary.fix_text(hook_text,fixes)
   if b.get('language')!='hi':      # Hindi is always written in Roman letters (Hinglish) unless हिंदी was picked on purpose
    from translit import roman_text
    words=[dict(w,text=roman_text(w['text'])) for w in words];words=[w for w in words if w['text'].strip()];hook_text=roman_text(hook_text)
    words=glossary.fix_words(words,fixes);hook_text=glossary.fix_text(hook_text,fixes)
   saved_text={k:glossary.fix_text(roman_text(glossary.fix_text(str(b.get(k) or ''),fixes)) if b.get('language')!='hi' else glossary.fix_text(str(b.get(k) or ''),fixes),fixes) for k in ('hook','title','post_caption') if b.get(k)}
   masked,spans=clip_effects.masked_words(words,censor_terms,dur) if censor_mode!='off' else (words,[])
   visual=clip_effects.video_filter(censor_mode,spans,camera_layer)
   if visual:g2=g2.replace('[base]','[effect_input]')+';'+visual
   if plan:plan.data=DATA;plan.job=job;g2=plan.graph(g2,src,width,height,dur)
   if plan and plan.template!='none':caption_pos=plan.template_caption_y;hook_text=''
   if b.get('loop_end') is True and dur>1:
    original,end_tag=g2.rsplit('[base]',1)
    g2=original+'[effect_input]'+end_tag+';'+clip_effects.loop_filter(dur,fps)
   if effect_cues:
    flash=clip_effects.timed_flash(effect_cues)
    if flash:
     original,end_tag=g2.rsplit('[base]',1)
     g2=original+'[effect_input]'+end_tag+';'+flash
   if b.get('clip_progress') is True:
    original,end_tag=g2.rsplit('[base]',1)
    g2=original+'[effect_input]'+end_tag+';'+clip_effects.progress_filter(width,height,dur,fps)
   visible_words=masked if b.get('captions') else []
   ass,srt=write_captions(visible_words,style,DATA,job,hook_text,caption_pos,hook_y,width,height,b.get('caption_anim') or 'highlight',b)
   if visible_words:
    (DATA/(job+'.vtt')).write_text(subtitles.write_track(subtitles.parse_track((DATA/srt).read_text(encoding='utf-8'),allow_overlap=True),'vtt',allow_overlap=True),encoding='utf-8')
   if plan:styling.append_ass(DATA/ass,plan,dur)
   fc=g2+f';[base]ass=filename={ass}[v]'
   audio_source='[0:a]'
   has_audio=(plan.has_audio if plan else styling.source_info(src)[1]) if spans or effect_cues else False
   if spans and has_audio:
    fc+=';'+clip_effects.audio_filter(spans,dur,censor_mode)
    audio_source='[censored]'
   cue_audio=clip_effects.timed_audio(effect_cues,dur,audio_source,has_audio)
   if cue_audio:
    fc+=';'+cue_audio
    audio_source='[editor_mix]'
   af,amap=plan.audio(dur,audio_source) if plan else (None,None)
   if af:fc+=';'+af
   if not amap and audio_source!='[0:a]':amap=audio_source
   vmap='[v]';fade_af=None
   if hooks.fade_on(b) and dur>1.2:
    fc+=f';[v]fade=t=in:st=0:d=0.25,fade=t=out:st={max(0,dur-0.3):.2f}:d=0.3[vfade]';vmap='[vfade]'
    if not af:fade_af=f'afade=t=in:st=0:d=0.25,afade=t=out:st={max(0,dur-0.3):.2f}:d=0.3'
   voice_af=None
   try:
    vol=float(b.get('voice_volume',1))
    if vol!=1 and 0<=vol<=2:voice_af='volume=%.2f'%vol
   except (TypeError,ValueError):pass
   audio_filters=','.join(x for x in (voice_af,fade_af) if x)
   if audio_filters and amap:
    fc+=f';{amap}{audio_filters}[audio_finish]';amap='[audio_finish]';audio_filters=''
   state[job].update(message='Rendering vertical clip with '+style+' captions' if visible_words else 'Rendering vertical clip',progress=0.0)
   base=['ffmpeg','-y','-v','error','-ss',str(start),'-t',str(end-start),'-i',str(src),*(plan.inputs if plan else []),'-filter_complex',fc,'-map',vmap,'-map',amap or '0:a?',*(['-af',audio_filters] if audio_filters else []),'-t',str(dur),'-c:a','aac','-b:a','160k','-movflags','+faststart']
   if fps:base+=['-r',str(fps),'-fps_mode','cfr']
   preset=os.environ.get('NEONCLIPPING_X264_PRESET') or ('veryfast' if os.environ.get('NEONCLIPPING_CPU')=='1' else 'fast')
   def _on_prog(p):
    row=state.get(job)
    if row and row.get('status')=='running':row['progress']=round(p,3)
   rc,err=1,''
   for encoder in encoders.h264(cq=20,x264_preset=preset,nv_preset='p5'):
    # NVIDIA: also decode the source on the GPU (4K VP9/AV1 on the CPU is what pinned it at 100%); retry on the CPU if that fails.
    for hw in ((['-hwaccel','auto'],[]) if encoder[1]!='libx264' and encoder[1]!='h264_videotoolbox' else ([],)):
     rc,err=_run_ffmpeg_export(base[:4]+hw+base[4:]+encoder+['-pix_fmt','yuv420p',str(out)],DATA,dur,_on_prog)
     if rc==0:break
    if rc==0:break
   if rc:raise RuntimeError(err[-900:])
   finished={'status':'done','kind':'export','internal':is_internal,'file':job,'meta':probe(out),'encoder':encoder[1],'caption_words':len(visible_words),'srt':f'/text/{job}/srt' if visible_words else None}
   (DATA/(job+'.json')).write_text(json.dumps({'source':id,'settings':{**b,**saved_text,'words':words},'result':finished},indent=2),encoding='utf-8')
   state[job]=finished
   if auto_source:
    import social as _social, automation as _automation
    clip_info={'file':job,'title':saved_text.get('title') or b.get('title') or 'NeonClipping clip','description':saved_text.get('post_caption') or b.get('post_caption') or '','hashtags':b.get('hashtags') or [],'score':b.get('viral_score'),'flags':_automation.check_clip([saved_text.get('title'),saved_text.get('hook'),saved_text.get('post_caption'),' '.join(str(w.get('text','')) for w in words)])}
    _social.auto_queue_clip(app,DATA,clip_info,source=auto_source)
  except Exception as e:
   import friendly;plain,original=friendly.explain(str(e)[-900:]);state[job]={'status':'error','kind':'export','internal':is_internal,'error':plain,'error_detail':original}
 threading.Thread(target=work,daemon=True).start();return {'job':job}
try:LIVE_AUTO_HOURS=max(.25,float(os.environ.get('NEONCLIPPING_LIVE_AUTO_HOURS','3')))   # unattended creator-watch sessions stop after this many hours
except ValueError:LIVE_AUTO_HOURS=3.0
PAD=15.0        # keep editable context around audio-first highlights; export still trims the selected range
FAST_OVER=600   # seconds: longer videos go audio-first, short ones are downloaded whole
def _yt(opts):
 return ytdl.YDL({'noplaylist':True,'quiet':True,'no_warnings':True,'socket_timeout':20,'retries':3,'fragment_retries':3,'concurrent_fragment_downloads':6,
                  'external_downloader_args':{'ffmpeg_i':['-rw_timeout','30000000']},**opts})      # FFmpeg gives up after 30 s without data instead of hanging
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

def post_text(c):
 """Ready-to-paste post text (1G): title, the AI's one-line description, hashtags."""
 parts=[c.get('title') or '',c.get('description') or '',' '.join('#'+t for t in (c.get('hashtags') or []))]
 return '\n\n'.join(p for p in parts if p.strip())[:2200]

def axes(f):
 """Four readable 0-100 axes from the scoring features (None = not measured for this clip)."""
 def mean(keys):
  v=[f[k] for k in keys if f.get(k) is not None]
  return round(100*sum(v)/len(v)) if v else None
 return {'energy':mean(('loud','shout')),'action':mean(('motion','flash','strobe')),'words':mean(('words',)),'ai':mean(('llm',)),'chat':mean(('chat',))}

def ai_found(moments,yt_words,duration):
 """Candidates built from moments the user pasted from a chatbot (see aiparts.py) instead of the local finder."""
 import captions_yt,thought
 out=[]
 for m in moments:
  try:s=float(m['start']);e=float(m['end'])
  except (KeyError,TypeError,ValueError):continue
  if not(math.isfinite(s) and math.isfinite(e)) or not 0<=s<e or s>=duration or e-s>180:continue
  e=min(e,duration)
  if m.get('snap') and yt_words:      # one time was given: start there, run the usual length, but finish the sentence
   ext=captions_yt.window(yt_words,s,min(duration,e+8))
   if ext:e=min(duration,s+thought.snap_end(ext,0,e-s,max(8,(e-s)*.6),min(180,(e-s)+8),duration-s))
  w=captions_yt.window(yt_words,s,e) if yt_words else None
  out.append({'start':s,'end':e,'score':50,'rank':.5,'title':str(m.get('title') or '')[:90],'hook':str(m.get('hook') or '')[:90],'transcript':' '.join(str(x['text']) for x in w) if w else '','words':w or None,'features':{'llm':.85},'reason':'The time you asked for' if 'snap' in m else 'Picked from your AI answer','language':None})
 if not out:raise RuntimeError('None of the pasted moments fit inside this video.')
 return out,('Your time' if any('snap' in m for m in moments) else 'AI answer')

@app.post('/make')
def make(b:dict):
 return start_make(b)

def start_make(b, previous=None):
 """One click. Short video: download, smart highlights, export. Long video (PeakCut-style): download AUDIO only, pick moments from
 audio + transcript, then fetch just those video sections. Clips stream into state[job]['clips']."""
 url,src0=app.neon['new_source'](b);save=app.neon['save']
 import storage      # disk almost full is the commonest silent failure: free old partial downloads first, then say so plainly
 free_=shutil.disk_usage(DATA).free
 if free_<15*1024**3:
  try:storage.apply(DATA,'temp')      # old .part files, leftover audio and preview folders only; never clips or sources
  except Exception:pass
  free_=shutil.disk_usage(DATA).free
 if free_<2*1024**3:raise HTTPException(507,'Your disk is almost full (%.1f GB free). Open Storage in the left sidebar and press the clean-up buttons, then press Make clips again. Disk bhar gayi hai: left mein Storage kholo aur clean-up dabao.'%(free_/1024**3))
 try:
  count=max(1,min(12,int(b.get('count',4))));raw_max=float(b.get('max_len',b.get('length',60)));raw_min=float(b.get('min_len',30))
  if not (math.isfinite(raw_max) and math.isfinite(raw_min)):raise ValueError()
  max_len=max(10,min(180,raw_max));min_len=max(5,min(max_len,raw_min))
 except (TypeError,ValueError,OverflowError):raise HTTPException(400,'Choose a valid clip count and length range.')
 if raw_min>raw_max:raise HTTPException(400,'Minimum clip length is longer than the maximum. Make the minimum smaller or the maximum bigger.')
 moments=b.get('moments')
 if moments is not None:
  if not isinstance(moments,list) or not 1<=len(moments)<=40 or not all(isinstance(m,dict) for m in moments):raise HTTPException(400,'Moments must be a list of 1 to 40 items with start and end.')
  count=min(24,len(moments))
 import modes
 flags=modes.resolve(b.get('mode'),b.get('features'))      # Fast / Balanced / Best + the 'What runs' tiles
 mode='deep' if flags['deep_scan'] else 'fast'
 src_h=source_height(b.get('source_height'))     # how sharp the downloaded source is: 1080p by default, 4K or 720p on request
 profile=b.get('moment_profile','balanced')
 if profile not in curation.PROFILES:raise HTTPException(400,'Choose Balanced, Action or Dialogue moments.')
 try:focus_brief,include_phrases,exclude_phrases=curation.focus_settings(b)
 except ValueError as error:raise HTTPException(400,str(error))
 exact_time=False;part_window=None
 if not moments:      # a time given on its own (focus box) or in 'Only a part of the video' (From/To) means THAT clip, not a hint
  import intent as _intent
  try:fs,ts=float(b.get('from_s')),float(b.get('to_s'))
  except (TypeError,ValueError):fs=ts=None
  asked=[]
  if fs is not None and ts is not None and math.isfinite(fs) and math.isfinite(ts) and 0<=fs<ts:
   if ts-fs<=180:asked=[{'start':fs,'end':ts,'snap':False}]
   else:part_window=(fs,ts)      # a longer part: the finder works inside it
  asked=asked or _intent.explicit(focus_brief,min_len,max_len)
  if asked:moments=asked;count=min(24,len(moments));exact_time=True
 if not moments:
  from intent import requested_count
  count=requested_count(focus_brief,count)
 acc='best' if b.get('accurate')=='best' else 'fast'     # the turbo/"accurate" local model was removed: its captions were worse than YouTube's. Only Best Hindi (large-v3) uses a local model on purpose.
 layout=b.get('layout','blur');style=b.get('caption_style',captions.DEFAULT_STYLE);language=b.get('language') or None
 if not languages.valid(language):raise HTTPException(400,'Choose Auto, Hinglish or a language from the list.')
 from translit import to_hinglish
 top_h=b.get('top');cam=b.get('cam') or {'x':0,'y':0,'w':.25,'h':.3};game=b.get('game') or {'x':.25,'y':0,'w':.75,'h':1}
 job=uuid.uuid4().hex;save(job,{'id':job,'status':'running','stage':'Starting','phase':'source','progress':0,'clips':[],'source':{'url':url,'id':str(b.get('id') or '')}})
 checkpoint_path=DATA/(job+'.resume.json')
 checkpoint=dict(previous or {},request=b)
 def persist():
  staged=checkpoint_path.with_suffix('.tmp')
  staged.write_text(json.dumps(checkpoint),encoding='utf-8')
  staged.replace(checkpoint_path)
 persist()
 def work():
  began=time.monotonic()
  try:
   from smart import find
   import games
   def detect_game():
    try:up=(info.get('channel') or info.get('uploader') or '') if url else ''
    except NameError:up=''
    return games.detect(b.get('game_name') if isinstance(b.get('game_name'),str) else '',title,up,'' if url else getattr(src0,'name','')) if flags['game_aware'] else (None,[])
   fast=False;title='';yt_words=None;video_lang='';heat=None;chat_sig=None;chat_ready=lambda:None
   cached=previous and previous.get('plan')
   completed=previous.get('completed',{}) if cached else {}
   if cached:
    fast=cached['fast'];title=cached['title'];video_lang=cached['language']
    found=cached['found'];engine=cached['engine'];sid=cached['sid'];p=DATA/cached['media']
    uploader=cached['uploader']
    game_name=cached.get('game_name')
    save(job,{'engine':engine,'stage':'Resuming saved moments','phase':'prepare','candidates':len(found)})
   elif 'source_info' in checkpoint:
    src_info=checkpoint['source_info']
    fast=src_info['fast'];video_lang=src_info['language'];title=src_info['title'];yt_words=src_info['words'];heat=src_info.get('heatmap')
    info={'uploader':src_info['uploader']}
   elif url:
    save(job,{'stage':'Reading video info','progress':.01})
    import prefetch      # Get preview may already have fetched the info and YouTube captions while settings were chosen
    info,ready_words=prefetch.get(url)
    if not info:
     with _yt({'skip_download':True}) as y:info=y.extract_info(url,download=False)
    if info.get('is_live') or info.get('live_status') in ('is_live','is_upcoming'):
     raise RuntimeError('This stream is live right now. Use the Live clipping panel to clip it while it is on, or wait until it ends and use Make clips on the finished video.')
    video_lang=str(info.get('language') or '')
    fast=float(info.get('duration') or 0)>FAST_OVER and not info.get('is_live') and (mode=='fast' or float(info.get('duration') or 0)>LONG_SECONDS);      # over 2 h: always audio-first, the whole file is never downloaded
    title=info.get('title') or ''
    try:
     from captions_yt import from_info
     yt_words=ready_words or from_info(info);save(job,{'transcript_source':'YouTube captions' if yt_words else 'speech model'})
    except Exception:yt_words=None
    import replay;heat=replay.from_info(info) if flags['most_replayed'] else None
    if flags['chat_replay'] and ('live_chat' in (info.get('subtitles') or {}) or 'twitch' in str(info.get('extractor','')).lower()):
     import chat_replay      # 3C: the finished stream's chat (text only), read in the background while the audio downloads
     chat_box={}
     def read_chat(info=info):
      rows=chat_replay.load(info,url,DATA)
      chat_box['sig']=chat_replay.signals(rows,float(info.get('duration') or 0)) if rows else None
      if rows:save(job,{'chat_messages':len(rows)})
     chat_thread=threading.Thread(target=read_chat,daemon=True);chat_thread.start()
     def chat_ready():
      save(job,{'stage':'Reading the stream chat (Fast waits up to 20 s)'})
      chat_thread.join(timeout=600 if b.get('mode') in ('balanced','deep') else 20);return chat_box.get('sig')      # Fast never waits long for a big chat download
    else:chat_ready=lambda:None
    checkpoint['source_info']={'heatmap':heat,'fast':fast,'language':video_lang,'title':title,'words':yt_words,'uploader':info.get('channel') or info.get('uploader') or ''}
    persist()
   if not cached and not url and src0:
    try:
     import transcripts
     yt_words=transcripts.cached_source(DATA,src0,language)
     if yt_words:save(job,{'transcript_source':'Saved full-source transcript'})
    except (OSError,ValueError):pass
   save(job,{'fast_path':fast,'title':title})
   import learn, action
   import vision
   react=flags['face_reaction'] and b.get('mode')=='deep'
   face_model=vision.model() if flags['facecam_check'] or react else None
   from concurrent.futures import ThreadPoolExecutor as _TP
   W=curation.profile_weights(learn.load_weights(DATA),profile)
   performance=social.duration_preferences(DATA)
   import proxies as _proxies
   using_proxy=_proxies.config(DATA)['proxy_mode']!='off'
   def lowres_section(u,c):
    """A tiny 144p copy of just this candidate, only for looking at the action (motion, flashes, light strobes)."""
    from yt_dlp.utils import download_range_func
    name='lr_'+uuid.uuid4().hex
    with _yt({'format':'worst[ext=mp4]/bv*[height<=240][ext=mp4]/worst','outtmpl':str(DATA/(name+'.%(ext)s')),'merge_output_format':'mp4',
              'retries':1,'fragment_retries':1,'concurrent_fragment_downloads':1,'socket_timeout':12,
              'external_downloader_args':{'ffmpeg_i':['-rw_timeout','12000000']},
              'download_ranges':download_range_func(None,[(max(0,c['start']),c['end'])])}) as y:y.download([u])
    f=next(x for x in DATA.glob(name+'.*') if x.suffix not in ('.part','.ytdl'))
    return f,0.0
   def lowres_whole(u):
    """For up to ~45 min videos, fetching one tiny low-res file once avoids 8 slow range-seeks over a proxy."""
    name='lrw_'+uuid.uuid4().hex
    try:
     with _yt({'format':'worst[height<=240][ext=mp4]/worst[ext=mp4]/worst','outtmpl':str(DATA/(name+'.%(ext)s')),'merge_output_format':'mp4',
               'retries':1,'fragment_retries':1,'concurrent_fragment_downloads':2,'socket_timeout':12,'max_filesize':70*1024*1024}) as y:y.download([u])
     return next((x for x in DATA.glob(name+'.*') if x.suffix not in ('.part','.ytdl') and x.stat().st_size>1024),None)
    except Exception:
     for x in DATA.glob(name+'.*'):x.unlink(missing_ok=True)
     return None
   def choose(pool_clips,locate,deadline_s=None):
    """Look at the action in the best candidates, re-rank with the learned weights, keep `count`."""
    K=min(len(pool_clips),count*2)
    top=pool_clips[:K];save(job,{'stage':'Checking action in the best moments','progress':.5})
    prog_lock=threading.Lock();checked=[0]
    deadline=(time.monotonic()+deadline_s) if deadline_s else None
    def one(c):
     tmp=None
     try:
      if deadline and time.monotonic()>deadline:
       c['_act']=None;c['reason']=c.get('reason','')+' (action check skipped — slow download)';return
      f,off=locate(c)
      tmp=f if str(f).startswith(str(DATA)) and Path(f).name.startswith('lr_') else None
      c['_act']=action.analyze(f,off,c['end']-c['start'])
      if b.get('vision_review'):
       try:c['visual_review']=vision.review(f,off,c['end']-c['start'],DATA,lambda message:save(job,{'stage':message}))
       except Exception as error:c['visual_error']=str(error)[-160:]
     except Exception as e:c['_act']=None;c['reason']=c.get('reason','')+' (no action check)'
     finally:
      if tmp:Path(tmp).unlink(missing_ok=True)
      with prog_lock:
       checked[0]+=1
       save(job,{'stage':f'Checking action {checked[0]}/{len(top)}','progress':round(.5+.07*checked[0]/max(1,len(top)),3)})
    workers=2 if using_proxy else 4
    with _TP(max_workers=workers) as ex:list(ex.map(one,top))
    for c in top:
     if c.get('_act'):
      for key in ('motion','flash','strobe','cuts'):
       c['features'][key]=round(c['_act'][key],3)
     if c.get('visual_review'):
      try:
       import smart
       observations='\n'.join(frame['description'] for frame in c['visual_review']['frames'])
       judged=smart._judge(c['visual_review']['model'],(c.get('transcript') or '[No speech]')+'\n[Sampled visual observations; uncertain, do not infer unseen events]\n'+observations,focus_brief)
       old=c['features'].get('llm');c['features']['llm']=judged['score']/10 if old is None else .7*old+.3*judged['score']/10
       if focus_brief:c['focus_match']=judged['focus_match']
      except Exception as error:c['visual_error']=str(error)[-160:]
     current=curation.focus_rank(learn.score(c['features'],W),c.get('focus_match'))+performance.get(int((c['end']-c['start'])//15),0)+c.get('direction_boost',0)
     if c.get('head_to_head') is not None:current=.7*current+.3*c['head_to_head']
     c['rank']=max(0,min(1,current));c['score']=round(c['rank']*100)
     cues=[n for n,k,t in (('shouting','shout',.6),('loud jump','loud',.6),('exclamations','words',.5),('fast motion','motion',.7),('explosion/flash','flash',.5),('police-light flicker','strobe',.5)) if (c['features'].get(k) or 0)>=t]
     c['reason']=(('Cues: '+', '.join(cues)) if cues else 'Steady energy')+(f" · AI {c['llm']:g}/10" if c.get('llm') else '')
     if c.get('visual_review'):c['reason']+=' · 3 visual frames reviewed'
     elif c.get('visual_error'):c['reason']+=' · visual review unavailable; using transcript/activity'
     c.pop('_act',None)
    top.sort(key=lambda c:-c['rank'])
    return top[:count] if moments else curation.select(top,count,profile)
   sections=None
   if not cached and fast:
    def hook(d):
     t=d.get('total_bytes') or d.get('total_bytes_estimate')
     if t and d.get('status')=='downloading':save(job,{'stage':f"Downloading audio {d['downloaded_bytes']/1048576:.0f}/{t/1048576:.0f} MB",'progress':.02+.1*d['downloaded_bytes']/t})
    audio=checkpoint.get('audio')
    if audio and (DATA/audio).is_file():
     p=DATA/audio
    else:
     last_error=None
     for audio_format in ('ba[ext=m4a]/ba/worst','ba/b','worst'):
      for leftover in DATA.glob(job+'.audio.*'):leftover.unlink(missing_ok=True)       # an empty or partial file from the last try
      try:
       with _yt({'format':audio_format,'outtmpl':str(DATA/(job+'.audio.%(ext)s')),'progress_hooks':[hook]}) as y:y.download([url])
       got=[f for f in DATA.glob(job+'.audio.*') if f.suffix not in ('.part','.ytdl') and f.stat().st_size>1024]
       if got:last_error=None;break
       last_error=RuntimeError('The downloaded audio file is empty.')
      except Exception as e:last_error=e
     if last_error:raise last_error
     p=next(f for f in DATA.glob(job+'.audio.*') if f.suffix not in ('.part','.ytdl'))
     checkpoint['audio']=p.name
     persist()
    duration=_dur(p);sid=job
    save(job,{'meta':{'duration':duration},'stage':'Finding moments in audio','phase':'analyze','progress':.12})
    beat={'live':True,'seen':time.monotonic()}
    def scan_report(f,m):beat['seen']=time.monotonic();save(job,{'stage':m,'progress':.12+.4*f})
    def heartbeat():
     t0=time.monotonic()
     while beat['live']:
      time.sleep(4)
      if beat['live'] and time.monotonic()-beat['seen']>=4:save(job,{'stage':f'Finding moments in audio · working {int(time.monotonic()-t0)}s (long videos take a few minutes)'})
    threading.Thread(target=heartbeat,daemon=True).start()
    game_name,game_tags=detect_game();chat_sig=chat_ready()
    try:found,engine=ai_found(moments,yt_words,duration) if moments else find(p,duration,count,max_len,scan_report,language,DATA,min_len,False,yt_words,False,W,False,profile,focus_brief,include_phrases,exclude_phrases,game=game_name,heat=heat,chat=chat_sig,whole=flags['whole_pass'] or b.get('whole_pass') is True,rerank_on=flags['rerank'],fair=flags['fair_order'],quality=b.get('mode') in ('balanced','deep'),window=part_window)
    finally:beat['live']=False
    lr_whole=None
    if duration<=2700:
     save(job,{'stage':'Downloading low-res preview for action check','progress':.5})
     lr_whole=lowres_whole(url)
    try:
     found=choose(found,(lambda c:(lr_whole,c['start'])) if lr_whole else (lambda c:lowres_section(url,c)),deadline_s=(None if lr_whole else (90 if using_proxy else 180)))
    finally:
     if lr_whole:Path(lr_whole).unlink(missing_ok=True)
    if not found:
     checkpoint_path.unlink(missing_ok=True)
     save(job,{'status':'done','stage':'No moments matched the transcript filters. Broaden the focus or required phrases.','progress':1,'clips':[],'elapsed_seconds':round(time.monotonic()-began,2)});return
    save(job,{'engine':engine+' (audio-first)','stage':'Fetching only the chosen sections','progress':.58,'candidates':len(found)})
   elif not cached:
    if url:
     save(job,{'stage':'Downloading source ('+quality_label(src_h)+')','progress':.02});sid,p=app.neon['download'](url,job,src_h)
    else:sid,p=src0.stem,src0
    meta=probe(p);duration=meta['duration'];save(job,{'source_id':sid,'meta':meta,'stage':'Finding moments','phase':'analyze','progress':.1})
    game_name,game_tags=detect_game();chat_sig=chat_ready()
    found,engine=ai_found(moments,yt_words,duration) if moments else find(p,duration,count,max_len,lambda f,m:save(job,{'stage':m,'progress':.1+.5*f}),language,DATA,min_len,True,yt_words,mode=='deep',W,False,profile,focus_brief,include_phrases,exclude_phrases,game=game_name,heat=heat,chat=chat_sig,whole=flags['whole_pass'] or b.get('whole_pass') is True,rerank_on=flags['rerank'],fair=flags['fair_order'],quality=b.get('mode') in ('balanced','deep'),window=part_window)
    found=choose(found,lambda c:(p,c['start']))
    if not found:
     checkpoint_path.unlink(missing_ok=True)
     save(job,{'status':'done','stage':'No moments matched the transcript filters. Broaden the focus or required phrases.','progress':1,'clips':[],'elapsed_seconds':round(time.monotonic()-began,2)});return
    save(job,{'engine':engine,'stage':'Rendering clips','progress':.6,'candidates':len(found)})
   if not cached:      # 1F: the game's own tags go first on every post, whatever the AI wrote
    for c in found:
     seen=set();c['hashtags']=[x for x in list(game_tags)+list(c.get('hashtags') or []) if not (x.lower() in seen or seen.add(x.lower()))][:8]
    if b.get('mode')=='deep' and not moments and any(c.get('transcript') for c in found):
     import smart
     reviewer=smart._model(True)
     if reviewer:
      save(job,{'stage':'Reviewing finalists for complete moments'})
      smart.review_finalists(found,reviewer)
   if game_name:save(job,{'game':game_name})
   dropped_frozen=[]
   used_titles_=set()
   done=[];cam_use,game_use,cam_checked,layout_use=cam,game,not b.get('cam_auto',True),layout       # facecam search is on unless switched off
   if not cached:
    uploader=str((info.get('channel') or info.get('uploader') or '')) if url else ''
   checkpoint.update({'request':b,'plan':{'fast':fast,'title':title,'language':video_lang,'found':found,'engine':engine,
                                  'sid':sid,'media':p.name,'uploader':uploader,'game_name':game_name},'completed':completed})
   if cached and previous.get('framing'):
    cam_use,game_use,layout_use=previous['framing']
    cam_checked=True
    checkpoint['framing']=previous['framing']
   persist()
   def finished(index):
    item=completed.get(str(index))
    return item and (DATA/(item['file']+'.mp4')).is_file() and (DATA/(item['file']+'.json')).is_file()
   if fast:
    from concurrent.futures import ThreadPoolExecutor
    from yt_dlp.utils import download_range_func
    def section(i,c):
     name=uuid.uuid4().hex
     for attempt in range(3):     # an FFmpeg crash on one section (seen on some FFmpeg 9.1 builds) must not lose the whole video
      try:
       with _yt({'format':(source_format(src_h) if attempt<2 else 'b[height<=720][ext=mp4]/b[height<=720]/b'),'merge_output_format':'mp4','outtmpl':str(DATA/(name+'.%(ext)s')),
                 'external_downloader_args':{'ffmpeg_i':['-rw_timeout','15000000']},
                 'download_ranges':download_range_func(None,[(max(0,c['start']-PAD),c['end']+PAD)])}) as y:y.download([url])
       return name
      except Exception:
       if attempt==2:raise
       time.sleep(3*(attempt+1))
    pool=ThreadPoolExecutor(max_workers=2 if using_proxy else 3);sections=[pool.submit(section,i,c) if not finished(i) else None for i,c in enumerate(found)]
   for i,c in enumerate(found):
    if finished(i):
     used_titles_.add(str(completed[str(i)].get('title') or '').strip().casefold())
     done.append(completed[str(i)]);save(job,{'clips':list(done)})
     continue
    save(job,{'stage':(f'Fetching clip section {i+1}/{len(found)}' if sections else f'Preparing clip {i+1}/{len(found)}'),'phase':'prepare','clip_index':i+1})
    if (not moments or exact_time) and c.get('transcript') and b.get('hook_enabled') is not False and not (c.get('hook') and c.get('hook_evidence')):      # the judge's hook is already backed by a quote: no second AI call
     try:
      import smart
      model=smart._model(b.get('mode') in ('balanced','deep'))
      if model:
       save(job,{'stage':f'Writing opening heading {i+1}/{len(found)}'})
       c['hook']=smart._heading(model,c['transcript'])
     except Exception:pass
    if sections:
     sid2=sections[i].result();real=section_start(p,DATA/(sid2+'.mp4'),max(0,c['start']-PAD));start=max(0,c['start']-real);end=min(_dur(DATA/(sid2+'.mp4')),start+c['end']-c['start']);words=c.get('words')
    else:sid2=sid;real=0;start=c['start'];end=c['end'];words=c.get('words')
    if not moments and words:
     from scene_edges import align
     from reedit import trim_words
     aligned_start,aligned_end=align(DATA/(sid2+'.mp4'),start,end,words,min_len)
     if aligned_start>start+.075 or aligned_end<end-.075:
      c['words']=trim_words(words,aligned_start-start,aligned_end-aligned_start)
      start,end=aligned_start,aligned_end
      c['start']=round(start+real,3);c['end']=round(end+real,3)
      c['reason']=c.get('reason','')+' · aligned with scene cut'
    if flags['skip_frozen']:      # 1E: ad break, BRB slate or frozen screen: not worth a clip
     import frozen
     still,share=frozen.is_frozen(DATA/(sid2+'.mp4'),start,end-start)
     if still:
      dropped_frozen.append({'start':c['start'],'end':c['end'],'title':c.get('title') or 'Skipped moment','frozen_share':round(share,2)});save(job,{'dropped_frozen':dropped_frozen,'stage':f'Skipped clip {i+1}: the picture is frozen (ad, BRB or loading screen)'})
      continue
    if not cam_checked:
     cam_checked=True
     try:
      fc=facecam_detect.detect(DATA/(sid2+'.mp4'))
      info={k:fc.get(k) for k in ('found','confidence','method','cam','reason')}
      if face_model and flags['facecam_check'] and fc.get('found'):
       try:
        save(job,{'stage':'Checking the facecam in one frame locally'})
        check=vision.inspect_facecam(DATA/(sid2+'.mp4'),start+(end-start)*.45,fc['cam'],face_model)
        info['vision']=check['facecam']
        if check['facecam']=='no' and (fc.get('confidence') or 0)<.7:
         fc['found']=info['found']=False
         info['reason']='The local check did not confirm a facecam.'
       except Exception:info['vision']='unavailable'
      if fc.get('found'):cam_use,game_use=fc['cam'],fc['game']
      elif layouts.needs_cam(layout) and layouts.is_default_cam(cam_use):
       layout_use='blur';info['layout_fallback']='blur'          # no webcam found and no boxes drawn: do not show an empty or wrong box
      save(job,{'facecam':info})
     except Exception as e:save(job,{'facecam':{'found':False,'reason':'detection failed: '+str(e)[:80]}})
    if cam_checked and 'framing' not in checkpoint:
     checkpoint['framing']=[cam_use,game_use,layout_use]
     persist()
    if react and face_model and layouts.needs_cam(layout_use):
     try:
      save(job,{'stage':f'Checking facecam reaction {i+1}/{len(found)} locally'})
      reaction=vision.inspect_facecam(DATA/(sid2+'.mp4'),start+(end-start)*.45,cam_use,face_model,True)['reaction']
      if reaction in ('laugh','surprise'):
       c['reason']=c.get('reason','')+' · visible '+reaction
       c['score']=min(99,c['score']+4)
     except Exception:pass
    ttl_=str(c.get('title') or '').strip().casefold()      # small models give every clip the same title: use the clip's own words instead
    if not ttl_ or ttl_ in used_titles_:c['title']=(' '.join(str(c.get('hook') or c.get('transcript') or '').replace('?!','').split()[:7]).strip() or 'Clip %d'%(i+1))
    used_titles_.add(str(c.get('title')).strip().casefold())
    lang=language or ('hinglish' if (video_lang.startswith('hi') or c.get('language')=='hi') else None)
    if language!='hi':
     from translit import roman_text
     c['hook']=roman_text(c.get('hook',''));c['title']=glossary.fix_text(roman_text(glossary.fix_text(c.get('title',''))))
     c['highlight_words']=[roman_text(w) for w in c.get('highlight_words') or []];c['description']=roman_text(c.get('description',''))
     if c.get('words') and any(DEVA_RX.search(str(w.get('text',''))) for w in c['words']):lang='hinglish'     # YouTube gave Hindi script although another language was picked
    body={'id':sid2,'start':start,'end':end,'layout':layout_use,'top':(top_h if isinstance(top_h,(int,float)) and .2<=top_h<=.5 else .32),'captions':True,'caption_style':style,'language':language,'hook':(' '.join(to_hinglish(w) for w in c.get('hook','').split()) if lang=='hinglish' else c.get('hook','')),
          'aspect':b.get('aspect','vertical'),'resolution':b.get('resolution',1080),'fps':b.get('fps',0),'title':c.get('title',''),'viral_score':min(99,c.get('score') or 0),'viral_parts':c.get('parts') or {},'post_caption':post_text(c),'punch_words':c.get('highlight_words') or [],'hashtags':c.get('hashtags') or [],'description':c.get('description',''),'batch_id':job,'source_url':url,'cam':cam_use,'game':game_use,'features':c.get('features'),'weights_used':W,'moment_profile':profile,'focus_brief':focus_brief,'focus_match':c.get('focus_match'),'visual_review':c.get('visual_review')}
    if game_name:body['game_name']=game_name
    full_words=yt_words or checkpoint.get('source_info',{}).get('words') or []
    context_words=[]
    for w in full_words:
     a=float(w['start'])-real;z=float(w['end'])-real
     if z<max(0,start-PAD) or a>end+PAD or a<end and z>start:continue
     text=glossary.fix_text(w['text'])
     if lang=='hinglish':text=ascii_fold(to_hinglish(text)).strip()
     if text:context_words.append({'start':max(0,a),'end':z,'text':text})
    if context_words:body['context_words']=context_words
    for k in styling.KEYS+brands.KEYS+hooks.KEYS:
     if b.get(k) not in (None,''):body[k]=b[k]
    if b.get('credit_auto') and uploader and not body.get('credit'):body['credit']='Clip: '+uploader[:40]
    if acc!='fast' or not c.get('words'):
     # local speech model: only when you ask for Accurate / Best, or the video has no YouTube captions (local files, Twitch)
     save(job,{'stage':f'Accurate captions {i+1}/{len(found)}'})
     body['words']=transcribe(DATA/(sid2+'.mp4'),start,end,DATA,(lambda m,i=i:save(job,{'stage':f'Accurate captions {i+1}/{len(found)} · {m}'})),lang,(large_v3() if acc=='best' else None))['words']
    else:
     ws=c['words']       # YouTube's own captions: better than a local model on game audio, and no waiting
     if lang=='hinglish':
      ws=collapse_repeats([dict(w,text=ascii_fold(to_hinglish(w['text'])).strip()) for w in ws if str(w.get('text','')).strip()])
      ws=[w for w in ws if w['text']]
     body['words']=ws
     save(job,{'caption_source':'YouTube captions' if url else 'Saved full-source transcript'})
    body['words']=subtitles.clean_words(body.get('words'),end-start)
    if (b.get('ai_caption_fix') is True or (flags['caption_fix'] and b.get('ai_caption_fix') is not False)) and language!='hi' and body['words'] and not any(DEVA_RX.search(str(w.get('text',''))) for w in body['words']):
     import capfix      # 1A: AI fixes spelling, numbers, names and punctuation word by word (timings kept); skipped when no AI model is set up
     save(job,{'stage':f'Fixing caption spelling {i+1}/{len(found)}'})
     body['words'],changed=capfix.fix(body['words'],c.get('title') or title)
     if changed:c['caption_fixes']=changed
    render_ids=checkpoint.setdefault('render_ids',{})
    ej=render_ids.get(str(i))
    if not ej:
     ej=uuid.uuid4().hex;render_ids[str(i)]=ej;persist()
    output_record=DATA/(ej+'.json')
    r=None
    if output_record.is_file() and (DATA/(ej+'.mp4')).is_file():
     saved=json.loads(output_record.read_text(encoding='utf-8'))
     if saved.get('result',{}).get('status')=='done':r=saved['result']
    if r is None:
     save(job,{'stage':f'Exporting clip {i+1}/{len(found)}','phase':'render','progress':round(.6+.4*i/len(found),3)})
     ej=start_export(body,ej,auto_source=None)['job']
     last_sub=-1
     while state.get(ej,{}).get('status')=='running':
      sub_p=float(state.get(ej,{}).get('progress') or 0)
      pct=min(99,max(0,int(sub_p*100)))
      if pct>=last_sub+2 or (pct>0 and last_sub<0):
       last_sub=pct
       save(job,{'stage':f'Exporting clip {i+1}/{len(found)} · {pct}%','progress':round(.6+.4*(i+min(.99,sub_p))/len(found),3)})
      time.sleep(.7)
     r=state[ej]
    import automation as _automation, social as _social      # 5H: words-to-avoid check, webhook, and optional auto-upload
    flags_=_automation.check_clip([c.get('title'),c.get('hook'),c.get('description'),' '.join(str(w.get('text','')) for w in (body.get('words') or []))])
    done.append({'flags':flags_,'caption_fixes':c.get('caption_fixes',0),'hashtags':c.get('hashtags') or [],'description':c.get('description',''),'punch_words':c.get('highlight_words') or [],'parts':c.get('parts') or {},'viral':min(99,c['score']),'axes':axes(c.get('features') or {}),'file':ej,'start':c['start'],'end':c['end'],'title':c.get('title') or 'Clip %d'%(i+1),'hook':c.get('hook',''),'score':c['score'],'reason':c.get('reason',''),'review_reason':c.get('review_reason',''),
                 'error':r.get('error'),'srt':r.get('srt'),'visual_review':c.get('visual_review')})
    if r.get('status')=='done':
     completed[str(i)]=done[-1]
     persist()
     _automation.notify(DATA,done[-1])
     _social.auto_queue_clip(app,DATA,done[-1],source='make')
    save(job,{'clips':list(done),'stage':f'Rendered {i+1}/{len(found)}','progress':.6+.4*(i+1)/len(found)})
   if any(item.get('error') for item in done):
    raise RuntimeError('Some clips failed. Resume this batch to retry the missing clips.')
   checkpoint_path.unlink(missing_ok=True)
   for prev_id in checkpoint.get('_chain') or []:
    if isinstance(prev_id,str) and prev_id.isalnum():(DATA/(prev_id+'.resume.json')).unlink(missing_ok=True)
   done_key=_source_key(b)
   if done_key:
    for rf in DATA.glob('*.resume.json'):
     try:
      if _source_key(json.loads(rf.read_text(encoding='utf-8')).get('request'))==done_key:rf.unlink(missing_ok=True)
     except (OSError,ValueError):pass
   save(job,{'status':'done','stage':'Clips ready','phase':'complete','progress':1,'elapsed_seconds':round(time.monotonic()-began,1)})
  except Exception as e:      # plain words for the common failures (private video, no internet, disk full, FFmpeg missing...)
   import friendly;plain,original=friendly.explain(str(e)[-600:]);save(job,{'status':'error','error':plain,'error_detail':original})
 threading.Thread(target=work,daemon=True).start();return {'job':job}
LIVE={}

def live_render(sess,start,dur,why,chat_feature):
 """Cut the backdated window out of the growing recording, caption it, write a hook, export with the user's layout."""
 import learn,excite
 from translit import to_hinglish
 o=sess.opts;name=uuid.uuid4().hex;out=DATA/(name+'.mp4');T={};_t=time.time()
 def lap(k):
  nonlocal _t;T[k]=round(time.time()-_t,1);_t=time.time()
 for enc in encoders.h264(cq=21,x264_preset='veryfast',nv_preset='p4'):
  r=subprocess.run(['ffmpeg','-y','-v','error','-ss',f'{start:.2f}','-i',str(sess.rec),'-t',f'{dur:.2f}',*enc,'-c:a','aac','-b:a','160k',str(out)],capture_output=True,text=True)
  if r.returncode==0 and out.exists() and out.stat().st_size>10000:break
 else:raise RuntimeError('Could not cut the clip from the recording: '+r.stderr[-150:])
 real=_dur(out);lap('cut')
 lang=o.get('language') or None;want_caps=o.get('captions',True) is not False
 if want_caps:
  res=transcribe(out,0,real,DATA,lambda m:None,('hinglish' if lang=='hinglish' else lang),'base')
  words=res['words']
  if res.get('language')=='hi' and lang in (None,'hinglish'):
   words=[dict(w,text=to_hinglish(w['text'])) for w in words]
 else:words=[]
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
  rms,hf=_audio(out)[:2]
  if len(rms)>4:
   base=float(np.median(rms))+1e-4;loud=float(min(1.0,max(0.0,(float(np.percentile(rms,95))/base-1.0)/3.0)))
 except Exception:pass
 hm=o.get('hook_mode','ai');stream_title=str(sess.state.get('title') or '')
 if hm=='title' and stream_title:hook=stream_title[:70]
 elif hm=='custom' and o.get('hook_text'):hook=str(o['hook_text'])[:70]
 feats={'chat':chat_feature,'words':excite.window_score(words,real),'llm':llm,'loud':loud}
 W=learn.load_weights(DATA);viral=min(99,round(100*learn.score(feats,W)))
 body={'id':name,'start':0,'end':real,'layout':o.get('layout','blur'),'captions':want_caps,'caption_style':o.get('caption_style',captions.DEFAULT_STYLE),'language':None,'hook':hook,
       'aspect':o.get('aspect','vertical'),'resolution':o.get('resolution',1080),'fps':o.get('fps',0),'title':title,'post_caption':title,'cam':o['cam'],'game':o['game'],'top':o.get('top',.32),'words':words,'features':feats,'weights_used':W,'creator':o.get('creator')}
 for k in styling.KEYS+brands.KEYS+hooks.KEYS:
  if o.get(k) not in (None,''):body[k]=o[k]
 lap('score')
 ej=start_export(body,auto_source=None)['job']
 while state.get(ej,{}).get('status')=='running':time.sleep(.3)
 r=state[ej]
 if r.get('error'):raise RuntimeError(r['error'])
 lap('render')
 import automation as _auto, social as _social
 _live_flags=_auto.check_clip([title,hook,text])
 _social.auto_queue_clip(app,DATA,{'file':ej,'title':title,'hook':hook,'score':viral,'flags':_live_flags},source='live')
 return {'secs':T,'file':ej,'title':title,'hook':hook,'why':why,'viral':viral,'axes':axes(feats),'at':int(sess.now()),'reason':why,'start':round(start),'end':round(start+real)}

def start_live(target,opts,creator=None,before=24,after=14):
 """Start one live-clipping session (used by the Live panel and by the creator watcher). Only one runs at a time."""
 import live_session
 for s_ in LIVE.values():
  if s_.state['status'] in ('starting','recording'):raise RuntimeError('A live session is already running. Stop it first.')
 clip_every=live_session.clip_interval(opts.get('clip_every',0))
 sess=live_session.LiveSession(target,DATA,live_render,before,after)
 sess.creator=creator;sess.auto=bool(creator);sess.max_seconds=LIVE_AUTO_HOURS*3600 if creator else None
 sess.clip_every=clip_every
 sess.opts={'layout':opts.get('layout','blur'),'caption_style':opts.get('caption_style',captions.DEFAULT_STYLE),'language':opts.get('language') or None,
            'cam':opts.get('cam') or {'x':0,'y':0,'w':.25,'h':.3},'game':opts.get('game') or {'x':.25,'y':0,'w':.75,'h':1},
            'aspect':opts.get('aspect','vertical'),'resolution':opts.get('resolution',1080),'fps':opts.get('fps',0),'top':opts.get('top') if isinstance(opts.get('top'),(int,float)) else .32,'creator':creator,
            'captions':opts.get('captions',True) is not False,'hook_mode':opts.get('hook_mode') if opts.get('hook_mode') in ('ai','title','custom') else 'ai','hook_text':str(opts.get('hook_text') or '')[:70]}
 for k in styling.KEYS+brands.KEYS+hooks.KEYS:
  if opts.get(k) not in (None,''):sess.opts[k]=opts[k]
 LIVE[sess.id]=sess;sess.start();return sess.id

@app.post('/live/start')
def live_start(b:dict):
 import live_session
 try:target=live_session.parse_target(str(b.get('url','')))
 except ValueError as e:raise HTTPException(400,str(e))
 before=max(4,min(60,float(b.get('before',24))));after=max(2,min(40,float(b.get('after',14))))
 try:sid=start_live(target,b,None,before,after)
 except (RuntimeError,ValueError) as e:raise HTTPException(400,str(e))
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
def live_clip_now(lid:str,b:dict=None):
 if lid not in LIVE:raise HTTPException(404,'Live session not found.')
 try:secs=max(5,min(60,int((b or {}).get('seconds',30))))
 except (TypeError,ValueError):raise HTTPException(400,'seconds must be a number.')
 try:LIVE[lid].clip_now(secs)
 except RuntimeError as e:raise HTTPException(400,str(e))
 return {'ok':True}

@app.post('/live/{lid}/stop')
def live_stop(lid:str):
 if lid not in LIVE:raise HTTPException(404,'Live session not found.')
 LIVE[lid].stop();return {'ok':True}

@app.get('/supporters')
def supporters():
 """Names shown under 'Our supporters' (supporters.json). Only plain short text is served; add a person only with their OK."""
 try:raw=json.loads((ROOT/'supporters.json').read_text(encoding='utf-8')).get('supporters',[])
 except (OSError,ValueError,AttributeError):raw=[]
 out=[]
 for r in raw if isinstance(raw,list) else []:
  if not isinstance(r,dict):continue
  name=' '.join(str(r.get('name') or '').split())[:40]
  if not name:continue
  amount=' '.join(str(r.get('amount') or '').split())[:14]
  out.append({'name':name,'amount':amount})
 return {'supporters':out[:300]}

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
 try:return learn.record(DATA,file,rating,m['features'],{'layout':m.get('layout'),'style':m.get('caption_style')})
 except ValueError as error:raise HTTPException(400,str(error))

@app.get('/feedback/summary')
def feedback_summary():
 import learn
 return learn.refit(DATA)

resume_lock=threading.Lock()

@app.post('/make/{job}/restore/{index}')
def restore_frozen(job:str,index:int,body:dict):
 with resume_lock:
  batch=state.get(job,{})
  dropped=batch.get('dropped_frozen') or []
  if batch.get('status')!='done' or not 0<=index<len(dropped):
   raise HTTPException(404,'This skipped moment is unavailable.')
  source=batch.get('source') or {}
  if not source.get('url') and not source.get('id'):
   raise HTTPException(409,'The original source is unavailable.')
  existing=(batch.get('restored') or {}).get(str(index))
  if existing and state.get(existing,{}).get('status') in ('running','done'):
   return {'job':existing}
  moment=dropped[index]
  settings={key:body[key] for key in ('layout','caption_style','resolution','aspect','fps','language','top','cam','game') if key in body}
  settings.update(source,count=1,moments=[{'start':moment['start'],'end':moment['end'],'title':moment['title']}],features={'skip_frozen':False})
  child=start_make(settings)['job']
  restored=dict(batch.get('restored') or {})
  restored[str(index)]=child
  app.neon['save'](job,{'restored':restored})
  return {'job':child}

def _source_key(obj):
 if not isinstance(obj,dict):return ''
 url=str(obj.get('url') or '').strip()
 if url:
  m=re.search(r'(?:youtu\.be/|v=|/live/|/shorts/)([A-Za-z0-9_-]{11})',url)
  if m:return 'yt:'+m.group(1)
  return 'url:'+url.split('?')[0].rstrip('/').lower()
 sid=str(obj.get('id') or '').strip()
 return 'id:'+sid if sid else ''

def _active_make_jobs():
 return [(jid,row) for jid,row in list(state.items()) if row.get('status')=='running' and row.get('kind') not in ('export','transcribe') and ('phase' in row or 'clips' in row or 'source' in row)]

def _resolve_resume_chain(job):
 seen={job}
 record=state.get(job,{})
 while record.get('resumed_as') and record['resumed_as'] in state and record['resumed_as'] not in seen:
  next_job=record['resumed_as']
  seen.add(next_job)
  job=next_job;record=state[job]
 return job,record

def _job_resumable(job,record):
 if record.get('status')!='error':return False
 path=DATA/(job+'.resume.json') if len(job)==32 and job.isalnum() else None
 if not path or not path.is_file():return False
 try:
  prev=json.loads(path.read_text(encoding='utf-8'))
  if prev.get('plan') and not (DATA/prev['plan']['media']).is_file():return False
 except (OSError,ValueError,KeyError):return False
 return True

@app.get('/make/resumable')
def latest_resumable():
 active=_active_make_jobs()
 if active:
  aid,arow=active[0]
  return {'job':None,'active_job':aid,'title':arow.get('title') or (arow.get('source') or {}).get('url') or 'Running batch','stage':arow.get('stage') or ''}
 files=sorted(DATA.glob('*.resume.json'),key=lambda p:p.stat().st_mtime,reverse=True)
 for f in files:
  jid=f.name.split('.')[0]
  if len(jid)!=32 or not jid.isalnum():continue
  term_id,term_rec=_resolve_resume_chain(jid)
  if _job_resumable(term_id,term_rec):
   return {'job':term_id,'active_job':None,'title':term_rec.get('title') or (term_rec.get('source') or {}).get('url') or 'Interrupted batch','stage':term_rec.get('stage') or ''}
 return {'job':None,'active_job':None}

@app.post('/make/{job}/resume')
def resume_make(job:str):
 with resume_lock:
  job,record=_resolve_resume_chain(job)
  if record.get('status') in ('running','done'):
   return {'job':job}
  path=DATA/(job+'.resume.json') if len(job)==32 and job.isalnum() else None
  if record.get('status')!='error' or not path or not path.is_file():
   raise HTTPException(409,'No interrupted analysis checkpoint is available.')
  previous=json.loads(path.read_text(encoding='utf-8'))
  req_key=_source_key(previous.get('request'))
  if req_key:
   for aid,arow in _active_make_jobs():
    if _source_key(arow.get('source'))==req_key:
     app.neon['save'](job,{'resumed_as':aid})
     return {'job':aid}
  if previous.get('plan') and not (DATA/previous['plan']['media']).is_file():
   raise HTTPException(409,'The cached source is missing. Start a new batch.')
  chain=list(previous.get('_chain') or [])
  if job not in chain:chain.append(job)
  previous['_chain']=chain
  started=start_make(previous['request'],previous)
  app.neon['save'](job,{'resumed_as':started['job']})
  if req_key:
   for rf in DATA.glob('*.resume.json'):
    oid=rf.name.split('.')[0]
    if oid==job or len(oid)!=32 or not oid.isalnum():continue
    try:
     if _source_key(json.loads(rf.read_text(encoding='utf-8')).get('request'))==req_key and state.get(oid,{}).get('status')=='error':
      app.neon['save'](oid,{'resumed_as':started['job']})
    except (OSError,ValueError):pass
  return started

@app.get('/make/{job}')
def make_status(job:str):
 if job not in state or state[job].get('kind') in ('export','transcribe'):raise HTTPException(404,'Job unavailable after restart. Please retry.')
 term_id,term_rec=_resolve_resume_chain(job)
 can_resume=_job_resumable(term_id,term_rec)
 return {**report.note_job_error(state[job]),'can_resume':can_resume,'resume_job':term_id if can_resume else None}
@app.get('/status/{id}')
def status(id:str):return report.note_job_error(state.get(id,{'status':'error','error':'Server restarted. Paste the link again to retry.'}))

# ---- Report a problem (all user-triggered; see report.py)
@app.get('/report/info')
def report_info(note:str=''):
 return {'diagnostics':report.diagnostics(note),'issue_url':report.issue_url(note),'can_send':bool(report.report_url())}
@app.get('/report/download')
def report_download(note:str=''):
 from fastapi.responses import PlainTextResponse
 return PlainTextResponse(report.diagnostics(note,errors=40),headers={'Content-Disposition':'attachment; filename="neonclipping-diagnostics.txt"'})
@app.post('/report/send')
def report_send(b:dict):
 if b.get('consent') is not True:raise HTTPException(400,'Tick the box to allow sending first.')
 ok,message=report.send(str(b.get('note') or '')[:600])
 return {'ok':ok,'message':message}
@app.post('/report/log')
def report_log(b:dict):
 """The page reports errors it caught itself (a request that failed)."""
 report.log_error(str(b.get('stage') or 'page')[:80],str(b.get('error') or '')[:700]);return {'ok':True}
@app.post('/readiness/fix')
def readiness_fix(body:dict):
 """The red FFmpeg chip: fetch the portable FFmpeg once (the same copy the installer uses) instead of sending people to a terminal."""
 if body.get('key')!='ffmpeg':raise HTTPException(400,'Nothing to fix automatically for this item.')
 if compat.ffmpeg_ready():return {'ok':True,'detail':'FFmpeg is already available.'}
 try:ok=bool(compat.ensure_ffmpeg())
 except Exception as e:raise HTTPException(502,'Could not download FFmpeg (no internet?): '+str(e)[-150:])
 return {'ok':ok,'detail':'FFmpeg installed.' if ok else 'FFmpeg could not be installed. Run NeonClipping-Setup.bat again.'}

@app.get('/readiness')
def readiness():
 """One-line health of everything NeonClipping needs, each with a plain fix, shown at the top of the page."""
 import compat,ytdl,encoders,smart
 items=[]
 def add(key,label,ok,detail,fix=''):items.append({'key':key,'label':label,'ok':bool(ok),'detail':detail,'fix':fix})
 add('ffmpeg','FFmpeg',compat.ffmpeg_ready(),'found' if compat.ffmpeg_ready() else 'not found','Run NeonClipping-Setup.bat again, or install it with: winget install Gyan.FFmpeg')
 try:enc=encoders.describe()
 except Exception:enc='libx264'
 add('encoder','Encoder',True,{'h264_nvenc':'NVIDIA GPU','h264_amf':'AMD GPU','h264_qsv':'Intel GPU','h264_videotoolbox':'Apple GPU'}.get(enc,'CPU'))
 runtimes=sorted(ytdl.js_runtimes())
 add('youtube','YouTube',bool(runtimes),'JS runtime: '+', '.join(runtimes) if runtimes else 'no JS runtime','Install Deno (winget install DenoLand.Deno) so YouTube shows every quality, then restart NeonClipping.')
 model=smart._model(False)
 add('ai','AI model',bool(model),(model[6:]+' (cloud)') if model and model.startswith('cloud:') else (model or 'Ollama not running (optional)'),'Optional: install Ollama and run: ollama pull llama3.2:3b for smarter titles and moment picking.')
 try:free=shutil.disk_usage(DATA).free/1024**3
 except Exception:free=0
 add('disk','Disk',free>=5,f'{free:.0f} GB free','Free some disk space (clips and downloads need several GB).')
 return {'items':items,'ok':all(i['ok'] for i in items if i['key'] in ('ffmpeg','disk'))}

@app.get('/llm/settings')
def llm_settings_get():
 import llm
 return llm.public()
@app.post('/llm/settings')
def llm_settings_set(b:dict):
 """Cloud AI on/off, provider address, model and key. The key is stored in data/llm.json and never sent back to the page."""
 import llm
 try:return llm.save(bool(b.get('enabled')),b.get('base_url'),b.get('model'),b.get('api_key'))
 except ValueError as e:raise HTTPException(400,str(e))
@app.post('/llm/forget-key')
def llm_forget_key():
 import llm
 llm.clear_key();return llm.public()
@app.post('/llm/test')
def llm_test():
 import llm
 return llm.test()

@app.post('/llm/models')
def llm_models(body:dict):
 """Find models: the provider's own model list (the key is used for this one request and not stored here)."""
 import llm
 try:return {'models':llm.list_models(body.get('base_url'),body.get('api_key'))}
 except (ValueError,RuntimeError) as e:raise HTTPException(400,str(e))
 except Exception as e:raise HTTPException(502,'Could not reach the provider: '+type(e).__name__)

import assistant
assistant.attach(app)
import storage
storage.attach(app,DATA,ROOT,lambda:any(row.get('status') in ('running','queued','starting','recording') for row in list(state.values())),
               lambda:__import__('threading').Timer(1.5,__import__('updater').restart,[ROOT]).start())      # answer first, then restart on the new folder

@app.get('/ytdl/settings')
def ytdl_settings_get():
 import ytdl, proxies
 browser,cookie_file=ytdl._config(DATA)
 pcfg=proxies.config(DATA)
 return {'cookies_browser':browser,'cookie_file':bool(Path(cookie_file).is_file()),'js_runtime':sorted(ytdl.js_runtimes()),
         **pcfg,'proxy':proxies.redact_proxy(pcfg['proxy']),'proxy_stats':proxies.stats(DATA)}
@app.post('/ytdl/settings')
def ytdl_settings_set(b:dict):
 """Which browser's YouTube login to borrow when YouTube shows its bot check, plus optional proxy / GitHub auto-rotation."""
 import ytdl, proxies
 path=DATA/'ytdl.json'
 if 'cookies_browser' in b:
  browser=str(b.get('cookies_browser') or '').strip().lower()
  if browser not in ('','chrome','edge','firefox','brave','opera','vivaldi','chromium'):raise HTTPException(400,'Choose Chrome, Edge, Firefox, Brave, Opera or Vivaldi.')
  try:cfg=json.loads(path.read_text(encoding='utf-8'))
  except (OSError,ValueError):cfg={}
  if browser:cfg['cookies_browser']=browser
  else:cfg.pop('cookies_browser',None)
  DATA.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(cfg),encoding='utf-8')
 try:pcfg=proxies.save_settings(DATA,b)
 except ValueError as e:raise HTTPException(400,str(e))
 browser,_=ytdl._config(DATA)
 return {'ok':True,'cookies_browser':browser,**pcfg,'proxy':proxies.redact_proxy(pcfg['proxy']),'proxy_stats':proxies.stats(DATA)}
@app.post('/ytdl/proxies/refresh')
def ytdl_proxies_refresh(b:dict=None):
 import proxies
 b=b or {}
 pcfg=proxies.config(DATA)
 country=proxies.normalize_country(b.get('proxy_country') or pcfg['proxy_country'])
 raw,alive=proxies.refresh_pool(DATA,country=country)
 return {'ok':True,'country':country,'fetched':len(raw),'alive':len(alive),'sample':[proxies.redact_proxy(p) for p in alive[:5]],'proxy_stats':proxies.stats(DATA)}

@app.get('/update/status')
def update_status():
 import updater
 busy=any(row.get('status') in ('running','queued','starting','recording') for row in list(state.values()))
 return updater.status(ROOT,busy)
@app.post('/update/apply')
def update_apply():
 import updater
 ok,msg=updater.apply(ROOT,lambda:any(row.get('status') in ('running','queued','starting','recording') for row in list(state.values())))
 if not ok:raise HTTPException(409,msg)
 return {'ok':True,'message':msg}

@app.get('/runtime')
def runtime():
 return {'active':[{'id':job,'status':row.get('status'),'stage':row.get('stage') or row.get('message','')} for job,row in list(state.items()) if row.get('status') in ('running','queued','starting','recording') and not row.get('internal')]}
from reedit import attach as attach_reedit
attach_reedit(app,DATA,state,probe,export,app.neon['save'])

import bundles
import editor_export;editor_export.attach(app,DATA,probe)
bundles.attach(app,DATA)

import jobs
import social, social_accounts
social_accounts.attach(app)
send_post=social.attach(app,DATA,state,probe)
jobs.attach(app,DATA,state,{'make':make,'export':export,'transcribe':caption_job,'social':send_post},resume_make)

styling.attach(app,DATA)
import phone
phone.attach(app,DATA,ROOT)
import share
share.attach(app,DATA,ROOT)
import subtitles,facecam_detect,aiparts
subtitles.attach(app)
aiparts.attach(app)
facecam_detect.attach(app,DATA)
brands.attach(app,DATA)
import modes as _modes;_modes.attach(app)
import shortcut;shortcut.attach(app)
import automation as _automation;_automation.attach(app,DATA,probe)
import campaigns;campaigns.attach(app,DATA)
import youtube_feed;youtube_feed.attach(app,DATA)
glossary.attach(app,DATA)
hooks.attach(app)
import transcripts
transcripts.attach(app,DATA,state,probe,transcribe)
import vision
vision.attach(app,DATA,state,probe)

import creators
creators.attach(app,DATA,LIVE,lambda target,opts,cid:start_live(target,opts,cid))

import timeline
timeline.attach(app,DATA,state,probe)
import studio_plans
studio_plans.attach(app,DATA,probe)

def host_binding():
 lan=os.environ.get('NEONCLIPPING_LAN','1')!='0'
 return os.environ.get('NEONCLIPPING_HOST') or ('0.0.0.0' if lan else '127.0.0.1')

if __name__=='__main__':
 host=host_binding()
 port=int(os.environ.get('NEONCLIPPING_PORT','8770'))
 lan=os.environ.get('NEONCLIPPING_LAN','1')!='0'
 print(f'NeonClipping listening on http://{host}:{port} (local: http://127.0.0.1:{port})')
 if lan:
  import phone as _ph;print('Every-device access ON. Open on phone / tablet / other devices:',', '.join(f"http://{ip}:{port}" for ip in _ph.lan_ips()) or f'http://0.0.0.0:{port}')
 uvicorn.run(app,host=host,port=port)
