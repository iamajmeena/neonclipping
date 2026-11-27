import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import camfx, hooks, layouts


class CamFxTests(unittest.TestCase):
    def test_defaults_change_nothing(self):
        self.assertEqual(camfx.filter({}), '')
        self.assertEqual(camfx.filter({'cam_contrast': 1, 'cam_brightness': 0, 'cam_saturation': 1, 'cam_clarity': 0}), '')

    def test_filter_text(self):
        f = camfx.filter({'cam_contrast': 1.3, 'cam_clarity': 0.8})
        self.assertTrue(f.startswith(','))
        self.assertIn('eq=contrast=1.300', f)
        self.assertIn('unsharp=5:5:0.80', f)

    def test_validation(self):
        for body in ({'cam_contrast': 5}, {'cam_brightness': -1}, {'cam_clarity': 'x'}, {'cam_saturation': float('nan')}):
            with self.assertRaises(ValueError):
                camfx.settings(body)
        with self.assertRaises(ValueError):
            hooks.settings({'cam_contrast': 9})
        self.assertIn('cam_contrast', hooks.KEYS)

    def test_only_the_facecam_layer_is_touched(self):
        rects = [(0, 0, 400, 300), (400, 0, 880, 720)]
        plain = layouts.render_graph('stack', rects, .32, 1080, 1920)
        fx = layouts.render_graph('stack', rects, .32, 1080, 1920, camfx.filter({'cam_contrast': 1.3}))
        self.assertNotIn('eq=', plain)
        self.assertEqual(fx.count('eq=contrast'), 1)


if __name__ == '__main__':
    unittest.main()


class LivenessTests(unittest.TestCase):
    def test_static_picture_is_not_a_webcam(self):
        import facecam_detect as fd
        self.assertFalse(fd.is_live(0.0))
        self.assertFalse(fd.is_live(0.2))
        self.assertTrue(fd.is_live(1.5))


class JsRuntimeTests(unittest.TestCase):
    def test_node_and_deno_are_allowed_when_installed(self):
        import ytdl
        from unittest import mock
        with mock.patch('shutil.which', lambda n: '/x/' + n if n == 'node' else None):
            self.assertEqual(ytdl.js_runtimes(), {'node': {}})
            opts = [o for o, d in ytdl.variants({'quiet': True})]
            self.assertTrue(all(o.get('js_runtimes') == {'node': {}} for o in opts))
        with mock.patch('shutil.which', lambda n: None):
            self.assertEqual(ytdl.js_runtimes(), {})
            self.assertTrue(all('js_runtimes' not in o for o, d in ytdl.variants({'quiet': True})))


class Round3Tests(unittest.TestCase):
    def test_clean_words_keeps_usable_words(self):
        import subtitles
        words = [{'start': -0.5, 'end': 0.4, 'text': 'a'}, {'start': 1, 'end': 99, 'text': 'b'}, {'start': 2, 'end': 2.0, 'text': 'c'},
                 {'start': 3, 'end': 3.5, 'text': '  '}, {'start': float('nan'), 'end': 4, 'text': 'd'}, {'start': 5, 'end': 6}]
        out = subtitles.clean_words(words, 10)
        self.assertEqual([w['text'] for w in out], ['a', 'b'])
        self.assertEqual((out[0]['start'], out[1]['end']), (0.0, 10.0))
        subtitles.validate_words(out, 10)            # whatever clean_words returns passes the strict check

    def test_audio_loads_without_pyav(self):
        import wave, tempfile, numpy as np, captions
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'a.wav'
            data = (np.sin(np.linspace(0, 100, 16000)) * 16000).astype(np.int16)
            with wave.open(str(path), 'wb') as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(data.tobytes())
            arr = captions._load_audio(path)
        self.assertEqual(arr.dtype, np.float32)
        self.assertEqual(len(arr), 16000)
        self.assertLessEqual(float(abs(arr).max()), 1.0)

    def test_blocked_pyav_gets_a_stub(self):
        import sys, subprocess
        code = "import sys; sys.modules['av']=None; import compat; m=sys.modules['av']; print(getattr(m,'__neon_stub__',False))"
        r = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, cwd=str(Path(__file__).resolve().parents[1]))
        self.assertEqual(r.stdout.strip().splitlines()[-1], 'True')

    def test_ass_filter_uses_explicit_option_name(self):
        text = (Path(__file__).resolve().parents[1] / 'app.py').read_text(encoding='utf-8')
        self.assertIn('=filename={ass}', text)
        self.assertNotIn('ass={ass}', text)


