from __future__ import annotations

import hmac
import logging
import os
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from rolecraft.brief import make_brief
from rolecraft.ingest import fetch_board, scrape_job
from rolecraft.models import Job, SearchRequest, utcnow
from rolecraft.providers import ProviderError
from rolecraft.search import search
from rolecraft.store import PostgresStore, get_store

ROOT = Path(__file__).resolve().parent
app = FastAPI(title='Rolecraft Hybrid Job Search', version='1.0.0', docs_url=None, redoc_url=None, openapi_url=None)
logger = logging.getLogger('rolecraft')

CSP = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; form-action 'self'; object-src 'none'; base-uri 'self'"


@app.middleware('http')
async def guardrails(request: Request, call_next):
    start = time.perf_counter()
    if request.method in ('POST','PUT','PATCH'):
        # Bound actual bytes, not just a user-controlled Content-Length header.
        body = bytearray()
        async for part in request.stream():
            body.extend(part)
            if len(body) > 256_000:
                return JSONResponse({'detail':'Request body is too large.'}, status_code=413, headers={'Content-Security-Policy':CSP,'X-Content-Type-Options':'nosniff','Cache-Control':'no-store','X-Frame-Options':'DENY'})
        request._body = bytes(body)
    response = await call_next(request)
    response.headers.update({'Content-Security-Policy':CSP,'X-Content-Type-Options':'nosniff','Referrer-Policy':'strict-origin-when-cross-origin','X-Frame-Options':'DENY','Permissions-Policy':'camera=(), microphone=(), geolocation=()','Server-Timing':f'app;dur={(time.perf_counter()-start)*1000:.1f}'})
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    return response


def authorize(request: Request, admin: bool = False):
    configured = os.getenv('INGEST_TOKEN' if admin else 'APP_ACCESS_TOKEN', '')
    live = bool(os.getenv('DATABASE_URL'))
    if admin or live or configured:
        if len(configured) < 32:
            raise HTTPException(503, 'This private workspace needs a server-side access token of at least 32 characters.')
        provided = request.headers.get('Authorization', '').removeprefix('Bearer ')
        if not hmac.compare_digest(provided.encode(), configured.encode()):
            raise HTTPException(401, 'Enter the workspace access token.' if not admin else 'An ingestion token is required.')


def live_budget(store, kind='search'):
    if isinstance(store, PostgresStore) and not store.consume_budget(kind):
        raise HTTPException(429, 'The daily workspace request budget has been reached. Try again tomorrow.')


def safe_operation(operation):
    try:
        return operation()
    except (HTTPException, ProviderError):
        raise
    except Exception as exc:
        # Never print database URLs, queries, provider bodies, or user search text.
        logger.error('operation_failed type=%s', type(exc).__name__)
        raise HTTPException(503, 'The workspace backend is unavailable. No demo fallback was substituted.') from exc


@app.exception_handler(ProviderError)
async def provider_error(request, exc):
    return JSONResponse({'detail':str(exc)}, status_code=502)


@app.get('/')
def home():
    return FileResponse(ROOT / 'public/index.html')


@app.get('/styles.css', include_in_schema=False)
def styles():
    return FileResponse(ROOT / 'public/styles.css', media_type='text/css')


@app.get('/app.js', include_in_schema=False)
def script():
    return FileResponse(ROOT / 'public/app.js', media_type='application/javascript')


@app.get('/icon.svg', include_in_schema=False)
def icon():
    return FileResponse(ROOT / 'public/icon.svg', media_type='image/svg+xml')


@app.get('/api/health')
def health():
    return {'status':'ok','service':'rolecraft','version':'1.0.0'}


