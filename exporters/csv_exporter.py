import csv
from typing import Iterator
from .base import BaseExporter
from ..logger import logger


class CSVExporter(BaseExporter):
    def export(self, question_id: str, question_title: str,
               answer_stream: Iterator[dict]):
        rows = list(answer_stream)
        if not rows:
            return
        
        out_path = self.output_dir / "data.csv"
        with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        
        logger.info("CSV 导出完成: %s", out_path)
