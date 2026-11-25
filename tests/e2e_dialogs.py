"""Browser regression for settings input and popup dismissal.

Start run.ps1 first, then run with a Python that has playwright installed:
    python tests/e2e_dialogs.py [--url http://127.0.0.1:8770] [--browser PATH]
Only dummy credentials are used; provider requests and settings writes are mocked.
"""
import argparse
import json

from playwright.sync_api import sync_playwright


def check_dialogs(browser, url, viewport):
    context = browser.new_context(viewport=viewport, permissions=['clipboard-read', 'clipboard-write'])
    page = context.new_page()
    errors, saved, tested = [], [], []
    connection = {'ready': False, 'model': '', 'presets': {'groq': {
        'label': 'Groq', 'base_url': 'https://api.groq.com/openai/v1',
        'model': 'test-model', 'key_url': 'https://example.com/keys', 'free': ''}}}
    page.on('pageerror', lambda error: errors.append(str(error)))

    def settings(route):
        if route.request.method == 'POST':
            saved.append(route.request.post_data_json)
            connection.update(ready=True, model=route.request.post_data_json['model'])
        route.fulfill(json=connection)

    def test_model(route):
        tested.append(route.request.post_data_json)
        route.fulfill(json={'ok': False, 'error': 'Provider unavailable'} if len(tested) == 3
                      else {'ok': True, 'ms': 1, 'model': 'test-model'})

    page.route('**/llm/settings', settings)
    page.route('**/llm/test', test_model)
    page.route('**/llm/models', lambda route: route.fulfill(json={'models': ['test-model']}))
    page.goto(url, wait_until='domcontentloaded')
    page.locator('#side-settings').click()
    assert page.locator('[data-kd="test"]').is_disabled()
    page.locator('button[data-prov="groq"]').click()
    field = page.locator('#kd-key')
    # A real pointer click and Ctrl+V catch form recreation that fill() alone misses.
    dummy = 'dummy-browser-regression-key'
    page.evaluate('(key) => navigator.clipboard.writeText(key)', dummy)
    field.click()
    page.keyboard.press('Control+V')
    assert field.input_value() == dummy, 'Pasted key was cleared'
    field.click()
    page.keyboard.press('End')
    page.keyboard.type('-typed')
    assert field.input_value() == dummy + '-typed', 'Input was recreated on click'
    page.locator('[data-kd="models"]').click()
    page.locator('button[data-model="test-model"]').click()
    assert page.locator('#kd-model').input_value() == 'test-model'
    assert field.input_value() == dummy + '-typed'
    page.locator('[data-kd="save"]').click()
    page.wait_for_function("document.querySelector('#kd-note').textContent.includes('Works')")
    assert saved == [{'enabled': True, 'base_url': 'https://api.groq.com/openai/v1',
                      'model': 'test-model', 'api_key': dummy + '-typed'}]
    assert field.input_value() == ''
    field.fill('unsaved-key')
    page.locator('#kd-model').fill('unsaved-model')
    page.locator('[data-kd="test"]').click()
    page.wait_for_function("document.querySelector('#kd-test-note').textContent.includes('Connected: test-model')")
    assert len(saved) == 1, 'Testing the saved connection must not save form edits'
    assert field.input_value() == 'unsaved-key'
    assert page.locator('#kd-model').input_value() == 'unsaved-model'
    page.locator('[data-kd="test"]').click()
    page.wait_for_function("document.querySelector('#kd-test-note').textContent.includes('Provider unavailable')")
    assert 'kd-ok' not in page.locator('#kd-test-note').get_attribute('class')
    page.locator('[data-kd="test"]').click()
    page.wait_for_function("document.querySelector('#kd-test-note').textContent.includes('Connected:')")
    assert tested == [{}] * 4
    page.locator('[data-kd="close"]').click()
    assert not page.locator('#key-dialog').evaluate('(d) => d.open'), 'Settings did not close'
    page.locator('#side-settings').click()
    page.locator('[data-kd="test"]').click()
    page.wait_for_function("document.querySelector('#kd-test-note').textContent.includes('Connected:')")
    assert page.locator('#kd-key').count() == 0, 'Test must work without opening the key form'
    assert len(saved) == 1
    page.locator('[data-kd="close"]').click()

    dialogs = [
        ('#side-settings', '#key-dialog', '[data-kd="close"]'),
        ('#side-storage', '#storage-dialog', '#sd-close'),
        ('#side-campaigns', '#campaign-dialog', '[data-campaign-close]'),
        ('#report-side', '#rp-dlg', '.rp-x'),
    ]
    for trigger, selector, close in dialogs:
        dialog = page.locator(selector)
        for method in ('button', 'escape', 'backdrop'):
            page.locator(trigger).click()
            assert dialog.evaluate('(d) => d.open')
            if method == 'button':
                dialog.locator(close).click()
            elif method == 'escape':
                page.keyboard.press('Escape')
            else:
                box = dialog.bounding_box()
                assert box['x'] > 1, 'Expected space outside the dialog'
                page.mouse.click(1, 1)
            assert not dialog.evaluate('(d) => d.open'), f'{selector} stuck after {method}'
    # The page is usable again without a reload.
    page.locator('#url').fill('https://example.com/video')
    assert page.locator('#url').input_value() == 'https://example.com/video'
    assert not errors, json.dumps(errors)
    print(f"PASS: paste, typing, models, save/test and popup dismissal at {viewport['width']}px")
    context.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8770')
    parser.add_argument('--browser', help='Optional Chromium executable path')
    args = parser.parse_args()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path=args.browser)
        try:
            for viewport in ({'width': 1366, 'height': 900}, {'width': 390, 'height': 844}):
                check_dialogs(browser, args.url, viewport)
        finally:
            browser.close()
