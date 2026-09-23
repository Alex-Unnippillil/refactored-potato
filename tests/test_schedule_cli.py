import json
import sys

import pytest

from scripts.manage import main


def test_schedule_cli_requires_database(monkeypatch,capsys):
    monkeypatch.delenv('DATABASE_URL',raising=False)
    monkeypatch.setattr(sys,'argv',['manage.py','schedules','list'])
    assert main()==1
    assert 'read-only' in capsys.readouterr().err


@pytest.mark.parametrize('arguments,method,expected',[
    (['add','Acme','--hours','12'],'create',('Acme',12,False)),
    (['update','acme','--hours','24','--state','enabled','--revision','3'],'update',('acme',24,True,3)),
    (['remove','acme','--revision','3'],'remove',('acme',3)),
    (['run','acme','--revision','3'],'run_now',('acme',3)),
])
def test_schedule_cli_contract(monkeypatch,capsys,arguments,method,expected):
    calls=[]
    class Fake:
        def __getattr__(self,key):
            def run(*args):
                calls.append((key,args))
                return ({'id':'test'},True) if key=='run_now' else {'ok':True}
            return run
    monkeypatch.setenv('DATABASE_URL','test-configuration-only')
    monkeypatch.setenv('OPENAI_API_KEY','test-not-real')
    monkeypatch.setattr('rolecraft.schedules.SourceSchedules',Fake)
    monkeypatch.setattr(sys,'argv',['manage.py','schedules',*arguments])
    assert main()==0 and calls==[(method,expected)]
    assert json.loads(capsys.readouterr().out)


def test_schedule_cli_does_not_leak_driver_details(monkeypatch,capsys):
    class Broken:
        def overview(self):
            raise RuntimeError('SECRET driver detail')
    monkeypatch.setenv('DATABASE_URL','test-only')
    monkeypatch.setattr('rolecraft.schedules.SourceSchedules',Broken)
    monkeypatch.setattr(sys,'argv',['manage.py','schedules','list'])
    assert main()==1
    assert 'SECRET' not in capsys.readouterr().err
