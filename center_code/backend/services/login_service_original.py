"""
登录服务模块
使用Playwright实现扫码登录和自动获取cookies
"""
import asyncio
import json
import base64
import os
from typing import Optional, Dict
from datetime import datetime
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from config import LOCAL_CHROME_PATH, LOCAL_CHROME_HEADLESS
from utils.base_social_media import set_init_script
import threading

# 存储登录会话的字典 {account_id: {browser, context, page, qrcode, status}}
login_sessions: Dict[int, Dict] = {}

# 全局事件循环（用于在Flask中运行异步代码）
_async_loop = None
_loop_thread = None
_loop_lock = threading.Lock()


def _is_session_closed_error(err: Exception) -> bool:
    """判断是否为 Playwright 会话/页面已关闭类错误。"""
    msg = str(err or "").lower()
    markers = [
        "target page, context or browser has been closed",
        "context has been closed",
        "browser has been closed",
        "page has been closed",
        "frame was detached",
        "net::err_aborted",
    ]
    return any(m in msg for m in markers)

def get_or_create_loop():
    """获取或创建全局事件循环"""
    global _async_loop, _loop_thread
    
    with _loop_lock:
        if _async_loop is None or _async_loop.is_closed():
            def run_loop():
                global _async_loop
                _async_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(_async_loop)
                _async_loop.run_forever()
            
            _loop_thread = threading.Thread(target=run_loop, daemon=True)
            _loop_thread.start()
            
            # 等待循环创建
            import time
            for _ in range(10):  # 最多等待1秒
                if _async_loop is not None and not _async_loop.is_closed():
                    break
                time.sleep(0.1)
    
    return _async_loop


