from typing import Iterator
from .base import BaseExporter
from ..logger import logger


class ExcelExporter(BaseExporter):
    def export(self, question_id: str, question_title: str,
               answer_stream: Iterator[dict]):
        try:
            import openpyxl
        except ImportError:
            logger.error("Excel 导出需要 openpyxl: pip install openpyxl")
            return

        rows = list(answer_stream)
        if not rows:
            logger.warning("Excel: 无数据")
            return

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Answers"

        headers = list(rows[0].keys())
        ws.append(headers)

        for row in rows:
            ws.append([row.get(h, "") for h in headers])

        out_path = self.output_dir / "data.xlsx"
        wb.save(str(out_path))
        logger.info("Excel 导出完成: %s, 共 %d 条", out_path, len(rows))
