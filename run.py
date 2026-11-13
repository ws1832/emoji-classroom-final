import uvicorn
from uvicorn.config import LOGGING_CONFIG

if __name__ == "__main__":
    # 修改默认日志配置
    LOGGING_CONFIG["formatters"]["default"]["fmt"] = "%(asctime)s - %(levelname)s - %(message)s"
    LOGGING_CONFIG["formatters"]["default"]["datefmt"] = "%Y-%m-%d %H:%M:%S"
    LOGGING_CONFIG["formatters"]["access"][
        "fmt"
    ] = '%(asctime)s - %(levelname)s - %(client_addr)s - "%(request_line)s" %(status_code)s'
    LOGGING_CONFIG["formatters"]["access"]["datefmt"] = "%Y-%m-%d %H:%M:%S"

    # 开发入口只监听本机；部署使用显式 uvicorn 命令和受限反向代理。
    uvicorn.run("app:app", host="127.0.0.1", port=9999, reload=True, log_config=LOGGING_CONFIG)
