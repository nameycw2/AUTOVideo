# -*- coding: utf-8 -*-
"""
TikTok 网页端视频发布
使用 Playwright 加载 cookies 并打开 https://www.tiktok.com/upload 发布视频
"""
from datetime import datetime
from typing import Optional
import os
import asyncio
import json

from playwright.async_api import async_playwright, Page
from config import LOCAL_CHROME_PATH, LOCAL_CHROME_HEADLESS
from utils.base_social_media import set_init_script
from utils.log import tiktok_logger

# TikTok 网页上传页
TIKTOK_UPLOAD_URL = "https://www.tiktok.com/upload"
TIKTOK_BASE = "https://www.tiktok.com"


class TiktokVideo(object):
    """TikTok 视频发布，接口与 DouYinVideo / XiaohongshuVideo 保持一致"""

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
        self.tags = tags if isinstance(tags, list) else (tags.split(",") if tags else [])
        self.publish_date = publish_date
        self.account_file = account_file
        self.account_id = account_id
        self.thumbnail_path = thumbnail_path
        self.action_delay = max(action_delay, 0.1)
        self.local_executable_path = LOCAL_CHROME_PATH
        self.headless = LOCAL_CHROME_HEADLESS
        tiktok_logger.info(
            f"TiktokVideo initialized - title: '{self.title}', tags: {self.tags}, account_id: {account_id}"
        )

    async def _human_pause(self, multiplier: float = 1.0):
        await asyncio.sleep(self.action_delay * multiplier)

    async def _wait_for_login(self, page: Page, context, browser, max_wait_time: int = 300):
        """等待用户在 TikTok 网页端完成登录"""
        tiktok_logger.info("=" * 60)
        tiktok_logger.info("⚠️  Cookies 已失效，请在浏览器中完成 TikTok 登录")
        tiktok_logger.info(f"⏱️  系统将等待最多 {max_wait_time} 秒...")
        tiktok_logger.info("=" * 60)
        start_time = asyncio.get_event_loop().time()
        check_interval = 3
        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= max_wait_time:
                tiktok_logger.error(f"等待登录超时（{max_wait_time} 秒）")
                await context.close()
                await browser.close()
                raise Exception(f"等待登录超时（{max_wait_time} 秒），请重新尝试")
            await asyncio.sleep(check_interval)
            try:
                current_url = page.url
                if "tiktok.com" in current_url and "login" not in current_url.lower():
                    try:
                        await page.goto(TIKTOK_UPLOAD_URL, wait_until="domcontentloaded", timeout=15000)
                        await self._human_pause(2)
                    except Exception:
                        pass
                    storage_state = await context.storage_state()
                    with open(self.account_file, "w", encoding="utf-8") as f:
                        json.dump(storage_state, f, ensure_ascii=False, indent=2)
                    tiktok_logger.success("登录成功，cookies 已保存，继续发布流程")
                    return
            except Exception as e:
                tiktok_logger.warning(f"检查登录状态时出错: {e}")

    async def upload(self, playwright):
        browser_options = {"headless": self.headless}
        if self.local_executable_path and os.path.exists(self.local_executable_path):
            browser_options["executable_path"] = self.local_executable_path
        browser = await playwright.chromium.launch(**browser_options)
        context = await browser.new_context(storage_state=self.account_file)
        context = await set_init_script(context)
        page = await context.new_page()

        tiktok_logger.info(f"[+] 正在上传 - {self.title}")
        tiktok_logger.info("[-] 打开 TikTok 上传页...")
        await page.goto(TIKTOK_UPLOAD_URL, wait_until="domcontentloaded", timeout=60000)
        await self._human_pause(2)

        current_url = page.url
        if "login" in current_url.lower() or await page.get_by_text("Log in").count() > 0 or await page.get_by_text("登录").count() > 0:
            tiktok_logger.warning("检测到登录页，cookies 已失效，等待用户登录...")
            await self._wait_for_login(page, context, browser)
            await page.goto(TIKTOK_UPLOAD_URL, wait_until="domcontentloaded", timeout=15000)
            await self._human_pause(2)

        # 上传视频：TikTok 上传页通常有 file input 或拖拽区
        try:
            file_input = page.locator('input[type="file"]').first
            if await file_input.count():
                await file_input.set_input_files(self.file_path)
                tiktok_logger.info("  [-] 已选择视频文件")
            else:
                upload_zone = page.locator('[class*="upload"]').first
                if await upload_zone.count():
                    await upload_zone.locator('input[type="file"]').set_input_files(self.file_path)
                else:
                    raise Exception("未找到视频上传输入框，请检查 TikTok 上传页面结构")
        except Exception as e:
            tiktok_logger.error(f"  [-] 上传视频失败: {e}")
            await context.close()
            await browser.close()
            raise
        await self._human_pause(3)

        for _ in range(90):
            await self._human_pause(1)
            if await page.get_by_placeholder("Caption").count() or await page.get_by_placeholder("标题").count() or await page.get_by_placeholder("Add a caption").count():
                break
            if await page.locator('text=Select file').count() == 0 and await page.locator('input[type="file"]').count() > 0:
                break
        await self._human_pause(1)

        if self.title:
            try:
                for placeholder in ["Caption", "Add a caption", "标题", "Write a caption"]:
                    caption_input = page.get_by_placeholder(placeholder).first
                    if await caption_input.count():
                        await caption_input.fill(self.title[:150])
                        tiktok_logger.info(f'  [-] 已填写标题/描述: "{self.title[:50]}..."')
                        break
                else:
                    title_label = page.get_by_text("Caption").first
                    if await title_label.count():
                        await title_label.locator("..").locator("input, textarea, [contenteditable]").first.fill(self.title[:150])
            except Exception as e:
                tiktok_logger.warning(f"  [-] 填写标题失败: {e}")
        await self._human_pause(0.5)

        if self.tags:
            try:
                hashtag_el = page.get_by_placeholder("Hashtags").first
                if await hashtag_el.count():
                    tag_text = " ".join(["#" + t.strip() for t in self.tags[:10] if t and t.strip()])
                    await hashtag_el.fill(tag_text[:500])
            except Exception:
                pass
        await self._human_pause(0.5)

        publish_clicked = False
        for _ in range(60):
            await self._human_pause(1)
            try:
                for name in ["Post", "发布", "Publish", "Submit"]:
                    publish_btn = page.get_by_role("button", name=name).first
                    if await publish_btn.count():
                        await publish_btn.click()
                        publish_clicked = True
                        tiktok_logger.info("  [-] 已点击发布，等待完成...")
                        break
                if publish_clicked:
                    break
                if page.get_by_text("Post").first:
                    await page.get_by_text("Post").first.click()
                    publish_clicked = True
                    break
            except Exception:
                pass
        if not publish_clicked:
            tiktok_logger.warning("  [-] 未找到发布按钮，请检查页面")
        await self._human_pause(3)

        for _ in range(30):
            await asyncio.sleep(1)
            if await page.get_by_text("Posted").count() or await page.get_by_text("发布成功").count() or await page.get_by_text("Your video has been posted").count():
                tiktok_logger.success("  [-] 视频发布成功")
                break

        await context.storage_state(path=self.account_file)
        tiktok_logger.success("  [-] cookie 已更新")

        updated_cookies = None
        try:
            if os.path.exists(self.account_file):
                with open(self.account_file, "r", encoding="utf-8") as f:
                    updated_cookies = json.load(f)
        except Exception as e:
            tiktok_logger.warning(f"  [-] 读取 cookies 失败: {e}")

        if self.account_id and updated_cookies:
            try:
                from db import get_db
                from services.task_executor import save_cookies_to_db
                with get_db() as db:
                    save_cookies_to_db(self.account_id, updated_cookies, db)
            except Exception as e:
                tiktok_logger.warning(f"  [-] 更新数据库 cookies 失败: {e}")

        result = updated_cookies if updated_cookies else {"upload_success": True}
        try:
            await context.close()
            await browser.close()
        except Exception as e:
            tiktok_logger.warning(f"  [-] 关闭浏览器时出错: {e}")
        return result

    async def main(self):
        async with async_playwright() as playwright:
            return await self.upload(playwright)
