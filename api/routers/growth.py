"""Small capability-checked workspace API; customer alias shares all handlers."""
from typing import Annotated
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from .. import growth_core as svc
from ..deps import _authenticate_context
from ..auth import AuthContext

router=APIRouter(tags=['growth-workspace'])


async def growth_auth(x_api_key: Annotated[str|None,Header()]=None,
                      x_tenant_id: Annotated[str|None,Header()]=None,
                      x_client_id: Annotated[str|None,Header()]=None,
                      tenant_id: str|None=None, client_id: str|None=None,
                      workspace_site_id: int|None=None):
    ctx=_authenticate_context(x_api_key,x_tenant_id,tenant_id)
    if ctx.role not in {'HQ_MANAGEMENT','HQ_TECHNICAL','DISTRIBUTOR_ADMIN','DISTRIBUTOR_USER','CLIENT_VIEWER','END_CUSTOMER','END_CUSTOMER_EDITOR'}:
        raise HTTPException(403,'身份未获增长工作区权限')
    if any(v and v != ctx.client_id for v in (client_id,x_client_id)):
        raise HTTPException(403,'客户归属由登录身份决定')
    if ctx.role.startswith('END_CUSTOMER'):
        from ..customer_service import bound_client
        await bound_client(ctx)
    if workspace_site_id is not None:
        from dataclasses import replace
        if workspace_site_id < 1:
            raise HTTPException(422,'资源编号无效')
        ctx=replace(ctx,workspace_site_id=workspace_site_id)
    return ctx


Auth=Annotated[AuthContext,Depends(growth_auth)]

class Operation(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:int=Field(ge=0)
    payload:dict


@router.get('/growth/workspace')
@router.get('/customer/growth/workspace')
async def workspace(auth:Auth):
    return await svc.workspace(auth)


@router.get('/growth/projects/{project_id}')
@router.get('/customer/growth/projects/{project_id}')
async def read(project_id:str,auth:Auth):
    return await svc.read(project_id,auth)


@router.post('/growth/projects/{project_id}/{operation}')
@router.post('/customer/growth/projects/{project_id}/{operation}')
async def write(project_id:str,operation:str,body:Operation,auth:Auth,
                idempotency_key:Annotated[str|None,Header()]=None):
    if not idempotency_key or len(idempotency_key)>128:
        raise HTTPException(422,'缺少有效提交编号')
    return await svc.write(project_id,operation,body.payload,body.revision,idempotency_key,auth)


@router.get('/growth/projects/{project_id}/reports/{report_id}')
@router.get('/customer/growth/projects/{project_id}/reports/{report_id}')
async def report(project_id:str,report_id:int,auth:Auth):
    return await svc.report(project_id,report_id,auth)
