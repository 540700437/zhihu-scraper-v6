from dataclasses import dataclass
from typing import List, Callable, Optional, Dict
from bs4 import BeautifulSoup, Tag
from .logger import logger


@dataclass
class SelectorCandidate:
    name: str
    selector: str
    weight: float = 1.0
    validator: Optional[Callable[[str], bool]] = None


class SelectorManager:
    """页面改版时，只需修改这里的候选选择器"""
    
    REGISTRY: Dict[str, List[SelectorCandidate]] = {
        "question_title": [
            SelectorCandidate("v1", "h1.QuestionHeader-title", 1.0),
            SelectorCandidate("v2", "h1[class*='QuestionHeader']", 0.9),
            SelectorCandidate("v3", "[class*='QuestionHeader'] h1", 0.8),
            SelectorCandidate("fb", "h1", 0.3),
        ],
        "answer_item": [
            SelectorCandidate("v1", ".List-item", 1.0),
            SelectorCandidate("v2", "[class*='List-item']", 0.8),
            SelectorCandidate("v3", "div.Card.AnswerCard", 0.7),
        ],
        "rich_content": [
            SelectorCandidate("v1", ".RichContent-inner", 1.0),
            SelectorCandidate("v2", "[class*='RichContent']", 0.8),
        ],
        "author_name": [
            SelectorCandidate("v1", ".AuthorInfo-name .UserLink-link", 1.0),
            SelectorCandidate("v2", ".AuthorInfo-name", 0.8),
            SelectorCandidate("v3", "[class*='AuthorInfo'] a", 0.6),
        ],
        "vote_count": [
            SelectorCandidate("v1", ".VoteButton--up", 1.0, 
                              lambda x: any(c.isdigit() for c in x)),
            SelectorCandidate("v2", "[data-za-detail-view-element_name='VoteButton']", 0.9),
            SelectorCandidate("v3", ".ContentItem-actions button", 0.6,
                              lambda x: any(c.isdigit() for c in x)),
        ],
        "answer_time": [
            SelectorCandidate("v1", ".ContentItem-time a", 1.0),
            SelectorCandidate("v2", ".ContentItem-time", 0.8),
        ],
        "expand_button": [
            SelectorCandidate("v1", ".ContentItem-expandButton", 1.0),
            SelectorCandidate("v2", "button:has-text('展开')", 0.8),
        ],
        "load_more": [
            SelectorCandidate("strict1", "button:has-text('更多回答')", 1.0),
            SelectorCandidate("strict2", "button:has-text('查看全部')", 1.0),
            SelectorCandidate("strict3", "button:has-text('继续浏览')", 1.0),
            SelectorCandidate("loose1", "[data-za-detail-view-element_name*='More' i]", 0.7),
            SelectorCandidate("loose2", "button[class*='more' i]", 0.5),
        ],
        "favorite_count": [
            SelectorCandidate("v1", ".ContentItem-actions", 1.0,
                              lambda x: "收藏" in x),
        ],
    }
    
    def __init__(self):
        self._validated: Dict[str, str] = {}
    
    def select(self, soup: BeautifulSoup, field: str) -> Optional[str]:
        """自动测试并选择最优选择器"""
        if field in self._validated:
            return self._validated[field]
        
        candidates = self.REGISTRY.get(field, [])
        best_selector = None
        best_score = -1.0
        
        for cand in candidates:
            try:
                elements = soup.select(cand.selector)
            except Exception:
                continue
            
            if not elements:
                continue
            
            hit_score = min(len(elements), 5) * cand.weight
            
            # 验证提取内容是否合理
            validity_score = 0.0
            if cand.validator:
                try:
                    sample = elements[0].get_text(strip=True)
                    if cand.validator(sample):
                        validity_score = 2.0
                except Exception:
                    pass
            
            score = hit_score + validity_score
            if score > best_score:
                best_score = score
                best_selector = cand.selector
        
        if best_selector:
            self._validated[field] = best_selector
            logger.debug("Selector validated [%s]: %s", field, best_selector)
        else:
            logger.warning("No valid selector found for: %s", field)
        
        return best_selector
    
    def get(self, field: str) -> str:
        """获取已验证的选择器，若无则返回权重最高的候选"""
        if field in self._validated:
            return self._validated[field]
        candidates = self.REGISTRY.get(field, [])
        return candidates[0].selector if candidates else ""
