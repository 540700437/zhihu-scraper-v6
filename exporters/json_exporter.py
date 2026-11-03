import json
from typing import Iterator
from .base import BaseExporter
from ..logger import logger


class JSONExporter(BaseExporter):
    def export(self, question_id: str, question_title: str,
               answer_stream: Iterator[dict]):
        rows = list(answer_stream)
        if not rows:
            logger.warning("JSON: 无数据")
            return
        
        out_path = self.output_dir / "data.json"
        out_path.write_text(
            json.dumps(rows, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        logger.info("JSON 导出完成: %s, 共 %d 条", out_path, len(rows))
