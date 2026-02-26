# -*- coding: utf-8 -*-
"""
微信视频号助手视频发布
使用 Playwright 加载 cookies 并打开 https://channels.weixin.qq.com 发布视频
"""
from datetime import datetime
from typing import Optional
import os
import re
import asyncio
import json

from playwright.async_api import async_playwright, Page
from config import LOCAL_CHROME_PATH, LOCAL_CHROME_HEADLESS
from utils.base_social_media import set_init_script
from utils.log import weixin_logger

# 微信视频号助手
WEIXIN_CHANNELS_BASE = "https://channels.weixin.qq.com"
WEIXIN_LOGIN_URL = "https://channels.weixin.qq.com/login.html"
# 首页（平台）：登录后在此页点击「发表视频」进入发布页
WEIXIN_PLATFORM_HOME = "https://channels.weixin.qq.com/platform/"
# 备用入口
WEIXIN_UPLOAD_URL = "https://channels.weixin.qq.com/"
WEIXIN_PLATFORM_URL = "https://channels.weixin.qq.com/platform"

# 短标题规则：符号仅支持书名号、引号、冒号、加号、问号、百分号、摄氏度，逗号用空格代替，字数6-16
WEIXIN_SHORT_TITLE_ALLOWED_RE = re.compile(
    r"[^\u4e00-\u9fffA-Za-z0-9《》\"\"「」『』：:\+?%°\s]"
)


def _weixin_short_title_sanitize(title: str, min_len: int = 6, max_len: int = 16) -> str:
    """短标题合规：仅保留允许的字符，逗号替为空格，长度 6-16 字。"""
    if not title:
        return ""
    s = title.replace("，", " ").replace(",", " ")
    s = WEIXIN_SHORT_TITLE_ALLOWED_RE.sub("", s)
    s = " ".join(s.split()).strip()  # 合并多余空格
    if len(s) > max_len:
        s = s[:max_len]
    return s


