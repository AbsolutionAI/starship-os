import os
import json
import asyncio
import logging
from typing import Optional

log = logging.getLogger("agnetic-browser")

BROWSER_TIMEOUT = int(os.getenv("BROWSER_TIMEOUT", "30"))
BROWSER_HEADLESS = os.getenv("BROWSER_HEADLESS", "true").lower() == "true"


class BrowserManager:
    def __init__(self):
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._available = False

    async def _ensure_playwright(self):
        if self._playwright is None:
            try:
                from playwright.async_api import async_playwright
                self._playwright = async_playwright
            except ImportError:
                log.warning("playwright not installed. Install: pip install playwright && playwright install chromium")
                self._available = False
                return False
        return True

    async def start(self, headless: bool = None):
        if not await self._ensure_playwright():
            return False
        try:
            headless = BROWSER_HEADLESS if headless is None else headless
            pw = self._playwright()
            self._playwright_instance = await pw.start()
            self._browser = await self._playwright_instance.chromium.launch(headless=headless)
            self._context = await self._browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (X11; Linux x86_64) AgneticOS/1.0",
            )
            self._page = await self._context.new_page()
            self._available = True
            log.info("Browser started (headless=%s)", headless)
            return True
        except Exception as e:
            log.warning("Failed to start browser: %s", e)
            self._available = False
            return False

    async def navigate(self, url: str, timeout: int = None) -> dict:
        if not self._available:
            return {"error": True, "message": "Browser not started"}
        try:
            timeout = timeout or BROWSER_TIMEOUT
            await self._page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")
            title = await self._page.title()
            return {
                "url": self._page.url,
                "title": title,
                "status": "loaded",
                "error": False,
            }
        except Exception as e:
            return {"error": True, "message": str(e)}

    async def screenshot(self, full_page: bool = False) -> dict:
        if not self._available:
            return {"error": True, "message": "Browser not started"}
        try:
            import base64
            screenshot_bytes = await self._page.screenshot(full_page=full_page)
            b64 = base64.b64encode(screenshot_bytes).decode()
            return {"screenshot": b64, "format": "png", "error": False}
        except Exception as e:
            return {"error": True, "message": str(e)}

    async def get_content(self) -> dict:
        if not self._available:
            return {"error": True, "message": "Browser not started"}
        try:
            html = await self._page.content()
            text = await self._page.evaluate("document.body.innerText")
            return {
                "html": html[:50000],
                "text": text[:20000],
                "url": self._page.url,
                "error": False,
            }
        except Exception as e:
            return {"error": True, "message": str(e)}

    async def click(self, selector: str) -> dict:
        if not self._available:
            return {"error": True, "message": "Browser not started"}
        try:
            await self._page.click(selector, timeout=BROWSER_TIMEOUT * 1000)
            return {"selector": selector, "status": "clicked", "error": False}
        except Exception as e:
            return {"error": True, "message": str(e)}

    async def fill(self, selector: str, value: str) -> dict:
        if not self._available:
            return {"error": True, "message": "Browser not started"}
        try:
            await self._page.fill(selector, value)
            return {"selector": selector, "status": "filled", "error": False}
        except Exception as e:
            return {"error": True, "message": str(e)}

    async def evaluate(self, script: str) -> dict:
        if not self._available:
            return {"error": True, "message": "Browser not started"}
        try:
            result = await self._page.evaluate(script)
            return {"result": str(result)[:5000], "error": False}
        except Exception as e:
            return {"error": True, "message": str(e)}

    async def close(self):
        if self._page:
            try:
                await self._page.close()
            except Exception:
                pass
            self._page = None
        if self._context:
            try:
                await self._context.close()
            except Exception:
                pass
            self._context = None
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None
        if hasattr(self, '_playwright_instance') and self._playwright_instance:
            try:
                await self._playwright_instance.stop()
            except Exception:
                pass
        self._available = False
        log.info("Browser closed")

    @property
    def is_available(self) -> bool:
        return self._available


_browser = BrowserManager()


async def ensure_browser() -> BrowserManager:
    if not _browser.is_available:
        await _browser.start()
    return _browser
