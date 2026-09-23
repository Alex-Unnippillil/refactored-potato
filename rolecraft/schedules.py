"""Opt-in, database-clock source refresh scheduling over the existing import queue.

A row lock serializes config changes and dispatch; run admission and advancing
its deadline commit together. Missed intervals coalesce into one import. No
provider is called here, and the process holds no authoritative schedule state.
"""
from __future__ import annotations

import os

from .import_queue import ImportQueue, QueueBudget, QueueConflict, board_token
from .models import Filters
from .store import where_clause

MAX_SCHEDULES = 20
MIN_INTERVAL_HOURS = 6
MAX_INTERVAL_HOURS = 168


class ScheduleMissing(ValueError):
    pass


def scheduler_enabled() -> bool:
    return os.getenv('IMPORT_SCHEDULER_ENABLED', '').strip().lower() in ('1', 'true')


def validate_config(interval_hours: int, enabled: bool) -> None:
    if type(interval_hours) is not int or not MIN_INTERVAL_HOURS <= interval_hours <= MAX_INTERVAL_HOURS:
        raise ValueError('Refresh intervals must be whole hours between 6 and 168.')
    if type(enabled) is not bool:
        raise ValueError('Enabled must be a boolean.')


class SourceSchedules:
    def __init__(self, queue: ImportQueue | None = None):
        self.queue = queue or ImportQueue()
        self.store = self.queue.store

    def create(self, board: str, interval_hours: int = 24, enabled: bool = False) -> dict:
        board = board_token(board)
        validate_config(interval_hours, enabled)
        with self.store.connect() as conn:
            conn.execute("SELECT pg_advisory_xact_lock(hashtext('rolecraft:schedule-admission'))")
            if conn.execute('SELECT 1 FROM source_schedules WHERE board=%s', (board,)).fetchone():
                raise QueueConflict('This board already has a schedule. Refresh and edit the existing one.')
            if conn.execute('SELECT count(*) AS n FROM source_schedules').fetchone()['n'] >= MAX_SCHEDULES:
                raise QueueConflict('At most 20 source schedules may be stored. Remove an unused schedule first.')
            row = conn.execute('''INSERT INTO source_schedules(board,interval_hours,enabled)
                VALUES(%s,%s,%s) RETURNING *''', (board, interval_hours, enabled)).fetchone()
        return dict(row)

    @staticmethod
    def _locked(conn, board: str, revision: int) -> dict:
        row = conn.execute('SELECT * FROM source_schedules WHERE board=%s FOR UPDATE', (board,)).fetchone()
        if not row:
            raise ScheduleMissing('This source schedule no longer exists.')
        if type(revision) is not int or row['revision'] != revision:
            raise QueueConflict('This schedule changed in another session. Refresh before trying again.')
        return row

    def update(self, board: str, interval_hours: int, enabled: bool, revision: int) -> dict:
        board = board_token(board)
        validate_config(interval_hours, enabled)
        with self.store.connect() as conn:
            old = self._locked(conn, board, revision)
            # Resume is due immediately; interval edits restart the cadence.
            # Pausing never cancels an admitted run or closes indexed jobs.
            row = conn.execute('''UPDATE source_schedules SET interval_hours=%s,enabled=%s,
                revision=revision+1,updated_at=now(),
                next_run_at=CASE WHEN %s THEN now() WHEN %s THEN now()+(%s * interval '1 hour')
                    ELSE next_run_at END WHERE board=%s RETURNING *''',
                (interval_hours, enabled, enabled and not old['enabled'], interval_hours != old['interval_hours'], interval_hours, board)).fetchone()
        return dict(row)

    def remove(self, board: str, revision: int) -> None:
        board = board_token(board)
        with self.store.connect() as conn:
            self._locked(conn, board, revision)
            conn.execute('DELETE FROM source_schedules WHERE board=%s', (board,))

    def run_now(self, board: str, revision: int) -> tuple[dict, bool]:
        board = board_token(board)
        with self.store.connect() as conn:
            schedule = self._locked(conn, board, revision)
            run, created = self.queue.enqueue_in_transaction(conn, board)
            conn.execute('''UPDATE source_schedules SET last_run_id=%s,last_dispatch_at=now(),dispatch_status=%s,
                last_queued_at=CASE WHEN %s THEN now() ELSE last_queued_at END,
                next_run_at=CASE WHEN %s THEN now()+(%s * interval '1 hour') ELSE next_run_at END
                WHERE board=%s''', (run['id'], 'queued' if created else 'active', created,
                                    created, schedule['interval_hours'], board))
        return run, created

    def dispatch_due(self) -> dict | None:
        """Dispatch at most one due schedule. Called only by an opted-in worker.

        Lock order is schedule row -> source admission lock -> queue admission
        lock. Queue workers never lock schedule rows. Do not invert this order.
        """
        with self.store.connect() as conn:
            conn.execute("INSERT INTO worker_heartbeat(name) VALUES('source-scheduler') ON CONFLICT(name) DO UPDATE SET last_seen=now()")
            schedule = conn.execute('''SELECT * FROM source_schedules
                WHERE enabled AND next_run_at <= now()
                ORDER BY next_run_at,board FOR UPDATE SKIP LOCKED LIMIT 1''').fetchone()
            if not schedule:
                return None
            board = schedule['board']
            run, created = None, False
            try:
                run, created = self.queue.enqueue_in_transaction(conn, board)
                status = 'queued' if created else 'active'
            except QueueBudget:
                status = 'daily_budget'
            except QueueConflict:
                status = 'queue_full'
            # No interval replay after downtime. Busy boards/queues get a
            # five-minute cooldown; the UTC admission budget resets at midnight.
            conn.execute('''UPDATE source_schedules SET last_dispatch_at=now(),dispatch_status=%s,
                last_run_id=COALESCE(%s,last_run_id),
                last_queued_at=CASE WHEN %s THEN now() ELSE last_queued_at END,
                next_run_at=CASE WHEN %s='queued' THEN now()+(interval_hours * interval '1 hour')
                    WHEN %s='daily_budget' THEN (CURRENT_DATE+1)::timestamptz
                    ELSE now()+interval '5 minutes' END WHERE board=%s''',
                (status, run['id'] if run else None, created, status, status, board))
        return {'board': board, 'status': status, 'created': created}

    def overview(self) -> dict:
        condition, args = where_clause(Filters(), True)
        with self.store.connect() as conn:
            # Use exactly the retrieval freshness/expiry predicates, not a
            # separate approximate definition of a "searchable" role.
            rows = conn.execute('''SELECT s.*,r.state AS last_run_state,r.error_code AS last_run_error,
                r.processed AS last_run_processed,r.total AS last_run_total,
                j.active_roles,j.searchable_roles,j.last_indexed_at,
                (SELECT max(finished_at) FROM import_runs h
                    WHERE h.board=s.board AND h.state='succeeded') AS last_retained_success_at
                FROM source_schedules s LEFT JOIN import_runs r ON r.id=s.last_run_id
                LEFT JOIN LATERAL (
                    SELECT count(*) FILTER(WHERE active) AS active_roles,
                    count(*) FILTER(WHERE ''' + condition + ''') AS searchable_roles,
                    max(last_seen) AS last_indexed_at FROM jobs WHERE source_key='greenhouse:' || s.board
                ) j ON true ORDER BY s.enabled DESC,s.next_run_at,s.board''', args).fetchall()
            worker = conn.execute("SELECT last_seen,last_seen > now()-interval '15 minutes' AS recent FROM worker_heartbeat WHERE name='source-scheduler'").fetchone()
            usage = {row['kind']: row['used'] for row in conn.execute("SELECT kind,used FROM usage_buckets WHERE day=CURRENT_DATE AND kind IN ('queue_requests','import_jobs')").fetchall()}
        limits = {'queue_requests': 10, 'import_jobs': max(5, min(int(os.getenv('DAILY_IMPORT_JOB_LIMIT', '200')), 2000))}
        return {'schedules': [dict(row) for row in rows],
                'scheduler': {'configured': scheduler_enabled(), 'worker': dict(worker) if worker else None},
                'budgets': {kind: {'used': usage.get(kind, 0), 'limit': cap,
                                  'remaining': max(0, cap-usage.get(kind, 0))} for kind, cap in limits.items()}}
