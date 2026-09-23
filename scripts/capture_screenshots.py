"""Capture the actual demo through HTTP; refuse private/live screenshot targets."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlparse

import httpx
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    parser.add_argument('--output', default=str(ROOT/'docs/assets'))
    args = parser.parse_args()
    origin = urlparse(args.base_url)
    if origin.scheme != 'http' or origin.hostname not in ('127.0.0.1','localhost') or origin.username or origin.password or origin.query or origin.fragment or origin.path not in ('','/'):
        raise ValueError('Screenshot capture is restricted to a local demo origin.')
    with httpx.Client(trust_env=False, timeout=10) as client:
        response=client.get(args.base_url+'/api/status'); response.raise_for_status()
        if response.json()['mode']!='demo' or response.json()['requires_access']:
            raise ValueError('Only the unauthenticated fictional demo may be captured.')
    output=Path(args.output); output.mkdir(parents=True,exist_ok=True)
    errors=[]
    with sync_playwright() as p:
        opts={'headless':True}
        if os.getenv('BROWSER_EXECUTABLE'):opts['executable_path']=os.environ['BROWSER_EXECUTABLE']
        browser=p.chromium.launch(**opts)
        for name,route,width,height in [('workspace-desktop','/',1440,1080),('workspace-mobile','/',390,1100),('operations-desktop','/operations',1440,1080),('operations-mobile','/operations',390,1100),('schedules-desktop','/operations',1440,1080),('schedules-mobile','/operations',390,1100)]:
            context=browser.new_context(viewport={'width':width,'height':height},device_scale_factor=2,locale='en-CA',timezone_id='UTC',reduced_motion='reduce')
            page=context.new_page();page.on('pageerror',lambda exc:errors.append(str(exc)))
            page.goto(args.base_url+route,wait_until='networkidle')
            if route=='/':expect(page.locator('#results .job-card')).to_have_count(12)
            else:expect(page.locator('#metric-jobs')).to_have_text('24')
            assert not page.evaluate('document.documentElement.scrollWidth > innerWidth'),name+' overflows'
            assert page.locator('img').evaluate_all('(imgs)=>imgs.every(i=>i.complete && i.naturalWidth>0)'),name+' has broken images'
            if name.startswith('schedules-'):
                expect(page.locator('#scheduler-state')).to_have_text('Off in demo')
                page.locator('.schedules-panel').screenshot(path=str(output/(name+'.png')))
            else:
                page.screenshot(path=str(output/(name+'.png')),full_page=name=='operations-desktop')
            context.close()
        browser.close()
    assert not errors,errors
    files=sorted(p for folder in ('rolecraft','public') for p in (ROOT/folder).glob('*') if p.suffix in ('.py','.js','.html','.css','.svg'))+[ROOT/'app.py']
    digest=hashlib.sha256(b''.join(str(p.relative_to(ROOT)).encode()+b'\0'+p.read_bytes() for p in files)).hexdigest()
    (output/'capture.json').write_text(json.dumps({'mode':'fictional demo','transport':'real HTTP; no browser mocks','device_scale_factor':2,'source_sha256':digest,'images':6},indent=2)+'\n')
    print('Captured six real-HTTP demo screenshots; no browser errors or horizontal overflow.')


if __name__=='__main__':main()
