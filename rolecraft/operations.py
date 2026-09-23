"""Readiness and operator routes. Only sanitized configuration flags leave here."""
from __future__ import annotations

import os
import re
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .import_queue import ImportQueue, QueueBudget, QueueConflict, board_token
from .models import Filters
from .providers import EMBEDDING_MODEL
from .store import get_store, where_clause

VERSION = '1.1.0'
ROOT = Path(__file__).resolve().parents[1]


class QueueRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    board: str = Field(min_length=1, max_length=60)

    @field_validator('board')
    @classmethod
    def validate_board(cls, value):
        return board_token(value)


def release_info():
    commit = os.getenv('VERCEL_GIT_COMMIT_SHA', os.getenv('ROLECRAFT_COMMIT', ''))
    return {'version': VERSION, 'commit': commit[:12] if re.fullmatch(r'[0-9a-f]{40}', commit) else 'local'}


def readiness(store=None):
    live = bool(os.getenv('DATABASE_URL'))
    checks = []
    def add(key, title, ok, detail):
        checks.append({'key': key, 'label': title, 'ok': bool(ok), 'detail': detail})
    add('process', 'Application process', True, 'HTTP process is responding.')
    stats = None
    worker = None
    if not live:
        stats = (store or get_store()).status()
        add('corpus', 'Fictional demo corpus', stats['jobs'] == 24, '24 labelled fictional roles; no live vacancies.')
        add('retrieval', 'Local retrieval', True, 'SQLite / FTS5 and deterministic concept vectors; not neural embeddings.')
    else:
        access, ingest = os.getenv('APP_ACCESS_TOKEN', ''), os.getenv('INGEST_TOKEN', '')
        add('access', 'Private workspace access', len(access) >= 32, 'A 32+ character workspace token is required.')
        add('embeddings', 'Embedding configuration', bool(os.getenv('OPENAI_API_KEY')) and (os.getenv('OPENAI_EMBEDDING_MODEL') or EMBEDDING_MODEL) == EMBEDDING_MODEL,
            'Configuration check only; no paid request or provider-health claim.')
        try:
            store = store or get_store()
            with store.connect() as conn:
                present = conn.execute("SELECT to_regclass('jobs') AS jobs,to_regclass('job_chunks') AS chunks,to_regclass('import_runs') AS queue,to_regclass('worker_heartbeat') AS heartbeat").fetchone()
                vector = conn.execute("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname='vector') AS installed").fetchone()['installed']
                schema = all(present.values()) and vector
                add('database', 'Database connectivity', True, 'PostgreSQL responded; connection details are never exposed.')
                add('schema', 'Schema and vector extension', schema, 'Apply all numbered migrations before starting the worker.')
                if schema:
                    stats = dict(conn.execute('SELECT (SELECT count(*) FROM jobs WHERE active) AS jobs,(SELECT count(*) FROM job_chunks) AS chunks,(SELECT count(*) FROM sources) AS sources').fetchone())
                    condition, args = where_clause(Filters(), True)
                    eligible = conn.execute('SELECT count(*) AS n FROM jobs WHERE ' + condition, args).fetchone()['n']
                    missing = conn.execute("SELECT count(*) AS n FROM jobs WHERE " + condition + " AND NOT EXISTS(SELECT 1 FROM job_chunks c WHERE c.job_id=jobs.id AND c.embedding_model=%s)", [*args, EMBEDDING_MODEL]).fetchone()['n']
                    add('corpus', 'Fresh indexed vacancies', eligible > 0 and missing == 0, f'{eligible} fresh eligible roles; {missing} missing an embedding.')
                    worker = conn.execute("SELECT last_seen,last_seen > now()-interval '15 minutes' AS recent FROM worker_heartbeat WHERE name='imports'").fetchone()
        except Exception:
            # Includes missing tables/permissions; never send driver text, DSNs,
            # SQL or upstream messages in readiness responses.
            add('backend', 'Backend verification', False, 'Database or schema check failed. Review operator configuration.')
    ready = all(check['ok'] for check in checks)
    ingestion = live and len(os.getenv('INGEST_TOKEN', '')) >= 32 and os.getenv('INGEST_TOKEN') != os.getenv('APP_ACCESS_TOKEN') and bool(worker and worker['recent']) and ready
    return {'status': 'ready' if ready else 'not_ready', 'mode': 'live' if live else 'demo',
            'release': release_info(), 'checks': checks, 'stats': stats,
            'worker': dict(worker) if worker else None, 'ingestion_ready': bool(ingestion),
            'provider_health': 'not_probed',
            'notice': 'Demo only. Imports are disabled; no live worker or provider is implied.' if not live else 'Private operator workspace. Readiness does not verify provider availability or source accuracy.'}


def router(authorize, safe_operation):
    routes = APIRouter()

    @routes.get('/operations')
    def page():
        return FileResponse(ROOT / 'public/operations.html')

    @routes.get('/operations.js')
    def js():
        return FileResponse(ROOT / 'public/operations.js', media_type='application/javascript')

    @routes.get('/operations.css')
    def css():
        return FileResponse(ROOT / 'public/operations.css', media_type='text/css')

    @routes.get('/api/readiness')
    def ready(request: Request):
        authorize(request)
        result = readiness()
        return JSONResponse(jsonable_encoder(result), status_code=200 if result['status'] == 'ready' else 503)

    @routes.get('/api/operations')
    def overview(request: Request):
        live = bool(os.getenv('DATABASE_URL'))
        authorize(request, admin=live)
        result = readiness()
        schema_ok = any(c['key'] == 'schema' and c['ok'] for c in result['checks'])
        result['runs'] = safe_operation(lambda: ImportQueue().recent()) if live and schema_ok else []
        result['can_enqueue'] = live and schema_ok and bool(os.getenv('OPENAI_API_KEY')) and os.getenv('INGEST_TOKEN') != os.getenv('APP_ACCESS_TOKEN')
        return result

    @routes.post('/api/import-runs')
    def enqueue(payload: QueueRequest, request: Request):
        authorize(request, admin=True)
        if not os.getenv('DATABASE_URL') or not os.getenv('OPENAI_API_KEY'):
            raise HTTPException(503, 'Durable imports need PostgreSQL, embedding credentials and a separate worker. The demo is read-only.')
        if os.getenv('INGEST_TOKEN') == os.getenv('APP_ACCESS_TOKEN'):
            raise HTTPException(503, 'Workspace and ingestion tokens must be different.')
        def run():
            try:
                job, created = ImportQueue().enqueue(payload.board)
                return JSONResponse(jsonable_encoder({'run': job, 'created': created}), status_code=202 if created else 200)
            except QueueBudget as exc:
                raise HTTPException(429, str(exc)) from exc
            except QueueConflict as exc:
                raise HTTPException(409, str(exc)) from exc
        return safe_operation(run)

    @routes.delete('/api/import-runs/{identifier}')
    def cancel(identifier: UUID, request: Request):
        authorize(request, admin=True)
        if not os.getenv('DATABASE_URL'):
            raise HTTPException(503, 'The demo is read-only.')
        def run():
            try:
                return {'run': ImportQueue().cancel(str(identifier))}
            except QueueConflict as exc:
                raise HTTPException(409, str(exc)) from exc
        return safe_operation(run)

    return routes
