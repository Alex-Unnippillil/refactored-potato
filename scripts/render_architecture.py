"""Render the README architecture overview without external assets or fonts."""
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
parts = ['''<svg xmlns="http://www.w3.org/2000/svg" width="1440" height="1160" viewBox="0 0 1440 1160" role="img" aria-labelledby="title desc">
<title id="title">Rolecraft: hybrid search and durable ingestion</title><desc id="desc">Two separate paths: SQL-filtered hybrid retrieval, and a database-backed Greenhouse import worker with fenced atomic progress. Demo data remains isolated.</desc>
<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto-start-reverse"><path d="M0,0 L8,4 L0,8" fill="#6c8751"/></marker></defs>
<rect width="1440" height="1160" fill="#f7f8f3"/>
<g font-family="Arial, Helvetica, sans-serif" fill="#183d2e">''']


def text(x,y,value,size=15,bold=False,fill='#183d2e'):
    parts.append(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{700 if bold else 400}" fill="{fill}">{escape(value)}</text>')


def rect(x,y,w,h,fill='#ffffff',stroke='#c6d5ba'):
    parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="{fill}" stroke="{stroke}"/>')


def box(x,y,label,title,lines):
    rect(x,y,300,137)
    text(x+20,y+26,label,11,True,'#5e7a47')
    text(x+20,y+54,title,18,True)
    for i,line in enumerate(lines):text(x+20,y+80+21*i,line,13,False,'#52634d')


def arrow(x1,y1,x2,y2):
    parts.append(f'<path d="M{x1} {y1} L{x2} {y2}" fill="none" stroke="#6c8751" stroke-width="2" marker-end="url(#arrow)"/>')


text(48,58,'ROLECRAFT 1.1',14,True,'#5e7a47')
text(48,103,'Hybrid search. Durable imports. Visible operations.',32,True)
text(48,134,'The database owns durable state. The web server never pretends an in-process task is a persistent worker.',16,False,'#52634d')
rect(28,168,1384,222,'#edf3e5')
text(48,197,'SEARCH PATH  /  Browser → authenticated FastAPI → the same SQL-eligible records',12,True)
x=[48,396,744,1092]
box(x[0],219,'01 / REQUEST','What matters to you',['Natural-language relevance','Explicit location / salary / work style','Workspace token in live mode'])
box(x[1],219,'02 / CONSTRAIN','SQL hard filters',['Parameterized values only','Active + fresh + non-expired jobs','Unknown pay does not pass a floor'])
box(x[2],219,'03 / RETRIEVE','Words + meaning',['PostgreSQL full-text retrieval','pgvector exact cosine on chunks','Both branches obey the filters'])
box(x[3],219,'04 / EXPLAIN','Fuse, rank, cite',['Job-level deduplication + RRF','Optional Cohere re-ranking','Verified excerpts; no culture scores'])
for a,b in zip(x,x[1:]):arrow(a+301,288,b-5,288)
rect(28,415,1384,458,'#ffffff')
text(48,448,'INGESTION PATH  /  Operator API + PostgreSQL queue + a SEPARATE worker runtime',12,True)
box(x[0],475,'01 / OPERATOR','Queue an allowed board',['Separate ingestion token','202 = admitted, not completed','One active run per board'])
box(x[1],475,'02 / PERSIST','PostgreSQL import queue',['Run state + progress + retry time','Admission and job-attempt budgets','Survives web / worker restarts'])
box(x[2],475,'03 / CLAIM','Independent worker',['SKIP LOCKED across boards','10-minute lease + fencing token','No long-running Vercel request'])
box(x[3],475,'04 / CAPTURE','One source snapshot',['Greenhouse public Job Board API','Validate all records before indexing','12 MB / 200-role safety bounds'])
for a,b in zip(x,x[1:]):arrow(a+301,544,b-5,544)
arrow(1242,613,1242,674)
text(1089,651,'Persist normalized snapshot once',12,False,'#52634d')
box(x[3],684,'05 / RESUME','Read the saved snapshot',['Stable IDs; no shifting offsets','At most five jobs per work unit','Reject empty / expired snapshots'])
box(x[2],684,'06 / EMBED','Chunk the next batch',['1,100 characters / 160 overlap','OpenAI 1,536-dimensional vectors','Network calls before transaction'])
box(x[1],684,'07 / COMMIT','Fence + atomic checkpoint',['Check current lease and cursor','Write jobs, vectors AND progress','Rollback leaves no cursor ahead'])
box(x[0],684,'08 / FINISH OR RESUME','Safe reconciliation',['More rows: requeue same snapshot','Final success: close missing roles','Cancel / failure: keep prior batches'])
for a,b in zip(list(reversed(x)),list(reversed(x))[1:]):arrow(a-2,752,b+305,752)
text(48,850,'Retries resume saved progress. Stale or cancelled workers cannot commit. Provider billing is at-least-once, not exactly-once.',13,False,'#52634d')
rect(48,900,640,110,'#edf3e5');text(69,931,'DURABLE DATA',12,True,'#5e7a47')
text(69,957,'jobs + job_chunks + sources + import_runs',17,True)
text(69,985,'Full-text / vectors / provenance / cursor / heartbeat / daily budgets',13,False,'#52634d')
rect(710,900,682,110,'#edf3e5');text(731,931,'OPERATIONS & TRUST BOUNDARY',12,True,'#5e7a47')
text(731,957,'/operations  ·  /api/readiness  ·  /api/health',17,True)
text(731,985,'Real database checks. Credential presence is NOT provider health.',13,False,'#52634d')
rect(48,1035,1344,90,'#fff4dc','#d8c69f')
text(69,1065,'ISOLATED, NO-KEY DEMO — DATABASE_URL ABSENT',12,True,'#7b652e')
text(69,1096,'24 fictional roles · SQLite + FTS5 · deterministic concept vectors · no neural model, paid provider, live vacancies or worker',15,False,'#6a5b38')
parts.append('</g></svg>')
(ROOT/'docs/assets').mkdir(parents=True,exist_ok=True)
(ROOT/'docs/assets/architecture.svg').write_text('\n'.join(parts)+'\n')
