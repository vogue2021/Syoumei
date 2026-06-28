"""EdgeOne Pages 云函数入口（Python / Flask）。

路由约定：对外路径 /api/* 由平台映射到本函数。为兼容平台是否剥离 /api
前缀的不确定性，register_routes 会同时注册带/不带 /api 前缀的内部路由。

注意：
1. 平台通过扫描 `app = Flask(...)` 字面量识别 Flask 入口，请勿改写为工厂函数调用。
2. 线上以文件路径加载本模块，函数自身目录不一定在 sys.path 中，
   因此先把当前目录加入 sys.path，确保能 import 同目录的 service/generator 等辅助模块。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask

from service import load_env, register_routes

# 本地若存在 .env 则加载（线上由平台环境变量注入，无文件时静默跳过）
load_env()

app = Flask(__name__)
register_routes(app, api_prefix="")
