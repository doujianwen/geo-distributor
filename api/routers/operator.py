"""Explicit project-scoped native compatibility surface."""
from fastapi import APIRouter, Request, Response, HTTPException
from .growth import Auth
from .. import operator_service as service

router = APIRouter(tags=['professional-operator'])


@router.get('/growth/projects/{project_id}/operator/export/{collection}')
@router.get('/customer/growth/projects/{project_id}/operator/export/{collection}')
async def export_csv(project_id: str, collection: str, request: Request, response: Response, auth: Auth, q: str=''):
    filters={k:v for k,v in request.query_params.items() if k not in {'q','tenant_id','client_id','workspace_site_id'}}
    result=await service.export_csv(project_id,collection,q,filters,auth)
    response.headers['Cache-Control']='no-store'
    return result


@router.get('/growth/projects/{project_id}/operator/context')
@router.get('/customer/growth/projects/{project_id}/operator/context')
async def context(project_id: str, auth: Auth):
    return await service.context(project_id, auth)


@router.get('/growth/projects/{project_id}/operator/paged/{collection}')
@router.get('/customer/growth/projects/{project_id}/operator/paged/{collection}')
async def paged(project_id: str, collection: str, request: Request, response: Response,
                auth: Auth, page: int = 1, page_size: int = 20, q: str = '', ids: str = ''):
    try: selected = [int(value) for value in ids.split(',') if value] if ids else []
    except ValueError: raise HTTPException(422, '选择项编号无效')
    metadata = {'page', 'page_size', 'q', 'ids', 'tenant_id', 'client_id', 'workspace_site_id'}
    filters = {k: v for k, v in request.query_params.items() if k not in metadata}
    value = await service.paged(project_id, collection, page, page_size, q, filters, selected, auth)
    response.headers['Cache-Control'] = 'no-store'
    return value


@router.api_route('/growth/projects/{project_id}/operator/api/{path:path}', methods=['GET', 'POST', 'PUT', 'DELETE'])
@router.api_route('/customer/growth/projects/{project_id}/operator/api/{path:path}', methods=['GET', 'POST', 'PUT', 'DELETE'])
async def native(project_id: str, path: str, request: Request, response: Response, auth: Auth):
    if len(await request.body()) > 200000: raise HTTPException(413, '单次提交过大')
    payload = None
    if request.method != 'GET':
        try: payload = await request.json() if await request.body() else {}
        except ValueError: raise HTTPException(422, '请求内容格式无效')
    raw = request.headers.get('If-Match', '')
    try: revision = int(raw.strip('"')) if raw else None
    except ValueError: raise HTTPException(422, '版本格式无效')
    value, next_revision = await service.request(project_id, request.method, path, payload,
                                                dict(request.query_params), revision,
                                                request.headers.get('Idempotency-Key'), auth,
                                                object_version=request.headers.get('If-Match-Object'))
    if next_revision is not None: response.headers['X-Workspace-Revision'] = str(next_revision)
    response.headers['Cache-Control'] = 'no-store'
    return value
