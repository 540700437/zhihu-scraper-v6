import time
import random
from enum import Enum, auto
from typing import Callable, Optional
from playwright.sync_api import Page, TimeoutError as PWTimeoutError
from .selectors import SelectorManager
from .logger import logger


class ScrollState(Enum):
    LOADING = auto()
    STALLED = auto()
    HAS_MORE_BUTTON = auto()
    DONE = auto()
    BLOCKED = auto()


class ScrollManager:
    def __init__(self, page: Page, selector_manager: SelectorManager):
        self.page = page
        self.sm = selector_manager
        self.state = ScrollState.LOADING
        self.no_change_rounds = 0
        self.last_answer_count = 0
        self.round = 0

    def run(self, max_rounds: int = 50, timeout: int = 300,
            min_answers: int = 0) -> int:
        start_time = time.time()
        logger.info("🔄 快速滚动开始，目标最少 %d 条", min_answers)

        while self.round < max_rounds:
            elapsed = time.time() - start_time
            if elapsed > timeout:
                logger.info("⏱️ 滚动超时（%ds），停止", timeout)
                break

            if self.page.is_closed():
                logger.warning("页面已关闭")
                break

            # 检测风控
            block = self._detect_block()
            if block:
                logger.error("🚧 检测到风控: %s", block)
                self.state = ScrollState.BLOCKED
                self._handle_block()
                continue

            current_count = self._get_answer_count()
            logger.debug("  第 %d 轮，当前回答数: %d", self.round + 1, current_count)

            # 状态转换
            if current_count > self.last_answer_count:
                self.state = ScrollState.LOADING
                self.no_change_rounds = 0
            else:
                self.no_change_rounds += 1
                if self.no_change_rounds >= 2:
                    if self._click_load_more():
                        self.state = ScrollState.HAS_MORE_BUTTON
                        self.no_change_rounds = 0
                        logger.info("  点击了「加载更多」")
                    else:
                        self.state = ScrollState.STALLED

            # 终止条件
            if self.state == ScrollState.STALLED and self.no_change_rounds >= 4:
                logger.info("✅ 连续 4 轮无变化，滚动结束")
                self.state = ScrollState.DONE
                break

            if current_count >= min_answers and self.state == ScrollState.STALLED:
                logger.info("✅ 已达目标数量且稳定")
                self.state = ScrollState.DONE
                break

            # 执行快速滚动（每次滚动一屏）
            self._perform_scroll_fast()

            self.last_answer_count = current_count
            self.round += 1

            # 动态等待：如果有新内容，等 0.3~0.6 秒；否则等 0.1~0.2 秒
            if self.state == ScrollState.LOADING:
                time.sleep(random.uniform(0.3, 0.6))
            else:
                time.sleep(random.uniform(0.1, 0.2))

        return self.last_answer_count

    def _perform_scroll_fast(self):
        """快速滚动：每次滚动一屏高度，更自然且减少渲染压力"""
        self.page.evaluate("window.scrollBy(0, window.innerHeight)")
        # 小幅回滚模拟人类
        self.page.evaluate("window.scrollBy(0, -50)")
        time.sleep(random.uniform(0.1, 0.2))

    def _get_answer_count(self) -> int:
        try:
            sel = self.sm.get("answer_item")
            if not sel:
                return 0
            return self.page.locator(sel).count()
        except Exception:
            return 0

    def _click_load_more(self) -> bool:
        selectors = [
            "button:has-text('更多回答')",
            "button:has-text('查看全部')",
            "button:has-text('继续浏览')",
            "a:has-text('更多回答')",
            "[data-za-detail-view-element_name*='More' i]",
        ]
        for sel in selectors:
            try:
                btn = self.page.locator(sel).first
                if btn.count() > 0:
                    btn.scroll_into_view_if_needed(timeout=2000)
                    btn.click(timeout=2000)
                    return True
            except Exception:
                continue
        return False

    def _detect_block(self) -> Optional[str]:
        indicators = [
            "text=环境异常", "text=请完成验证", "text=安全验证",
            "text=账号存在风险", "text=请输入验证码", "text=滑动验证",
            "[class*='captcha' i]", "[class*='Captcha' i]",
        ]
        for ind in indicators:
            try:
                if self.page.locator(ind).count() > 0:
                    return ind
            except Exception:
                continue
        return None

    def _handle_block(self):
        from .config import settings
        if settings.block_policy == "abort":
            raise RuntimeError("风控拦截，策略为 abort")
        elif settings.block_policy == "wait":
            logger.warning("等待 30 秒后重试...")
            time.sleep(30)
        else:
            logger.warning("请手动处理风控...")
            input("按 Enter 继续...")