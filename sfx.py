import os
import re
from pathlib import Path
import subprocess
import shutil

BUILTIN_SFX = {
    'none': {'name': 'None (No Sound Effect)', 'file': None},
    'vine_boom': {'name': '💥 Vine Boom Bass', 'file': 'vine_boom.wav'},
    'whoosh': {'name': '💨 Whoosh Transition', 'file': 'whoosh.wav'},
    'ding': {'name': '🔔 Ding / Bell Chime', 'file': 'ding.wav'},
    'punch': {'name': '🥊 Punch / Slap Hit', 'file': 'punch.wav'},
    'bruh': {'name': '🗿 Bruh Sound', 'file': 'bruh.wav'},
    'fail': {'name': '🎺 Fail / Sad Horn', 'file': 'fail.wav'},
    'record_scratch': {'name': '🛑 Record Scratch', 'file': 'record_scratch.wav'}
}

def sfx_dir(base_dir):
    d = Path(base_dir) / 'sfx'
    d.mkdir(parents=True, exist_ok=True)
    (d / 'custom').mkdir(parents=True, exist_ok=True)
    return d

def list_all(base_dir):
    d = sfx_dir(base_dir)
    items = []
    for k, v in BUILTIN_SFX.items():
        items.append({'id': k, 'name': v['name'], 'builtin': True})
    
    custom_dir = d / 'custom'
    if custom_dir.exists():
        for f in custom_dir.glob('*.*'):
            if f.suffix.lower() in ('.wav', '.mp3', '.ogg', '.m4a', '.flac'):
                items.append({'id': f'custom:{f.name}', 'name': f'🎵 {f.stem} (Custom)', 'builtin': False, 'file': f.name})
    return items

def resolve_file(base_dir, sfx_id):
    if not sfx_id or sfx_id == 'none':
        return None
    d = sfx_dir(base_dir)
    if sfx_id.startswith('custom:'):
        name = sfx_id.split(':', 1)[1]
        p = d / 'custom' / name
        if p.exists():
            return p
    elif sfx_id in BUILTIN_SFX and BUILTIN_SFX[sfx_id]['file']:
        p = d / BUILTIN_SFX[sfx_id]['file']
        if p.exists():
            return p
    return None

def mix_audio(base_dir, sfx_id, duration, sfx_time='hook', volume=0.75, input_idx=1, base_audio='0:a?'):
    """Returns (extra_inputs_list, extra_filter_str, final_audio_map) or ([], None, base_audio)."""
    p = resolve_file(base_dir, sfx_id)
    if not p:
        return [], None, base_audio or '0:a?'
    
    # Calculate timing in seconds
    t = 0.8
    if sfx_time == 'start':
        t = 0.1
    elif sfx_time == 'hook':
        t = 0.8
    elif sfx_time == 'peak':
        t = max(0.5, duration * 0.65)
    else:
        try:
            t = float(sfx_time)
        except (ValueError, TypeError):
            t = 0.8
    
    t = max(0.0, min(max(0.0, duration - 0.2), t))
    ms = int(t * 1000)
    vol = max(0.05, min(2.0, float(volume or 0.75)))
    
    inputs = ['-i', str(p)]
    src = base_audio.strip('[]') if base_audio else '0:a'
    fc = f"[{input_idx}:a]volume={vol:.2f},adelay={ms}|{ms},apad[sfx_bed];[{src}][sfx_bed]amix=inputs=2:duration=first:dropout_transition=0[sfx_out]"
    return inputs, fc, '[sfx_out]'

def attach(app, root_dir):
    from fastapi import UploadFile, File, HTTPException
    from fastapi.responses import FileResponse, JSONResponse
    import uuid

    d = sfx_dir(root_dir)

    @app.get('/sfx')
    def get_sfx():
        return list_all(root_dir)

    @app.get('/sfx/audio/{sfx_id}')
    def get_sfx_audio(sfx_id: str):
        p = resolve_file(root_dir, sfx_id)
        if not p or not p.exists():
            raise HTTPException(404, 'Audio file not found')
        media_type = 'audio/wav' if p.suffix.lower() == '.wav' else 'audio/mpeg'
        return FileResponse(p, media_type=media_type)

    @app.post('/sfx/upload')
    async def upload_sfx(file: UploadFile = File(...)):
        ext = Path(file.filename or '').suffix.lower()
        if ext not in ('.wav', '.mp3', '.ogg', '.m4a', '.flac'):
            raise HTTPException(400, 'Audio format must be .wav, .mp3, .ogg, or .m4a')
        
        # Safe filename
        stem = re.sub(r'[^a-zA-Z0-9_\- ]', '', Path(file.filename or 'sound').stem).strip() or 'custom'
        out_name = f"{stem}_{uuid.uuid4().hex[:6]}{ext}"
        target = d / 'custom' / out_name
        
        with target.open('wb') as out:
            while chunk := await file.read(512 * 1024):
                out.write(chunk)
                
        # Validate with ffprobe
        r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type', '-of', 'csv=p=0', str(target)],
                           capture_output=True, text=True)
        if r.returncode != 0 or 'audio' not in r.stdout:
            target.unlink(missing_ok=True)
            raise HTTPException(400, 'Invalid audio file')
            
        return {'id': f'custom:{out_name}', 'name': f'🎵 {stem} (Custom)', 'builtin': False}

    @app.delete('/sfx/{filename}')
    def delete_custom_sfx(filename: str):
        target = d / 'custom' / filename
        if target.exists():
            target.unlink(missing_ok=True)
            return {'ok': True}
        raise HTTPException(404, 'File not found')
