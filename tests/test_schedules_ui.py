"""Real private HTTP + PostgreSQL operations flows; provider calls stay mocked.

The web server runs the unmodified application in its own process. The test
process advances the actual worker with synthetic source records. One race
case delays a real HTTP response in the browser; it never substitutes data.
"""
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import expect, sync_playwright

from test_schedules import schedules, sample_jobs  # shared disposable-DB fixture
from rolecraft.worker import tick

pytestmark = pytest.mark.skipif(not (os.getenv('RUN_UI_TESTS') and os.getenv('TEST_DATABASE_URL')),
                                reason='Needs RUN_UI_TESTS=1 and a disposable PostgreSQL database')
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def browser():
    with sync_playwright() as p:
        kind=getattr(p,os.getenv('TEST_BROWSER','chromium'))
        kwargs={'headless':True}
        if os.getenv('BROWSER_EXECUTABLE'):
            kwargs['executable_path']=os.environ['BROWSER_EXECUTABLE']
        result=kind.launch(**kwargs)
        yield result
        result.close()


@pytest.fixture(scope='module')
def live_origin(tmp_path_factory):
    with socket.socket() as listener:
        listener.bind(('127.0.0.1',0))
        port=listener.getsockname()[1]
    origin=f'http://127.0.0.1:{port}'
    env={**os.environ,'DATABASE_URL':os.environ['TEST_DATABASE_URL'],
         'APP_ACCESS_TOKEN':'workspace-test-'+'a'*32,'INGEST_TOKEN':'operator-test-'+'b'*32,
         'OPENAI_API_KEY':'test-only-not-real','IMPORT_SCHEDULER_ENABLED':'true',
         'DAILY_IMPORT_JOB_LIMIT':'200','SOURCE_FRESH_DAYS':'14'}
    logfile=tmp_path_factory.mktemp('private-http')/'server.log'
    with logfile.open('w') as log:
        proc=subprocess.Popen([sys.executable,'-m','uvicorn','app:app','--host','127.0.0.1','--port',str(port)],
                              cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
        try:
            with httpx.Client(trust_env=False,timeout=1) as client:
                for _ in range(100):
                    if proc.poll() is not None:
                        raise RuntimeError('Private test server exited: '+logfile.read_text())
                    try:
                        if client.get(origin+'/api/health').status_code==200:
                            break
                    except httpx.TransportError:
                        pass
                    time.sleep(.1)
                else:
                    raise RuntimeError('Private test server failed to start')
            yield origin
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill(); proc.wait(timeout=5)


@pytest.fixture
def ops(browser,live_origin,schedules):
    context=browser.new_context(viewport={'width':1440,'height':1080})
    page=context.new_page()
    errors=[]
    page.on('pageerror',lambda exc: errors.append(str(exc)))
    page.goto(live_origin+'/operations',wait_until='networkidle')
    expect(page.locator('#schedule-submit')).to_be_disabled()
    page.locator('#operator-token').fill(os.environ['INGEST_TOKEN'])
    page.locator('#unlock').click()
    expect(page.locator('#schedule-submit')).to_be_enabled()
    yield page
    context.close()
    assert not errors,errors


def add_source(page,board='acme'):
    page.locator('#schedule-board').fill(board)
    page.locator('#schedule-submit').click()
    expect(page.locator('#schedules .source-card')).to_have_count(1)
    expect(page.locator('#schedules')).to_contain_text('Paused')


def test_schedule_resume_worker_success_and_pause(ops,schedules,monkeypatch):
    add_source(ops)
    ops.get_by_role('button',name='Resume acme',exact=True).click()
    expect(ops.locator('#schedules')).to_contain_text('Scheduled')
    monkeypatch.setattr('rolecraft.worker.fetch_board',lambda *_:(sample_jobs(),1,True))
    tick(schedules.queue,schedule=True)
    ops.locator('#refresh').click()
    expect(ops.locator('#schedules')).to_contain_text('1 searchable / 1 active')
    expect(ops.locator('#schedules')).to_contain_text('succeeded')
    expect(ops.locator('#scheduler-state')).to_contain_text('heartbeat recent')
    ops.get_by_role('button',name='Pause acme',exact=True).click()
    expect(ops.locator('#schedules')).to_contain_text('Paused')
    assert schedules.store.status()['jobs']==1


def test_paused_manual_run_deduplicates_and_cancellation_preserves_batches(ops,schedules,monkeypatch):
    add_source(ops)
    ops.get_by_role('button',name='Run now acme',exact=True).click()
    expect(ops.locator('#runs')).to_contain_text('acme')
    ops.get_by_role('button',name='Run now acme',exact=True).click()
    expect(ops.locator('#action-status')).to_contain_text('no duplicate')
    assert len(schedules.queue.recent())==1
    monkeypatch.setattr('rolecraft.worker.fetch_board',lambda *_:(sample_jobs(7),7,True))
    tick(schedules.queue)
    ops.locator('#refresh').click()
    expect(ops.locator('#runs')).to_contain_text('5/7 roles')
    ops.get_by_role('button',name='Cancel acme import',exact=True).click()
    expect(ops.locator('#runs')).to_contain_text('cancelled')
    assert schedules.store.status()['jobs']==5
    expect(ops.locator('#schedules')).to_contain_text('Paused')


def test_stale_editor_is_rejected_and_preserves_draft(ops,schedules):
    add_source(ops)
    ops.get_by_role('button',name='Edit interval acme',exact=True).click()
    ops.locator('#schedule-hours').fill('12')
    schedules.update('acme',24,False,1)
    ops.locator('#schedule-submit').click()
    expect(ops.locator('#error')).to_contain_text('another session')
    expect(ops.locator('#schedule-hours')).to_have_value('12')
    assert schedules.overview()['schedules'][0]['interval_hours']==24
    ops.locator('#refresh').click()
    expect(ops.locator('#refresh')).to_be_enabled()
    ops.locator('#schedule-cancel').click()
    ops.get_by_role('button',name='Edit interval acme',exact=True).click()
    ops.locator('#schedule-hours').fill('12')
    ops.locator('#schedule-submit').click()
    expect(ops.locator('#schedules')).to_contain_text('every 12 hours')


def test_remove_requires_confirmation_and_preserves_history(ops,schedules):
    add_source(ops)
    ops.get_by_role('button',name='Run now acme',exact=True).click()
    expect(ops.locator('#runs')).to_contain_text('acme')
    ops.once('dialog',lambda dialog: dialog.dismiss())
    ops.get_by_role('button',name='Remove acme',exact=True).click()
    expect(ops.locator('#schedules .source-card')).to_have_count(1)
    ops.once('dialog',lambda dialog: dialog.accept())
    ops.get_by_role('button',name='Remove acme',exact=True).click()
    expect(ops.locator('#schedules .source-card')).to_have_count(0)
    expect(ops.locator('#runs')).to_contain_text('acme')
    assert len(schedules.queue.recent())==1


def test_access_clear_discards_schedules_drafts_and_late_response(ops,schedules):
    add_source(ops)
    ops.get_by_role('button',name='Edit interval acme',exact=True).click()
    ops.locator('#schedule-hours').fill('18')
    ops.evaluate('''() => {
      const original = window.fetch;
      window.fetch = (...args) => original(...args).then(response =>
        args[0] === '/api/operations' ? new Promise(resolve => setTimeout(() => resolve(response), 400)) : response);
    }''')
    ops.locator('#refresh').click()
    ops.locator('#lock').click()
    ops.wait_for_timeout(700)  # deliberate late-response race, not a readiness wait
    expect(ops.locator('#schedules')).not_to_contain_text('acme')
    expect(ops.locator('#schedule-board')).to_have_value('')
    expect(ops.locator('#metric-jobs')).to_have_text('—')
    expect(ops.locator('#schedule-submit')).to_be_disabled()
    assert os.environ['INGEST_TOKEN'] not in ops.evaluate('JSON.stringify(localStorage)+JSON.stringify(sessionStorage)')
    ops.reload(wait_until='networkidle')
    expect(ops.locator('#schedules')).not_to_contain_text('acme')
    expect(ops.locator('#operator-token')).to_have_value('')
    assert len(schedules.overview()['schedules'])==1


@pytest.mark.parametrize('width',[320,390])
def test_narrow_source_card_and_keyboard_controls(ops,width):
    ops.set_viewport_size({'width':width,'height':844})
    board='a'*60
    add_source(ops,board)
    assert not ops.evaluate('document.documentElement.scrollWidth > innerWidth')
    button=ops.get_by_role('button',name='Resume '+board,exact=True)
    assert button.bounding_box()['height']>=44
    button.focus(); ops.keyboard.press('Enter')
    expect(ops.locator('#schedules')).to_contain_text('Scheduled')
    assert not ops.evaluate('document.documentElement.scrollWidth > innerWidth')