class CoverTests(unittest.TestCase):
    def test_frame_time_stays_inside_the_clip(self):
        import cover
        self.assertEqual(cover.frame_time(0.2), 0.0)
        self.assertAlmostEqual(cover.frame_time(10), 4.0)
        self.assertLess(cover.frame_time(1.0), 1.0)

    def test_ass_text_has_box_and_title(self):
        import cover
        text = cover.ass_text(['HELLO WORLD'], 1080, 1920)
        self.assertIn('PlayResX: 1080', text)
        self.assertIn('HELLO', text)
        self.assertIn('WORLD', text)          # the accent word is wrapped in its own colour tag
        self.assertGreaterEqual(text.count('Dialogue:'), 2)       # text + accent bar


class CoverHookTests(unittest.TestCase):
    def test_hook_until(self):
        import cover
        self.assertEqual(cover.hook_until({}), 0.0)
        self.assertEqual(cover.hook_until({'hook': 'X'}), 8.0)
        self.assertEqual(cover.hook_until({'hook': 'X', 'hook_duration': 5}), 5.0)
        self.assertEqual(cover.hook_until({'hook': 'X', 'hook_enabled': False}), 0.0)
        self.assertEqual(cover.hook_until({'hook': 'X', 'template': 'x_dark'}), 0.0)


class CoverTimingTests(unittest.TestCase):
    def test_title_overlay_lasts_the_whole_clip(self):
        import cover
        text = cover.ass_text(['TITLE'], 1080, 1920)
        self.assertIn('9:59:59.00', text)
        self.assertNotIn('0:01:00.00', text)


class Round4Tests(unittest.TestCase):
    def test_layouts_know_when_a_facecam_box_is_needed(self):
        import layouts
        self.assertTrue(layouts.needs_cam('stack'))
        self.assertFalse(layouts.needs_cam('blur'))
        self.assertFalse(layouts.needs_cam('no-such-layout'))
        self.assertTrue(layouts.is_default_cam({'x': 0, 'y': 0, 'w': .25, 'h': .3}))
        self.assertFalse(layouts.is_default_cam({'x': .7, 'y': .05, 'w': .25, 'h': .3}))
        self.assertFalse(layouts.is_default_cam(None))

    def test_speech_model_download_needs_internet_and_says_so(self):
        import captions
        from unittest import mock
        with mock.patch.object(captions, 'internet_ok', return_value=False), \
                mock.patch('pathlib.Path.glob', return_value=[]):
            with self.assertRaises(RuntimeError) as c:
                captions._turbo_spec()
        self.assertIn('cannot be reached', str(c.exception))

    def test_hf_timeouts_are_set_and_downloads_have_ffmpeg_timeout(self):
        import os, compat
        self.assertEqual(os.environ.get('HF_HUB_DOWNLOAD_TIMEOUT'), '60')
        text = (Path(__file__).resolve().parents[1] / 'app.py').read_text(encoding='utf-8')
        self.assertIn("'ffmpeg_i':['-rw_timeout','30000000']", text)
        std = (Path(__file__).resolve().parents[1] / 'standalone.py').read_text(encoding='utf-8')
        self.assertIn("'ffmpeg_i':['-rw_timeout','30000000']", std)


class WholeVsRangedTests(unittest.TestCase):
    def test_choice(self):
        import standalone
        self.assertTrue(standalone.prefer_whole_download(213, (10, 200)))            # short video
        self.assertTrue(standalone.prefer_whole_download(2400, (0, 60)))             # under 45 min: whole is faster
        self.assertTrue(standalone.prefer_whole_download(6000, (0, 3000)))           # part is half of a 100 min video
        self.assertFalse(standalone.prefer_whole_download(6000, (0, 600)))           # small part of a long video: ranged
        self.assertFalse(standalone.prefer_whole_download(30000, (0, 7000)))         # beyond the 2 h limit: never whole
        self.assertFalse(standalone.prefer_whole_download(None, (0, 10)))
        self.assertFalse(standalone.prefer_whole_download(100, None))


