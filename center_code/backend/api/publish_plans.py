"""
发布计划API
"""
from flask import Blueprint, request, Response, stream_with_context
from datetime import datetime
import sys
import os
import json
import time
from urllib.parse import urlparse
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import response_success, response_error, login_required, decode_access_token
from models import PublishPlan, PlanVideo, Merchant, VideoTask
from db import get_db

publish_plans_bp = Blueprint('publish_plans', __name__, url_prefix='/api/publish-plans')


def _canonical_video_key(url: str) -> str:
    """Normalize video URL for deduplication: ignore query params/signature."""
    if not url:
        return ''
    try:
        parsed = urlparse(url)
        # Keep host + path to avoid cross-domain collisions while ignoring presigned query
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}{parsed.path}".lower()
        return (parsed.path or url).lower()
    except Exception:
        return (url or '').lower()


def _calc_plan_counts(db, plan_id: int):
    total = db.query(PlanVideo).filter(PlanVideo.plan_id == plan_id).count()
    published = db.query(PlanVideo).filter(
        PlanVideo.plan_id == plan_id,
        PlanVideo.status == 'published'
    ).count()
    pending = max(total - published, 0)
    processing = db.query(PlanVideo).filter(
        PlanVideo.plan_id == plan_id,
        PlanVideo.status == 'processing'
    ).count()
    failed = db.query(PlanVideo).filter(
        PlanVideo.plan_id == plan_id,
        PlanVideo.status == 'failed'
    ).count()
    return total, published, pending, processing, failed


def _derive_plan_status(total: int, published: int, processing: int, failed: int) -> str:
    # Keep business semantics simple and stable for the list UI:
    # pending -> publishing -> completed
    if total > 0 and published >= total:
        return 'completed'
    if published > 0 or processing > 0:
        return 'publishing'
    if failed > 0 and published == 0:
        return 'failed'
    return 'pending'


def _parse_client_datetime(value: str) -> datetime:
    """
    Parse client datetime and normalize to local naive datetime for scheduler.
    Supports ISO strings with/without timezone and simple 'YYYY/MM/DD HH:MM:SS'.
    """
    if value is None:
        raise ValueError("empty datetime")
    text = str(value).strip()
    if not text:
        raise ValueError("empty datetime")

    # Accept trailing Z from frontend ISO strings.
    if text.endswith('Z'):
        text = text[:-1] + '+00:00'

    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        dt = datetime.strptime(text, "%Y/%m/%d %H:%M:%S")

    if dt.tzinfo is not None:
        local_tz = datetime.now().astimezone().tzinfo
        dt = dt.astimezone(local_tz).replace(tzinfo=None)
    return dt


@publish_plans_bp.route('/events', methods=['GET'])
def publish_plan_events():
    """
    SSE event stream for publish-plan progress.
    Frontend passes JWT via query param `token` because EventSource cannot set Authorization header.
    """
    token = (request.args.get('token') or '').strip()
    if not token:
        return response_error('Unauthorized', 401)
    try:
        decode_access_token(token)
    except Exception:
        return response_error('Unauthorized', 401)

    def event_stream():
        last_payload = None
        while True:
            try:
                with get_db() as db:
                    plans = db.query(PublishPlan).all()
                    data = [
                        {
                            'id': p.id,
                            'published_count': int(p.published_count or 0),
                            'status': p.status,
                            'updated_at': p.updated_at.isoformat() if p.updated_at else None
                        }
                        for p in plans
                    ]
                payload = json.dumps({'plans': data}, ensure_ascii=False, sort_keys=True)
                if payload != last_payload:
                    yield f"data: {payload}\n\n"
                    last_payload = payload
            except GeneratorExit:
                break
            except Exception as e:
                yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"
            time.sleep(1)

    headers = {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        'X-Accel-Buffering': 'no'
    }
    return Response(stream_with_context(event_stream()), headers=headers)


