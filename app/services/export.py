"""数据导出服务。

负责把 Emoji 记录导出为 CSV，并处理：
- 字段转义（逗号、双引号、换行符）；
- CSV 注入防护（以 =、+、-、@、制表符、回车开头的单元格前缀单引号）。
"""

import csv
import io

# 以这些字符开头的单元格可能被电子表格软件当作公式执行。
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _sanitize(value: object) -> str:
    text = "" if value is None else str(value)
    if text.startswith(_FORMULA_PREFIXES):
        return "'" + text
    return text


def _build_row(values: list[object]) -> list[str]:
    return [_sanitize(value) for value in values]


def build_csv(headers: list[str], rows: list[list[object]]) -> str:
    """构建 CSV 字符串（UTF-8，带 BOM，便于 Excel 识别中文）。"""

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow([_sanitize(header) for header in headers])
    for row in rows:
        writer.writerow(_build_row(row))
    return buffer.getvalue()


def build_csv_bytes(headers: list[str], rows: list[list[object]]) -> bytes:
    """构建带 UTF-8 BOM 的 CSV 字节流，供文件下载响应使用。"""

    content = build_csv(headers, rows)
    return ("\ufeff" + content).encode("utf-8")


def csv_row_bytes(values: list[object]) -> bytes:
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator="\n").writerow(_build_row(values))
    return buffer.getvalue().encode("utf-8")
