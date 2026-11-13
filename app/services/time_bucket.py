"""对旧北京无偏移 DATETIME 直接分桶，不按服务器时区二次偏移。"""

from pypika.terms import Function as SQLFunction
from tortoise.expressions import Function


class TimeBucket(Function):
    def __init__(self, field, precision, dialect):
        formats = {
            "day": ("%Y-%m-%d", "%Y-%m-%d"),
            "hour": ("%H:00", "%H:00"),
            "minute": ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%i"),
        }
        sqlite_format, mysql_format = formats[precision]
        self.dialect = dialect
        super().__init__(field, sqlite_format if dialect == "sqlite" else mysql_format)

    def _get_function_field(self, field, format_string):
        if self.dialect == "sqlite":
            # SQLite ORM 会写 "+08:00"；strftime 直接读它会转 UTC。
            # 去掉 offset 后对原本北京 wall-clock 分桶，兼容旧无偏移数据。
            return SQLFunction("strftime", format_string, SQLFunction("substr", field, 1, 19))
        return SQLFunction("DATE_FORMAT", field, format_string)