async def start_login_session(account_id: int, platform: str = 'douyin') -> Dict:
    """
    启动登录会话，打开浏览器并获取二维码
    
    Args:
        account_id: 账号ID
        platform: 平台类型，默认'douyin'
    
    Returns:
        {
            'success': bool,
            'qrcode': str (base64编码的二维码图片),
            'message': str
        }
    """
    try:
        # 如果已有会话，先清理
        if account_id in login_sessions:
            await cleanup_login_session(account_id)
        
        # 启动浏览器。优先使用配置；在无图形桌面的服务器环境自动退化为 headless。
        playwright = await async_playwright().start()
        use_headless = LOCAL_CHROME_HEADLESS
        if not use_headless:
            # Linux 服务器常见无 DISPLAY，强制有头会启动失败。
            if os.name != 'nt' and not os.environ.get('DISPLAY'):
                use_headless = True
        browser_options = {
            'headless': use_headless
        }
        if LOCAL_CHROME_PATH and os.path.exists(LOCAL_CHROME_PATH):
            browser_options['executable_path'] = LOCAL_CHROME_PATH
        
        browser = await playwright.chromium.launch(**browser_options)
        context = await browser.new_context()
        context = await set_init_script(context)
        page = await context.new_page()
        
        # 根据平台选择登录URL
        if platform == 'douyin':
            login_url = 'https://creator.douyin.com/'
        elif platform == 'xiaohongshu':
            login_url = 'https://creator.xiaohongshu.com/login'
        elif platform == 'weixin':
            login_url = 'https://channels.weixin.qq.com/login.html'
        elif platform == 'tiktok':
            login_url = 'https://www.tiktok.com/upload'
        elif platform == 'kuaishou':
            login_url = 'https://cp.kuaishou.com/'
        else:
            login_url = 'https://creator.douyin.com/'  # 默认抖音
        
        await page.goto(login_url, wait_until='domcontentloaded', timeout=60000)
        
        # 等待页面加载
        try:
            await page.wait_for_load_state('networkidle', timeout=10000)
        except:
            # 如果networkidle超时，至少等待domcontentloaded
            try:
                await page.wait_for_load_state('domcontentloaded', timeout=5000)
            except:
                pass
        
        # 额外等待页面渲染
        await asyncio.sleep(3)
        
        # 快手：先点击「立即登录」进入登录页，才会出现扫码二维码
        if platform == 'kuaishou':
            try:
                login_now_btn = page.get_by_text("立即登录").first
                if await login_now_btn.count():
                    await login_now_btn.click(timeout=5000)
                    await asyncio.sleep(2)
                    print("已点击「立即登录」，等待扫码页面出现")
                else:
                    login_now_btn = page.get_by_role("button", name="立即登录").first
                    if await login_now_btn.count():
                        await login_now_btn.click(timeout=5000)
                        await asyncio.sleep(2)
                        print("已点击「立即登录」按钮，等待扫码页面出现")
            except Exception as e:
                print(f"点击「立即登录」失败（可能已在登录页）: {e}")
        
        # 尝试点击"扫码登录"按钮（按平台使用不同文案）
        try:
            qr_button_selectors = [
                'text=扫码登录',
                'button:has-text("扫码登录")',
                '[class*="qr"]',
                '[class*="scan"]'
            ]
            if platform == 'weixin':
                qr_button_selectors = ['text=微信扫码登录', 'text=扫码登录', 'button:has-text("扫码登录")'] + qr_button_selectors
            elif platform == 'kuaishou':
                qr_button_selectors = ['text=快手扫码登录', 'text=扫码登录', 'button:has-text("扫码登录")'] + qr_button_selectors
            
            clicked = False
            for selector in qr_button_selectors:
                try:
                    qr_button = page.locator(selector).first
                    count = await qr_button.count()
                    if count > 0:
                        await qr_button.click(timeout=5000)
                        await asyncio.sleep(2)
                        clicked = True
                        break
                except Exception as e:
                    print(f"尝试选择器 {selector} 失败: {e}")
                    continue
            
            if not clicked:
                print("未找到扫码登录按钮，可能已经在登录页面")
        except Exception as e:
            print(f"点击扫码登录按钮失败: {e}")
            # 继续尝试，可能已经在登录页面
        
        # 查找二维码图片
        qrcode_base64 = None
        sms_required = False
        max_retries = 10
        for i in range(max_retries):
            try:
                # 尝试多种选择器来查找二维码
                qr_selectors = [
                    'img[alt*="二维码"]',
                    'img[alt*="QR"]',
                    '.qrcode img',
                    '.qr-code img',
                    '[class*="qrcode"] img',
                    '[class*="qr-code"] img',
                    'canvas',
                ]
                
                for selector in qr_selectors:
                    qr_element = page.locator(selector).first
                    if await qr_element.count() > 0:
                        # 获取二维码图片的base64
                        qrcode_base64 = await qr_element.screenshot(type='png')
                        if qrcode_base64:
                            qrcode_base64 = base64.b64encode(qrcode_base64).decode('utf-8')
                            break
                
                if qrcode_base64:
                    break
                    
                await asyncio.sleep(1)
            except Exception as e:
                print(f"查找二维码失败 (尝试 {i+1}/{max_retries}): {e}")
                await asyncio.sleep(1)

        # 检测是否处于手机号/验证码登录流程
        if not qrcode_base64:
            try:
                phone_login_count = await page.get_by_text('手机号登录').count()
                sms_code_count = await page.get_by_text('验证码').count()
                sms_required = (phone_login_count > 0) or (sms_code_count > 0)
            except Exception:
                sms_required = False

        if not qrcode_base64 and not sms_required:
            # 二维码模式下必须真实拿到二维码，避免前端未展示二维码就进入“登录成功”流程
            try:
                await context.close()
            except Exception:
                pass
            try:
                await browser.close()
            except Exception:
                pass
            try:
                await playwright.stop()
            except Exception:
                pass
            return {
                'success': False,
                'qrcode': None,
                'status': 'failed',
                'login_mode': 'qrcode',
                'message': '未检测到可用二维码，请重试'
            }

        session_status = 'sms_required' if sms_required else 'waiting'

        # 保存会话信息
        login_sessions[account_id] = {
            'playwright': playwright,
            'browser': browser,
            'context': context,
            'page': page,
            'qrcode': qrcode_base64,
            'login_mode': 'sms' if sms_required else 'qrcode',
            'qrcode_seen': bool(qrcode_base64),
            'scan_seen': False,
            'status': session_status,  # waiting, scanning, sms_required, logged_in, failed
            'start_time': datetime.now(),
            'platform': platform
        }
        
        return {
            'success': True,
            'qrcode': qrcode_base64,
            'status': session_status,
            'login_mode': 'sms' if sms_required else 'qrcode',
            'message': '检测到手机号验证码登录，请在浏览器完成验证' if sms_required else ('二维码获取成功' if qrcode_base64 else '二维码获取失败，请查看页面截图')
        }
        
    except Exception as e:
        print(f"启动登录会话失败: {e}")
        return {
            'success': False,
            'qrcode': None,
            'message': f'启动登录会话失败: {str(e)}'
        }


