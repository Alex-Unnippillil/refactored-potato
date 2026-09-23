"""Bounded PostgreSQL import queue. No process-local task state or secret payloads.

A lease token fences stale workers. Job writes and cursor advancement share one
transaction. Provider calls are at-least-once; committed database batches are
idempotent. SKIP LOCKED allows independent boards to be processed concurrently.
"""
from __future__ import annotations

import json
import os
import re
from uuid import uuid4

from .models import Job
from .store import PostgresStore

MAX_JOBS = 200
BATCH_SIZE = 5
LEASE_SECONDS = 600
PUBLIC_FIELDS = ('id', 'board', 'state', 'created_at', 'updated_at', 'available_at',
                 'claims', 'failures', 'processed', 'total', 'error_code', 'finished_at')


class QueueConflict(ValueError):
    pass


class QueueBudget(ValueError):
    pass


class LeaseLost(RuntimeError):
    pass


def public_run(row):
    return {key: row[key] for key in PUBLIC_FIELDS}


def board_token(value: str) -> str:
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,60}', value):
        raise ValueError('Use a Greenhouse board token of 1–60 letters, digits, underscores or hyphens; not a URL.')
    return value.lower()


class ImportQueue:
    def __init__(self, store=None):
        self.store = store or PostgresStore()

    def enqueue(self, board: str) -> tuple[dict, bool]:
        board = board_token(board)
        with self.store.connect() as conn:
            # Consistent source/admission locking also excludes legacy syncs.
            conn.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', ('greenhouse:' + board,))
            conn.execute("SELECT pg_advisory_xact_lock(hashtext('rolecraft:queue-admission'))")
            existing = conn.execute("SELECT * FROM import_runs WHERE board=%s AND state IN ('queued','running','retry')", (board,)).fetchone()
            if existing:
                return public_run(existing), False
            active = conn.execute("SELECT count(*) AS n FROM import_runs WHERE state IN ('queued','running','retry')").fetchone()['n']
            if active >= 20:
                raise QueueConflict('The import queue is full. Finish or cancel an existing run first.')
            admitted = conn.execute("""INSERT INTO usage_buckets(day,kind,used) VALUES(CURRENT_DATE,'queue_requests',1)
                ON CONFLICT(day,kind) DO UPDATE SET used=usage_buckets.used+1
                WHERE usage_buckets.used < 10 RETURNING used""").fetchone()
            if not admitted:
                raise QueueBudget('The daily limit of 10 new import runs has been reached.')
            row = conn.execute('INSERT INTO import_runs(id,board) VALUES(%s,%s) RETURNING *', (str(uuid4()), board)).fetchone()
        return public_run(row), True

    def recent(self) -> list[dict]:
        with self.store.connect() as conn:
            rows = conn.execute('SELECT ' + ','.join(PUBLIC_FIELDS) + ' FROM import_runs ORDER BY created_at DESC,id LIMIT 40').fetchall()
        return [dict(row) for row in rows]

    def cancel(self, identifier: str) -> dict:
        with self.store.connect() as conn:
            row = conn.execute("""UPDATE import_runs SET state='cancelled', snapshot=NULL,
                lease_token=NULL,lease_until=NULL,updated_at=now(),finished_at=now()
                WHERE id=%s AND state IN ('queued','running','retry') RETURNING *""", (identifier,)).fetchone()
            if not row:
                raise QueueConflict('This run does not exist or is already finished.')
        return public_run(row)

    def heartbeat(self):
        with self.store.connect() as conn:
            conn.execute("INSERT INTO worker_heartbeat(name) VALUES('imports') ON CONFLICT(name) DO UPDATE SET last_seen=now()")

    def claim(self) -> dict | None:
        with self.store.connect() as conn:
            # A crashed worker consumes the same bounded failure budget as an
            # upstream failure. Never leave an exhausted lease stuck forever.
            conn.execute("""UPDATE import_runs SET state='failed',error_code='retry_exhausted',
                failures=3,snapshot=NULL,lease_token=NULL,lease_until=NULL,finished_at=now(),updated_at=now()
                WHERE state='running' AND lease_until < clock_timestamp() AND failures >= 2""")
            row = conn.execute("""WITH candidate AS (
                SELECT id FROM import_runs WHERE
                    (state IN ('queued','retry') AND available_at <= clock_timestamp()) OR
                    (state='running' AND lease_until < clock_timestamp())
                ORDER BY created_at,id FOR UPDATE SKIP LOCKED LIMIT 1)
                UPDATE import_runs r SET state='running',claims=r.claims+1,
                    failures=r.failures+CASE WHEN r.state='running' THEN 1 ELSE 0 END,
                    lease_token=%s,lease_until=clock_timestamp()+(%s * interval '1 second'),updated_at=now()
                FROM candidate c WHERE r.id=c.id RETURNING r.*""", (str(uuid4()), LEASE_SECONDS)).fetchone()
        return dict(row) if row else None

    @staticmethod
    def guard(conn, run):
        row = conn.execute("""SELECT * FROM import_runs WHERE id=%s AND state='running'
            AND lease_token=%s AND lease_until > clock_timestamp() FOR UPDATE""", (run['id'], run['lease_token'])).fetchone()
        if not row or row['processed'] != run['processed']:
            raise LeaseLost('The import lease or cursor changed; no stale writes are permitted.')
        return row

    def set_snapshot(self, run, jobs: list[Job]):
        if not jobs:
            raise ValueError('Empty snapshots require operator review; no existing jobs were closed.')
        if len(jobs) > MAX_JOBS or len({j.id for j in jobs}) != len(jobs):
            raise ValueError('Snapshot size or unique identifiers failed validation.')
        if any(j.is_demo or j.source_key != 'greenhouse:' + run['board'] for j in jobs):
            raise ValueError('Snapshot provenance failed validation.')
        payload = [j.model_dump() for j in jobs]
        with self.store.connect() as conn:
            row = self.guard(conn, run)
            if row['snapshot'] is not None:
                raise LeaseLost('A snapshot already exists.')
            conn.execute('UPDATE import_runs SET snapshot=%s::jsonb,total=%s,snapshot_at=now(),updated_at=now() WHERE id=%s',
                         (json.dumps(payload), len(payload), run['id']))
        run.update(snapshot=payload, total=len(payload))

    def reserve_budget(self, run, count: int) -> bool:
        cap = max(5, min(int(os.getenv('DAILY_IMPORT_JOB_LIMIT', '200')), 2000))
        with self.store.connect() as conn:
            self.guard(conn, run)
            row = conn.execute("""INSERT INTO usage_buckets(day,kind,used) VALUES(CURRENT_DATE,'import_jobs',%s)
                ON CONFLICT(day,kind) DO UPDATE SET used=usage_buckets.used+EXCLUDED.used
                WHERE usage_buckets.used+EXCLUDED.used <= %s RETURNING used""", (count, cap)).fetchone()
            if not row:
                conn.execute("""UPDATE import_runs SET state='retry',error_code='daily_budget',
                    available_at=(CURRENT_DATE+1)::timestamptz,lease_token=NULL,lease_until=NULL,updated_at=now()
                    WHERE id=%s""", (run['id'],))
        return bool(row)

    def checkpoint(self, conn, run, count: int):
        """Called INSIDE the same transaction as the corresponding job writes."""
        row = self.guard(conn, run)
        done = row['processed'] + count
        if not row['snapshot'] or done > row['total'] or count < 1:
            raise LeaseLost('Invalid snapshot checkpoint.')
        complete = done == row['total']
        if complete:
            # Closure happens only after every persisted snapshot row has been
            # indexed, atomically with the final batch. Failures never reconcile.
            ids = [job['id'] for job in row['snapshot']]
            conn.execute("""UPDATE jobs SET active=false,payload=jsonb_set(payload,'{active}','false'::jsonb)
                WHERE source_key=%s AND NOT(id=ANY(%s))""", ('greenhouse:' + row['board'], ids))
        conn.execute("""UPDATE import_runs SET processed=%s,state=%s,error_code=NULL,
            lease_token=NULL,lease_until=NULL,available_at=now(),updated_at=now(),
            finished_at=CASE WHEN %s THEN now() ELSE NULL END,
            snapshot=CASE WHEN %s THEN NULL ELSE snapshot END WHERE id=%s""",
            (done, 'succeeded' if complete else 'queued', complete, complete, run['id']))

    def fail(self, run, code='upstream_unavailable', permanent=False):
        with self.store.connect() as conn:
            row = self.guard(conn, run)
            failures = row['failures'] + 1
            terminal = permanent or failures >= 3
            conn.execute("""UPDATE import_runs SET state=%s,failures=%s,error_code=%s,
                available_at=now()+(%s * interval '1 second'),updated_at=now(),
                lease_token=NULL,lease_until=NULL,
                finished_at=CASE WHEN %s THEN now() ELSE NULL END,
                snapshot=CASE WHEN %s THEN NULL ELSE snapshot END WHERE id=%s""",
                ('failed' if terminal else 'retry', failures, code, 30 * 2 ** (failures-1), terminal, terminal, run['id']))

    def prune(self, days=7) -> int:
        if not 1 <= days <= 90:
            raise ValueError('Retention must be 1–90 days.')
        with self.store.connect() as conn:
            result = conn.execute("DELETE FROM import_runs WHERE finished_at < now()-(%s * interval '1 day') AND state IN ('succeeded','failed','cancelled')", (days,))
        return result.rowcount