@app.get('/api/status')
def status():
    live = bool(os.getenv('DATABASE_URL'))
    stats = safe_operation(lambda: get_store().status()) if not live else None
    return {'mode':'live' if live else 'demo','requires_access':live or bool(os.getenv('APP_ACCESS_TOKEN')),
        'stats':stats,'storage':'PostgreSQL + pgvector' if live else 'SQLite + FTS5',
        'embedding':'OpenAI neural embeddings' if live else 'Local concept index (not a neural model)',
        'sources':{'greenhouse':live,'firecrawl':live and bool(os.getenv('FIRECRAWL_API_KEY')),
            'cross_encoder':live and bool(os.getenv('COHERE_API_KEY')),'ai_brief':live and bool(os.getenv('OPENAI_CHAT_MODEL'))},
        'notice':'The demo contains 24 fictional jobs. No live vacancy or external AI service is implied.' if not live else 'Private workspace. Listings are source claims; confirm eligibility and terms with the employer.'}


@app.post('/api/search')
def search_jobs(payload: SearchRequest, request: Request):
    authorize(request)
    def run():
        store = get_store()
        live_budget(store)
        return search(payload, store)
    return safe_operation(run)


@app.post('/api/brief')
def brief(payload: SearchRequest, request: Request):
    authorize(request)
    def run():
        store = get_store()
        live_budget(store, 'brief')
        return make_brief(payload, store)
    return safe_operation(run)


class SavedLookup(BaseModel):
    model_config = ConfigDict(extra='forbid')
    ids: list[str] = Field(max_length=200)


@app.post('/api/jobs')
def saved_jobs(payload: SavedLookup, request: Request):
    authorize(request)
    if any(len(identifier) > 100 for identifier in payload.ids):
        raise HTTPException(422, 'A saved job identifier is invalid.')
    return safe_operation(lambda: {'jobs':get_store().find(payload.ids)})


class IngestRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    provider: str = Field(pattern=r'^(greenhouse|firecrawl|json)$')
    board: str = Field(default='', max_length=80)
    url: str = Field(default='', max_length=2048)
    offset: int = Field(default=0, ge=0, le=20000)
    limit: int = Field(default=5, ge=1, le=10)
    jobs: list[Job] = Field(default_factory=list, max_length=10)


@app.post('/api/ingest')
def ingest(payload: IngestRequest, request: Request):
    authorize(request, admin=True)
    if not os.getenv('DATABASE_URL') or not os.getenv('OPENAI_API_KEY'):
        raise HTTPException(503, 'Live ingestion needs DATABASE_URL and OPENAI_API_KEY; the demo is read-only.')
    def run():
        store = get_store()
        live_budget(store, 'ingest')
        total, complete = 1, False
        try:
            if payload.provider == 'greenhouse':
                jobs, total, complete = fetch_board(payload.board, payload.offset, payload.limit)
                key, label = f'greenhouse:{payload.board}', f'Greenhouse · {payload.board}'
            elif payload.provider == 'firecrawl':
                jobs = [scrape_job(payload.url)]
                key, label = jobs[0].source_key, 'Firecrawl career page'
            else:
                if not payload.jobs or any(j.is_demo or not j.source_url for j in payload.jobs):
                    raise ValueError('JSON ingestion needs 1–10 non-demo jobs with HTTPS source links.')
                key, label = 'manual:verified-import', 'Operator-provided JSON'
                jobs = []
                for job in payload.jobs:
                    # Normalize identifiers into this source namespace; imports
                    # cannot overwrite a job owned by a different connector.
                    import hashlib
                    identifier = 'json-' + hashlib.sha256(job.source_url.encode()).hexdigest()[:24]
                    jobs.append(job.model_copy(update={'id':identifier,'source_key':key,'source':label,'last_seen':utcnow(),'active':True}))
                total = len(jobs)
            count = store.upsert_jobs(jobs, key, label, complete)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {'indexed':count,'source':label,'total_in_source':total,
            'next_offset':payload.offset + payload.limit if payload.provider == 'greenhouse' and payload.offset + payload.limit < total else None,
            'complete_snapshot':complete,'note':'Unknown fields remain unknown. Large boards require all batches; stale records age out after the freshness window.'}
    return safe_operation(run)
