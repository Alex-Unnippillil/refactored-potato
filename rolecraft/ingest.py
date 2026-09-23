from __future__ import annotations

import hashlib
import ipaddress
import os
import re
import socket
from urllib.parse import urlparse

import httpx

from .models import Job, utcnow
from .providers import ProviderError, provider_json
from .text import plain_text


def safe_scrape_url(value: str) -> str:
    parsed = urlparse(value)
    hosts = {host.strip().lower() for host in os.getenv('SCRAPE_ALLOWED_HOSTS', '').split(',') if host.strip()}
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (443, None):
        raise ValueError('Only public HTTPS career-page URLs on port 443 are accepted.')
    host = parsed.hostname.lower().rstrip('.')
    if host not in hosts:
        raise ValueError('This career-site hostname is not in SCRAPE_ALLOWED_HOSTS.')
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(record[4][0]).is_global for record in addresses):
            raise ValueError('Private and reserved network addresses are not permitted.')
    except socket.gaierror as exc:
        raise ValueError('The career-site hostname could not be resolved.') from exc
    return value


def fetch_board(board: str, offset: int = 0, limit: int = 5) -> tuple[list[Job], int, bool]:
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', board):
        raise ValueError('Use the Greenhouse board token, not a URL.')
    # The request destination is fixed, and redirects are never followed.
    url = f'https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true'
    try:
        with httpx.Client(timeout=20, follow_redirects=False, trust_env=False) as client:
            with client.stream('GET', url, headers={'User-Agent': 'Rolecraft/1.0 (job-board sync)'}) as response:
                response.raise_for_status()
                body = bytearray()
                for part in response.iter_bytes():
                    body.extend(part)
                    if len(body) > 12_000_000:
                        raise ProviderError('The job board exceeds the bounded import size.')
                import json
                raw = json.loads(body)
        rows = raw['jobs']
        if not isinstance(rows, list):
            raise ValueError('Unexpected jobs payload.')
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        raise ProviderError('This Greenhouse board could not be imported. Check its token and try again.') from exc
    now, jobs = utcnow(), []
    for row in rows[offset:offset + limit]:
        # Missing pay and geographic eligibility stay unknown. Never infer salary
        # or right-to-work from a city, company, or the word "remote" alone.
        location = str((row.get('location') or {}).get('name') or 'Not specified')
        country = next((c for c in ('Canada', 'United States', 'United Kingdom', 'Germany', 'Netherlands') if c.lower() in location.lower()), 'Not specified')
        mode = next((m for m in ('Hybrid', 'Remote', 'On-site') if m.lower() in location.lower()), 'Unknown')
        title = str(row.get('title') or 'Untitled role')
        level = 'Lead' if re.search(r'\b(lead|principal|staff)\b', title, re.I) else 'Senior' if re.search(r'\bsenior\b', title, re.I) else 'Entry' if re.search(r'\b(junior|intern|entry)\b', title, re.I) else 'Unknown'
        description = plain_text(str(row.get('content') or ''))
        if len(description) < 40:
            raise ProviderError('A source listing has no usable description; this batch was not written.')
        jobs.append(Job(id=f'gh-{board}-{row["id"]}', title=title, company=board,
            city=location, country=country, work_mode=mode, level=level, description=description,
            tags=[str(d['name'])[:60] for d in row.get('departments', [])[:5] if d.get('name')],
            source='Greenhouse', source_key=f'greenhouse:{board}', source_url=row['absolute_url'],
            first_seen=now, last_seen=now, source_updated_at=row.get('updated_at')))
    return jobs, len(rows), offset == 0 and len(rows) <= limit


def scrape_job(url: str) -> Job:
    url = safe_scrape_url(url)
    schema = {
        'type': 'object', 'properties': {
            'title': {'type': 'string'}, 'company': {'type': 'string'},
            'city': {'type': 'string'}, 'country': {'type': 'string'},
            'description': {'type': 'string'},
            'work_mode': {'type': 'string', 'enum': ['Remote','Hybrid','On-site','Unknown']},
            'level': {'type': 'string', 'enum': ['Entry','Mid','Senior','Lead','Unknown']},
            'salary_min': {'type': ['integer','null']}, 'salary_max': {'type': ['integer','null']},
            'currency': {'type': ['string','null'], 'enum': ['CAD','USD','EUR','GBP',None]},
            'salary_period': {'type': ['string','null'], 'enum': ['year',None]},
            'remote_scope': {'type': 'string'},
        }, 'required': ['title','company','description'], 'additionalProperties': False,
    }
    raw = provider_json('https://api.firecrawl.dev/v2/scrape', os.getenv('FIRECRAWL_API_KEY', ''), {
        'url': url, 'formats': [{'type': 'json', 'schema': schema, 'prompt': 'Extract this single job vacancy, not other jobs on the page. Copy the full job description without summarizing. Only use explicitly stated facts. Do not infer country or remote eligibility. Set absent salary fields to null. Only extract annual base salary with an explicitly named supported currency; do not annualize or convert currency. If the page is not a single current job vacancy, return an empty object.'}],
        'onlyMainContent': True,
    }, timeout=30)
    try:
        data = raw['data']['json']
        if not isinstance(data, dict):
            raise ValueError('Missing structured extraction.')
        if not data.get('salary_period') or not data.get('currency'):
            for field in ('salary_min','salary_max','currency','salary_period'):
                data[field] = None
        data['description'] = plain_text(data.get('description',''))
        now = utcnow()
        host = urlparse(url).hostname
        return Job(**data, id='web-' + hashlib.sha256(url.encode()).hexdigest()[:24],
            source='Firecrawl extraction', source_key=f'web:{host}', source_url=url, first_seen=now, last_seen=now)
    except (KeyError, TypeError, ValueError) as exc:
        raise ProviderError('The page did not produce a valid single-job record. Nothing was stored.') from exc