class AssetsTests(unittest.TestCase):
    def test_every_asset_in_the_page_is_served(self):
        import re
        root = Path(__file__).resolve().parents[1]
        page = (root / 'index.html').read_text(encoding='utf-8')
        wanted = set(re.findall(r'/assets/([A-Za-z0-9_.-]+?)\?v=', page))
        app = (root / 'app.py').read_text(encoding='utf-8')
        allowed = set(re.findall(r"'([A-Za-z0-9_.-]+\.(?:js|css))'", re.search(r"if name not in \(([^)]*)\)", app).group(1)))
        self.assertTrue(wanted)
        self.assertEqual(wanted - allowed, set(), 'referenced in index.html but not served by /assets')
        for name in wanted:
            self.assertTrue((root / name).is_file(), name)


class LoanwordTests(unittest.TestCase):
    def test_english_words_written_in_devanagari_get_their_english_spelling(self):
        from translit import to_hinglish
        cases = {'पुलिस': 'police', 'पोलिस': 'police', 'फोन': 'phone', 'फ़ोन': 'phone', 'गेम': 'game', 'कार': 'car', 'मोबाइल': 'mobile',
                 'जीटीए': 'gta', 'स्ट्रीमर': 'streamer', 'वायरल': 'viral', 'क्लिप': 'clip', 'हेलीकॉप्टर': 'helicopter'}
        for dev, eng in cases.items():
            self.assertEqual(to_hinglish(dev), eng, dev)

    def test_punctuation_and_hindi_words_are_untouched(self):
        from translit import to_hinglish
        self.assertEqual(to_hinglish('पुलिस,'), 'police,')
        self.assertEqual(to_hinglish('पुलिस।'), 'police.')
        self.assertEqual(to_hinglish('है'), 'hai')
        self.assertEqual(to_hinglish('बस'), 'bas')           # Hindi "enough", not the English bus
        self.assertEqual(to_hinglish('गाड़ी'), to_hinglish('गाड़ी'))
        self.assertEqual(to_hinglish('पुलिसवाले'), 'police wale')
        self.assertEqual(to_hinglish('फोनों'), 'phones')

    def test_every_loanword_is_plain_ascii_lowercase_letters(self):
        import loanwords
        for dev, eng in loanwords.LOANWORDS.items():
            self.assertTrue(all(c.isascii() and (c.isalpha() or c == ' ') for c in eng), (dev, eng))


class ScorePartsTests(unittest.TestCase):
    def test_parts_are_scaled_clamped_and_never_invented(self):
        import smart
        self.assertEqual(smart._parts({'hook': 10, 'engagement': 8, 'value': 4, 'shareability': 99}), {'hook': 25, 'engagement': 20, 'value': 10, 'shareability': 25})
        self.assertEqual(smart._parts({'hook': 5}), {})
        self.assertEqual(smart._parts('x'), {})
        self.assertEqual(smart._parts({'hook': 'a', 'engagement': 1, 'value': 1, 'shareability': 1}), {})


class ExportStyleTests(unittest.TestCase):
    def test_export_accepts_every_caption_style(self):
        import re
        root = Path(__file__).resolve().parents[1]
        app = (root / 'app.py').read_text(encoding='utf-8')
        self.assertIn("STYLE_NAMES:raise", app)
        self.assertNotIn("('gta','bold','clean','hormozi','mrbeast')", app)


class AppImportsTests(unittest.TestCase):
    def test_every_project_module_used_in_app_py_is_imported(self):
        import ast
        root = Path(__file__).resolve().parents[1]
        tree = ast.parse((root / 'app.py').read_text(encoding='utf-8'))
        modules = {p.stem for p in root.glob('*.py')}
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {a.asname or a.name.split('.')[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                imported |= {a.asname or a.name for a in node.names}
        used = {n.value.id for n in ast.walk(tree) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)}
        self.assertEqual({m for m in used if m in modules and m != 'app'} - imported, set())