async def check_login_status(account_id: int) -> Dict:
    """
    检查登录状态
    
    Args:
        account_id: 账号ID
    
    Returns:
        {
            'status': str,  # waiting, scanning, logged_in, failed
            'cookies': dict or None,
            'message': str
        }
    """
    if account_id not in login_sessions:
        return {
            'status': 'failed',
            'cookies': None,
            'message': '登录会话不存在，请重新启动登录'
        }
    
    session = login_sessions[account_id]
    page = session.get('page')
    context = session.get('context')
    platform = session.get('platform', 'douyin')
    
    if not page or not context:
        return {
            'status': 'failed',
            'cookies': None,
            'message': '登录会话无效，请重新启动登录'
        }

    def _allow_logged_in_transition() -> bool:
        # 二维码模式下，必须先出现“已扫描”阶段，才允许判定成功
        if session.get('login_mode') == 'qrcode':
            return bool(session.get('scan_seen'))
        return True
    
    # 按平台配置关键 cookie 与 URL
    if platform == 'xiaohongshu':
        key_cookies_list = ['web_session', 'a1', 'webId', 'gid']
        url_creator = 'creator.xiaohongshu.com'
        url_upload = 'creator.xiaohongshu.com/publish/publish'
        url_login_check = lambda u: 'login' not in u.lower()
    elif platform == 'weixin':
        # 视频号助手可能使用多种 cookie 名称，任一存在或不在登录页即视为已登录
        key_cookies_list = ['wxtoken', 'wxuin', 'MM_WX_NOTIFY_STATE', 'token', 'wx_open_id', 'app_openid']
        url_creator = 'channels.weixin.qq.com'
        url_upload = 'channels.weixin.qq.com'
        url_login_check = lambda u: 'login' not in u.lower()
    elif platform == 'tiktok':
        key_cookies_list = ['sessionid', 'sid_tt', 'tt_chain_token']
        url_creator = 'tiktok.com'
        url_upload = 'tiktok.com/upload'
        url_login_check = lambda u: 'login' not in u.lower()
    elif platform == 'kuaishou':
        key_cookies_list = ['userId', 'kuaishou.logged.in', 'did', 'token', 'clientid']
        url_creator = 'cp.kuaishou.com'
        url_upload = 'cp.kuaishou.com'
        url_login_check = lambda u: 'passport' not in u.lower() and 'login' not in u.lower()
    else:
        key_cookies_list = ['sessionid', 'passport_auth', 'sid_guard', 'passport_csrf_token', 'sid_tt']
        url_creator = 'creator.douyin.com'
        url_upload = 'creator.douyin.com/creator-micro/content/upload'
        url_login_check = lambda u: 'login' not in u.lower() and 'passport' not in u.lower()
    
    try:
        # 首先尝试获取cookies并检查是否已登录
        try:
            storage_state = await context.storage_state()
            cookies = storage_state.get('cookies', [])
            
            if cookies:
                cookie_names = [c.get('name', '') for c in cookies]
                has_key_cookie = any(name in cookie_names for name in key_cookies_list)
                
                # 微信视频号：只要不在登录页且有本域 cookie 也可视为已登录
                if platform == 'weixin' and not has_key_cookie:
                    weixin_domain_cookies = [c for c in cookies if isinstance(c, dict) and 'weixin.qq.com' in c.get('domain', '')]
                    if weixin_domain_cookies:
                        has_key_cookie = True
                # 快手：只要不在登录页且有本域 cookie 也可视为已登录
                if platform == 'kuaishou' and not has_key_cookie:
                    kuaishou_domain_cookies = [c for c in cookies if isinstance(c, dict) and 'kuaishou.com' in c.get('domain', '')]
                    if kuaishou_domain_cookies:
                        has_key_cookie = True
                
                # 重要：若仍显示「立即登录」「扫码登录」等，说明还在登录页，不能判为已登录（避免未扫码就跳转成功）
                if has_key_cookie and platform in ('weixin', 'kuaishou'):
                    try:
                        if await page.get_by_text("立即登录").count() > 0:
                            has_key_cookie = False
                        if await page.get_by_text("扫码登录").count() > 0:
                            has_key_cookie = False
                        if platform == 'kuaishou' and await page.get_by_text("快手扫码登录").count() > 0:
                            has_key_cookie = False
                        if platform == 'weixin' and await page.get_by_text("微信扫码登录").count() > 0:
                            has_key_cookie = False
                    except Exception:
                        pass
                
                if has_key_cookie:
                    try:
                        current_url = page.url
                        if url_creator in current_url and url_login_check(current_url) and _allow_logged_in_transition():
                            session['status'] = 'logged_in'
                            session['cookies'] = storage_state
                            return {
                                'status': 'logged_in',
                                'cookies': storage_state,
                                'message': '登录成功'
                            }
                    except Exception as e:
                        print(f"检查URL失败: {e}")
                    # 仅凭 cookie 不判定成功，必须满足 URL 已离开登录页。
        except Exception as e:
            print(f"获取cookies失败: {e}")
            if _is_session_closed_error(e):
                await cleanup_login_session(account_id)
                return {
                    'status': 'failed',
                    'cookies': None,
                    'message': '登录会话已关闭，请重新启动登录'
                }
        
        # 仅读取当前页面状态，不做 wait_for_load_state 等操作，避免轮询时干扰页面导致二维码刷新/失效
        try:
            current_url = page.url
            
            if url_upload in current_url:
                if not _allow_logged_in_transition():
                    return {
                        'status': 'waiting',
                        'cookies': None,
                        'message': '等待扫码登录'
                    }
                try:
                    # 微信/快手：若页面仍显示「立即登录」「扫码登录」，说明未真正登录，不返回成功
                    if platform in ('weixin', 'kuaishou'):
                        if await page.get_by_text("立即登录").count() > 0 or await page.get_by_text("扫码登录").count() > 0:
                            pass  # 不返回 logged_in，继续后续判断
                        elif platform == 'kuaishou' and await page.get_by_text("快手扫码登录").count() > 0:
                            pass
                        elif platform == 'weixin' and await page.get_by_text("微信扫码登录").count() > 0:
                            pass
                        else:
                            storage_state = await context.storage_state()
                            session['status'] = 'logged_in'
                            session['cookies'] = storage_state
                            return {'status': 'logged_in', 'cookies': storage_state, 'message': '登录成功'}
                    else:
                        storage_state = await context.storage_state()
                        session['status'] = 'logged_in'
                        session['cookies'] = storage_state
                        return {
                            'status': 'logged_in',
                            'cookies': storage_state,
                            'message': '登录成功'
                        }
                except Exception as e:
                    print(f"获取cookies失败: {e}")
                    if _is_session_closed_error(e):
                        await cleanup_login_session(account_id)
                        return {
                            'status': 'failed',
                            'cookies': None,
                            'message': '登录会话已关闭，请重新启动登录'
                        }
            
            if url_creator in current_url and url_login_check(current_url) and _allow_logged_in_transition():
                try:
                    storage_state = await context.storage_state()
                    cookies = storage_state.get('cookies', [])
                    if cookies:
                        cookie_names = [c.get('name', '') for c in cookies]
                        if any(name in cookie_names for name in key_cookies_list):
                            session['status'] = 'logged_in'
                            session['cookies'] = storage_state
                            return {
                                'status': 'logged_in',
                                'cookies': storage_state,
                                'message': '登录成功'
                            }
                except Exception as e:
                    print(f"验证cookies失败: {e}")
                    if _is_session_closed_error(e):
                        await cleanup_login_session(account_id)
                        return {
                            'status': 'failed',
                            'cookies': None,
                            'message': '登录会话已关闭，请重新启动登录'
                        }
        except Exception as e:
            print(f"检查URL失败: {e}")
            if _is_session_closed_error(e):
                await cleanup_login_session(account_id)
                return {
                    'status': 'failed',
                    'cookies': None,
                    'message': '登录会话已关闭，请重新启动登录'
                }
        
        # 安全地检查页面是否有登录元素
        login_text_count = 0
        phone_login_count = 0
        try:
            phone_login_locator = page.get_by_text('手机号登录')
            if phone_login_locator:
                phone_login_count = await phone_login_locator.count()
                login_text_count += phone_login_count
        except Exception as e:
            print(f"检查'手机号登录'文本失败: {e}")
            if _is_session_closed_error(e):
                await cleanup_login_session(account_id)
                return {
                    'status': 'failed',
                    'cookies': None,
                    'message': '登录会话已关闭，请重新启动登录'
                }
        
        try:
            qr_login_locator = page.get_by_text('扫码登录')
            if qr_login_locator:
                login_text_count += await qr_login_locator.count()
        except Exception as e:
            print(f"检查'扫码登录'文本失败: {e}")
            if _is_session_closed_error(e):
                await cleanup_login_session(account_id)
                return {
                    'status': 'failed',
                    'cookies': None,
                    'message': '登录会话已关闭，请重新启动登录'
                }
        
        try:
            if platform == 'weixin':
                weixin_qr_locator = page.get_by_text('微信扫码登录')
                if weixin_qr_locator:
                    login_text_count += await weixin_qr_locator.count()
        except Exception as e:
            print(f"检查'微信扫码登录'文本失败: {e}")
        
        try:
            if platform == 'kuaishou':
                ks_qr_locator = page.get_by_text('快手扫码登录')
                if ks_qr_locator:
                    login_text_count += await ks_qr_locator.count()
        except Exception as e:
            print(f"检查'快手扫码登录'文本失败: {e}")
        
        # 手机号验证码流程优先返回，让前端展示对应界面
        if phone_login_count > 0:
            session['status'] = 'sms_required'
            return {
                'status': 'sms_required',
                'cookies': None,
                'message': '检测到手机号验证码登录，请在浏览器中完成登录'
            }

        if login_text_count > 0:
            # 还在登录页面
            # 检查二维码是否过期
            try:
                expired_locator = page.get_by_text('二维码已过期')
                if expired_locator:
                    expired_count = await expired_locator.count()
                    if expired_count > 0:
                        session['status'] = 'failed'
                        return {
                            'status': 'failed',
                            'cookies': None,
                            'message': '二维码已过期，请重新获取'
                        }
            except Exception as e:
                print(f"检查二维码过期状态失败: {e}")
            
            # 检查是否正在扫描
            try:
                scanning_count = 0
                scanning_locator = page.get_by_text('扫描中')
                if scanning_locator:
                    scanning_count += await scanning_locator.count()
                
                confirm_locator = page.get_by_text('请确认')
                if confirm_locator:
                    scanning_count += await confirm_locator.count()
                
                if scanning_count > 0:
                    session['scan_seen'] = True
                    session['status'] = 'scanning'
                    return {
                        'status': 'scanning',
                        'cookies': None,
                        'message': '等待用户确认登录'
                    }
            except Exception as e:
                print(f"检查扫描状态失败: {e}")
            
            return {
                'status': 'waiting',
                'cookies': None,
                'message': '等待扫码登录'
            }
        else:
            # 没有登录元素，可能已登录，再次尝试获取cookies
            try:
                storage_state = await context.storage_state()
                cookies = storage_state.get('cookies', [])
                if cookies:
                    cookie_names = [c.get('name', '') for c in cookies]
                    if any(name in cookie_names for name in key_cookies_list):
                        current_url = page.url
                        if ((url_creator in current_url and url_login_check(current_url)) or (url_upload in current_url)) and _allow_logged_in_transition():
                            session['status'] = 'logged_in'
                            session['cookies'] = storage_state
                            return {
                                'status': 'logged_in',
                                'cookies': storage_state,
                                'message': '登录成功'
                            }
            except Exception as e:
                print(f"获取cookies失败: {e}")
                if _is_session_closed_error(e):
                    await cleanup_login_session(account_id)
                    return {
                        'status': 'failed',
                        'cookies': None,
                        'message': '登录会话已关闭，请重新启动登录'
                    }
            
            return {
                'status': 'waiting',
                'cookies': None,
                'message': '等待登录完成'
            }
            
    except Exception as e:
        print(f"检查登录状态失败: {e}")
        import traceback
        traceback.print_exc()
        return {
            'status': 'failed',
            'cookies': None,
            'message': f'检查登录状态失败: {str(e)}'
        }


