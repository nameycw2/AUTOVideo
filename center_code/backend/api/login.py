"""
登录相关API（二维码等）
"""
from flask import Blueprint, request, Response, stream_with_context
import sys
import os
import json
import time
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import response_success, response_error, login_required
from models import Account
from db import get_db
from datetime import datetime
from services.login_service import (
    start_login_session_sync,
    check_login_status_sync,
    get_cookies_from_session_sync,
    cleanup_login_session_sync,
    screenshot_session_sync,
    interact_session_sync,
    get_session_viewport,
)
from utils import decode_access_token

login_bp = Blueprint('login', __name__, url_prefix='/api/login')


def _persist_account_cookies(account_id: int, cookies_obj):
    if not cookies_obj:
        return False, '无法获取cookies，请确保已登录'

    with get_db() as db:
        account = db.query(Account).filter(Account.id == account_id).first()
        if not account:
            return False, 'Account not found'

        cookies_json = json.dumps(cookies_obj, ensure_ascii=False)
        account.cookies = cookies_json
        account.login_status = 'logged_in'
        account.last_login_time = datetime.now()
        account.updated_at = datetime.now()
        db.commit()
    return True, None


@login_bp.route('/start', methods=['POST'])
@login_required
def start_login():
    """
    启动账号登录流程接口
    
    请求方法: POST
    路径: /api/login/start
    认证: 需要登录
    
    请求体 (JSON):
        {
            "account_id": int  # 必填，账号ID
        }
    
    返回数据:
        成功 (200):
        {
            "code": 200,
            "message": "Login helper URL generated",
            "data": {
                "account_id": int,
                "login_url": "string"  # 登录助手页面URL
            }
        }
        
        失败 (400/500):
        {
            "code": 400/500,
            "message": "错误信息",
            "data": null
        }
    
    说明:
        - 返回登录助手页面的URL，用户可以在该页面完成账号登录
        - 登录助手页面URL格式：/login-helper?account_id={account_id}
    """
    try:
        data = request.json
        account_id = data.get('account_id')
        
        if not account_id:
            return response_error('account_id is required', 400)
        
        # 验证账号是否存在
        with get_db() as db:
            account = db.query(Account).filter(Account.id == account_id).first()
            if not account:
                return response_error('Account not found', 404)
        
        # 返回登录助手页面URL
        login_url = f'/login-helper?account_id={account_id}'
        return response_success({
            'account_id': account_id,
            'login_url': login_url
        }, 'Login helper URL generated', 200)
    except Exception as e:
        return response_error(str(e), 500)


@login_bp.route('/qrcode', methods=['GET'])
@login_required
def get_login_qrcode():
    """
    获取登录二维码接口
    
    请求方法: GET
    路径: /api/login/qrcode
    认证: 需要登录
    
    查询参数:
        account_id (int): 账号ID
    
    返回数据:
        成功 (200):
        {
            "code": 200,
            "message": "二维码获取成功",
            "data": {
                "qrcode": "string",  # base64编码的二维码图片
                "account_id": int
            }
        }
        
        失败 (400/500):
        {
            "code": 400/500,
            "message": "错误信息",
            "data": null
        }
    """
    try:
        account_id = request.args.get('account_id', type=int)
        
        if not account_id:
            return response_error('account_id is required', 400)
        
        # 验证账号是否存在
        with get_db() as db:
            account = db.query(Account).filter(Account.id == account_id).first()
            if not account:
                return response_error('Account not found', 404)
            
            platform = account.platform or 'douyin'
        
        # 启动登录会话并获取二维码
        result = start_login_session_sync(account_id, platform)
        
        if result['success']:
            return response_success({
                'qrcode': result['qrcode'],
                'account_id': account_id,
                'status': result.get('status', 'waiting'),
                'login_mode': result.get('login_mode', 'qrcode')
            }, result['message'])
        else:
            return response_error(result['message'], 500)
            
    except Exception as e:
        return response_error(str(e), 500)


@login_bp.route('/status', methods=['GET'])
@login_required
def get_login_status():
    """
    检查登录状态接口
    
    请求方法: GET
    路径: /api/login/status
    认证: 需要登录
    
    查询参数:
        account_id (int): 账号ID
    
    返回数据:
        成功 (200):
        {
            "code": 200,
            "message": "success",
            "data": {
                "status": "string",  # waiting, scanning, logged_in, failed
                "cookies": object or null,  # 如果已登录，返回cookies
                "message": "string"
            }
        }
    """
    try:
        account_id = request.args.get('account_id', type=int)
        
        if not account_id:
            return response_error('account_id is required', 400)
        
        # 检查登录状态
        result = check_login_status_sync(account_id)
        
        return response_success({
            'status': result['status'],
            'cookies': result['cookies'],
            'message': result['message']
        })
        
    except Exception as e:
        return response_error(str(e), 500)


