"""Persistent fictional canonical-core exercise, using the production domain services."""
import hashlib
import json
import sqlite3
from pathlib import Path
from api.growth_core import contract
from scripts.growth_workspace_setup import create_core


def seed(path, editor_subject):
    path=Path(path)
    if path.exists():
        c=sqlite3.connect(path)
        try:
            marker=c.execute("SELECT value FROM workspace_fixture_marker WHERE name='origin'").fetchone()
            if marker != ('fictional-growth-v1',):raise RuntimeError('Unknown Growth fixture')
            # Stable server-only credential file makes grants survive restart.
            return
        finally:c.close()
    create_core(path)
    c=sqlite3.connect(path);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON')
    core=contract()
    try:
        c.execute('CREATE TABLE workspace_fixture_marker(name TEXT PRIMARY KEY,value TEXT NOT NULL)')
        c.execute('INSERT INTO workspace_fixture_marker VALUES(?,?)',('origin','initializing-fictional-growth-v1'));c.commit()
        with core.atomic(c) as tx:
            core.bind(tx,project_key='DEMO-GEO/DEMO-PRJ-1',tenant='DEMO-GEO',client='DEMO-CLI-1',name='澄源工业｜虚拟演练',domain='https://chengyuan.example.test')
        b=core.binding(c,'DEMO-GEO/DEMO-PRJ-1','DEMO-GEO','DEMO-CLI-1')
        index=0
        def op(name,p):
            nonlocal index
            index+=1
            rev=c.execute('SELECT revision FROM workspace_sites WHERE site_id=?',(b['site_id'],)).fetchone()[0]
            return core.operate(c,b,name,p,revision=rev,key='seed-'+str(index),role='HQ_MANAGEMENT',subject='fictional-headquarters')
        op('brand',dict(name='澄源工业｜虚拟演练',market='US',target_customer='中小型制造企业',description='虚拟工业过滤设备企业。所有回答、排名与发布记录都是演示构造。'))
        page=op('page',dict(url='https://chengyuan.example.test/guide',title='工业过滤选型指南（虚拟）'))['id']
        op('fact',dict(fact_key='适用范围',fact_text='虚拟产品适用于中小型工厂，用于演练事实维护。',source_ref='虚拟产品说明'))
        op('persona',dict(name='工厂采购经理（虚拟）',description='负责过滤设备选型',pain_points='难以核对供应商适用范围',goals='获得可验证的选型依据'))
        op('scenario',dict(name='选型评估',description='比较工业过滤设备供应商',stage='consideration'))
        op('cluster',dict(name='工业过滤选型',description='围绕适用范围与维护成本回答问题'))
        op('entity',dict(name='澄源工业（虚拟）',type='brand',description='演示品牌'))
        op('brief',dict(title='补齐选型问答',body='说明适用范围、事实出处与限制。',content_type='FAQ',target_url='https://chengyuan.example.test/guide'))
        prompt='哪些工业过滤品牌适合中小型工厂？（虚拟问题）'
        q=op('question',{'text':prompt,'notes':'演示一个问题的真实核心对象流转，不代表总体趋势。'})['id']
        def obs(day,mentions):
            req=op('measurement_request',dict(question_id=q,note='虚拟'+('基线测量' if day==1 else '复测验证')))['id']
            p=dict(question_id=q,request_id=req,provider='chatgpt',model='fictional-model-v1',surface='chatgpt',language='Chinese',market='US',environment='sandbox',question_set_version='fictional-v1',collector_version='fictional-registration-v1',request_config_hash=hashlib.sha256(b'fictional-identical-config').hexdigest(),started_at=f'2026-10-{day:02d}T08:00:00+00:00',completed_at=f'2026-10-{day:02d}T08:10:00+00:00',observed_at=f'2026-10-{day:02d}T08:05:00+00:00',prompt_text=prompt,response_text='【构造回答】'+('可比较澄源工业等品牌，需核实实际适用范围。' if mentions else '需要先核实供应商的适用范围，暂无品牌提及。'),source_url='https://chengyuan.example.test/fictional-record/'+str(day),source_ref='fictional-'+str(day),brand_mentioned=mentions,citation_count=mentions,recommendation_level=2 if mentions else 0)
            o=op('observation',p)
            op('quality',dict(observation_id=o['id'],disposition='APPROVED',reason='仅核验演练结构与虚拟来源；不是平台实采',evidence_checked=True))
            return o
        base=obs(1,0)
        diag=op('diagnosis',dict(question_id=q,diagnosis_type='MISSING_PAGE',evidence_ids=[base['evidence_id']],title='选型页面信息不足（虚拟）',finding='构造回答没有引用品牌页面',rationale='此演练证据用于说明诊断与行动的链接',target_context='industrial filtration guide',page_ids=[page]))['diagnosis_id']
        op('diagnosis_status',dict(diagnosis_id=diag,status='confirmed'))
        action=op('action',dict(action_type='CONTENT_UPDATE',title='完善过滤选型指南（虚拟）',target_context='industrial filtration guide',description='补齐适用范围与来源',body='这是一份虚拟执行示例。',diagnosis_ids=[diag],page_ids=[page]))['action_id']
        op('action_status',dict(action_id=action,status='approved',note='总部批准虚拟行动'))
        op('action_status',dict(action_id=action,status='in_progress',note='演练执行记录'))
        op('publication',dict(action_id=action,page_id=page,published_url='https://chengyuan.example.test/guide',published_at='2026-10-03T08:00:00+00:00',title_snapshot='过滤选型指南（虚拟发布）',content_hash=hashlib.sha256(b'fictional-publication').hexdigest()))
        op('action_status',dict(action_id=action,status='published',note='仅登记虚拟发布快照，不曾访问外站'))
        comp=obs(8,1)
        result=op('compare',dict(baseline=base['run_id'],comparison=comp['run_id'],question=q))
        if not result['comparable']:raise RuntimeError(result['reason'])
        op('action_status',dict(action_id=action,status='measured',note='演练数据通过结构校验，不代表实际增长'))
        op('competitor',dict(name='蓝峰设备（虚拟）',domain='lanfeng.example.test',source='虚拟对照案例'))
        kw=op('keyword',dict(name='industrial filtration selection',search_intent='供应商比较',target_page_id=page))['id']
        for day,rank in [(1,18),(8,12)]:
            op('rank',dict(keyword_id=kw,search_engine='google',observed_at=f'2026-10-{day:02d}T08:00:00+00:00',source_observation_id='fictional-rank-'+str(day),rank=rank,url='https://chengyuan.example.test/guide',notes='虚拟构造排名，不是实测'))
        op('seo_diagnosis',dict(keyword_id=kw,search_engine='google'))
        op('report',dict(title='澄源工业 GEO 演练报告 · 固定快照'))
        op('grant',dict(subject=editor_subject,enabled=True))
        task=op('action',dict(action_type='FAQ_UPDATE',title='客户可执行的问答补充（虚拟）',target_context='industrial filtration guide',description='体验总部指派与客户执行',body='核对选型说明并开始执行。',diagnosis_ids=[diag],page_ids=[page]))['action_id']
        op('action_status',dict(action_id=task,status='approved',note='授权客户参与准备与执行'))
        op('assignment',dict(action_id=task,subject=editor_subject))
        # Publish AFTER the fixture has finished, so the demonstration report is valid.
        c.execute("UPDATE workspace_snapshots SET status='withdrawn'");c.commit()
        op('report',dict(title='澄源工业 GEO 演练报告 · 完整链路快照'))
        c.execute("UPDATE workspace_fixture_marker SET value='fictional-growth-v1' WHERE name='origin'");c.commit()
    finally:c.close()
