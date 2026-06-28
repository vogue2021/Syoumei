"""部署探针：零依赖，用于判断 Python 云函数是否被平台正确构建/激活。

部署后访问 /ping：
- 返回 200 + JSON  -> Python 函数已激活，问题在 api 函数（多半是依赖 reportlab 构建失败）。
- 返回 404         -> 平台根本没构建 Python 函数（部署方式/构建配置问题）。
"""
from http.server import BaseHTTPRequestHandler
import json


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"ok": True, "msg": "pong"}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
