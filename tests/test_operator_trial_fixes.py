import csv
import io
import pytest
from tests.test_operator_workspace import world,write
from tests.test_v22_independent_acceptance import independent_http
from api.operator_service import csv_cell


def test_paging_search_and_out_of_range_clamp(world):
    c,core,adapter,b,other,_=world
    c.executemany('INSERT INTO questions(product_id,text) VALUES(?,?)',[(b['product_id'],f'question {i}') for i in range(41)]+[(b['product_id'],'epub vs mobi which is better'),(other['product_id'],'epub vs mobi which is better')]);c.commit()
    result=adapter.paged(c,b,'questions',q='epub vs mobi which is better')
    assert result['total']==1 and result['items'][0]['product_id']==b['product_id']
    result=adapter.paged(c,b,'questions',page=999)
    assert result['page']==3 and len(result['items'])==2


def test_current_engines_and_align_only_active_monitor_configuration(world):
    c,core,adapter,b,other,_=world
    assert adapter.dispatch(c,b,'GET','meta')['engines']==['ChatGPT','Gemini','Copilot','Perplexity']
    for pid,status in [(b['product_id'],'active'),(b['product_id'],'paused'),(other['product_id'],'active')]:
        c.execute('INSERT INTO monitors(product_id,query_text,target_engines,status) VALUES(?,?,?,?)',(pid,'test','ChatGPT,Claude,Perplexity',status))
    c.execute("INSERT INTO citations(product_id,query_text,engine) VALUES(?,?,'Claude')",(b['product_id'],'historical result'));c.commit()
    c.execute('INSERT INTO monitors(product_id,query_text,target_engines,status) VALUES(?,?,?,?)',(b['product_id'],'legacy JSON','["chatgpt", "claude", "gemini"]','active'));c.commit()
    result=write(world,f'products/{b["product_id"]}/monitors/align-engines')['result']
    assert result['changed']==2
    assert c.execute('SELECT target_engines FROM monitors WHERE product_id=? AND status=?',(b['product_id'],'active')).fetchone()[0]=='ChatGPT,Copilot,Perplexity'
    assert c.execute('SELECT target_engines FROM monitors WHERE product_id=? AND status=?',(b['product_id'],'paused')).fetchone()[0]=='ChatGPT,Claude,Perplexity'
    assert c.execute('SELECT engine FROM citations').fetchone()[0]=='Claude'
    assert write(world,f'products/{b["product_id"]}/monitors/align-engines')['result']['changed']==0


def test_formula_escape():
    assert csv_cell('=HYPERLINK("evil")').startswith("'=")
    assert csv_cell('  @SUM(A1)').startswith("'")
    assert csv_cell(None)=='' and csv_cell(5)==5
    assert csv_cell('ordinary text')=='ordinary text'


def test_export_http_scope_filters_revocation_and_customer_alias(independent_http):
    from api import growth_core,auth
    client,prefix,grant,post,headers=independent_http
    grant('author',['read','operate']);grant('client',['read','operate'])
    context=client.get(prefix+'/operator/context',headers=headers('author')).json()
    conn=growth_core.connection()
    conn.executemany('INSERT INTO questions(product_id,text,notes) VALUES(?,?,?)',[(context['product_id'],f'export fixture {i}','=SUM(1,2)') for i in range(121)])
    conn.execute('INSERT INTO products(name) VALUES(?)',('Foreign',));foreign=conn.execute('SELECT max(id) FROM products').fetchone()[0]
    conn.execute('INSERT INTO questions(product_id,text) VALUES(?,?)',(foreign,'FOREIGN_SENTINEL'));conn.commit();conn.close()
    result=client.get(prefix+'/operator/export/questions',headers=headers('author'))
    assert result.status_code==200,result.text
    data=result.json();rows=list(csv.reader(io.StringIO(data['csv'].lstrip('\ufeff'))))
    assert data['total']==121 and len(rows)==122 and 'FOREIGN_SENTINEL' not in data['csv']
    assert rows[1][-1]=="'=SUM(1,2)" and result.headers['cache-control']=='no-store'
    filtered=client.get(prefix+'/operator/export/questions?q=fixture+120',headers=headers('author'))
    assert filtered.json()['total']==1
    assert client.get('/customer'+prefix+'/operator/export/questions',headers=headers('client')).status_code==200
    assert client.post('/ui/customer/session',json={'api_key':'client'},headers={'Origin':'http://testserver'}).status_code==200
    attachment='/ui/customer/operator-export/DEMO-PRJ-1/questions?q=fixture+120'
    response=client.get(attachment)
    assert response.status_code==200 and response.headers['content-disposition'].startswith('attachment;')
    assert 'export fixture 120' in response.text and 'export fixture 119' not in response.text
    assert client.get(attachment+'&tenant_id=FOREIGN').status_code==403
    grant('client',['read'])
    assert client.get('/customer'+prefix+'/operator/export/questions',headers=headers('client')).status_code==403
    assert client.get(attachment).status_code==403
    assert client.get(prefix+'/operator/export/observations',headers=headers('author')).status_code==404
    assert client.get(prefix+'/operator/export/questions?status=invalid',headers=headers('author')).status_code==422