@publish_plans_bp.route('', methods=['GET'])
@login_required
def get_publish_plans():
    """
    获取发布计划列表接口
    
    请求方法: GET
    路径: /api/publish-plans
    认证: 需要登录
    
    查询参数:
        platform (string, 可选): 平台类型，筛选指定平台的计划（douyin/kuaishou/xiaohongshu）
        status (string, 可选): 状态筛选（pending/publishing/completed/failed）
        limit (int, 可选): 每页数量，默认 20
        offset (int, 可选): 偏移量，默认 0
    
    返回数据:
        成功 (200):
        {
            "code": 200,
            "message": "success",
            "data": {
                "plans": [
                    {
                        "id": int,
                        "plan_name": "string",
                        "platform": "string",
                        "merchant_id": int,
                        "merchant_name": "string",
                        "video_count": int,
                        "published_count": int,
                        "pending_count": int,
                        "claimed_count": int,
                        "account_count": int,
                        "distribution_mode": "string",
                        "status": "string",
                        "publish_time": "string",
                        "created_at": "string"
                    }
                ],
                "total": int,
                "limit": int,
                "offset": int
            }
        }
    
    说明:
        - 支持按平台和状态筛选
        - 结果按创建时间倒序排列
        - 自动关联商家名称和视频数量
    """
    try:
        platform = request.args.get('platform')
        status = request.args.get('status')
        limit = request.args.get('limit', type=int, default=20)
        offset = request.args.get('offset', type=int, default=0)
        
        with get_db() as db:
            query = db.query(PublishPlan)
            
            if platform:
                query = query.filter(PublishPlan.platform == platform)
            
            if status:
                query = query.filter(PublishPlan.status == status)
            
            total = query.count()
            plans = query.order_by(PublishPlan.created_at.desc()).limit(limit).offset(offset).all()
            
            plans_list = []
            for plan in plans:
                merchant_name = None
                if plan.merchant_id:
                    merchant = db.query(Merchant).filter(Merchant.id == plan.merchant_id).first()
                    merchant_name = merchant.merchant_name if merchant else None

                total, published, pending, processing, failed = _calc_plan_counts(db, plan.id)
                derived_status = _derive_plan_status(total, published, processing, failed)
                # 同步回表，避免后续页面看到旧计数
                plan.video_count = total
                plan.published_count = published
                plan.pending_count = pending
                plan.status = derived_status
                
                plans_list.append({
                    'id': plan.id,
                    'plan_name': plan.plan_name,
                    'platform': plan.platform,
                    'merchant_id': plan.merchant_id,
                    'merchant_name': merchant_name,
                    'video_count': total,
                    'published_count': published,
                    'pending_count': pending,
                    'claimed_count': plan.claimed_count,
                    'account_count': plan.account_count,
                    'distribution_mode': plan.distribution_mode,
                    'status': derived_status,
                    'publish_time': plan.publish_time.isoformat() if plan.publish_time else None,
                    'created_at': plan.created_at.isoformat() if plan.created_at else None
                })
            db.commit()
        
        return response_success({
            'plans': plans_list,
            'total': total,
            'limit': limit,
            'offset': offset
        })
    except Exception as e:
        return response_error(str(e), 500)


@publish_plans_bp.route('', methods=['POST'])
@login_required
def create_publish_plan():
    """
    创建发布计划接口
    
    请求方法: POST
    路径: /api/publish-plans
    认证: 需要登录
    
    请求体 (JSON):
        {
            "plan_name": "string",           # 必填，计划名称
            "platform": "string",            # 可选，平台类型，默认 douyin
            "merchant_id": int,              # 可选，关联商家ID
            "distribution_mode": "string",   # 可选，分发模式（manual/sms/qrcode/ai），默认 manual
            "publish_time": "string"         # 可选，发布时间（ISO 格式）
        }
    
    返回数据:
        成功 (201):
        {
            "code": 201,
            "message": "Publish plan created",
            "data": {
                "id": int,
                "plan_name": "string",
                "platform": "string",
                "status": "string"
            }
        }
        
        失败 (400/500):
        {
            "code": 400/500,
            "message": "错误信息",
            "data": null
        }
    
    说明:
        - 创建的计划初始状态为 pending（待发布）
        - 分发模式：manual（手动分发）、sms（接收短信派发）、qrcode（扫二维码派发）、ai（AI智能分发）
    """
    try:
        data = request.json
        plan_name = data.get('plan_name')
        platform = data.get('platform', 'douyin')
        merchant_id = data.get('merchant_id')
        distribution_mode = data.get('distribution_mode', 'manual')
        publish_time = data.get('publish_time')
        account_ids = data.get('account_ids', [])  # 获取指定的账号ID列表
        
        if not plan_name:
            return response_error('plan_name is required', 400)
        
        # 先解析 publish_time，确保格式正确
        parsed_publish_time = None
        if publish_time:
            try:
                parsed_publish_time = _parse_client_datetime(publish_time)
            except ValueError:
                return response_error('Invalid publish_time format. Please use ISO format (YYYY-MM-DD HH:mm:ss)', 400)
        
        # 处理账号ID列表：转换为JSON字符串存储
        account_ids_json = None
        account_count = 0
        if account_ids and isinstance(account_ids, list) and len(account_ids) > 0:
            # 确保都是整数
            try:
                account_ids = [int(aid) for aid in account_ids if aid is not None]
                account_ids_json = json.dumps(account_ids)
                account_count = len(account_ids)
            except (ValueError, TypeError) as e:
                return response_error(f'Invalid account_ids format: {e}', 400)
        
        with get_db() as db:
            plan = PublishPlan(
                plan_name=plan_name,
                platform=platform,
                merchant_id=merchant_id,
                distribution_mode=distribution_mode,
                publish_time=parsed_publish_time,
                account_ids=account_ids_json,
                account_count=account_count,
                status='pending'
            )
            db.add(plan)
            db.flush()
            db.commit()
            
            return response_success({
                'id': plan.id,
                'plan_name': plan.plan_name,
                'platform': plan.platform,
                'status': plan.status
            }, 'Publish plan created', 201)
    except Exception as e:
        return response_error(str(e), 500)


