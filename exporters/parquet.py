from typing import Iterator
from .base import BaseExporter
from ..logger import logger


class ParquetExporter(BaseExporter):
    def export(self, question_id: str, question_title: str,
               answer_stream: Iterator[dict]):
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
            import pandas as pd
        except ImportError:
            logger.error("Parquet 导出需要 pyarrow + pandas: pip install pyarrow pandas")
            return

        rows = list(answer_stream)
        if not rows:
            logger.warning("Parquet: 无数据")
            return

        df = pd.DataFrame(rows)
        out_path = self.output_dir / "data.parquet"
        df.to_parquet(out_path, index=False, compression="zstd")
        logger.info("Parquet 导出完成: %s, 共 %d 条", out_path, len(rows))
