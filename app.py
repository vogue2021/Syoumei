"""本地开发服务器（与 EdgeOne Pages 部署等价的本地形态）。

- 静态前端 index.html 由本服务在 `/` 提供；线上由 EdgeOne Pages 静态托管提供。
- API 复用云函数中的 service.register_routes；本地以 `/api` 前缀挂载，
  与线上 `/api/*`（平台剥离前缀后进入云函数）保持一致的对外路径。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
# 复用 cloud-functions/api 下的后端代码，保持单一事实来源
sys.path.insert(0, str(ROOT / "cloud-functions" / "api"))

from flask import Flask, send_file  # noqa: E402

from service import load_env, register_routes  # noqa: E402

load_env(ROOT / ".env")

app = Flask(__name__, static_folder=None)


@app.route("/")
def index():
    return send_file(str(ROOT / "index.html"))


register_routes(app, api_prefix="/api")


def main() -> None:
    print("Open http://127.0.0.1:8765")
    app.run("127.0.0.1", 8765, debug=False)


if __name__ == "__main__":
    main()
