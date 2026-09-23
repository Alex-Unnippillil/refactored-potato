"""Durable Greenhouse worker; run separately from the Vercel web process."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import argparse
import logging
import os
import signal
import threading

from .import_queue import BATCH_SIZE, MAX_JOBS, ImportQueue, LeaseLost
from .ingest import fetch_board
from .models import Job
from .providers import ProviderError

log = logging.getLogger('rolecraft.worker')


def tick(queue=None) -> bool:
    queue = queue or ImportQueue()
    queue.heartbeat()
    run = queue.claim()
    if not run:
        return False
    try:
        if run.get('snapshot_at') and run['snapshot_at'] < datetime.now(timezone.utc) - timedelta(days=1):
            raise ValueError('Snapshot expired; queue a fresh run before reconciling.')
        if run['snapshot'] is None:
            # Fetch ONCE and persist the validated, bounded snapshot. Subsequent
            # units and retries read it, never a shifting upstream offset window.
            jobs, total, _ = fetch_board(run['board'], 0, MAX_JOBS + 1)
            if total > MAX_JOBS or total != len(jobs):
                raise ValueError('The board exceeds the 200-job snapshot limit; nothing was reconciled.')
            queue.set_snapshot(run, jobs)
        batch = [Job.model_validate(row) for row in run['snapshot'][run['processed']:run['processed'] + BATCH_SIZE]]
        if not queue.reserve_budget(run, len(batch)):
            return True
        queue.store.upsert_jobs(batch, 'greenhouse:' + run['board'], 'Greenhouse · ' + run['board'], False,
                               transaction_hook=lambda conn: queue.checkpoint(conn, run, len(batch)))
        log.info('import_batch_committed count=%d', len(batch))
    except LeaseLost:
        log.info('import_lease_changed')
    except Exception as exc:
        code = 'invalid_snapshot' if isinstance(exc, (ValueError, KeyError, TypeError)) else 'upstream_unavailable' if isinstance(exc, ProviderError) else 'backend_unavailable'
        log.warning('import_unit_failed code=%s type=%s', code, type(exc).__name__)
        try:
            queue.fail(run, code, permanent=code == 'invalid_snapshot')
        except LeaseLost:
            pass
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once', action='store_true', help='Process at most one bounded work unit, then exit')
    parser.add_argument('--prune', type=int, metavar='DAYS', help='Remove terminal run history older than 1–90 days')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    if not os.getenv('DATABASE_URL') or (not args.prune and not os.getenv('OPENAI_API_KEY')):
        log.error('worker_configuration_missing DATABASE_URL and OPENAI_API_KEY are required')
        return 2
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    try:
        if args.prune is not None:
            log.info('pruned_runs count=%d', ImportQueue().prune(args.prune))
            return 0
        while not stop.is_set():
            try:
                busy = tick()
            except Exception as exc:
                log.error('worker_unavailable type=%s', type(exc).__name__)
                if args.once:
                    return 1
                busy = False
            if args.once:
                break
            stop.wait(0.2 if busy else 5)
        return 0
    except ValueError:
        log.error('invalid_worker_arguments')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
