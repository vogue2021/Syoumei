"""EdgeOne Pages 云函数入口（Python / Flask）。

路由约定：对外路径 /api/* 由平台映射到本函数，并剥离 /api 前缀，
因此这里以空前缀注册内部路由（/generate、/feedback、/sample）。

注意：平台通过扫描 `app = Flask(...)` 字面量识别 Flask 入口，请勿改写为工厂函数调用。
"""
from flask import Flask

from service import load_env, register_routes

# 本地若存在 .env 则加载（线上由平台环境变量注入，无文件时静默跳过）
load_env()

app = Flask(__name__)
register_routes(app, api_prefix="")
