"""Primary-agent final acceptance, distinct from the independent audit tests.

All data is fixture-owned. No original database, account or external provider writes.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3
import time
from uuid import uuid4

import pytest
from fastapi import HTTPException
from api import auth, state, growth_core, personal_identity
from api.commercial_guard import write_guard
from tests.test_operator_workspace import world, write
from tests.test_v22_independent_acceptance import independent_http, identity_env


def test_sql_paging_one_thousand_questions_and_literal_search(world,record_property):
    c,core,adapter,b,other,_=world
    c.executemany('INSERT INTO questions(product_id,text,source) VALUES(?,?,?)',
                  [(b['product_id'],f'fixture question {i:04d}','isolated') for i in range(1000)])
    c.execute('INSERT INTO questions(product_id,text) VALUES(?,?)',(other['product_id'],'FOREIGN_SENTINEL'))
    c.commit()
    trace=[];c.set_trace_callback(trace.append)
    start=time.perf_counter();ids=[]
    for page in range(1,51):
        data=adapter.paged(c,b,'questions',page=page,page_size=20)
        assert data['total']==1000 and data['pages']==50 and len(data['items'])==20
        ids.extend(r['id'] for r in data['items'])
        assert all(r['product_id']==b['product_id'] and len(r['_version'])==64 for r in data['items'])
    record_property('paging_1000_rows_50_pages_seconds',round(time.perf_counter()-start,4))
    assert len(set(ids))==1000
    assert any('SELECT * FROM questions WHERE product_id=' in sql and 'LIMIT 20 OFFSET' in sql for sql in trace)
    c.set_trace_callback(None)
    found=adapter.paged(c,b,'questions',q='question 0999')
    assert found['total']==1 and found['items'][0]['text']=='fixture question 0999'
    assert adapter.paged(c,b,'questions',q='%')['total']==0
    selected=adapter.paged(c,b,'questions',page=1,selected_ids=[ids[-1]])
    assert selected['selected_items'][0]['id']==ids[-1]
    alien=c.execute('SELECT id FROM questions WHERE product_id=?',(other['product_id'],)).fetchone()[0]
    with pytest.raises(core.ContractError):adapter.paged(c,b,'questions',selected_ids=[alien])
    with pytest.raises(core.ContractError):adapter.paged(c,b,'questions',page_size=10000)


def test_one_hundred_item_bulk_atomicity_and_replay(world,record_property):
    c,core,adapter,b,other,_=world
    path=f"products/{b['product_id']}/questions/bulk"
    body={'items':[{'text':f'100-item batch question {i}'} for i in range(100)]}
    revision=c.execute('SELECT revision FROM workspace_sites WHERE site_id=?',(b['site_id'],)).fetchone()[0]
    start=time.perf_counter()
    first=write(world,path,body,revision=revision,key='hundred-item-fixed-key')
    again=write(world,path,body,revision=revision,key='hundred-item-fixed-key')
    record_property('bulk_100_items_with_replay_seconds',round(time.perf_counter()-start,4))
    assert first==again and c.execute('SELECT count(*) FROM questions WHERE product_id=?',(b['product_id'],)).fetchone()[0]==100
    before=c.execute('SELECT count(*) FROM questions').fetchone()[0]
    with pytest.raises(Exception):
        write(world,path,{'items':[{'text':'must rollback'},{'text':'invalid foreign','persona_id':999999}]})
    assert c.execute('SELECT count(*) FROM questions').fetchone()[0]==before


def test_commercial_stop_serializes_with_inflight_short_command(independent_http):
    client,prefix,grant,post,headers=independent_http
    grant('author',['operate'])
    ctx=auth.verify_api_key('author')
    project=asyncio.run(growth_core.project_scope('DEMO-PRJ-1',ctx))
    def stop(timeout):
        c=sqlite3.connect(state.active_db_path,timeout=timeout)
        try:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute("SELECT payload FROM clients WHERE id='DEMO-CLI-1'").fetchone()
            data=json.loads(row[0]);data['is_active']=False
            c.execute("UPDATE clients SET payload=? WHERE id='DEMO-CLI-1'",(json.dumps(data),));c.commit()
            return 'stopped'
        except sqlite3.OperationalError:return 'locked'
        finally:c.close()
    with write_guard(ctx,project):
        with ThreadPoolExecutor(1) as pool:
            assert pool.submit(stop,0.1).result(timeout=3)=='locked'
    assert stop(1)=='stopped'
    denied=client.post(prefix+'/question',headers=headers('author'),json={'revision':1,'payload':{'text':'must not write after committed stop'}})
    assert denied.status_code in {403,404}
    response=client.post(prefix+'/operator/api/questions',headers={**headers('author'),'If-Match':'1'},json={'text':'alternate path denied'})
    assert response.status_code in {403,404}


def test_personal_revocation_serializes_and_cannot_reuse_old_context(independent_http,identity_env):
    client,prefix,grant,post,headers=independent_http
    subject='wp:fixture:123';token='person_'+uuid4().hex
    c=personal_identity.connect()
    c.execute('INSERT INTO identity_memberships VALUES(?,?,?,?,?,?)',(subject,'DEMO-GEO','HQ_TECHNICAL',None,1,1))
    c.execute('INSERT INTO identity_sessions VALUES(?,?,?)',(personal_identity.digest(token),subject,int(time.time())+600));c.commit();c.close()
    ctx=personal_identity.token_context(token)
    from types import SimpleNamespace
    project=SimpleNamespace(tenant_id='DEMO-GEO',project_id='DEMO-PRJ-1',client_id='DEMO-CLI-1')
    def revoke(timeout):
        con=sqlite3.connect(__import__('os').environ['GEO_IDENTITY_DB'],timeout=timeout)
        try:
            con.execute('BEGIN IMMEDIATE');con.execute('DELETE FROM identity_sessions WHERE subject=?',(subject,));con.commit();return 'revoked'
        except sqlite3.OperationalError:return 'locked'
        finally:con.close()
    with write_guard(ctx,project):
        with ThreadPoolExecutor(1) as pool:
            assert pool.submit(revoke,0.1).result(timeout=3)=='locked'
    assert revoke(1)=='revoked'
    assert personal_identity.token_context(token) is None
    with pytest.raises(HTTPException) as denied:
        with write_guard(ctx,project):pass
    assert denied.value.status_code==401


def test_real_mode_rejects_integration_actor_even_with_professional_grant(independent_http,monkeypatch):
    client,prefix,grant,post,headers=independent_http
    grant('author',['operate'])
    monkeypatch.delenv('GEO_OPERATOR_ALLOW_SERVICE_ACTORS',raising=False)
    monkeypatch.delenv('GEO_GROWTH_SANDBOX',raising=False)
    assert client.get(prefix+'/operator/context',headers=headers('author')).status_code==403
    denied=client.post(prefix+'/question',headers=headers('author'),json={'revision':1,'payload':{'text':'service credential is not a human'}})
    assert denied.status_code==403


def test_explicit_revoke_cannot_fall_back_to_legacy_editor_grant(independent_http):
    client,prefix,grant,post,headers=independent_http
    subject=auth.verify_api_key('client').user_id
    assert post('root','grant',{'subject':subject,'enabled':True}).status_code==200
    assert post('client','question',{'text':'Legacy explicit editor permitted'}).status_code==200
    grant('client',[])
    # Even a legacy grant recreated later cannot override the new explicit denial.
    assert post('root','grant',{'subject':subject,'enabled':True}).status_code==200
    assert post('client','question',{'text':'Must remain denied'}).status_code==403


def test_assigned_execution_is_distinct_from_professional_and_approval(independent_http):
    client,prefix,grant,post,headers=independent_http
    grant('client',['prepare','execute_assigned'])
    subject=auth.verify_api_key('client').user_id
    c=growth_core.connection()
    site=c.execute("SELECT site_id FROM workspace_bindings WHERE project_key='DEMO-GEO/DEMO-PRJ-1'").fetchone()[0]
    action=c.execute("INSERT INTO actions(site_id,action_type,title,status,target_context) VALUES(?,'CONTENT_UPDATE','Approved fixture action','approved','fixture')",(site,)).lastrowid
    other=c.execute("INSERT INTO actions(site_id,action_type,title,status,target_context) VALUES(?,'CONTENT_UPDATE','Not assigned to this person','approved','other')",(site,)).lastrowid
    c.execute('INSERT INTO workspace_assignments VALUES(?,?)',(action,subject));c.commit();c.close()
    assert client.get(prefix+'/operator/context',headers=headers('client')).status_code==403
    assert post('client','action_status',{'action_id':other,'status':'in_progress'}).status_code==403
    assert post('client','action_status',{'action_id':action,'status':'approved'}).status_code==403
    assert post('client','action_status',{'action_id':action,'status':'in_progress'}).status_code==200
    assert post('client','action_status',{'action_id':action,'status':'closed'}).status_code==403
    grant('client',[])
    assert post('client','action_status',{'action_id':action,'status':'in_progress'}).status_code==403
