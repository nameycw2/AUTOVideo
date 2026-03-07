"""
Local login agent.

Run on user machine and expose localhost HTTP APIs for frontend:
- POST /login/start
- GET  /login/status
- POST /login/complete
- POST /login/cancel
"""

from __future__ import annotations

import asyncio
import base64
import os
import threading
from datetime import datetime
from typing import Dict, Optional, Tuple

import requests
from flask import Flask, jsonify, request
from playwright.async_api import async_playwright

app = Flask(__name__)

SESSIONS: Dict[int, Dict] = {}
_ASYNC_LOOP = None
_LOOP_THREAD = None
_LOOP_LOCK = threading.Lock()


def _json_ok(data=None, message="ok", code=200):
    return jsonify({"code": code, "message": message, "data": data or {}})


def _json_err(message, code=400):
    return jsonify({"code": code, "message": message, "data": None}), code


@app.after_request
def _cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return resp


@app.route("/<path:path>", methods=["OPTIONS"])
def _options(path):
    return _json_ok()


def _get_or_create_loop():
    global _ASYNC_LOOP, _LOOP_THREAD
    with _LOOP_LOCK:
        if _ASYNC_LOOP is None or _ASYNC_LOOP.is_closed():
            def _run():
                global _ASYNC_LOOP
                _ASYNC_LOOP = asyncio.new_event_loop()
                asyncio.set_event_loop(_ASYNC_LOOP)
                _ASYNC_LOOP.run_forever()

            _LOOP_THREAD = threading.Thread(target=_run, daemon=True)
            _LOOP_THREAD.start()
            for _ in range(20):
                if _ASYNC_LOOP is not None and not _ASYNC_LOOP.is_closed():
                    break
                import time
                time.sleep(0.05)
    return _ASYNC_LOOP


def _run_coro(coro, timeout=120):
    loop = _get_or_create_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=timeout)


def _platform_rules(platform: str):
    if platform == "xiaohongshu":
        return (
            "https://creator.xiaohongshu.com/login",
            "creator.xiaohongshu.com",
            "creator.xiaohongshu.com/publish/publish",
            lambda u: "login" not in u.lower(),
            ["web_session", "a1", "webId", "gid"],
        )
    if platform == "weixin":
        return (
            "https://channels.weixin.qq.com/login.html",
            "channels.weixin.qq.com",
            "channels.weixin.qq.com",
            lambda u: "login" not in u.lower(),
            ["wxtoken", "wxuin", "MM_WX_NOTIFY_STATE", "token", "wx_open_id", "app_openid"],
        )
    if platform == "tiktok":
        return (
            "https://www.tiktok.com/upload",
            "tiktok.com",
            "tiktok.com/upload",
            lambda u: "login" not in u.lower(),
            ["sessionid", "sid_tt", "tt_chain_token"],
        )
    if platform == "kuaishou":
        return (
            "https://cp.kuaishou.com/",
            "cp.kuaishou.com",
            "cp.kuaishou.com",
            lambda u: "passport" not in u.lower() and "login" not in u.lower(),
            ["userId", "kuaishou.logged.in", "did", "token", "clientid"],
        )
    return (
        "https://creator.douyin.com/",
        "creator.douyin.com",
        "creator.douyin.com/creator-micro/content/upload",
        lambda u: "login" not in u.lower() and "passport" not in u.lower(),
        ["sessionid", "passport_auth", "sid_guard", "passport_csrf_token", "sid_tt"],
    )


async def _cleanup(account_id: int):
    session = SESSIONS.pop(account_id, None)
    if not session:
        return
    for key in ("page", "context", "browser"):
        obj = session.get(key)
        if obj:
            try:
                await obj.close()
            except Exception:
                pass
    pw = session.get("playwright")
    if pw:
        try:
            await pw.stop()
        except Exception:
            pass


async def _start(account_id: int, platform: str):
    if account_id in SESSIONS:
        await _cleanup(account_id)

    login_url, _, _, _, _ = _platform_rules(platform)
    pw = await async_playwright().start()
    launch_opts = {"headless": os.environ.get("LOCAL_CHROME_HEADLESS", "false").lower() == "true"}
    chrome_path = os.environ.get("LOCAL_CHROME_PATH", "").strip()
    if chrome_path and os.path.exists(chrome_path):
        launch_opts["executable_path"] = chrome_path

    browser = await pw.chromium.launch(**launch_opts)
    context = await browser.new_context()
    page = await context.new_page()
    await page.goto(login_url, wait_until="domcontentloaded", timeout=60000)
    try:
        await page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass

    qrcode = None
    sms_required = False

    selectors = [
        'img[alt*="二维码"]',
        'img[alt*="QR"]',
        ".qrcode img",
        ".qr-code img",
        '[class*="qrcode"] img',
        '[class*="qr-code"] img',
        "canvas",
    ]
    for _ in range(8):
        for selector in selectors:
            try:
                el = page.locator(selector).first
                if await el.count() > 0:
                    png = await el.screenshot(type="png")
                    if png:
                        qrcode = base64.b64encode(png).decode("utf-8")
                        break
            except Exception:
                continue
        if qrcode:
            break
        await asyncio.sleep(0.8)

    if not qrcode:
        try:
            sms_required = (await page.get_by_text("手机号登录").count()) > 0 or (await page.get_by_text("验证码").count()) > 0
        except Exception:
            sms_required = False

    if not qrcode and not sms_required:
        await _cleanup(account_id)
        return {"success": False, "status": "failed", "message": "未检测到二维码或短信验证码登录页面"}

    status = "sms_required" if sms_required else "waiting"
    SESSIONS[account_id] = {
        "playwright": pw,
        "browser": browser,
        "context": context,
        "page": page,
        "qrcode": qrcode,
        "status": status,
        "platform": platform,
        "login_mode": "sms" if sms_required else "qrcode",
        "scan_seen": False,
        "start_time": datetime.now(),
    }
    return {
        "success": True,
        "status": status,
        "login_mode": "sms" if sms_required else "qrcode",
        "qrcode": qrcode,
    }


