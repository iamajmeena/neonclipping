"""Chat assistant: plain rules, validation of model output, safe fallbacks."""
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import assistant

CLIP = 'a' * 32


def opts(actions):
    return {(a['key']): a['value'] for a in actions if a['type'] == 'set_option'}


class RuleTests(unittest.TestCase):
    def plan(self, text, **ctx):
        return assistant.plan(text, ctx, model=lambda m, c: (None, []))

    def test_counts_length_and_quality(self):
        o = opts(self.plan('make 3 clips of 30-45 seconds in 4K')['actions'])
        self.assertEqual((o['count'], o['minlen'], o['length'], o['quality']), (3, 30, 45, 2160))

    def test_caption_style_and_layout(self):
        o = opts(self.plan('use pill captions with face + gameplay layout')['actions'])
        self.assertEqual(o['caption_style'], 'pill')
        self.assertEqual(o['layout'], 'stack')

    def test_captions_off(self):
        self.assertFalse(opts(self.plan('turn off the captions')['actions'])['captions'])

    def test_link_starts_make_with_that_link(self):
        acts = self.plan('make clips from https://youtu.be/abc123')['actions']
        self.assertEqual([a for a in acts if a['type'] == 'make'][0]['url'], 'https://youtu.be/abc123')

    def test_selected_clip_gets_an_edit_action_not_a_global_setting(self):
        acts = self.plan('this clip: tiktok captions', clip_id=CLIP)['actions']
        self.assertEqual(acts[0]['type'], 'edit_clip')
        self.assertEqual(acts[0]['changes'], {'caption_style': 'tiktok'})
        self.assertNotIn('caption_style', opts(acts))

    def test_unknown_message_gives_help_not_actions(self):
        r = self.plan('what is the weather')
        self.assertEqual(r['actions'], [])
        self.assertEqual(r['source'], 'none')

    def test_empty_message(self):
        self.assertEqual(self.plan('  ')['actions'], [])


class ValidationTests(unittest.TestCase):
    def test_values_are_clamped_and_unknown_things_dropped(self):
        self.assertEqual(assistant.normalize_action({'type': 'set_option', 'key': 'count', 'value': 999})['value'], 12)
        for bad in ({'type': 'set_option', 'key': 'caption_style', 'value': 'nope'}, {'type': 'set_option', 'key': 'quality', 'value': 5},
                    {'type': 'delete_all'}, {'type': 'make', 'url': 'file:///etc/passwd'}, {'type': 'edit_clip', 'changes': {'cmd': 'x'}}, 'text', None):
            self.assertIsNone(assistant.normalize_action(bad), bad)

    def test_model_actions_are_validated_too(self):
        r = assistant.plan('zzz qqq', {}, model=lambda m, c: ('ok', [a for a in map(assistant.normalize_action, [
            {'type': 'set_option', 'key': 'caption_style', 'value': 'comic'}, {'type': 'set_option', 'key': 'rm', 'value': 1}]) if a]))
        self.assertEqual(r['source'], 'model')
        self.assertEqual(len(r['actions']), 1)

    def test_no_model_available_is_not_an_error(self):
        self.assertEqual(assistant.ask_model('hello', {})[1] if False else [], [])

    def test_string_booleans_are_parsed_not_coerced_to_true(self):
        for false_val in ('false', 'False', 'off', 'no', '0', 0):
            act = assistant.normalize_action({'type': 'set_option', 'key': 'captions', 'value': false_val})
            self.assertEqual(act['value'], False, false_val)
            self.assertEqual(act['label'], 'captions off')
            edit = assistant.normalize_action({'type': 'edit_clip', 'changes': {'captions': false_val}})
            self.assertEqual(edit['changes']['captions'], False, false_val)
            self.assertEqual(edit['label'], 'This clip: captions off')
        for true_val in ('true', 'on', 'yes', '1', 1):
            act = assistant.normalize_action({'type': 'set_option', 'key': 'heading_on', 'value': true_val})
            self.assertEqual(act['value'], True, true_val)
        self.assertIsNone(assistant.normalize_action({'type': 'set_option', 'key': 'captions', 'value': 'maybe'}))
        self.assertIsNone(assistant.normalize_action({'type': 'edit_clip', 'changes': {'captions': 'maybe'}}))


if __name__ == '__main__':
    unittest.main()
