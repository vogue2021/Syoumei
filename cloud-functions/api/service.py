from __future__ import annotations

import os
import re
import smtplib
import ssl
import traceback
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from flask import Response, jsonify, request

from generator import SCORE_COLUMNS, generate_pdf_bytes, load_data


ROOT = Path(__file__).resolve().parent
SAMPLE_PATH = ROOT / "sample_data.json"

FEEDBACK_TYPES = {"功能建议", "商务合作", "印章 / 公章需求", "问题反馈 / 报错", "其他"}

MODE_LABELS = {
    "en": "英语版",
    "ja": "日语版",
    "zh": "中文版",
    "zh_en": "中英双语版",
    "zh_ja": "中日双语版",
}


def load_env(path: Path = ROOT.parent.parent / ".env") -> None:
    """把 .env 中的键值读进 os.environ（不覆盖真实环境变量）。

    仅用于本地开发；线上 EdgeOne 由平台环境变量注入，无 .env 时静默跳过。
    """
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _clean_header(text: str) -> str:
    """去除可能的换行，防止邮件头注入。"""
    return re.sub(r"[\r\n]+", " ", str(text or "")).strip()


def send_feedback_email(ftype: str, contact: str, content: str) -> None:
    """通过 SMTP 把反馈发送到 FEEDBACK_TO。密钥仅来自环境变量。"""
    user = os.environ.get("SMTP_USER", "").strip()
    password = os.environ.get("SMTP_PASS", "").strip()
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com").strip()
    port = int(os.environ.get("SMTP_PORT", "587") or "587")
    to_addr = os.environ.get("FEEDBACK_TO", user).strip() or user
    if not user or not password:
        raise RuntimeError("SMTP 未配置：请配置 SMTP_USER / SMTP_PASS 环境变量")

    ftype = _clean_header(ftype)[:40] or "其他"
    contact = _clean_header(contact)[:120]
    content = str(content or "").strip()[:5000]

    msg = EmailMessage()
    msg["Subject"] = f"[{ftype}] 高中证明文书生成台 · 用户反馈"
    msg["From"] = user
    msg["To"] = to_addr
    if contact:
        msg["Reply-To"] = contact if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", contact) else user
    msg.set_content(
        f"反馈类型：{ftype}\n联系方式：{contact or '（未填写）'}\n\n具体内容：\n{content}"
    )

    context = ssl.create_default_context()
    with smtplib.SMTP(host, port, timeout=15) as server:
        server.starttls(context=context)
        server.login(user, password)
        server.send_message(msg)


def slug(text: str) -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", str(text).strip())
    return cleaned or "certificate"


def json_to_data(payload: dict[str, Any]) -> dict[str, Any]:
    """把前端提交的 JSON 合并到示例默认值上，生成 generate_pdf 所需的数据结构。"""
    data = load_data(SAMPLE_PATH)
    payload = payload or {}

    scalar_keys = [key for key in data.keys() if key != "subjects"]
    for key in scalar_keys:
        if key in payload and payload[key] is not None:
            data[key] = str(payload[key]).strip()
    # language_mode 必须能被覆盖（示例已含该键）
    if payload.get("language_mode"):
        data["language_mode"] = str(payload["language_mode"]).strip()

    raw_subjects = payload.get("subjects")
    if isinstance(raw_subjects, list):
        subjects = []
        for item in raw_subjects:
            if not isinstance(item, dict):
                continue
            name_en = str(item.get("name_en", "")).strip()
            name_ja = str(item.get("name_ja", "")).strip()
            name_zh = str(item.get("name_zh", "")).strip()
            row = {
                "name": name_en or name_ja or name_zh,
                "name_en": name_en,
                "name_ja": name_ja,
                "name_zh": name_zh,
            }
            for col in SCORE_COLUMNS:
                row[col] = str(item.get(col, "")).strip()
            if row["name"] or any(row[col] for col in SCORE_COLUMNS):
                subjects.append(row)
        data["subjects"] = subjects
    return data


def register_routes(app, api_prefix: str = "") -> None:
    """把 API 路由挂到 Flask app 上。

    - 本地开发：api_prefix="/api"，对外路径为 /api/generate 等。
    - EdgeOne 云函数：api_prefix=""（平台已剥离 /api 前缀），内部路径为 /generate 等。
    """
    prefix = api_prefix.rstrip("/")

    @app.route(prefix + "/sample", methods=["GET"], endpoint="api_sample")
    def sample():
        return jsonify(load_data(SAMPLE_PATH))

    @app.route(prefix + "/generate", methods=["POST"], endpoint="api_generate")
    def generate():
        try:
            payload = request.get_json(force=True, silent=True) or {}
            data = json_to_data(payload)
            mode_label = MODE_LABELS.get(data.get("language_mode"), "英语版")
            action = str(payload.get("action", "generate"))
            student = data.get("name_cn") or data.get("name_en") or "学生"
            if action == "preview":
                filename = f"preview_{slug(student)}_{mode_label}.pdf"
                disposition = "inline"
            else:
                filename = f"{slug(student)}_高中证明资料_{mode_label}.pdf"
                disposition = "inline"
            pdf_bytes = generate_pdf_bytes(data)
        except Exception:
            traceback.print_exc()
            return jsonify({"ok": False, "error": traceback.format_exc()}), 500

        from urllib.parse import quote
        resp = Response(pdf_bytes, mimetype="application/pdf")
        resp.headers["Content-Disposition"] = (
            f"{disposition}; filename*=UTF-8''{quote(filename)}"
        )
        resp.headers["Content-Length"] = str(len(pdf_bytes))
        return resp

    @app.route(prefix + "/feedback", methods=["POST"], endpoint="api_feedback")
    def feedback():
        try:
            payload = request.get_json(force=True, silent=True) or {}
            content = str(payload.get("content", "")).strip()
            if not content:
                return jsonify({"ok": False, "error": "内容不能为空"}), 400
            ftype = str(payload.get("type", "其他"))
            if ftype not in FEEDBACK_TYPES:
                ftype = "其他"
            send_feedback_email(ftype, str(payload.get("contact", "")), content)
            return jsonify({"ok": True})
        except RuntimeError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500
        except Exception:
            traceback.print_exc()
            return jsonify({"ok": False, "error": "邮件发送失败，请稍后重试"}), 500