@publish_plans_bp.route('/<int:plan_id>', methods=['GET'])
@login_required
def get_publish_plan(plan_id):
    """
    获取发布计划详情接口
    
    请求方法: GET
    路径: /api/publish-plans/{plan_id}
    认证: 需要登录
    
    路径参数:
        plan_id (int): 发布计划ID
    
    返回数据:
        成功 (200):
        {
            "code": 200,
            "message": "success",
            "data": {
                "id": int,
                "plan_name": "string",
                "platform": "string",
                "merchant_id": int,
                "merchant_name": "string",
                "video_count": int,
                "videos": [
                    {
                        "id": int,
                        "video_url": "string",
                        "video_title": "string",
                        "thumbnail_url": "string",
                        "status": "string"
                    }
                ],
                "published_count": int,
                "pending_count": int,
                "claimed_count": int,
                "account_count": int,
                "distribution_mode": "string",
                "status": "string",
                "publish_time": "string",
                "created_at": "string"
            }
        }
        
        失败 (404/500):
        {
            "code": 404/500,
            "message": "错误信息",
            "data": null
        }
    
    说明:
        - 返回计划详情及关联的视频列表
        - 如果计划不存在，返回 404 错误
    """
    try:
        with get_db() as db:
            plan = db.query(PublishPlan).filter(PublishPlan.id == plan_id).first()
            
            if not plan:
                return response_error('Publish plan not found', 404)
            
            # 获取关联的商家
            merchant_name = None
            if plan.merchant_id:
                merchant = db.query(Merchant).filter(Merchant.id == plan.merchant_id).first()
                merchant_name = merchant.merchant_name if merchant else None
            
            # 获取计划中的视频
            videos = db.query(PlanVideo).filter(PlanVideo.plan_id == plan_id).order_by(PlanVideo.created_at.asc()).all()
            videos_list = []
            for video in videos:
                videos_list.append({
                    'id': video.id,
                    'video_url': video.video_url,
                    'video_title': video.video_title,
                    'video_description': video.video_description or '',
                    'video_tags': video.video_tags or '',
                    'thumbnail_url': video.thumbnail_url,
                    'schedule_time': video.schedule_time.isoformat() if video.schedule_time else None,
                    'status': video.status,
                    'created_at': video.created_at.isoformat() if video.created_at else None
                })
            
            total, published, pending, processing, failed = _calc_plan_counts(db, plan.id)
            derived_status = _derive_plan_status(total, published, processing, failed)
            plan.video_count = total
            plan.published_count = published
            plan.pending_count = pending
            plan.status = derived_status
            db.commit()

            return response_success({
                'id': plan.id,
                'plan_name': plan.plan_name,
                'platform': plan.platform,
                'merchant_id': plan.merchant_id,
                'merchant_name': merchant_name,
                'video_count': total,
                'videos': videos_list,
                'published_count': published,
                'pending_count': pending,
                'claimed_count': plan.claimed_count,
                'account_count': plan.account_count,
                'distribution_mode': plan.distribution_mode,
                'status': derived_status,
                'publish_time': plan.publish_time.isoformat() if plan.publish_time else None,
                'created_at': plan.created_at.isoformat() if plan.created_at else None
            })
    except Exception as e:
        return response_error(str(e), 500)


