import os
import random
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError
from .config import settings
from .logger import logger


STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'plugins', {
    get: () => [
        {name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer'},
        {name: 'Native Client', filename: 'internal-nacl-plugin'},
        {name: 'Widevine Content Decryption Module', filename: 'widevinecdmadapter.dll'}
    ]
});
window.chrome = { runtime: {} };
Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications'
        ? Promise.resolve({ state: Notification.permission })
        : originalQuery(parameters)
);
"""


class BrowserManager:
    def __init__(self):
        self.playwright = None
        self.context = None
        self.page = None
    
    def __enter__(self):
        self.playwright = sync_playwright().start()
        viewport = random.choice(settings.viewport_pool)
        
        os.makedirs(settings.user_data_dir, exist_ok=True)
        
        self.context = self.playwright.chromium.launch_persistent_context(
            user_data_dir=str(settings.user_data_dir),
            headless=settings.headless,
            viewport=viewport,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
            ignore_https_errors=True,
        )
        
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        self.page.add_init_script(STEALTH_SCRIPT)
        
        logger.info("🚀 浏览器启动，视口 %dx%d", viewport["width"], viewport["height"])
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.context:
            self.context.close()
        if self.playwright:
            self.playwright.stop()
        logger.info("🛑 浏览器已关闭")
    
    def ensure_login(self, timeout: int = 300) -> bool:
        """检查 z_c0 cookie"""
        cookies = self.context.cookies("https://www.zhihu.com")
        has_login = any(c.get("name") == "z_c0" and c.get("value") for c in cookies)
        
        if has_login:
            logger.info("✅ 检测到登录态")
            return True
        
        logger.warning("⚠️ 未登录，请在浏览器中手动登录（%d 秒超时）", timeout)
        start = time.time()
        while time.time() - start < timeout:
            cookies = self.context.cookies("https://www.zhihu.com")
            if any(c.get("name") == "z_c0" and c.get("value") for c in cookies):
                logger.info("✅ 登录成功")
                return True
            import time
            time.sleep(2)
        
        logger.error("❌ 登录超时")
        return False
    
    def goto(self, url: str, retries: int = 3):
        for i in range(retries):
            try:
                self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
                return
            except PWTimeoutError:
                logger.warning("页面加载超时，重试 %d/%d", i + 1, retries)
                import time
                time.sleep(random.uniform(2, 4))
        raise RuntimeError(f"无法打开页面: {url}")