class WeixinVideo(object):
    """微信视频号视频发布，接口与 DouYinVideo / XiaohongshuVideo 保持一致"""

    def __init__(
        self,
        title: str,
        file_path: str,
        tags: list,
        publish_date,
        account_file: str,
        thumbnail_path: Optional[str] = None,
        action_delay: float = 0.3,
        account_id: Optional[int] = None,
        description: str = '',
    ):
        self.title = (title or "").strip() or title
        self.description = (description or "").strip()  # 正文/描述，填入「视频描述」区域
        self.file_path = file_path
        raw = tags if isinstance(tags, list) else (tags.split(",") if tags else [])
        self.tags = [t.strip() for t in raw if t and str(t).strip()][:10]  # 微信视频号标签最多10个
        self.publish_date = publish_date
        self.account_file = account_file
        self.account_id = account_id
        self.thumbnail_path = thumbnail_path
        self.action_delay = max(action_delay, 0.1)
        self.local_executable_path = LOCAL_CHROME_PATH
        self.headless = LOCAL_CHROME_HEADLESS
        weixin_logger.info(
            f"WeixinVideo initialized - title: '{self.title}', description: {len(self.description)} chars, tags: {self.tags}, account_id: {account_id}"
        )

    async def _human_pause(self, multiplier: float = 1.0):
        await asyncio.sleep(self.action_delay * multiplier)

    async def _wait_for_login(self, page: Page, context, browser, max_wait_time: int = 300):
        """等待用户在视频号助手完成登录"""
        weixin_logger.info("=" * 60)
        weixin_logger.info("⚠️  Cookies 已失效，请在浏览器中完成微信扫码登录")
        weixin_logger.info(f"⏱️  系统将等待最多 {max_wait_time} 秒...")
        weixin_logger.info("=" * 60)
        start_time = asyncio.get_event_loop().time()
        check_interval = 3
        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= max_wait_time:
                weixin_logger.error(f"等待登录超时（{max_wait_time} 秒）")
                await context.close()
                await browser.close()
                raise Exception(f"等待登录超时（{max_wait_time} 秒），请重新尝试")
            await asyncio.sleep(check_interval)
            try:
                current_url = page.url
                if "channels.weixin.qq.com" in current_url and "login" not in current_url.lower():
                    try:
                        await page.goto(WEIXIN_PLATFORM_HOME, wait_until="domcontentloaded", timeout=15000)
                        await self._human_pause(2)
                    except Exception:
                        pass
                    storage_state = await context.storage_state()
                    with open(self.account_file, "w", encoding="utf-8") as f:
                        json.dump(storage_state, f, ensure_ascii=False, indent=2)
                    weixin_logger.success("登录成功，cookies 已保存，继续发布流程")
                    return
            except Exception as e:
                weixin_logger.warning(f"检查登录状态时出错: {e}")

    async def upload(self, playwright):
        browser_options = {"headless": self.headless}
        if self.local_executable_path and os.path.exists(self.local_executable_path):
            browser_options["executable_path"] = self.local_executable_path
        browser = await playwright.chromium.launch(**browser_options)
        context = await browser.new_context(storage_state=self.account_file)
        context = await set_init_script(context)
        page = await context.new_page()

        weixin_logger.info(f"[+] 正在上传 - {self.title}")
        weixin_logger.info("[-] 打开视频号助手...")
        await page.goto(WEIXIN_PLATFORM_HOME, wait_until="domcontentloaded", timeout=60000)
        await self._human_pause(2)

        current_url = page.url
        # 检测登录页：URL 含 login 或页面有扫码/手机登录文案
        is_login_page = (
            "login" in current_url.lower()
            or await page.get_by_text("扫码登录").count() > 0
            or await page.get_by_text("微信扫码登录").count() > 0
            or await page.get_by_text("手机号登录").count() > 0
        )
        if is_login_page:
            weixin_logger.warning("检测到登录页，cookies 已失效，等待用户登录...")
            await self._wait_for_login(page, context, browser)
            await page.goto(WEIXIN_PLATFORM_HOME, wait_until="domcontentloaded", timeout=15000)
            await self._human_pause(2)

        # 必须在首页点击「发表视频」才能进入发布页（视频管理/发表动态），发布页才有上传输入框
        weixin_logger.info("[-] 进入首页，等待并点击「发表视频」进入发布页...")
        entered_publish = False
        for attempt in range(2):
            if entered_publish:
                break
            # 确保在平台首页
            if attempt == 1 or "platform" not in page.url:
                try:
                    await page.goto(WEIXIN_PLATFORM_HOME, wait_until="domcontentloaded", timeout=15000)
                    await self._human_pause(3)
                except Exception:
                    pass
            # 等待首页内容渲染（发表视频按钮可能由 SPA 稍后挂上）
            try:
                await page.get_by_text("发表视频").first.wait_for(state="visible", timeout=10000)
            except Exception:
                try:
                    await page.get_by_text("最近视频").first.wait_for(state="visible", timeout=5000)
                except Exception:
                    pass
            await self._human_pause(1)
            for text in ["发表视频", "发表", "发视频", "发布", "上传视频", "创作"]:
                try:
                    btn = page.get_by_role("button", name=text).first
                    if await btn.count():
                        await btn.click()
                        await self._human_pause(2)
                        entered_publish = True
                        weixin_logger.info(f"  [-] 已点击「{text}」进入发布页")
                        break
                except Exception:
                    pass
                if entered_publish:
                    break
                try:
                    btn = page.get_by_text(text).first
                    if await btn.count():
                        await btn.click()
                        await self._human_pause(2)
                        entered_publish = True
                        weixin_logger.info(f"  [-] 已点击「{text}」进入发布页")
                        break
                except Exception:
                    pass
                # 可能是链接或带 role 的 div
                if not entered_publish:
                    try:
                        btn = page.locator(f'a:has-text("{text}"), [role="button"]:has-text("{text}")').first
                        if await btn.count():
                            await btn.click()
                            await self._human_pause(2)
                            entered_publish = True
                            weixin_logger.info(f"  [-] 已点击「{text}」进入发布页")
                            break
                    except Exception:
                        pass
            if not entered_publish:
                await self._human_pause(2)
        if not entered_publish:
            weixin_logger.warning("  [-] 未在首页找到「发表视频」入口，将尝试在当前页面上传")

        # 等待发布页加载：出现上传区域或描述输入框
        weixin_logger.info("[-] 等待发布页加载...")
        for _ in range(25):
            await self._human_pause(1)
            if await page.locator('input[type="file"]').count() > 0:
                break
            if await page.get_by_placeholder("添加描述").count() > 0:
                break
            if await page.get_by_text("视频管理").count() > 0 or await page.get_by_text("发表动态").count() > 0:
                break
        await self._human_pause(1)
        file_input = None
        for _ in range(15):
            try:
                file_input = page.locator('input[type="file"]').first
                if await file_input.count():
                    break
                upload_zone = page.locator('[class*="upload"]').first
                if await upload_zone.count():
                    file_input = upload_zone.locator('input[type="file"]').first
                    if await file_input.count():
                        break
            except Exception:
                pass
            await self._human_pause(1)
        if not file_input or await file_input.count() == 0:
            await context.close()
            await browser.close()
            raise Exception(
                "未找到视频上传输入框。请确认已从首页点击「发表视频」进入发布页（视频管理/发表动态），或检查视频号助手页面结构是否变更。"
            )
        try:
            await file_input.set_input_files(self.file_path)
        except Exception as e:
            weixin_logger.error(f"  [-] 上传视频失败: {e}")
            await context.close()
            await browser.close()
            raise
        weixin_logger.info("  [-] 已选择视频文件")
        await self._human_pause(3)

        for _ in range(90):
            await self._human_pause(1)
            if await page.get_by_placeholder("添加描述").count() or await page.get_by_placeholder("概括视频主要内容").count():
                break
            if await page.get_by_placeholder("标题").count() or await page.get_by_text("标题").count():
                break
            if await page.locator('text=重新上传').count():
                break
        await self._human_pause(1)

        for _ in range(90):
            await self._human_pause(1)
            if await page.get_by_placeholder("添加描述").count() or await page.get_by_placeholder("概括视频主要内容").count():
                break
            if await page.locator('[data-placeholder="添加描述"]').count() or await page.locator(".input-editor").count():
                break
            if await page.get_by_placeholder("标题").count() or await page.get_by_text("标题").count():
                break
            if await page.locator('text=重新上传').count():
                break
        await self._human_pause(1)

        # 视频描述（正文+标签）：优先填 contenteditable 的 div.input-editor[data-placeholder="添加描述"]
        tag_part = ""
        if self.tags:
            tag_part = " " + " ".join(["#" + t.strip() for t in self.tags if t and t.strip()])
        body_content = (self.description or self.title or "").strip()
        desc_text = (body_content + tag_part).strip()[:500]
        if not desc_text:
            desc_text = (self.title or "").strip() + tag_part
        desc_text = desc_text[:500].strip()
        if desc_text:
            desc_filled = False
            try:
                # 视频号发布页：视频描述为 contenteditable，class="input-editor" data-placeholder="添加描述"
                for sel in [
                    'div.input-editor[data-placeholder="添加描述"]',
                    'div[data-placeholder="添加描述"]',
                    '.input-editor',
                ]:
                    editor = page.locator(sel).first
                    if await editor.count():
                        try:
                            await editor.wait_for(state="visible", timeout=3000)
                            await editor.click()
                            await self._human_pause(0.3)
                            await editor.fill(desc_text)
                            desc_filled = True
                            weixin_logger.info(f'  [-] 已填写视频描述（正文+话题）: "{desc_text[:50]}..."')
                            break
                        except Exception:
                            pass
                if not desc_filled:
                    for placeholder in ["添加描述", "描述", "填写描述", "请输入描述"]:
                        desc = page.get_by_placeholder(placeholder).first
                        if await desc.count():
                            await desc.fill(desc_text)
                            weixin_logger.info(f'  [-] 已填写视频描述: "{desc_text[:50]}..."')
                            break
            except Exception as e:
                weixin_logger.warning(f"  [-] 填写视频描述失败: {e}")
        await self._human_pause(0.5)

        if self.title:
            try:
                # 短标题：6-16 字，符号仅支持书名号、引号、冒号、加号、问号、百分号、摄氏度，逗号用空格代替
                short_title = _weixin_short_title_sanitize(self.title, min_len=6, max_len=16)
                if not short_title or len(short_title) < 6:
                    short_title = (self.title or "").replace("，", " ").replace(",", " ").strip()[:16]
                short_title = short_title[:16]
                for placeholder in ["概括视频主要内容", "短标题"]:
                    inp = page.get_by_placeholder(placeholder).first
                    if await inp.count():
                        await inp.fill(short_title)
                        weixin_logger.info(f'  [-] 已填写短标题(6-16字): "{short_title}"')
                        break
                else:
                    for placeholder in ["标题", "填写标题", "请输入标题"]:
                        title_input = page.get_by_placeholder(placeholder).first
                        if await title_input.count():
                            try:
                                if await title_input.is_visible():
                                    await title_input.fill(self.title[:100])
                                    weixin_logger.info(f'  [-] 已填写标题: "{self.title[:50]}..."')
                                    break
                            except Exception:
                                pass
            except Exception as e:
                weixin_logger.warning(f"  [-] 填写标题失败: {e}")
        await self._human_pause(0.5)

        publish_clicked = False
        for _ in range(60):
            await self._human_pause(1)
            try:
                for name in ["发布", "发表", "完成"]:
                    publish_btn = page.get_by_role("button", name=name).first
                    if await publish_btn.count():
                        await publish_btn.click()
                        publish_clicked = True
                        weixin_logger.info("  [-] 已点击发布，等待完成...")
                        break
                if publish_clicked:
                    break
                if page.get_by_text("发布").first:
                    await page.get_by_text("发布").first.click()
                    publish_clicked = True
                    break
            except Exception:
                pass
        if not publish_clicked:
            weixin_logger.warning("  [-] 未找到发布按钮，请检查页面")
        await self._human_pause(3)

        for _ in range(30):
            await asyncio.sleep(1)
            if await page.get_by_text("发布成功").count() or await page.get_by_text("发表成功").count():
                weixin_logger.success("  [-] 视频发布成功")
                break

        await context.storage_state(path=self.account_file)
        weixin_logger.success("  [-] cookie 已更新")

        updated_cookies = None
        try:
            if os.path.exists(self.account_file):
                with open(self.account_file, "r", encoding="utf-8") as f:
                    updated_cookies = json.load(f)
        except Exception as e:
            weixin_logger.warning(f"  [-] 读取 cookies 失败: {e}")

        if self.account_id and updated_cookies:
            try:
                from db import get_db
                from services.task_executor import save_cookies_to_db
                with get_db() as db:
                    save_cookies_to_db(self.account_id, updated_cookies, db)
            except Exception as e:
                weixin_logger.warning(f"  [-] 更新数据库 cookies 失败: {e}")

        result = updated_cookies if updated_cookies else {"upload_success": True}
        try:
            await context.close()
            await browser.close()
        except Exception as e:
            weixin_logger.warning(f"  [-] 关闭浏览器时出错: {e}")
        return result

    async def main(self):
        async with async_playwright() as playwright:
            return await self.upload(playwright)