@publish_plans_bp.route('/<int:plan_id>', methods=['PUT'])
@login_required
def update_publish_plan(plan_id):
    """
    更新发布计划接口
    
    请求方法: PUT
    路径: /api/publish-plans/{plan_id}
    认证: 需要登录
    
    路径参数:
        plan_id (int): 发布计划ID
    
    请求体 (JSON):
        {
            "plan_name": "string",      # 可选，计划名称
            "status": "string",          # 可选，状态（pending/publishing/completed/failed）
            "publish_time": "string"     # 可选，发布时间（ISO 格式）
        }
    
    返回数据:
        成功 (200):
        {
            "code": 200,
            "message": "Publish plan updated",
            "data": {
                "id": int,
                "plan_name": "string",
                "status": "string"
            }
        }
        
        失败 (404/500):
        {
            "code": 404/500,
            "message": "错误信息",
            "data": null
        }
    
    说明:
        - 只更新提供的字段，未提供的字段保持不变
        - 如果计划不存在，返回 404 错误
    """
    try:
        data = request.json
        with get_db() as db:
            plan = db.query(PublishPlan).filter(PublishPlan.id == plan_id).first()
            
            if not plan:
                return response_error('Publish plan not found', 404)
            
            if 'plan_name' in data:
                plan.plan_name = data['plan_name']
            if 'status' in data:
                plan.status = data['status']
            if 'publish_time' in data:
                if data['publish_time']:
                    try:
                        plan.publish_time = _parse_client_datetime(data['publish_time'])
                    except ValueError:
                        return response_error('Invalid publish_time format. Please use ISO format (YYYY-MM-DD HH:mm:ss)', 400)
                else:
                    plan.publish_time = None
            
            # 更新账号ID列表
            if 'account_ids' in data:
                account_ids = data['account_ids']
                account_ids_json = None
                account_count = 0
                if account_ids and isinstance(account_ids, list) and len(account_ids) > 0:
                    try:
                        account_ids = [int(aid) for aid in account_ids if aid is not None]
                        account_ids_json = json.dumps(account_ids)
                        account_count = len(account_ids)
                    except (ValueError, TypeError) as e:
                        return response_error(f'Invalid account_ids format: {e}', 400)
                plan.account_ids = account_ids_json
                plan.account_count = account_count
            
            plan.updated_at = datetime.now()
            
            db.commit()
            
            return response_success({
                'id': plan.id,
                'plan_name': plan.plan_name,
                'status': plan.status
            }, 'Publish plan updated')
    except Exception as e:
        return response_error(str(e), 500)


@publish_plans_bp.route('/<int:plan_id>', methods=['DELETE'])
@login_required
def delete_publish_plan(plan_id):
    """
    删除发布计划接口
    
    请求方法: DELETE
    路径: /api/publish-plans/{plan_id}
    认证: 需要登录
    
    路径参数:
        plan_id (int): 发布计划ID
    
    返回数据:
        成功 (200):
        {
            "code": 200,
            "message": "Publish plan deleted",
            "data": {
                "plan_id": int
            }
        }
        
        失败 (404/500):
        {
            "code": 404/500,
            "message": "错误信息",
            "data": null
        }
    
    说明:
        - 删除计划时会级联删除关联的所有视频（PlanVideo）
        - 如果计划不存在，返回 404 错误
    """
    try:
        with get_db() as db:
            plan = db.query(PublishPlan).filter(PublishPlan.id == plan_id).first()
            
            if not plan:
                return response_error('Publish plan not found', 404)
            
            # 先查出关联的视频，用于删除对应的视频任务
            videos = db.query(PlanVideo).filter(PlanVideo.plan_id == plan_id).all()
            video_urls = [v.video_url for v in videos if v.video_url]
            
            if video_urls:
                # 删除与这些视频相关的视频任务（无论状态如何，全部清理）
                deleted_tasks = db.query(VideoTask).filter(
                    VideoTask.video_url.in_(video_urls)
                ).delete(synchronize_session=False)
                print(f"[发布计划] 删除计划 {plan_id} 时，一并删除关联视频任务数量: {deleted_tasks}")
            
            # 删除关联的视频
            db.query(PlanVideo).filter(PlanVideo.plan_id == plan_id).delete()
            
            # 删除计划
            db.delete(plan)
            db.commit()
            
            return response_success({'plan_id': plan_id}, 'Publish plan deleted')
    except Exception as e:
        return response_error(str(e), 500)


