"""Video Effects Studio for NeonClipping: Zoom, Screen Shake, Flash, VHS Glitch, Color Presets, Vignette."""

def timing_range(timing, dur, custom_start=0.0, custom_end=2.0):
    """Resolve (start_t, end_t) based on timing option."""
    if timing == 'hook':
        return 0.0, min(dur, 2.0)
    elif timing == 'peak':
        p = max(0.5, dur * 0.55)
        return max(0.0, p - 0.5), min(dur, p + 1.0)
    elif timing == 'start':
        return 0.0, min(dur, 0.5)
    elif timing == 'always':
        return 0.0, dur
    elif timing == 'custom':
        s = max(0.0, float(custom_start or 0.0))
        e = min(dur, float(custom_end or 2.0))
        if e <= s:
            e = min(dur, s + 1.0)
        return s, e
    return 0.0, min(dur, 2.0)

def build_filtergraph(effects, dur, width=1080, height=1920):
    """
    Build chain of FFmpeg filters for enabled effects.
    Returns comma-separated filter string (empty string if no effects enabled).
    """
    if not isinstance(effects, dict) or not effects:
        return ''
    
    filters = []

    # 1. Dynamic Punch-In / Zoom
    zoom = effects.get('zoom')
    if isinstance(zoom, dict) and zoom.get('enabled'):
        s_t, e_t = timing_range(zoom.get('timing', 'hook'), dur, zoom.get('start', 0), zoom.get('end', 2.0))
        scale = max(1.05, min(1.4, float(zoom.get('scale', 1.18))))
        diff = scale - 1.0
        period = max(0.2, e_t - s_t)
        expr_sin = f"({diff:.3f}*sin(3.14159*(t-{s_t:.2f})/{period:.2f}))"
        z_filter = (
            f"crop=w='in_w/(1.0+if(between(t,{s_t:.2f},{e_t:.2f}),{expr_sin},0))':"
            f"h='in_h/(1.0+if(between(t,{s_t:.2f},{e_t:.2f}),{expr_sin},0))':"
            f"x='(in_w-out_w)/2':y='(in_h-out_h)/2',scale={width}:{height}"
        )
        filters.append(z_filter)

    # 2. Screen Shake / Quake
    shake = effects.get('shake')
    if isinstance(shake, dict) and shake.get('enabled'):
        s_t, e_t = timing_range(shake.get('timing', 'peak'), dur, shake.get('start', 0), shake.get('end', 1.0))
        intensity = shake.get('intensity', 'med')
        amp = 18 if intensity == 'high' else (8 if intensity == 'low' else 13)
        s_filter = (
            f"crop=w=in_w*0.96:h=in_h*0.96:"
            f"x='(in_w-out_w)/2+if(between(t,{s_t:.2f},{e_t:.2f}),{amp}*sin(110*t),0)':"
            f"y='(in_h-out_h)/2+if(between(t,{s_t:.2f},{e_t:.2f}),{int(amp*0.8)}*cos(95*t),0)',"
            f"scale={width}:{height}"
        )
        filters.append(s_filter)

    # 3. Flash on Impact
    flash = effects.get('flash')
    if isinstance(flash, dict) and flash.get('enabled'):
        s_t, _ = timing_range(flash.get('timing', 'peak'), dur, flash.get('start', 0), flash.get('end', 0.2))
        flash_dur = 0.22
        b_amount = max(0.2, min(0.9, float(flash.get('brightness', 0.6))))
        f_filter = f"eq=brightness='if(between(t,{s_t:.2f},{s_t+flash_dur:.2f}),{b_amount:.2f}*(1-(t-{s_t:.2f})/{flash_dur:.2f}),0)'"
        filters.append(f_filter)

    # 4. Retro VHS & Glitch
    glitch = effects.get('glitch')
    if isinstance(glitch, dict) and glitch.get('enabled'):
        timing = glitch.get('timing', 'always')
        intensity = glitch.get('intensity', 'med')
        noise_amt = 16 if intensity == 'heavy' else 9
        shift_amt = 6 if intensity == 'heavy' else 3
        
        if timing == 'always':
            g_filter = f"noise=alls={noise_amt}:allf=t+u,rgbashift=rh=-{shift_amt}:bv={shift_amt},eq=contrast=1.12:saturation=1.2"
        else:
            s_t, e_t = timing_range(timing, dur, glitch.get('start', 0), glitch.get('end', 2.0))
            g_filter = (
                f"noise=alls='if(between(t,{s_t:.2f},{e_t:.2f}),{noise_amt},0)':allf=t+u,"
                f"rgbashift=rh='if(between(t,{s_t:.2f},{e_t:.2f}),-{shift_amt},0)':"
                f"bv='if(between(t,{s_t:.2f},{e_t:.2f}),{shift_amt},0)'"
            )
        filters.append(g_filter)

    # 5. Cinematic Color Presets
    color = effects.get('color')
    if isinstance(color, dict) and color.get('enabled'):
        preset = color.get('preset', 'teal_orange')
        if preset == 'teal_orange':
            filters.append("colorbalance=rs=0.15:gs=-0.05:bs=-0.15:rh=-0.1:bh=0.25,eq=saturation=1.2:contrast=1.1")
        elif preset == 'cyberpunk':
            filters.append("colorbalance=rs=0.2:bs=0.2:rm=-0.1:bm=0.2:rh=-0.15:gh=-0.05:bh=0.3,eq=saturation=1.35:contrast=1.15")
        elif preset == 'warm_sunset':
            filters.append("colorbalance=rs=0.2:gs=0.05:bs=-0.15:rm=0.15:gm=0.05:bm=-0.1,eq=saturation=1.12:contrast=1.08")
        elif preset == 'bw_noir':
            filters.append("hue=s=0,eq=contrast=1.3:brightness=0.02")
        elif preset == 'vibrant_pop':
            filters.append("eq=contrast=1.15:saturation=1.28:brightness=0.02,cas=0.35")

    # 6. Vignette
    vignette = effects.get('vignette')
    if isinstance(vignette, dict) and vignette.get('enabled'):
        val = max(0.4, min(1.2, float(vignette.get('intensity', 0.8))))
        filters.append(f"vignette=angle={val:.2f}")

    return ','.join(filters)
