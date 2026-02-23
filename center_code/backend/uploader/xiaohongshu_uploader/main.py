# -*- coding: utf-8 -*-
"""
小红书创作者中心视频发布
使用 Playwright 加载 cookies 并打开 https://creator.xiaohongshu.com/publish/publish 发布视频
"""
from datetime import datetime
from typing import Optional, Union
import os
import asyncio
import json

from playwright.async_api import async_playwright, Page
from config import LOCAL_CHROME_PATH, LOCAL_CHROME_HEADLESS
from utils.base_social_media import set_init_script
from utils.log import xiaohongshu_logger

# 小红书创作者中心发布页
XHS_UPLOAD_URL = "https://creator.xiaohongshu.com/publish/publish"
XHS_CREATOR_BASE = "https://creator.xiaohongshu.com"
XHS_LOGIN_URL = "https://creator.xiaohongshu.com/login"

# 小红书标题最大字符数（平台限制）
XHS_TITLE_MAX_LENGTH = 20


class XiaohongshuVideo(object):
    """小红书视频发布，接口与 DouYinVideo 保持一致"""

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
        title_str = (title or "").strip()
        if len(title_str) > XHS_TITLE_MAX_LENGTH:
            raise ValueError(
                f"小红书标题最多{XHS_TITLE_MAX_LENGTH}个字符，当前{len(title_str)}字，请缩短后重试"
            )
        self.title = title_str or title
        self.file_path = file_path
        self.tags = tags if isinstance(tags, list) else (tags.split(",") if tags else [])
        self.publish_date = publish_date
        self.account_file = account_file
        self.account_id = account_id
        self.thumbnail_path = thumbnail_path
        self.action_delay = max(action_delay, 0.1)
        self.local_executable_path = LOCAL_CHROME_PATH
        self.headless = LOCAL_CHROME_HEADLESS
        xiaohongshu_logger.info(
            f"XiaohongshuVideo initialized - title: '{self.title}', tags: {self.tags}, account_id: {account_id}"
        )

    async def _human_pause(self, multiplier: float = 1.0):
        await asyncio.sleep(self.action_delay * multiplier)

    async def _wait_for_login(self, page: Page, context, browser, max_wait_time: int = 300):
        """等待用户在小红书创作者中心完成登录"""
        xiaohongshu_logger.info("=" * 60)
        xiaohongshu_logger.info("⚠️  Cookies 已失效，请在浏览器中完成小红书登录")
        xiaohongshu_logger.info(f"⏱️  系统将等待最多 {max_wait_time} 秒...")
        xiaohongshu_logger.info("=" * 60)
        start_time = asyncio.get_event_loop().time()
        check_interval = 3
        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= max_wait_time:
                xiaohongshu_logger.error(f"等待登录超时（{max_wait_time} 秒）")
                await context.close()
                await browser.close()
                raise Exception(f"等待登录超时（{max_wait_time} 秒），请重新尝试")
            await asyncio.sleep(check_interval)
            try:
                current_url = page.url
                if XHS_CREATOR_BASE in current_url and "login" not in current_url.lower():
                    try:
                        await page.goto(XHS_UPLOAD_URL, wait_until="domcontentloaded", timeout=15000)
                        await self._human_pause(2)
                    except Exception:
                        pass
                    storage_state = await context.storage_state()
                    with open(self.account_file, "w", encoding="utf-8") as f:
                        json.dump(storage_state, f, ensure_ascii=False, indent=2)
                    xiaohongshu_logger.success("登录成功，cookies 已保存，继续发布流程")
                    return
            except Exception as e:
                xiaohongshu_logger.warning(f"检查登录状态时出错: {e}")

    async def upload(self, playwright):
        browser_options = {"headless": self.headless}
        if self.local_executable_path and os.path.exists(self.local_executable_path):
            browser_options["executable_path"] = self.local_executable_path
        browser = await playwright.chromium.launch(**browser_options)
        context = await browser.new_context(storage_state=self.account_file)
        context = await set_init_script(context)
        page = await context.new_page()

        xiaohongshu_logger.info(f"[+] 正在上传 - {self.title}")
        xiaohongshu_logger.info("[-] 打开小红书发布页...")
        await page.goto(XHS_UPLOAD_URL, wait_until="domcontentloaded", timeout=60000)
        await self._human_pause(2)

        # 若跳转到登录页则等待用户登录
        current_url = page.url
        if "login" in current_url.lower() or await page.get_by_text("扫码登录").count() > 0 or await page.get_by_text("手机号登录").count() > 0:
            xiaohongshu_logger.warning("检测到登录页，cookies 已失效，等待用户登录...")
            await self._wait_for_login(page, context, browser)
            await page.goto(XHS_UPLOAD_URL, wait_until="domcontentloaded", timeout=15000)
            await self._human_pause(2)

        # 上传视频：优先找文件输入框
        try:
            file_input = page.locator('input[type="file"]').first
            if await file_input.count():
                await file_input.set_input_files(self.file_path)
                xiaohongshu_logger.info("  [-] 已选择视频文件")
            else:
                # 备选：通过“上传”或“选择文件”等按钮触发的上传区域
                upload_zone = page.locator('[class*="upload"]').first
                if await upload_zone.count():
                    await upload_zone.locator('input[type="file"]').set_input_files(self.file_path)
                else:
                    raise Exception("未找到视频上传输入框，请检查创作者中心页面结构")
        except Exception as e:
            xiaohongshu_logger.error(f"  [-] 上传视频失败: {e}")
            await context.close()
            await browser.close()
            raise
        await self._human_pause(3)

        # 等待视频上传完成（页面出现“重新上传”或进度消失等，按实际页面调整）
        for _ in range(120):
            await self._human_pause(1)
            # 若存在“标题”或“描述”等编辑区域，认为进入编辑页
            if await page.get_by_placeholder("填写标题").count() or await page.get_by_text("标题").count():
                break
            if await page.locator('text=重新上传').count():
                break
        await self._human_pause(1)

        # 填写标题
        if self.title and self.title.strip():
            try:
                title_input = page.get_by_placeholder("填写标题").first
                if await title_input.count():
                    await title_input.fill(self.title[:XHS_TITLE_MAX_LENGTH])
                else:
                    title_label = page.get_by_text("标题").first
                    if await title_label.count():
                        await title_label.locator("..").locator("input, textarea").first.fill(self.title[:XHS_TITLE_MAX_LENGTH])
                xiaohongshu_logger.info(f'  [-] 已填写标题: "{self.title[:50]}..."')
            except Exception as e:
                xiaohongshu_logger.warning(f"  [-] 填写标题失败: {e}")
        await self._human_pause(0.5)

        # 填写描述/正文（小红书多为笔记正文）
        try:
            desc_placeholder = page.get_by_placeholder("填写正文").first
            if await desc_placeholder.count():
                desc_text = self.title
                if self.tags:
                    desc_text += " " + " ".join(["#" + t.strip() for t in self.tags if t and t.strip()])
                await desc_placeholder.fill(desc_text[:1000])
        except Exception:
            pass
        await self._human_pause(0.5)

        # 定时发布（若有）
        if self.publish_date and isinstance(self.publish_date, datetime):
            try:
                # 若有“定时发布”开关或入口可在此扩展
                pass
            except Exception:
                pass

        # 点击发布按钮
        publish_clicked = False
        for _ in range(60):
            await self._human_pause(1)
            try:
                publish_btn = page.get_by_role("button", name="发布").first
                if await publish_btn.count():
                    await publish_btn.click()
                    publish_clicked = True
                    xiaohongshu_logger.info("  [-] 已点击发布，等待完成...")
                    break
                if page.get_by_text("发布").first:
                    await page.get_by_text("发布").first.click()
                    publish_clicked = True
                    break
            except Exception:
                pass
        if not publish_clicked:
            xiaohongshu_logger.warning("  [-] 未找到发布按钮，请检查页面")
        await self._human_pause(3)

        # 等待成功或跳转
        for _ in range(30):
            await asyncio.sleep(1)
            url = page.url
            if "publish" not in url or "success" in url.lower():
                break
            if await page.get_by_text("发布成功").count() or await page.get_by_text("发布完成").count():
                xiaohongshu_logger.success("  [-] 视频发布成功")
                break

        await context.storage_state(path=self.account_file)
        xiaohongshu_logger.success("  [-] cookie 已更新")

        updated_cookies = None
        try:
            if os.path.exists(self.account_file):
                with open(self.account_file, "r", encoding="utf-8") as f:
                    updated_cookies = json.load(f)
        except Exception as e:
            xiaohongshu_logger.warning(f"  [-] 读取 cookies 失败: {e}")

        if self.account_id and updated_cookies:
            try:
                from db import get_db
                from services.task_executor import save_cookies_to_db
                with get_db() as db:
                    save_cookies_to_db(self.account_id, updated_cookies, db)
            except Exception as e:
                xiaohongshu_logger.warning(f"  [-] 更新数据库 cookies 失败: {e}")

        result = updated_cookies if updated_cookies else {"upload_success": True}
        try:
            await context.close()
            await browser.close()
        except Exception as e:
            xiaohongshu_logger.warning(f"  [-] 关闭浏览器时出错: {e}")
        return result

    async def main(self):
        async with async_playwright() as playwright:
            return await self.upload(playwright)