@publish_plans_bp.route('/<int:plan_id>/execute', methods=['POST'])
@login_required
def execute_publish_plan(plan_id):
    """
    手动触发发布计划执行接口
    
    请求方法: POST
    路径: /api/publish-plans/{plan_id}/execute
    认证: 需要登录
    
    路径参数:
        plan_id (int): 发布计划ID
    
    返回数据:
        成功 (200):
        {
            "code": 200,
            "message": "发布计划已触发执行",
            "data": {
                "plan_id": int,
                "status": "publishing"
            }
        }
        
        失败 (400/404/500):
        {
            "code": 400/404/500,
            "message": "错误信息",
            "data": null
        }
    
    说明:
        - 只有状态为 'pending' 的计划可以触发执行
        - 触发后计划状态变为 'publishing'
        - 系统会为每个待发布视频创建上传任务
    """
    try:
        with get_db() as db:
            plan = db.query(PublishPlan).filter(PublishPlan.id == plan_id).first()
            
            if not plan:
                return response_error('发布计划不存在', 404)
            
            if plan.status != 'pending':
                return response_error(f'只有待发布状态的计划可以执行，当前状态: {plan.status}', 400)
            
            videos = db.query(PlanVideo).filter(
                PlanVideo.plan_id == plan.id,
                PlanVideo.status == 'pending'
            ).all()
            
            if not videos:
                return response_error('该计划没有待发布的视频', 400)
            
            from models import Account
            accounts = db.query(Account).filter(
                Account.platform == plan.platform,
                Account.login_status == 'logged_in'
            ).all()
            
            if not accounts:
                return response_error(f'平台 {plan.platform} 没有已登录的账号', 400)
            
            plan.status = 'publishing'
            plan.publish_time = datetime.now()
            plan.updated_at = datetime.now()
            db.commit()
            
            def trigger_task_processing():
                try:
                    from services.task_processor import get_task_processor
                    task_processor = get_task_processor()
                    task_processor._process_pending_tasks()
                except Exception as e:
                    print(f"[发布计划] 触发任务处理失败: {e}")
                    import traceback
                    traceback.print_exc()
            
            import threading
            thread = threading.Thread(target=trigger_task_processing, daemon=True)
            thread.start()
            
            return response_success({
                'plan_id': plan_id,
                'status': 'publishing'
            }, '发布计划已触发执行')
    except Exception as e:
        return response_error(str(e), 500)


