"""Real HTTP browsers; synthetic provider outage only, never fake API responses."""
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import expect

from test_ui import browser, page
from test_postgres import pg

ROOT = Path(__file__).resolve().parents[1]
TOKEN = 'private-search-test-' + 'x' * 32
pytestmark = pytest.mark.skipif(not os.getenv('RUN_UI_TESTS'), reason='Requires real HTTP browser tests')


def test_selected_preferences_expose_source_audit(page):
    page.locator('[data-example="calm"]').click()
    expect(page.locator('#results')).to_have_attribute('aria-busy', 'false')
    page.locator('#results [data-detail]').first.click()
    expect(page.locator('.preference-audit')).to_be_visible()
    expect(page.locator('.preference-check')).to_have_count(2)
    expect(page.locator('.retrieval-facts')).to_contain_text('Keyword rank')
    for quote in page.locator('.preference-check blockquote').all_inner_texts():
        assert quote[1:-1] in page.locator('.description-copy').first.inner_text()


@pytest.mark.parametrize('width', [320, 390])
def test_evidence_audit_mobile_and_keyboard(page, width):
    page.set_viewport_size({'width': width, 'height': 900})
    page.locator('[data-example="calm"]').click()
    expect(page.locator('#results')).to_have_attribute('aria-busy', 'false')
    page.locator('#results [data-detail]').first.focus()
    page.keyboard.press('Enter')
    expect(page.locator('.preference-audit')).to_be_visible()
    assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
    assert not page.locator('#detail-dialog').evaluate('(d) => d.scrollWidth > d.clientWidth')
    page.keyboard.press('Escape')
    expect(page.locator('#detail-dialog')).not_to_be_visible()


@pytest.fixture(scope='module')
def origins(tmp_path_factory):
    running = []
    def start(live=False):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
        env = {**os.environ, 'APP_ACCESS_TOKEN': TOKEN, 'INGEST_TOKEN': 'operator-' + 'y' * 32}
        for name in ('DATABASE_URL','COHERE_API_KEY','OPENAI_API_KEY','OPENAI_CHAT_MODEL','OPENAI_EMBEDDING_MODEL'):
            env.pop(name, None)
        if live:
            env['DATABASE_URL'] = os.environ['TEST_DATABASE_URL']
        code = "import rolecraft.providers as p\ndef outage(*a,**k):\n raise p.ProviderUnavailable('Synthetic provider outage.')\np.embed=outage\nimport uvicorn\nuvicorn.run('app:app',host='127.0.0.1',port=" + str(port) + ")"
        log = (tmp_path_factory.mktemp('search-http')/'server.log').open('w')
        proc = subprocess.Popen([sys.executable, '-c', code], cwd=ROOT, env=env, stdout=log, stderr=log)
        running.append((proc, log))
        origin = f'http://127.0.0.1:{port}'
        with httpx.Client(trust_env=False, timeout=1) as client:
            for _ in range(100):
                if proc.poll() is not None:
                    raise RuntimeError('Search test server exited.')
                try:
                    if client.get(origin+'/api/health').status_code == 200:
                        return origin
                except httpx.TransportError:
                    pass
                time.sleep(.05)
        raise RuntimeError('Search test server failed to start.')
    yield start
    for proc, log in running:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill(); proc.wait(timeout=5)
        log.close()


def unlock(page, origin):
    page.goto(origin, wait_until='networkidle')
    expect(page.locator('#access-dialog')).to_be_visible()
    page.locator('#access-token').fill(TOKEN)
    page.locator('#access-form button[type="submit"]').click()
    expect(page.locator('#results .job-card')).to_have_count(12)


@pytest.fixture
def private_page(browser, origins):
    context = browser.new_context(viewport={'width':1440,'height':1080})
    page = context.new_page(); errors = []
    page.on('pageerror', lambda exc: errors.append(str(exc)))
    unlock(page, origins())
    yield page
    assert not errors, errors
    context.close()