@login_bp.route('/complete', methods=['POST'])
@login_required
def complete_login():
    """
    完成登录并保存cookies到数据库
    
    请求方法: POST
    路径: /api/login/complete
    认证: 需要登录
    
    请求体 (JSON):
        {
            "account_id": int  # 必填，账号ID
        }
    
    返回数据:
        成功 (200):
        {
            "code": 200,
            "message": "登录完成，cookies已保存",
            "data": {
                "account_id": int,
                "login_status": "string"
            }
        }
        
        失败 (400/500):
        {
            "code": 400/500,
            "message": "错误信息",
            "data": null
        }
    """
    try:
        data = request.json
        account_id = data.get('account_id')
        
        if not account_id:
            return response_error('account_id is required', 400)

        # 仅当登录会话已确认成功时才允许完成并落库
        status_result = check_login_status_sync(account_id)
        if status_result.get('status') != 'logged_in':
            return response_error(status_result.get('message') or '登录尚未完成，请先扫码确认', 400)
        
        # 获取cookies
        cookies = get_cookies_from_session_sync(account_id)
        
        if not cookies:
            return response_error('无法获取cookies，请确保已登录', 400)
        
        ok, err = _persist_account_cookies(account_id, cookies)
        if not ok:
            return response_error(err, 404 if err == 'Account not found' else 400)
        
        # 清理登录会话
        cleanup_login_session_sync(account_id)
        
        return response_success({
            'account_id': account_id,
            'login_status': 'logged_in'
        }, '登录完成，cookies已保存')
        
    except Exception as e:
        return response_error(str(e), 500)


@login_bp.route('/complete_local', methods=['POST'])
@login_required
def complete_login_local():
    """
    本地代理回传 cookies 后直接入库。
    请求体:
      {
        "account_id": int,
        "cookies": object
      }
    """
    try:
        data = request.json or {}
        account_id = data.get('account_id')
        cookies = data.get('cookies')

        if not account_id:
            return response_error('account_id is required', 400)
        if not cookies:
            return response_error('cookies is required', 400)

        ok, err = _persist_account_cookies(account_id, cookies)
        if not ok:
            return response_error(err, 404 if err == 'Account not found' else 400)

        return response_success({
            'account_id': account_id,
            'login_status': 'logged_in'
        }, '登录完成，cookies已保存')
    except Exception as e:
        return response_error(str(e), 500)


@login_bp.route('/cancel', methods=['POST'])
@login_required
def cancel_login():
    """
    取消登录并清理会话
    
    请求方法: POST
    路径: /api/login/cancel
    认证: 需要登录
    
    请求体 (JSON):
        {
            "account_id": int  # 必填，账号ID
        }
    
    返回数据:
        成功 (200):
        {
            "code": 200,
            "message": "登录已取消",
            "data": {
                "account_id": int
            }
        }
    """
    try:
        data = request.json
        account_id = data.get('account_id')
        
        if not account_id:
            return response_error('account_id is required', 400)
        
        # 清理登录会话
        cleanup_login_session_sync(account_id)
        
        return response_success({
            'account_id': account_id
        }, '登录已取消')

    except Exception as e:
        return response_error(str(e), 500)


@login_bp.route('/screenshot', methods=['GET'])
@login_required
def get_screenshot():
    """
    获取当前登录会话的页面截图（用于手机号验证码等需要用户看到浏览器的场景）

    查询参数:
        account_id (int): 账号ID
    """
    try:
        account_id = request.args.get('account_id', type=int)
        if not account_id:
            return response_error('account_id is required', 400)

        screenshot = screenshot_session_sync(account_id)
        if not screenshot:
            return response_error('截图失败，会话可能已关闭', 400)

        return response_success({
            'screenshot': screenshot,
            'account_id': account_id
        }, '截图成功')
    except Exception as e:
        return response_error(str(e), 500)


@login_bp.route('/interact', methods=['POST'])
@login_required
def interact():
    """
    向登录会话页面发送交互操作（点击/输入/按键/滚动）
    请求体: { "account_id": int, "action": { "type": "click", "x": 320, "y": 240 } }
    返回: { "screenshot": "<base64>", "width": 1280, "height": 720 }
    """
    try:
        data = request.json or {}
        account_id = data.get('account_id')
        action = data.get('action')
        if not account_id:
            return response_error('account_id is required', 400)
        if not action or not action.get('type'):
            return response_error('action is required', 400)

        ok = interact_session_sync(account_id, action)
        if not ok:
            return response_error('交互失败，会话可能已关闭', 400)

        # 交互后立即截图返回最新画面
        screenshot = screenshot_session_sync(account_id)
        viewport = get_session_viewport(account_id)
        return response_success({
            'screenshot': screenshot,
            'width': viewport['width'],
            'height': viewport['height'],
        })
    except Exception as e:
        return response_error(str(e), 500)


@login_bp.route('/stream', methods=['GET'])
def stream_browser():
    """
    SSE 截图流，每 300ms 推一帧浏览器截图。
    SSE 不支持自定义 header，token 通过 query param 传递。
    查询参数: account_id (int), token (str)
    """
    # 手动鉴权（SSE 无法用 @login_required）
    token = request.args.get('token', '')
    if not token:
        return Response('Unauthorized', status=401)
    try:
        payload = decode_access_token(token)
        if not payload or not payload.get('user_id'):
            return Response('Unauthorized', status=401)
    except Exception:
        return Response('Unauthorized', status=401)

    account_id = request.args.get('account_id', type=int)
    if not account_id:
        return Response('account_id is required', status=400)

    def generate():
        viewport = get_session_viewport(account_id)
        while True:
            screenshot = screenshot_session_sync(account_id)
            if screenshot is None:
                # 会话已关闭，推一个结束事件
                yield 'event: close\ndata: {}\n\n'
                break
            payload = json.dumps({
                'screenshot': screenshot,
                'width': viewport['width'],
                'height': viewport['height'],
            })
            yield f'data: {payload}\n\n'
            time.sleep(0.3)

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',  # 禁用 nginx 缓冲
        }
    )