async def get_cookies_from_session(account_id: int) -> Optional[Dict]:
    """
    从登录会话获取cookies
    
    Args:
        account_id: 账号ID
    
    Returns:
        cookies字典（Playwright storage_state格式）或None
    """
    if account_id not in login_sessions:
        return None
    
    session = login_sessions[account_id]
    
    try:
        context = session['context']
        storage_state = await context.storage_state()
        return storage_state
    except Exception as e:
        print(f"获取cookies失败: {e}")
        return None


async def cleanup_login_session(account_id: int):
    """
    清理登录会话
    
    Args:
        account_id: 账号ID
    """
    if account_id not in login_sessions:
        return
    
    session = login_sessions.get(account_id)
    if not session:
        return

    try:
        if session.get('page'):
            try:
                await session['page'].close()
            except Exception:
                pass
        if session.get('context'):
            try:
                await session['context'].close()
            except Exception:
                pass
        if session.get('browser'):
            try:
                await session['browser'].close()
            except Exception:
                pass
        if session.get('playwright'):
            try:
                await session['playwright'].stop()
            except Exception:
                pass
    finally:
        login_sessions.pop(account_id, None)


# 同步包装函数，用于在Flask中使用
def start_login_session_sync(account_id: int, platform: str = 'douyin') -> Dict:
    """同步包装函数 - 使用全局事件循环"""
    try:
        loop = get_or_create_loop()
        if loop is None or loop.is_closed():
            # 如果循环不可用，使用 asyncio.run
            return asyncio.run(start_login_session(account_id, platform))
        
        future = asyncio.run_coroutine_threadsafe(
            start_login_session(account_id, platform),
            loop
        )
        result = future.result(timeout=120)  # 2分钟超时
        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'qrcode': None,
            'message': f'启动登录会话失败: {str(e)}'
        }


