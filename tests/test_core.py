import json
import math
from pathlib import Path

import pytest
from pydantic import ValidationError

from rolecraft.models import Filters, Job, SearchRequest
from rolecraft.search import fuse, search
from rolecraft.store import demo_store, where_clause
from rolecraft.text import chunk_text, concept_vector, cosine, evidence, plain_text


@pytest.fixture
def store():
    return demo_store()


def test_demo_is_real_sql_and_all_fictional(store):
    assert store.db.execute('SELECT count(*) FROM jobs').fetchone()[0] == 24
    assert all(j['is_demo'] and j['source_url'] is None for j in store.jobs)


def test_browse_pages_have_no_duplicates(store):
    one = search(SearchRequest(), store)
    two = search(SearchRequest(page=2), store)
    assert one['total'] == 24
    assert len(one['jobs']) == len(two['jobs']) == 12
    assert not {j['id'] for j in one['jobs']} & {j['id'] for j in two['jobs']}
    assert one['has_more'] and not two['has_more']


@pytest.mark.parametrize('filters',[
    {'country':'Canada'}, {'country':'United States'}, {'work_mode':'Remote'},
    {'work_mode':'Hybrid','level':'Senior'}, {'country':'Canada','city':'Toronto'},
    {'min_salary':120000,'currency':'CAD'}, {'min_salary':165000,'currency':'USD'},
    {'min_salary':70000,'currency':'EUR'}, {'country':'Canada','work_mode':'Remote','min_salary':140000,'level':'Senior'},
])
def test_hard_filters_always_hold(filters,store):
    request = SearchRequest(query='engineer meaningful calm learning', filters=Filters(**filters), page_size=24)
    result = search(request,store)
    assert result['jobs']
    for j in result['jobs']:
        for key,val in filters.items():
            if key == 'min_salary': assert j['salary_min'] is not None and j['salary_min'] >= val
            elif key == 'currency' and not filters.get('min_salary'): pass
            elif key == 'city': assert val.lower() in j['city'].lower()
            else: assert j[key] == val


def test_no_currency_comparison_without_minimum(store):
    assert search(SearchRequest(filters=Filters(currency='EUR')),store)['total'] == 24


def test_unknown_salary_never_passes_minimum(store):
    result = search(SearchRequest(filters=Filters(min_salary=1),page_size=24),store)
    assert 'Evergreen Systems' not in {j['company'] for j in result['jobs']}


@pytest.mark.parametrize('city',["' OR 1=1 --",'%', '_',"Toronto'; DROP TABLE jobs; --"])
def test_sql_injection_and_literal_wildcards(city,store):
    assert search(SearchRequest(filters=Filters(city=city)),store)['total'] == 0
    assert store.status()['jobs'] == 24


def test_parameterized_postgres_filters():
    statement,args = where_clause(Filters(city="' OR 1=1",min_salary=120000),True)
    assert "' OR 1=1" not in statement
    assert '%s' in statement and '%\' or 1=1%' in args


def test_semantic_query_surfaces_documented_focus(store):
    result = search(SearchRequest(query='quiet maker schedule', preferences=['async','balance'],semantic_weight=1),store)
    assert result['trace']['semantic_candidates'] > 0
    assert result['jobs'][0]['company'] in {'Fieldwork','Northstar Labs','Paperplane','Moss Climate','Openmeadow','Bluehour'}
    assert result['trace']['embedding'].endswith('not a neural model')


def test_keyword_mode_does_not_include_vector_only_results(store):
    result=search(SearchRequest(query='PostgreSQL',semantic_weight=0,page_size=24),store)
    assert result['jobs'] and result['trace']['semantic_candidates'] == 0
    assert all('postgresql' in (j['description']+' '+' '.join(j['skills'])).lower() for j in result['jobs'])


def test_zero_results_for_unknown_query(store):
    # Keyword-only mode has strict term retrieval. Demo vector hashes may collide;
    # that limitation is documented rather than hidden behind invented confidence.
    assert search(SearchRequest(query='zyxwvu987654',semantic_weight=0),store)['total'] == 0


def test_fusion_uses_rank_not_raw_scores():
    scores=fuse([('a',9000),('b',100)],[('b',.5),('c',.4)],.5)
    assert scores['b'] > scores['a'] > scores['c']
    assert fuse([('a',1)],[('b',1)],0) == {'a':1/61}
    assert fuse([('a',1)],[('b',1)],1) == {'b':1/61}


def test_evidence_is_verbatim_and_corpus_is_immutable(store):
    result=search(SearchRequest(query='backend calm',preferences=['async','balance']),store)
    for job in result['jobs']:
        assert all(e['quote'] in job['description'] for e in job['evidence'])
    assert all('scores' not in j and 'evidence' not in j for j in store.jobs)


@pytest.mark.parametrize('text',['word '*1700,'A'*7000,'Climate 🌿 '*1000,'first paragraph.\n\n'+'second '*600])
def test_chunk_bounds_and_exact_source_spans(text):
    chunks=chunk_text(text)
    assert chunks and all(len(c)<=1100 and c in text for c in chunks)
    assert chunks[-1].endswith(text.rstrip()[-10:])


@pytest.mark.parametrize('size,overlap',[(99,0),(200,100),(200,-1)])
def test_invalid_chunk_configuration(size,overlap):
    with pytest.raises(ValueError):chunk_text('hello',size,overlap)


def test_html_stripping_and_scripts():
    assert plain_text('<h1>Engineer</h1><script>alert(1)</script><p>Build &amp; learn.</p>') == 'Engineer\nBuild & learn.'


def test_embedding_is_deterministic_and_normalized():
    a=concept_vector('calm async python')
    assert a == concept_vector('calm async python')
    assert math.isclose(cosine(a,a),1)
    assert len(a)==256
    with pytest.raises(ValueError):cosine([1],[1,2])


@pytest.mark.parametrize('payload',[{'query':'x'*601},{'semantic_weight':1.01},{'page':0},{'page_size':100},{'filters':{'country':'Atlantis'}},{'filters':{'min_salary':-1}},{'preferences':['not-a-vibe']},{'unknown':1}])
def test_input_validation(payload):
    with pytest.raises(ValidationError):SearchRequest.model_validate(payload)


def test_preferences_deduplicated():
    assert SearchRequest(preferences=['async','async']).preferences == ['async']


def test_invalid_salary_contract(store):
    row=dict(store.jobs[0]);row['salary_min']=100;row['salary_max']=1
    with pytest.raises(ValidationError):Job.model_validate(row)
    row=dict(store.jobs[0]);row['currency']=None
    with pytest.raises(ValidationError):Job.model_validate(row)


@pytest.mark.parametrize('url',['javascript:alert(1)','http://example.org','https://user:pass@example.org'])
def test_unsafe_source_links(url,store):
    with pytest.raises(ValidationError):Job.model_validate(dict(store.jobs[0],source_url=url))