@publish_plans_bp.route('/<int:plan_id>/videos', methods=['POST'])
@login_required
def add_video_to_plan(plan_id):
    """
    向发布计划添加视频接口
    
    请求方法: POST
    路径: /api/publish-plans/{plan_id}/videos
    认证: 需要登录
    
    路径参数:
        plan_id (int): 发布计划ID
    
    请求体 (JSON):
        {
            "video_url": "string",       # 必填，视频URL
            "video_title": "string",     # 可选，视频标题
            "thumbnail_url": "string"     # 可选，缩略图URL
        }
    
    返回数据:
        成功 (201):
        {
            "code": 201,
            "message": "Video added to plan",
            "data": {
                "id": int,
                "video_url": "string",
                "video_title": "string"
            }
        }
        
        失败 (400/404/500):
        {
            "code": 400/404/500,
            "message": "错误信息",
            "data": null
        }
    
    说明:
        - 添加视频后会自动更新计划的 video_count
        - 如果计划不存在，返回 404 错误
    """
    try:
        data = request.json
        video_url = data.get('video_url')
        video_title = data.get('video_title')
        video_description = data.get('video_description')  # 视频正文/描述
        video_tags = data.get('video_tags')  # 视频标签/话题，可以是字符串（逗号分隔）或列表
        thumbnail_url = data.get('thumbnail_url')
        publish_time = data.get('publish_time')
        
        if not video_url:
            return response_error('video_url is required', 400)
        
        # 处理 video_tags：如果是列表，转换为逗号分隔的字符串；如果是字符串，直接使用
        video_tags_str = None
        if video_tags:
            if isinstance(video_tags, list):
                video_tags_str = ','.join([str(tag).strip() for tag in video_tags if tag])
            elif isinstance(video_tags, str):
                video_tags_str = video_tags.strip()
        
        with get_db() as db:
            plan = db.query(PublishPlan).filter(PublishPlan.id == plan_id).first()
            if not plan:
                return response_error('Publish plan not found', 404)
            
            canonical_key = _canonical_video_key(video_url)
            existing_video = db.query(PlanVideo).filter(
                PlanVideo.plan_id == plan_id,
                PlanVideo.video_url == video_url
            ).first()
            if not existing_video and canonical_key:
                # 兜底：忽略 query 参数后去重，避免同一 COS 文件因签名不同重复加入
                candidates = db.query(PlanVideo).filter(PlanVideo.plan_id == plan_id).all()
                for c in candidates:
                    if _canonical_video_key(c.video_url) == canonical_key:
                        existing_video = c
                        break
            
            if existing_video:
                return response_success({
                    'id': existing_video.id,
                    'video_url': existing_video.video_url,
                    'video_title': existing_video.video_title,
                    'message': 'Video already exists in this plan'
                }, 'Video already exists in this plan', 200)
            
            # 从请求中获取该视频的发布时间（用于分阶段发布）
            schedule_time = data.get('schedule_time')
            parsed_schedule_time = None
            if schedule_time:
                try:
                    parsed_schedule_time = _parse_client_datetime(schedule_time)
                except ValueError:
                    return response_error('Invalid schedule_time format. Please use ISO format (YYYY-MM-DD HH:mm:ss)', 400)
            
            video = PlanVideo(
                plan_id=plan_id,
                video_url=video_url,
                video_title=video_title,
                video_description=video_description,
                video_tags=video_tags_str,
                thumbnail_url=thumbnail_url,
                schedule_time=parsed_schedule_time,
                status='pending'
            )
            db.add(video)
            db.flush()
            
            total, published, pending, processing, failed = _calc_plan_counts(db, plan_id)
            plan.video_count = total
            plan.published_count = published
            plan.pending_count = pending
            plan.status = _derive_plan_status(total, published, processing, failed)
            plan.updated_at = datetime.now()
            
            db.commit()
            
            # 如果视频发布时间为空（立即）或已到，触发任务处理
            # 注意：使用全局任务处理器，避免数据库会话冲突
            now = datetime.now()
            effective_time = video.schedule_time or plan.publish_time
            should_trigger = (effective_time is None) or (effective_time <= now)
            
            if should_trigger:
                print(f"[发布计划] 检测到需要触发任务处理: {plan.plan_name} (ID: {plan.id}), status={plan.status}")
                # 使用全局任务处理器，在数据库会话外触发处理
                def trigger_task_processing():
                    try:
                        from services.task_processor import get_task_processor
                        task_processor = get_task_processor()
                        task_processor._process_pending_tasks()
                    except Exception as e:
                        print(f"[发布计划] 触发任务处理失败: {e}")
                        import traceback
                        traceback.print_exc()
                
                # 在后台线程中触发，避免阻塞当前请求和数据库会话冲突
                import threading
                thread = threading.Thread(target=trigger_task_processing, daemon=True)
                thread.start()
            
            return response_success({
                'id': video.id,
                'video_url': video.video_url,
                'video_title': video.video_title
            }, 'Video added to plan', 201)
    except Exception as e:
        return response_error(str(e), 500)


