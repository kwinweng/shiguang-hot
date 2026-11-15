"""历史归档与搜索索引。frontend-v11 构建时调用 build(items, out_dir)；未合入前可跳过。"""
from .build import (ARCHIVE_DAY_SCHEMA, EMPTY_MESSAGE, HISTORY_DAY_SCHEMA, HISTORY_INDEX_SCHEMA,
                    SEARCH_INDEX_SCHEMA, TIMEZONE, beijing_date, build, empty_day_payload)

__all__ = ['ARCHIVE_DAY_SCHEMA', 'EMPTY_MESSAGE', 'HISTORY_DAY_SCHEMA', 'HISTORY_INDEX_SCHEMA',
           'SEARCH_INDEX_SCHEMA', 'TIMEZONE', 'beijing_date', 'build', 'empty_day_payload']
