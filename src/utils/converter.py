from abc import ABC, abstractmethod
import zhconv

class BaseConverter(ABC):
    """文字轉換服務的抽象基類"""
    
    @abstractmethod
    def convert(self, text: str) -> str:
        """轉換文字"""
        pass

class ZhConvConverter(BaseConverter):
    """使用 zhconv 實作的簡繁轉換器 (台灣正體)"""
    
    def __init__(self, locale: str = 'zh-tw'):
        self.locale = locale
    
    def convert(self, text: str) -> str:
        if not text:
            return text
        return zhconv.convert(text, self.locale)