@publish_plans_bp.route('/<int:plan_id>/videos/<int:video_id>', methods=['PUT'])
@login_required
def update_plan_video(plan_id, video_id):
    """
    更新发布计划中的视频信息接口
    
    请求方法: PUT
    路径: /api/publish-plans/{plan_id}/videos/{video_id}
    认证: 需要登录
    
    路径参数:
        plan_id (int): 发布计划ID
        video_id (int): 计划视频ID
    
    请求体 (JSON):
        {
            "video_title": "string",        # 可选，视频标题
            "video_description": "string",   # 可选，视频描述
            "video_tags": "string",         # 可选，标签（逗号分隔）
            "schedule_time": "string"        # 可选，发布时间（ISO 格式）
        }
    
    返回数据:
        成功 (200):
        {
            "code": 200,
            "message": "Video updated",
            "data": {
                "id": int,
                "video_title": "string",
                "video_description": "string",
                "video_tags": "string",
                "schedule_time": "string"
            }
        }
        
        失败 (404/500):
        {
            "code": 404/500,
            "message": "错误信息",
            "data": null
        }
    
    说明:
        - 只更新提供的字段，未提供的字段保持不变
        - 只能更新未发布的视频（status='pending'）
        - 如果视频不存在或已发布，返回 404/400 错误
    """
    try:
        data = request.json or {}
        with get_db() as db:
            plan = db.query(PublishPlan).filter(PublishPlan.id == plan_id).first()
            if not plan:
                return response_error('Publish plan not found', 404)
            
            video = db.query(PlanVideo).filter(
                PlanVideo.id == video_id,
                PlanVideo.plan_id == plan_id
            ).first()
            
            if not video:
                return response_error('Video not found in this plan', 404)
            
            # 只能更新未发布的视频
            if video.status != 'pending':
                return response_error(f'Cannot update video with status: {video.status}. Only pending videos can be updated.', 400)
            
            # 更新视频标题
            if 'video_title' in data:
                video.video_title = data['video_title'] or None
            
            # 更新视频描述
            if 'video_description' in data:
                video.video_description = data['video_description'] or None
            
            # 更新视频标签
            if 'video_tags' in data:
                video_tags = data['video_tags']
                if video_tags:
                    video_tags_str = video_tags.strip()
                else:
                    video_tags_str = None
                video.video_tags = video_tags_str
            
            # 更新发布时间
            if 'schedule_time' in data:
                schedule_time = data['schedule_time']
                if schedule_time:
                    try:
                        video.schedule_time = _parse_client_datetime(schedule_time)
                    except ValueError:
                        return response_error('Invalid schedule_time format. Please use ISO format (YYYY-MM-DD HH:mm:ss)', 400)
                else:
                    video.schedule_time = None
            
            video.updated_at = datetime.now()
            db.commit()
            
            return response_success({
                'id': video.id,
                'video_title': video.video_title,
                'video_description': video.video_description,
                'video_tags': video.video_tags,
                'schedule_time': video.schedule_time.isoformat() if video.schedule_time else None
            }, 'Video updated')
    except Exception as e:
        return response_error(str(e), 500)


