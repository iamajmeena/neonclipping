"""NeonClipping's native layout geometry, shared by browser preview and FFmpeg."""
import math

CATALOG = [
    ('stack', 'Face + gameplay', 'Camera above the action'),
    ('brainrot', 'Viral Split', 'Streamer on top + satisfying loop below'),
    ('bottom', 'Gameplay + face', 'Camera below the action'),
    ('blur', 'Blurred fill', 'Keep the complete source'),
    ('fill', 'Fill screen', 'Full-frame centre crop'),
    ('game', 'Gameplay only', 'Use your selected game area'),
    ('pip_tl', 'Camera top-left', 'Floating selected facecam'),
    ('pip_tr', 'Camera top-right', 'Floating selected facecam'),
    ('pip_bl', 'Camera bottom-left', 'Floating selected facecam'),
    ('pip_br', 'Camera bottom-right', 'Floating selected facecam'),
    ('circle', 'Circle camera', 'Round facecam above gameplay'),
    ('side', 'Side by side', 'Camera and gameplay columns'),
]

ASPECTS={'vertical':(1080,1920),'square':(1080,1080),'portrait':(1080,1350),'landscape':(1920,1080),'threefour':(1080,1440)}

def output_settings(body):
    aspect=str(body.get('aspect','vertical'))
    if aspect not in ASPECTS:raise ValueError('Choose a supported aspect ratio.')
    resolution=int(body.get('resolution',1080));fps=int(body.get('fps') or 0)
    if resolution not in (720,1080,2160) or fps not in (0,24,30,60):raise ValueError('Choose 720, 1080 or 2160 and a supported frame rate.')
    width,height=ASPECTS[aspect];scale=resolution/1080
    return int(width*scale)//2*2,int(height*scale)//2*2,fps

def text_positions(name, top=.32, caption_y=1450, width=1080, height=1920):
    spec=geometry(name,top,width,height)
    cam=next((layer for layer in spec['layers'] if layer['source']=='cam'),None)
    hook_y=260*height/1920;position=caption_y*height/1920
    if name=='brainrot':
        hook_y=180*height/1920
        position=min(position, round(height * 0.48))
    elif cam and cam['y']<100*height/1920:hook_y=cam['y']+cam['h']+30*height/1920
    if name=='side':hook_y=260*height/1920
    if caption_y==1450 and cam and cam['y']>900*height/1920:position=min(position,cam['y']-120*height/1920)
    return {'hook_y':round(hook_y),'caption_y':round(position)}