def delay_response(page, endpoint):
    # Delay a real response AFTER HTTP completion so even AbortController alone
    # cannot provide the guarantee under test. No response data is substituted.
    page.evaluate('''endpoint => {
      const original = window.fetch;
      window.fetch = (...args) => original(...args).then(response =>
        args[0] === endpoint ? new Promise(resolve => setTimeout(() => resolve(response), 450)) : response);
    }''', endpoint)


@pytest.mark.parametrize('operation', ['search', 'saved', 'export', 'brief'])
def test_lock_discards_private_payloads_and_late_responses(private_page, operation):
    page = private_page
    page.locator('#results [data-save]').first.click()
    page.locator('#results [data-compare]').first.check()
    downloads = []
    page.on('download', lambda _: downloads.append(True))
    endpoint = '/api/search' if operation == 'search' else '/api/brief' if operation == 'brief' else '/api/jobs'
    delay_response(page, endpoint)
    if operation == 'search':
        page.locator('#query').fill('Python'); page.locator('#search-button').click()
    elif operation == 'saved':
        page.locator('.main-nav [data-view="saved"]').click()
    elif operation == 'export':
        page.locator('.main-nav [data-view="saved"]').click()
        expect(page.locator('#saved-results .job-card')).to_have_count(1)
        page.locator('#export-saved').click()
    else:
        page.locator('#brief-shortcut').click()
        page.locator('#close-dialog').click()
    page.locator('#lock-workspace').click()
    page.wait_for_timeout(700)  # deliberate race: obsolete HTTP response arrives
    assert page.locator('.job-card').count() == 0
    assert page.locator('.brief-card').count() == 0
    expect(page.locator('#compare-bar')).not_to_be_visible()
    expect(page.locator('#pipeline-trace')).to_have_text('{}')
    expect(page.locator('#query')).to_have_value('')
    assert not downloads
    assert TOKEN not in page.evaluate('location.href+JSON.stringify(localStorage)+JSON.stringify(sessionStorage)')
    assert page.evaluate('state.token === "" && state.cache.size === 0')


def test_replacing_token_clears_previous_private_results(private_page):
    page = private_page
    page.locator('#access-button').click()
    page.locator('#access-token').fill('wrong-token-' + 'z'*32)
    page.locator('#access-form button[type="submit"]').click()
    expect(page.locator('#access-dialog')).to_be_visible()
    assert page.locator('.job-card').count() == 0
    assert page.evaluate('state.cache.size === 0')


@pytest.mark.skipif(not os.getenv('TEST_DATABASE_URL'), reason='Requires a disposable PostgreSQL database')
def test_live_outage_notice_and_explicit_meaning_mode(browser, origins, pg):
    context = browser.new_context(viewport={'width':1440,'height':1080})
    page = context.new_page(); errors = []
    page.on('pageerror', lambda exc: errors.append(str(exc)))
    try:
        unlock(page, origins(live=True))
        page.locator('#country').select_option('Canada')
        page.locator('#query').fill('python')
        with page.expect_response(lambda r: r.url.endswith('/api/search') and r.request.post_data_json.get('query') == 'python') as completed:
            page.locator('#search-button').click()
        expect(page.locator('#retrieval-status')).to_have_text('Keywords only · fallback')
        expect(page.locator('#search-notice')).to_contain_text('all hard filters unchanged')
        assert page.locator('#results .job-card').count() > 0
        assert all(j['country'] == 'Canada' for j in completed.value.json()['jobs'])
        page.locator('#brief-shortcut').click()
        expect(page.locator('#dialog-content')).to_contain_text('keyword-only')
        page.locator('#close-dialog').click()
        page.locator('#retrieval-mode').select_option('1')
        expect(page.locator('#retrieval-status')).to_have_text('Search unavailable')
        expect(page.locator('#search-notice')).not_to_be_visible()
        assert page.locator('#results .job-card').count() == 0
        expect(page.locator('#pipeline-trace')).to_have_text('{}')
        page.locator('#retrieval-mode').select_option('0')
        expect(page.locator('#retrieval-status')).to_have_text('Keywords only')
        expect(page.locator('#search-notice')).not_to_be_visible()
    finally:
        context.close()
    assert not errors, errors
