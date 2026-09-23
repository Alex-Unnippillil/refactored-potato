"""Real browser/HTTP checks by default; optional offline bridge for restricted sandboxes.

CI uses normal HTTP, browser storage, CSP and URLs without mocks. The bridge
mode replaces only network transport/history/storage; it is not a deployment test.
"""
import base64
import os
import re
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(not os.getenv('RUN_UI_TESTS'), reason='Set RUN_UI_TESTS=1 and start the app on port 8000')


@pytest.fixture(scope='module')
def browser():
    with sync_playwright() as p:
        kind = getattr(p, os.getenv('TEST_BROWSER', 'chromium'))
        kwargs = {'headless': True}
        if os.getenv('BROWSER_EXECUTABLE'):
            kwargs['executable_path'] = os.environ['BROWSER_EXECUTABLE']
        result = kind.launch(**kwargs)
        yield result
        result.close()


@pytest.fixture
def page(browser):
    context = browser.new_context(viewport={'width': 1440, 'height': 1000})
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda exc: errors.append(str(exc)))
    if os.getenv('UI_TEST_MODE') == 'bridge':
        html = (ROOT / 'public/index.html').read_text()
        html = re.sub(r'<link[^>]*>', '', html)
        html = re.sub(r'<script[^>]*></script>', '', html)
        html = html.replace('src="/icon.svg"', 'src="data:image/svg+xml;base64,' + base64.b64encode((ROOT / 'public/icon.svg').read_bytes()).decode() + '"')
        def backend(path, method, body, headers):
            response = httpx.request(method, 'http://127.0.0.1:8000' + path, content=body, headers=headers, timeout=60)
            return {'status': response.status_code, 'body': response.text}
        page.expose_function('testBackend', backend)
        page.set_content(html)
        page.add_style_tag(content=(ROOT / 'public/styles.css').read_text())
        page.evaluate('''() => {
            history.replaceState = () => {};
            const values = new Map();
            Object.defineProperty(window, 'localStorage', {value: {
                getItem: k => values.get(k) ?? null,
                setItem: (k,v) => values.set(k,String(v)),
                removeItem: k => values.delete(k)
            }});
            window.fetch = async (path, options={}) => {
                const r=await window.testBackend(path,options.method||'GET',options.body||null,options.headers||{});
                return new Response(r.body,{status:r.status,headers:{'Content-Type':'application/json'}});
            };
        }''')
        page.add_script_tag(content=(ROOT / 'public/app.js').read_text())
    else:
        page.goto(os.getenv('TEST_BASE_URL', 'http://127.0.0.1:8000'), wait_until='networkidle')
    expect(page.locator('#results .job-card')).to_have_count(12)
    yield page
    assert not errors, errors
    context.close()


def wait_search(page):
    expect(page.locator('#results')).to_have_attribute('aria-busy', 'false')


def test_initial_workspace_and_pagination(page):
    expect(page.locator('#mode-badge')).to_contain_text('Demo mode')
    first = page.locator('#results .job-card').evaluate_all('(cards) => cards.map(c=>c.dataset.job)')
    page.locator('#next-page').click()
    expect(page.locator('#page-label')).to_contain_text('2')
    second = page.locator('#results .job-card').evaluate_all('(cards) => cards.map(c=>c.dataset.job)')
    assert not set(first) & set(second)
    assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')


def test_hard_filter_search_and_reset(page):
    page.locator('#country').select_option('Canada')
    page.locator('#work-mode').select_option('Remote')
    page.locator('#min-salary').select_option('150000')
    wait_search(page)
    expect(page.locator('#results .job-card')).to_have_count(2)
    expect(page.locator('#results')).to_contain_text('CAD 150')
    page.locator('#reset-filters').click()
    expect(page.locator('#results .job-card')).to_have_count(12)


def test_save_shortlist_and_remove(page):
    first = page.locator('#results .job-card').first
    title = first.locator('.job-title').inner_text()
    first.locator('[data-save]').click()
    expect(page.locator('#saved-count')).to_have_text('1')
    page.locator('.main-nav [data-view="saved"]').click()
    expect(page.locator('#saved-results .job-card')).to_have_count(1)
    expect(page.locator('#saved-results')).to_contain_text(title)
    page.locator('#saved-results [data-save]').click()
    expect(page.locator('#saved-count')).to_have_text('0')
    expect(page.locator('#saved-results .empty-state')).to_be_visible()


def test_details_have_honest_source_and_escape_closes(page):
    page.locator('#results [data-detail]').first.click()
    expect(page.locator('#detail-dialog')).to_be_visible()
    expect(page.locator('#dialog-content')).to_contain_text('fictional')
    assert page.locator('#dialog-content a[target="_blank"]').count() == 0
    page.keyboard.press('Escape')
    expect(page.locator('#detail-dialog')).not_to_be_visible()


def test_compare_and_limit(page):
    checks = page.locator('#results [data-compare]')
    for i in range(3):
        checks.nth(i).check()
    checks.nth(3).click()
    expect(checks.nth(3)).not_to_be_checked()
    expect(page.locator('#compare-count')).to_have_text('3')
    page.locator('#compare-button').click()
    expect(page.locator('#detail-dialog')).to_be_visible()
    expect(page.locator('#dialog-content table')).to_be_visible()
    page.locator('#close-dialog').click()
    page.locator('#compare-clear').click()
    expect(page.locator('#compare-bar')).not_to_be_visible()


def test_evidence_brief_has_source_quotes(page):
    page.locator('#brief-shortcut').click()
    expect(page.locator('#dialog-content .brief-card')).to_have_count(3)
    expect(page.locator('#dialog-content')).to_contain_text('Extractive')
    assert page.locator('#dialog-content blockquote').count() == 3


def test_no_results_and_xss_is_not_executed(page):
    page.locator('#retrieval-mode').select_option('0')
    page.locator('#query').fill('zyxw987654 <img src=x onerror=window.xss=true>')
    page.locator('#search-button').click()
    expect(page.locator('#results .empty-state')).to_be_visible()
    assert page.evaluate('window.xss === undefined')
    assert page.locator('#results img').count() == 0


def test_pipeline_sources_and_access_token_privacy(page):
    page.locator('.main-nav [data-view="pipeline"]').click()
    expect(page.locator('#pipeline-engine')).to_contain_text('demo')
    expect(page.locator('#pipeline-trace')).to_contain_text('rrf_k')
    page.locator('.main-nav [data-view="sources"]').click()
    expect(page.locator('#ingest-button')).to_be_disabled()
    page.locator('#access-button').click()
    page.locator('#access-token').fill('test-token-not-saved')
    page.locator('#close-access').click()
    expect(page.locator('#access-token')).to_have_value('')
    assert page.evaluate("localStorage.getItem('test-token-not-saved')") is None


def test_mobile_layout_and_touch_controls(page):
    page.set_viewport_size({'width': 390, 'height': 844})
    assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
    page.locator('#filter-toggle').click()
    expect(page.locator('#filter-fields')).not_to_be_visible()
    page.locator('#filter-toggle').click()
    expect(page.locator('#country')).to_be_visible()
    page.locator('.main-nav [data-view="saved"]').click()
    expect(page.locator('#view-saved')).to_be_visible()
    assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