def geometry(name, top=.32, width=1080, height=1920):
    if name not in {x[0] for x in CATALOG}:raise ValueError('Choose a valid layout.')
    top=float(top)
    if not math.isfinite(top) or not .2<=top<=.7:raise ValueError('Face or split size must be between 20% and 70%.')
    h=int(top*height)//2*2
    full={'source':'full','x':0,'y':0,'w':width,'h':height};game={**full,'source':'game'}
    if name=='blur':return {'mode':'blur','layers':[],'width':width,'height':height}
    if name=='brainrot':
        split_h = int((top if .3<=top<=.7 else .5) * height)//2*2
        layers = [
            {'source': 'game', 'x': 0, 'y': 0, 'w': width, 'h': split_h},
            {'source': 'brainrot_bg', 'x': 0, 'y': split_h, 'w': width, 'h': height - split_h}
        ]
        return {'mode': 'brainrot', 'layers': layers, 'width': width, 'height': height}
    if name in ('fill','game'):layers=[full if name=='fill' else game]
    elif name in ('stack','bottom'):
        cam={'source':'cam','x':0,'y':0 if name=='stack' else height-h,'w':width,'h':h}
        layers=[{**game,'y':h if name=='stack' else 0,'h':height-h},cam]
    elif name=='side':
        w=int(top*width)//2*2;layers=[{**game,'x':w,'w':width-w},{'source':'cam','x':0,'y':0,'w':w,'h':height}]
    else:
        # A wide output must not make a square facecam taller than the frame.
        w=min(int(top*width)//2*2,int(height*.45)//2*2)
        size=w if name=='circle' else int(w*.9)//2*2
        margin=int(width*36/1080)//2*2
        layers=[game,{'source':'cam','x':width-w-margin if name in ('pip_tr','pip_br') else margin,
            'y':height-size-round(180*height/1920) if name in ('pip_bl','pip_br') else round(72*height/1920),
            'w':w,'h':size,'circle':name=='circle'}]
    return {'mode':'layers','layers':layers,'width':width,'height':height}

def render_graph(name, rects, top=.32, width=1080, height=1920, enhance='smart', filters=None, bg_idx=1, top_source='game'):
    spec = geometry(name, top, width, height)
    if spec['mode'] == 'blur':
        bw,bh=max(2,width//8*2),max(2,height//8*2)
        return f'[0:v]split=2[b][f];[b]scale={bw}:{bh}:force_original_aspect_ratio=increase,crop={bw}:{bh},boxblur=8:2,scale={width}:{height}[bg];[f]scale={width}:{height}:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[base]'
    if spec['mode'] == 'brainrot':
        h_top = spec['layers'][0]['h']
        h_bot = spec['layers'][1]['h']
        chosen = 0 if top_source == 'cam' else 1
        crop = ''
        if len(rects) > chosen:
            x,y,w,h = rects[chosen]
            crop = f'crop={w}:{h}:{x}:{y},'
        extra = ''
        scale_flags = ':flags=lanczos'
        if top_source == 'cam' and enhance != 'off':
            c = 1.0; b_val = 0.0; s = 1.0; clarity = 0.0; hue_val = 0.0
            has_custom = False
            if isinstance(filters, dict) and filters:
                c = float(filters.get('contrast', 1.0))
                b_val = float(filters.get('brightness', 0.0))
                s = float(filters.get('saturation', 1.0))
                clarity = float(filters.get('clarity', 0.0))
                hue_val = float(filters.get('hue', 0.0))
                if c != 1.0 or b_val != 0.0 or s != 1.0 or clarity > 0.0 or hue_val != 0.0:
                    has_custom = True
            if not has_custom:
                if enhance == 'high':
                    c = 1.16; s = 1.14; b_val = 0.01; clarity = 0.7
                else:
                    c = 1.12; s = 1.10; b_val = 0.01; clarity = 0.5
            extra_filters = []
            if c != 1.0 or b_val != 0.0 or s != 1.0:
                extra_filters.append(f'eq=contrast={c:.2f}:brightness={b_val:.2f}:saturation={s:.2f}')
            if hue_val != 0.0:
                extra_filters.append(f'hue=h={hue_val:.1f}')
            if clarity > 0.0:
                cas_val = max(0.05, min(1.0, clarity))
                extra_filters.append(f'cas={cas_val:.2f}')
                if clarity > 0.7:
                    extra_filters.append('unsharp=5:5:0.6:5:5:0.2')
            if extra_filters:
                extra = ',' + ','.join(extra_filters)
        return f"[0:v]{crop}scale={width}:{h_top}{scale_flags}:force_original_aspect_ratio=increase,crop={width}:{h_top},setsar=1{extra}[top_v];[{bg_idx}:v]scale={width}:{h_bot}{scale_flags}:force_original_aspect_ratio=increase,crop={width}:{h_bot},setsar=1[bot_v];[top_v][bot_v]vstack=inputs=2[base]"
    layers = spec['layers']; parts=[]
    if len(layers)>1: parts.append('[0:v]split='+str(len(layers))+''.join(f'[s{i}]' for i in range(len(layers))))
    for i, layer in enumerate(layers):
        source = f'[s{i}]' if len(layers)>1 else '[0:v]'
        crop = ''
        if layer['source'] != 'full':
            x,y,w,h = rects[0 if layer['source']=='cam' else 1]
            crop = f'crop={w}:{h}:{x}:{y},'
        w,h = layer['w'],layer['h']
        mask = ''
        if layer.get('circle'):
            mask = ",format=rgba,geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='if(lte(pow(X-W/2,2)+pow(Y-H/2,2),pow(min(W,H)/2,2)),255,0)'"
        extra = ''
        scale_flags = ':flags=lanczos'
        if layer['source'] == 'cam' and enhance != 'off':
            c = 1.0; b_val = 0.0; s = 1.0; clarity = 0.0; hue_val = 0.0
            has_custom = False
            if isinstance(filters, dict) and filters:
                c = float(filters.get('contrast', 1.0))
                b_val = float(filters.get('brightness', 0.0))
                s = float(filters.get('saturation', 1.0))
                clarity = float(filters.get('clarity', 0.0))
                hue_val = float(filters.get('hue', 0.0))
                if c != 1.0 or b_val != 0.0 or s != 1.0 or clarity > 0.0 or hue_val != 0.0:
                    has_custom = True
            if not has_custom:
                if enhance == 'high':
                    c = 1.16; s = 1.14; b_val = 0.01; clarity = 0.7
                else:
                    c = 1.12; s = 1.10; b_val = 0.01; clarity = 0.5
            extra_filters = []
            if c != 1.0 or b_val != 0.0 or s != 1.0:
                extra_filters.append(f'eq=contrast={c:.2f}:brightness={b_val:.2f}:saturation={s:.2f}')
            if hue_val != 0.0:
                extra_filters.append(f'hue=h={hue_val:.1f}')
            if clarity > 0.0:
                cas_val = max(0.05, min(1.0, clarity))
                extra_filters.append(f'cas={cas_val:.2f}')
                if clarity > 0.7:
                    extra_filters.append('unsharp=5:5:0.6:5:5:0.2')
            if extra_filters:
                extra = ',' + ','.join(extra_filters)
        parts.append(source+crop+f'scale={w}:{h}{scale_flags}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1'+extra+mask+f'[p{i}]')
    first = layers[0]
    parts.append(f"[p0]pad={width}:{height}:{first['x']}:{first['y']}:black[b0]")
    for i, layer in enumerate(layers[1:],1):
        parts.append(f"[b{i-1}][p{i}]overlay={layer['x']}:{layer['y']}:shortest=1[b{i}]")
    parts.append(f'[b{len(layers)-1}]null[base]')
    return ';'.join(parts)
