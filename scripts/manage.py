"""Operator commands. Secrets are read only from environment variables."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('migrate', help='Apply the idempotent PostgreSQL/pgvector schema')
    commands.add_parser('status', help='Check database connectivity and indexed counts')
    sync = commands.add_parser('sync', help='Import one Greenhouse batch, or every batch')
    sync.add_argument('board')
    sync.add_argument('--all', action='store_true')
    sync.add_argument('--offset', type=int, default=0)
    sync.add_argument('--base-url', default='http://127.0.0.1:8000')
    query = commands.add_parser('search', help='Run a local demo or configured live query')
    query.add_argument('query')
    query.add_argument('--country', default='')
    schedules = commands.add_parser('schedules', help='Manage recurring source refreshes with direct operator database access')
    actions = schedules.add_subparsers(dest='schedule_action', required=True)
    actions.add_parser('list', help='Show saved schedules, freshness and budgets')
    add = actions.add_parser('add', help='Save a paused source; never starts collection')
    add.add_argument('board')
    add.add_argument('--hours', type=int, default=24)
    update = actions.add_parser('update', help='Update interval and paused/enabled state with a revision check')
    update.add_argument('board')
    update.add_argument('--hours', type=int, required=True)
    update.add_argument('--state', choices=('paused', 'enabled'), required=True)
    update.add_argument('--revision', type=int, required=True)
    for name in ('run', 'remove'):
        action = actions.add_parser(name, help='Queue one import' if name == 'run' else 'Remove only the schedule, not jobs or runs')
        action.add_argument('board')
        action.add_argument('--revision', type=int, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'migrate':
            if not os.getenv('DATABASE_URL'):
                raise ValueError('Set DATABASE_URL in your environment first.')
            import psycopg
            with psycopg.connect(os.environ['DATABASE_URL'], autocommit=True, connect_timeout=10) as conn:
                for migration in sorted((ROOT / 'sql').glob('[0-9][0-9][0-9]_*.sql')):
                    conn.execute(migration.read_text())
            print('Schema applied. No jobs were imported.')
        elif args.command == 'schedules':
            if not os.getenv('DATABASE_URL'):
                raise ValueError('Schedules require a live DATABASE_URL. The demo is read-only.')
            from rolecraft.schedules import SourceSchedules
            manager = SourceSchedules()
            if args.schedule_action == 'list':
                result = manager.overview()
            elif args.schedule_action == 'add':
                result = manager.create(args.board, args.hours, False)
            elif args.schedule_action == 'update':
                result = manager.update(args.board, args.hours, args.state == 'enabled', args.revision)
            elif args.schedule_action == 'run':
                if not os.getenv('OPENAI_API_KEY'):
                    raise ValueError('Configure embedding credentials and the separate worker before importing.')
                run, created = manager.run_now(args.board, args.revision)
                result = {'run': run, 'created': created}
            else:
                manager.remove(args.board, args.revision)
                result = {'removed': True, 'notice': 'Indexed jobs and admitted runs were preserved.'}
            print(json.dumps(result, default=str, indent=2))
        elif args.command == 'status':
            from rolecraft.store import get_store
            store = get_store()
            print(json.dumps({'mode': store.mode, **store.status()}, indent=2))
        elif args.command == 'search':
            from rolecraft.models import SearchRequest, Filters
            from rolecraft.search import search
            result = search(SearchRequest(query=args.query, filters=Filters(country=args.country)))
            print(json.dumps(result, indent=2))
        elif args.command == 'sync':
            from urllib.parse import urlparse
            import httpx
            url = urlparse(args.base_url)
            if url.username or url.password or url.query or url.fragment or url.path not in ('', '/'):
                raise ValueError('Use a plain workspace origin as --base-url.')
            if url.scheme != 'https' and not (url.scheme == 'http' and url.hostname in ('127.0.0.1', 'localhost')):
                raise ValueError('Use HTTPS except when developing on localhost.')
            token = os.getenv('INGEST_TOKEN', '')
            if len(token) < 32:
                raise ValueError('Set INGEST_TOKEN to a strong 32+ character value.')
            offset = args.offset
            if offset < 0:
                raise ValueError('Offset must be nonnegative.')
            with httpx.Client(timeout=120, follow_redirects=False, trust_env=False) as client:
                while True:
                    response = client.post(args.base_url.rstrip('/') + '/api/ingest',
                        headers={'Authorization': 'Bearer ' + token},
                        json={'provider': 'greenhouse', 'board': args.board, 'offset': offset, 'limit': 10})
                    if response.status_code != 200:
                        raise ValueError(f'Import stopped at offset {offset}; HTTP {response.status_code}. Completed batches remain indexed. Retry this offset; writes are idempotent.')
                    result = response.json()
                    print(json.dumps(result))
                    if not args.all or result['next_offset'] is None:
                        break
                    offset = result['next_offset']
            # Each batch requests a fresh source snapshot. For large boards, use
            # periodic refresh + freshness expiry; do not close unseen jobs here.
        return 0
    except Exception as exc:
        # Avoid exposing URLs containing database passwords or response bodies.
        if isinstance(exc, ValueError):
            print(str(exc), file=sys.stderr)
        else:
            print(f'Operation failed ({type(exc).__name__}). Check configuration and service connectivity.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
