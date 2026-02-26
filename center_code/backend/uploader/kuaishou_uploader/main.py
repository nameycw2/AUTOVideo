# -*- coding: utf-8 -*-
"""
快手创作者服务平台视频发布
使用 Playwright 加载 cookies 并打开 https://cp.kuaishou.com 发布视频
官方流程：登录 -> 首页 -> 发布作品/内容管理 -> 上传视频 -> 填标题、文案、话题 -> 发布
"""
from datetime import datetime
from typing import Optional
import os
import asyncio
import json

from playwright.async_api import async_playwright, Page
from config import LOCAL_CHROME_PATH, LOCAL_CHROME_HEADLESS
from utils.base_social_media import set_init_script
from utils.log import kuaishou_logger

# 快手创作者服务平台
KUAISHOU_CP_BASE = "https://cp.kuaishou.com"
KUAISHOU_LOGIN_URL = "https://cp.kuaishou.com/article/publish/video"
KUAISHOU_UPLOAD_URL = "https://cp.kuaishou.com/"
# 发布作品入口（部分版本路径）
KUAISHOU_PUBLISH_PATH = "https://cp.kuaishou.com/article/publish/video"


class KuaishouVideo(object):
    """快手视频发布，接口与 DouYinVideo / WeixinVideo 保持一致"""

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
    ):
        self.title = (title or "").strip() or title
        self.file_path = file_path
        raw = tags if isinstance(tags, list) else (tags.split(",") if tags else [])
        self.tags = [t.strip() for t in raw if t and str(t).strip()][:10]
        self.publish_date = publish_date
        self.account_file = account_file
        self.account_id = account_id
        self.thumbnail_path = thumbnail_path
        self.action_delay = max(action_delay, 0.1)
        self.local_executable_path = LOCAL_CHROME_PATH
        self.headless = LOCAL_CHROME_HEADLESS
        kuaishou_logger.info(
            f"KuaishouVideo initialized - title: '{self.title}', tags: {self.tags}, account_id: {account_id}"
        )

    async def _human_pause(self, multiplier: float = 1.0):
        await asyncio.sleep(self.action_delay * multiplier)

    async def _wait_for_login(self, page: Page, context, browser, max_wait_time: int = 300):
        """等待用户在快手创作者平台完成扫码登录"""
        kuaishou_logger.info("=" * 60)
        kuaishou_logger.info("⚠️  Cookies 已失效，请使用快手 APP 扫码登录")
        kuaishou_logger.info(f"⏱️  系统将等待最多 {max_wait_time} 秒...")
        kuaishou_logger.info("=" * 60)
        start_time = asyncio.get_event_loop().time()
        check_interval = 3
        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= max_wait_time:
                kuaishou_logger.error(f"等待登录超时（{max_wait_time} 秒）")
                await context.close()
                await browser.close()
                raise Exception(f"等待登录超时（{max_wait_time} 秒），请重新尝试")
            await asyncio.sleep(check_interval)
            try:
                current_url = page.url
                if "cp.kuaishou.com" in current_url and "passport" not in current_url.lower() and "login" not in current_url.lower():
                    try:
                        await page.goto(KUAISHOU_UPLOAD_URL, wait_until="domcontentloaded", timeout=15000)
                        await self._human_pause(2)
                    except Exception:
                        pass
                    storage_state = await context.storage_state()
                    with open(self.account_file, "w", encoding="utf-8") as f:
                        json.dump(storage_state, f, ensure_ascii=False, indent=2)
                    kuaishou_logger.success("登录成功，cookies 已保存，继续发布流程")
                    return
            except Exception as e:
                kuaishou_logger.warning(f"检查登录状态时出错: {e}")

    async def upload(self, playwright):
        browser_options = {"headless": self.headless}
        if self.local_executable_path and os.path.exists(self.local_executable_path):
            browser_options["executable_path"] = self.local_executable_path
        browser = await playwright.chromium.launch(**browser_options)
        context = await browser.new_context(storage_state=self.account_file)
        context = await set_init_script(context)
        page = await context.new_page()

        kuaishou_logger.info(f"[+] 正在上传 - {self.title}")
        kuaishou_logger.info("[-] 打开快手创作者平台...")
        await page.goto(KUAISHOU_UPLOAD_URL, wait_until="domcontentloaded", timeout=60000)
        await self._human_pause(2)

        current_url = page.url
        is_login_page = (
            "passport" in current_url.lower()
            or "login" in current_url.lower()
            or await page.get_by_text("扫码登录").count() > 0
            or await page.get_by_text("快手扫码登录").count() > 0
            or await page.get_by_text("手机号登录").count() > 0
        )
        if is_login_page:
            kuaishou_logger.warning("检测到登录页，cookies 已失效，等待用户登录...")
            await self._wait_for_login(page, context, browser)
            await page.goto(KUAISHOU_UPLOAD_URL, wait_until="domcontentloaded", timeout=15000)
            await self._human_pause(2)

        # 进入发布作品入口：左侧「发布作品」或「内容管理」-> 上传视频
        entered_publish = False
        for text in ["发布作品", "发布", "上传视频", "发视频", "内容管理"]:
            try:
                btn = page.get_by_role("button", name=text).first
                if await btn.count():
                    await btn.click()
                    await self._human_pause(2)
                    entered_publish = True
                    kuaishou_logger.info(f"  [-] 已点击「{text}」")
                    break
            except Exception:
                pass
            try:
                btn = page.get_by_text(text).first
                if await btn.count():
                    await btn.click()
                    await self._human_pause(2)
                    entered_publish = True
                    kuaishou_logger.info(f"  [-] 已点击「{text}」")
                    break
            except Exception:
                pass
        if not entered_publish:
            try:
                await page.goto(KUAISHOU_PUBLISH_PATH, wait_until="domcontentloaded", timeout=15000)
                await self._human_pause(2)
            except Exception:
                pass
            kuaishou_logger.warning("  [-] 未找到发布入口，将尝试在当前页面上传")

        # 上传视频
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
            raise Exception("未找到视频上传输入框，请检查快手创作者平台页面结构")
        try:
            await file_input.set_input_files(self.file_path)
        except Exception as e:
            kuaishou_logger.error(f"  [-] 上传视频失败: {e}")
            await context.close()
            await browser.close()
            raise
        kuaishou_logger.info("  [-] 已选择视频文件")
        await self._human_pause(3)

        for _ in range(90):
            await self._human_pause(1)
            if await page.get_by_placeholder("标题").count() or await page.get_by_text("标题").count():
                break
            if await page.get_by_placeholder("填写标题").count():
                break
            if await page.locator('text=重新上传').count():
                break
        await self._human_pause(1)

        if self.title:
            try:
                for placeholder in ["标题", "填写标题", "请输入标题", "作品标题"]:
                    title_input = page.get_by_placeholder(placeholder).first
                    if await title_input.count():
                        await title_input.fill(self.title[:100])
                        kuaishou_logger.info(f'  [-] 已填写标题: "{self.title[:50]}..."')
                        break
                else:
                    title_label = page.get_by_text("标题").first
                    if await title_label.count():
                        await title_label.locator("..").locator("input, textarea").first.fill(self.title[:100])
                        kuaishou_logger.info(f'  [-] 已填写标题: "{self.title[:50]}..."')
            except Exception as e:
                kuaishou_logger.warning(f"  [-] 填写标题失败: {e}")
        await self._human_pause(0.5)

        try:
            for placeholder in ["描述", "填写描述", "作品描述", "请输入描述"]:
                desc = page.get_by_placeholder(placeholder).first
                if await desc.count():
                    desc_text = self.title
                    if self.tags:
                        desc_text += " " + " ".join(["#" + t.strip() for t in self.tags if t and t.strip()])
                    await desc.fill(desc_text[:500])
                    break
        except Exception:
            pass
        await self._human_pause(0.5)

        publish_clicked = False
        for _ in range(60):
            await self._human_pause(1)
            try:
                for name in ["发布", "发表", "完成", "确认发布"]:
                    publish_btn = page.get_by_role("button", name=name).first
                    if await publish_btn.count():
                        await publish_btn.click()
                        publish_clicked = True
                        kuaishou_logger.info("  [-] 已点击发布，等待完成...")
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
            kuaishou_logger.warning("  [-] 未找到发布按钮，请检查页面")
        await self._human_pause(3)

        for _ in range(30):
            await asyncio.sleep(1)
            if await page.get_by_text("发布成功").count() or await page.get_by_text("发表成功").count():
                kuaishou_logger.success("  [-] 视频发布成功")
                break

        await context.storage_state(path=self.account_file)
        kuaishou_logger.success("  [-] cookie 已更新")

        updated_cookies = None
        try:
            if os.path.exists(self.account_file):
                with open(self.account_file, "r", encoding="utf-8") as f:
                    updated_cookies = json.load(f)
        except Exception as e:
            kuaishou_logger.warning(f"  [-] 读取 cookies 失败: {e}")

        if self.account_id and updated_cookies:
            try:
                from db import get_db
                from services.task_executor import save_cookies_to_db
                with get_db() as db:
                    save_cookies_to_db(self.account_id, updated_cookies, db)
            except Exception as e:
                kuaishou_logger.warning(f"  [-] 更新数据库 cookies 失败: {e}")

        result = updated_cookies if updated_cookies else {"upload_success": True}
        try:
            await context.close()
            await browser.close()
        except Exception as e:
            kuaishou_logger.warning(f"  [-] 关闭浏览器时出错: {e}")
        return result

    async def main(self):
        async with async_playwright() as playwright:
            return await self.upload(playwright)
