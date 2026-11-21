"""Brainrot / Viral Split-screen satisfying background loops for NeonClipping."""
from pathlib import Path
import re
import subprocess
import uuid

BUILTIN_BG = {
    'subway': {'name': '🚇 Subway Surfers', 'file': 'subway.mp4'},
    'minecraft': {'name': '🧱 Minecraft Parkour', 'file': 'minecraft.mp4'},
    'gta': {'name': '🚗 GTA 5 Mega Ramp', 'file': 'gta.mp4'},
    'soap': {'name': '🧼 Soap / Kinetic Sand', 'file': 'soap.mp4'},
}

def brainrot_dir(root_dir):
    d = Path(root_dir) / 'brainrot'
    d.mkdir(exist_ok=True)
    (d / 'custom').mkdir(exist_ok=True)
    return d

def list_all(root_dir):
    d = brainrot_dir(root_dir)
    res = []
    for bg_id, item in BUILTIN_BG.items():
        if (d / item['file']).exists():
            res.append({'id': bg_id, 'name': item['name'], 'builtin': True})
    for f in (d / 'custom').glob('*.*'):
        if f.suffix.lower() in ('.mp4', '.mov', '.webm', '.mkv'):
            clean_name = f.stem.split('_')[0]
            res.append({'id': f'custom:{f.name}', 'name': f'📁 {clean_name} (Custom)', 'builtin': False})
    return res

def resolve_bg(root_dir, bg_id):
    d = brainrot_dir(root_dir)
    if not bg_id:
        bg_id = 'subway'
    if str(bg_id).startswith('custom:'):
        fname = str(bg_id).split(':', 1)[1]
        p = d / 'custom' / fname
        if p.exists():
            return p
    if bg_id in BUILTIN_BG:
        p = d / BUILTIN_BG[bg_id]['file']
        if p.exists():
            return p
    for item in BUILTIN_BG.values():
        p = d / item['file']
        if p.exists():
            return p
    return None

def attach(app, root_dir):
    from fastapi import UploadFile, File, HTTPException
    from fastapi.responses import FileResponse
    
    d = brainrot_dir(root_dir)

    @app.get('/brainrot/backgrounds')
    def get_backgrounds():
        return list_all(root_dir)

    @app.get('/brainrot/video/{bg_id}')
    def get_bg_video(bg_id: str):
        p = resolve_bg(root_dir, bg_id)
        if not p or not p.exists():
            raise HTTPException(404, 'Background video not found')
        return FileResponse(p, media_type='video/mp4')

    @app.post('/brainrot/upload')
    async def upload_bg(file: UploadFile = File(...)):
        ext = Path(file.filename or '').suffix.lower()
        if ext not in ('.mp4', '.mov', '.webm', '.mkv'):
            raise HTTPException(400, 'Video format must be .mp4, .mov, or .webm')
        stem = re.sub(r'[^a-zA-Z0-9_\- ]', '', Path(file.filename or 'bg').stem).strip() or 'custom'
        out_name = f"{stem}_{uuid.uuid4().hex[:6]}{ext}"
        target = d / 'custom' / out_name
        with target.open('wb') as out:
            while chunk := await file.read(1024 * 1024):
                out.write(chunk)
        r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type', '-of', 'csv=p=0', str(target)],
                           capture_output=True, text=True)
        if r.returncode != 0 or 'video' not in r.stdout:
            target.unlink(missing_ok=True)
            raise HTTPException(400, 'Invalid video file')
        return {'id': f'custom:{out_name}', 'name': f'📁 {stem} (Custom)', 'builtin': False}

    @app.delete('/brainrot/{filename}')
    def delete_custom_bg(filename: str):
        target = d / 'custom' / filename
        if target.exists():
            target.unlink(missing_ok=True)
            return {'ok': True}
        raise HTTPException(404, 'File not found')