@publish_plans_bp.route('/videos/history', methods=['GET'])
@login_required
def get_plan_videos_history():
    """
    获取发布计划中的视频任务历史接口
    
    请求方法: GET
    路径: /api/publish-plans/videos/history
    认证: 需要登录
    
    查询参数:
        limit (int, 可选): 每页数量，默认 20
        offset (int, 可选): 偏移量，默认 0
        plan_id (int, 可选): 筛选指定计划ID
        status (string, 可选): 状态筛选（pending/processing/published/failed）
    
    返回数据:
        成功 (200):
        {
            "code": 200,
            "message": "success",
            "data": {
                "items": [
                    {
                        "id": int,
                        "plan_id": int,
                        "plan_name": "string",
                        "video_title": "string",
                        "video_url": "string",
                        "account_id": int,
                        "account_name": "string",
                        "platform": "string",
                        "status": "string",
                        "publish_time": "string",
                        "created_at": "string"
                    }
                ],
                "total": int,
                "limit": int,
                "offset": int
            }
        }
    """
    try:
        limit = request.args.get('limit', type=int, default=20)
        offset = request.args.get('offset', type=int, default=0)
        plan_id_filter = request.args.get('plan_id', type=int)
        status_filter = request.args.get('status')
        
        with get_db() as db:
            from models import Account
            
            # 查询 PlanVideo，关联 PublishPlan 和 VideoTask
            query = db.query(PlanVideo, PublishPlan).join(
                PublishPlan, PlanVideo.plan_id == PublishPlan.id
            )
            
            if plan_id_filter:
                query = query.filter(PlanVideo.plan_id == plan_id_filter)
            
            if status_filter:
                query = query.filter(PlanVideo.status == status_filter)
            
            # 获取总数
            total = query.count()
            
            # 分页查询
            results = query.order_by(PlanVideo.created_at.desc()).limit(limit).offset(offset).all()
            
            # 构建返回数据
            items = []
            for plan_video, plan in results:
                # 优先按 plan_video_id 关联任务，避免同 URL 误匹配
                video_task = db.query(VideoTask).filter(
                    VideoTask.plan_video_id == plan_video.id
                ).order_by(VideoTask.id.desc()).first()
                if not video_task:
                    # 兼容历史数据（旧任务可能没有 plan_video_id）
                    video_task = db.query(VideoTask).filter(
                        VideoTask.video_url == plan_video.video_url,
                        VideoTask.account_id.isnot(None)
                    ).order_by(VideoTask.id.desc()).first()
                
                account_name = None
                account_id = None
                if video_task:
                    account = db.query(Account).filter(Account.id == video_task.account_id).first()
                    if account:
                        account_name = account.account_name
                        account_id = account.id

                # 统一状态口径，前端按 completed/processing/pending/failed 展示
                status = plan_video.status or 'pending'
                if status == 'published':
                    status = 'completed'
                elif status == 'processing':
                    status = 'processing'
                elif status == 'pending' and video_task:
                    if video_task.status in ('uploading', 'processing'):
                        status = 'processing'
                    elif video_task.status in ('completed',):
                        status = 'completed'
                    elif video_task.status in ('failed',):
                        status = 'failed'

                progress = 0
                error_message = None
                if video_task:
                    progress = int(video_task.progress or 0)
                    error_message = video_task.error_message
                if status == 'completed':
                    progress = 100
                
                items.append({
                    'id': plan_video.id,
                    'plan_id': plan.id,
                    'plan_name': plan.plan_name,
                    'video_title': plan_video.video_title,
                    'video_url': plan_video.video_url,
                    'account_id': account_id,
                    'account_name': account_name or '-',
                    'platform': plan.platform,
                    'status': status,
                    'progress': progress,
                    'error_message': error_message,
                    'publish_time': (plan_video.schedule_time or plan.publish_time).isoformat() if (plan_video.schedule_time or plan.publish_time) else None,
                    'created_at': plan_video.created_at.isoformat() if plan_video.created_at else None,
                    'task_id': video_task.id if video_task else None,
                })
            
            return response_success({
                'items': items,
                'total': total,
                'limit': limit,
                'offset': offset
            })
    except Exception as e:
        return response_error(str(e), 500)


@publish_plans_bp.route('/<int:plan_id>/save-info', methods=['POST'])
@login_required
def save_publish_info(plan_id):
    """
    保存发布信息接口（占位接口，复杂功能待实现）
    
    请求方法: POST
    路径: /api/publish-plans/{plan_id}/save-info
    认证: 需要登录
    
    路径参数:
        plan_id (int): 发布计划ID
    
    请求体 (JSON):
        {
            "distribution_rules": {},      # 可选，分发规则配置（待实现）
            "account_assignment": [],      # 可选，账号分配列表（待实现）
            "publish_schedule": {},        # 可选，发布计划配置（待实现）
            "sms_config": {},              # 可选，短信分发配置（待实现）
            "qrcode_config": {},           # 可选，二维码分发配置（待实现）
            "ai_config": {}                # 可选，AI智能分发配置（待实现）
        }
    
    返回数据:
        成功 (200):
        {
            "code": 200,
            "message": "Publish info saved (placeholder)",
            "data": {
                "plan_id": int
            }
        }
        
        失败 (404/500):
        {
            "code": 404/500,
            "message": "错误信息",
            "data": null
        }
    
    说明:
        - 此接口为占位接口，具体实现待开发
        - 用于保存发布计划的详细信息，包括：
          * 分发规则：手动分发、短信分发、二维码分发、AI智能分发的配置
          * 账号分配：指定哪些账号参与发布计划
          * 发布计划：定时发布、批量发布等配置
        - 如果计划不存在，返回 404 错误
    """
    try:
        data = request.json
        # TODO: 实现保存发布信息的逻辑
        return response_success({'plan_id': plan_id}, 'Publish info saved (placeholder)')
    except Exception as e:
        return response_error(str(e), 500)