def check_login_status_sync(account_id: int) -> Dict:
    """同步包装函数 - 使用全局事件循环"""
    try:
        loop = get_or_create_loop()
        if loop is None or loop.is_closed():
            # 如果循环不可用，使用 asyncio.run
            return asyncio.run(check_login_status(account_id))
        
        future = asyncio.run_coroutine_threadsafe(
            check_login_status(account_id),
            loop
        )
        result = future.result(timeout=10)  # 10秒超时
        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            'status': 'failed',
            'cookies': None,
            'message': f'检查登录状态失败: {str(e)}'
        }


def get_cookies_from_session_sync(account_id: int) -> Optional[Dict]:
    """同步包装函数 - 使用全局事件循环"""
    try:
        loop = get_or_create_loop()
        if loop is None or loop.is_closed():
            # 如果循环不可用，使用 asyncio.run
            return asyncio.run(get_cookies_from_session(account_id))
        
        future = asyncio.run_coroutine_threadsafe(
            get_cookies_from_session(account_id),
            loop
        )
        result = future.result(timeout=10)  # 10秒超时
        return result
    except Exception as e:
        print(f"获取cookies失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def cleanup_login_session_sync(account_id: int):
    """同步包装函数 - 使用全局事件循环"""
    try:
        loop = get_or_create_loop()
        if loop is None or loop.is_closed():
            # 如果循环不可用，使用 asyncio.run
            asyncio.run(cleanup_login_session(account_id))
            return
        
        future = asyncio.run_coroutine_threadsafe(
            cleanup_login_session(account_id),
            loop
        )
        future.result(timeout=10)  # 10秒超时
    except Exception as e:
        print(f"清理登录会话失败: {e}")
        import traceback
        traceback.print_exc()
        # 即便异步清理超时，也要强制移除内存会话，防止脏状态残留
        login_sessions.pop(account_id, None)