async def _status(account_id: int):
    session = SESSIONS.get(account_id)
    if not session:
        return {"status": "failed", "message": "登录会话不存在"}

    page = session["page"]
    context = session["context"]
    platform = session["platform"]
    _, creator_host, upload_url, url_login_check, key_cookies = _platform_rules(platform)

    try:
        scanning = (await page.get_by_text("扫描中").count()) + (await page.get_by_text("请确认").count())
        if scanning > 0:
            session["scan_seen"] = True
            session["status"] = "scanning"
            return {"status": "scanning", "message": "已扫描，等待确认"}
    except Exception:
        pass

    try:
        phone_login = await page.get_by_text("手机号登录").count()
        if phone_login > 0:
            session["status"] = "sms_required"
            return {"status": "sms_required", "message": "请在浏览器中完成手机号验证码登录"}
    except Exception:
        pass

    try:
        state = await context.storage_state()
        cookies = state.get("cookies", [])
        names = [c.get("name", "") for c in cookies if isinstance(c, dict)]
        has_key_cookie = any(n in names for n in key_cookies)
        url = page.url or ""
        url_ok = (creator_host in url and url_login_check(url)) or (upload_url in url)

        if has_key_cookie and url_ok:
            if session.get("login_mode") == "qrcode" and not session.get("scan_seen"):
                return {"status": "waiting", "message": "等待扫码登录"}
            session["status"] = "logged_in"
            return {"status": "logged_in", "message": "登录成功", "cookies": state}
    except Exception as e:
        return {"status": "failed", "message": f"状态检查失败: {e}"}

    return {"status": session.get("status", "waiting"), "message": "等待登录"}


@app.route("/health", methods=["GET"])
def health():
    return _json_ok({"name": "local-agent", "ready": True})


@app.route("/login/start", methods=["POST"])
def login_start():
    data = request.json or {}
    account_id = data.get("account_id")
    platform = (data.get("platform") or "douyin").strip()
    if not account_id:
        return _json_err("account_id is required", 400)
    try:
        result = _run_coro(_start(int(account_id), platform), timeout=120)
        if result.get("success"):
            return _json_ok(result, result.get("message", "ok"))
        return _json_err(result.get("message") or "start failed", 500)
    except Exception as e:
        return _json_err(f"start failed: {e}", 500)


@app.route("/login/status", methods=["GET"])
def login_status():
    account_id = request.args.get("account_id", type=int)
    if not account_id:
        return _json_err("account_id is required", 400)
    try:
        result = _run_coro(_status(account_id), timeout=30)
        return _json_ok(result)
    except Exception as e:
        return _json_err(f"status failed: {e}", 500)


@app.route("/login/complete", methods=["POST"])
def login_complete():
    data = request.json or {}
    account_id = data.get("account_id")
    backend_base_url = (data.get("backend_base_url") or "").strip().rstrip("/")
    auth_token = (data.get("auth_token") or "").strip()
    if not account_id:
        return _json_err("account_id is required", 400)
    if not backend_base_url:
        return _json_err("backend_base_url is required", 400)
    if not auth_token:
        return _json_err("auth_token is required", 400)

    try:
        status = _run_coro(_status(int(account_id)), timeout=30)
        if status.get("status") != "logged_in":
            return _json_err(status.get("message") or "登录尚未完成", 400)

        state = status.get("cookies")
        if not state:
            session = SESSIONS.get(int(account_id))
            if session:
                state = _run_coro(session["context"].storage_state(), timeout=30)
        if not state:
            return _json_err("未获取到 cookies", 400)

        url = f"{backend_base_url}/api/login/complete_local"
        headers = {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}
        resp = requests.post(url, headers=headers, json={"account_id": int(account_id), "cookies": state}, timeout=30)
        if resp.status_code != 200:
            try:
                msg = (resp.json() or {}).get("message") or resp.text
            except Exception:
                msg = resp.text
            return _json_err(f"后端入库失败: {msg}", 500)

        _run_coro(_cleanup(int(account_id)), timeout=30)
        return _json_ok({"account_id": int(account_id), "login_status": "logged_in"}, "登录完成，cookies已保存")
    except Exception as e:
        return _json_err(f"complete failed: {e}", 500)


@app.route("/login/cancel", methods=["POST"])
def login_cancel():
    data = request.json or {}
    account_id = data.get("account_id")
    if not account_id:
        return _json_err("account_id is required", 400)
    try:
        _run_coro(_cleanup(int(account_id)), timeout=30)
        return _json_ok({"account_id": int(account_id)}, "已取消")
    except Exception as e:
        return _json_err(f"cancel failed: {e}", 500)


if __name__ == "__main__":
    host = os.environ.get("LOCAL_AGENT_HOST", "127.0.0.1")
    port = int(os.environ.get("LOCAL_AGENT_PORT", "17171"))
    app.run(host=host, port=port, debug=False)
