from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterator
from ..config import settings


class BaseExporter(ABC):
    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    @abstractmethod
    def export(self, question_id: str, question_title: str, 
               answer_stream: Iterator[dict]):
        pass
