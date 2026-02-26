# -*- coding: utf-8 -*-
"""
小红书创作者中心视频发布
使用 Playwright 加载 cookies 并打开 https://creator.xiaohongshu.com/publish/publish 发布视频
"""
from datetime import datetime
from typing import Optional, Union
import os
import re
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
        description: str = '',
    ):
        title_str = (title or "").strip()
        if len(title_str) > XHS_TITLE_MAX_LENGTH:
            raise ValueError(
                f"小红书标题最多{XHS_TITLE_MAX_LENGTH}个字符，当前{len(title_str)}字，请缩短后重试"
            )
        self.title = title_str or title
        self.description = (description or "").strip()  # 用户输入的正文/描述
        self.file_path = file_path
        # 确保 tags 为列表且每项为字符串，便于正文与话题填写
        if isinstance(tags, list):
            self.tags = [str(t).strip() for t in tags if t and str(t).strip()]
        elif tags:
            self.tags = [t.strip() for t in str(tags).split(",") if t.strip()]
        else:
            self.tags = []
        self.tags = self.tags[:20]  # 小红书单条笔记话题数量限制
        self.publish_date = publish_date
        self.account_file = account_file
        self.account_id = account_id
        self.thumbnail_path = thumbnail_path
        self.action_delay = max(action_delay, 0.1)
        self.local_executable_path = LOCAL_CHROME_PATH
        self.headless = LOCAL_CHROME_HEADLESS
        xiaohongshu_logger.info(
            f"XiaohongshuVideo initialized - title: '{self.title}', description: {len(self.description)} chars, tags: {self.tags}, account_id: {account_id}"
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

        # 等待视频上传完成，且标题/正文编辑区出现
        for _ in range(120):
            await self._human_pause(1)
            if await page.get_by_placeholder("填写标题").count() or await page.get_by_placeholder("填写标题会有更多赞哦").count():
                break
            if await page.get_by_text("标题").count():
                break
            if await page.locator('text=重新上传').count():
                break
        await self._human_pause(1)

        # 先等待并定位正文输入框（小红书为 TipTap 富文本：contenteditable + 内部 p[data-placeholder]）
        body_input = None
        try:
            # 方式1：TipTap/ProseMirror 正文框 — div.contenteditable[role=textbox] 或 .tiptap.ProseMirror
            for sel in [
                'div[contenteditable="true"][role="textbox"]',
                'div.tiptap.ProseMirror',
                '.ProseMirror[contenteditable="true"]',
            ]:
                el = page.locator(sel).first
                if await el.count():
                    try:
                        if await el.is_visible():
                            body_input = el
                            xiaohongshu_logger.info("  [-] 已通过 TipTap 正文框定位")
                            break
                    except Exception:
                        pass
                if body_input is not None:
                    break
            # 方式2：通过内部 p[data-placeholder*="输入正文描述"] 找到父级 contenteditable（TipTap 结构）
            if body_input is None:
                try:
                    editable = page.locator('div[contenteditable="true"]').filter(
                        has=page.locator('p[data-placeholder*="输入正文描述"]')
                    ).first
                    if await editable.count() and await editable.is_visible():
                        body_input = editable
                        xiaohongshu_logger.info("  [-] 已通过 data-placeholder 定位正文框")
                except Exception:
                    pass
            # 方式3：通过「输入正文描述」文案所在区域找 contenteditable
            if body_input is None:
                hint = page.get_by_text("输入正文描述").first
                if await hint.count():
                    await hint.wait_for(state="visible", timeout=5000)
                    for container in [hint.locator(".."), hint.locator("../.."), hint.locator("..").locator("..")]:
                        el = container.locator("[contenteditable=true]").first
                        if await el.count():
                            try:
                                if await el.is_visible():
                                    body_input = el
                                    break
                            except Exception:
                                pass
                        if body_input is not None:
                            break
            # 方式4：placeholder 包含「输入正文描述」的输入框（普通 input/textarea）
            if body_input is None:
                for pattern in [re.compile(r"输入正文描述"), re.compile(r"正文")]:
                    inp = page.get_by_placeholder(pattern).first
                    if await inp.count():
                        try:
                            if await inp.is_visible():
                                body_input = inp
                                break
                        except Exception:
                            pass
            # 方式5：页面上第二个 textarea
            if body_input is None:
                textareas = page.locator("textarea")
                if await textareas.count() >= 2:
                    body_input = textareas.nth(1)
        except Exception as e:
            xiaohongshu_logger.warning(f"  [-] 定位正文框时: {e}")

        # 填写标题（占位符多为「填写标题会有更多赞哦」或「填写标题」）
        if self.title and self.title.strip():
            try:
                for placeholder in ["填写标题会有更多赞哦", "填写标题"]:
                    title_input = page.get_by_placeholder(placeholder).first
                    if await title_input.count():
                        await title_input.fill(self.title[:XHS_TITLE_MAX_LENGTH])
                        break
                else:
                    title_label = page.get_by_text("标题").first
                    if await title_label.count():
                        await title_label.locator("..").locator("input, textarea").first.fill(self.title[:XHS_TITLE_MAX_LENGTH])
                xiaohongshu_logger.info(f'  [-] 已填写标题: "{self.title[:50]}..."')
            except Exception as e:
                xiaohongshu_logger.warning(f"  [-] 填写标题失败: {e}")
        await self._human_pause(0.5)

        # 填写描述/正文（小红书为笔记正文）：正文内容 + 话题标签（紧跟在后、无空格），如 1234#1#2
        try:
            tag_part = ""
            if self.tags:
                tag_part = "".join(
                    ("#" + str(t).strip() if not str(t).strip().startswith("#") else str(t).strip())
                    for t in self.tags[:20]
                    if t and str(t).strip()
                )
                xiaohongshu_logger.info(f"  [-] 将 {len(self.tags)} 个标签紧跟正文后写入: {tag_part[:80]}...")
            # 正文内容 + 标签（无空格），例如：1234#1#2
            body_content = (self.description or self.title or "").strip()
            desc_text = (body_content + tag_part).strip()[:1000]
            if not desc_text:
                desc_text = (self.title or "").strip() + tag_part
            desc_text = desc_text[:1000].strip()

            filled = False
            # 优先使用前面已定位的正文输入框
            if body_input is not None:
                try:
                    await body_input.wait_for(state="visible", timeout=3000)
                    await body_input.click()
                    await self._human_pause(0.3)
                    await body_input.fill(desc_text)
                    filled = True
                    xiaohongshu_logger.info("  [-] 已填写正文（含描述与话题）")
                except Exception as e:
                    xiaohongshu_logger.warning(f"  [-] 向已定位正文框填写失败: {e}")
            if not filled:
                await self._human_pause(0.5)
                for placeholder in [
                    "输入正文描述,真诚有价值的分享予人温暖",
                    "输入正文描述",
                    "填写正文",
                    "添加正文",
                    "请输入正文",
                    "写正文",
                    "正文",
                ]:
                    inp = page.get_by_placeholder(placeholder).first
                    if await inp.count():
                        try:
                            await inp.wait_for(state="visible", timeout=3000)
                            await inp.click()
                            await self._human_pause(0.3)
                            await inp.fill(desc_text)
                            filled = True
                            xiaohongshu_logger.info("  [-] 已填写正文（含描述与话题）")
                            break
                        except Exception:
                            pass
            if not filled:
                # 通过「正文」文案找相邻的 textarea 或 contenteditable
                desc_label = page.get_by_text("正文").first
                if await desc_label.count():
                    parent = desc_label.locator("..")
                    for sel in ["textarea", "[contenteditable=true]", "input[type=text]"]:
                        el = parent.locator(sel).first
                        if await el.count():
                            try:
                                await el.wait_for(state="visible", timeout=2000)
                                await el.click()
                                await self._human_pause(0.3)
                                await el.fill(desc_text)
                                filled = True
                                xiaohongshu_logger.info("  [-] 已通过正文区域填写（含话题）")
                                break
                            except Exception:
                                pass
                    if not filled:
                        grand = desc_label.locator("../..")
                        textarea = grand.locator("textarea, [contenteditable=true]").first
                        if await textarea.count():
                            try:
                                await textarea.click()
                                await self._human_pause(0.3)
                                await textarea.fill(desc_text)
                                filled = True
                                xiaohongshu_logger.info("  [-] 已通过正文区域填写（含话题）")
                            except Exception:
                                pass
            if not filled:
                # 发布页内若有多个 textarea，第二个多为正文
                textareas = page.locator("textarea")
                n = await textareas.count()
                if n >= 2:
                    try:
                        second = textareas.nth(1)
                        await second.wait_for(state="visible", timeout=2000)
                        await second.click()
                        await self._human_pause(0.3)
                        await second.fill(desc_text)
                        xiaohongshu_logger.info("  [-] 已通过正文 textarea 填写（含话题）")
                    except Exception:
                        pass
                elif n == 1:
                    try:
                        first = textareas.first
                        await first.click()
                        await self._human_pause(0.3)
                        await first.fill(desc_text)
                        xiaohongshu_logger.info("  [-] 已通过 textarea 填写正文（含话题）")
                    except Exception:
                        pass
            if not filled:
                xiaohongshu_logger.warning("  [-] 未找到正文输入框，正文与标签可能未填充")
        except Exception as e:
            xiaohongshu_logger.warning(f"  [-] 填写正文/话题时出错: {e}")
        await self._human_pause(0.5)

        # 小红书发布时不处理封面（封面由平台从视频帧生成，无需操作）

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
