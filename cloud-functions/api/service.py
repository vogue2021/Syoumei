from __future__ import annotations

import os
import random
import re
import smtplib
import ssl
import traceback
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from flask import Response, jsonify, request

from generator import SCORE_COLUMNS, generate_pdf_bytes
from sample_data import default_data


ROOT = Path(__file__).resolve().parent

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


# 随机但合理的预置数据：让用户进入页面即可看到完整效果。
_PEOPLE = [
    ("王子轩", "Wang Zixuan", "男"),
    ("李欣怡", "Li Xinyi", "女"),
    ("张浩然", "Zhang Haoran", "男"),
    ("刘梓涵", "Liu Zihan", "女"),
    ("陈宇航", "Chen Yuhang", "男"),
    ("杨思琪", "Yang Siqi", "女"),
    ("黄俊杰", "Huang Junjie", "男"),
    ("赵可馨", "Zhao Kexin", "女"),
    ("周雨桐", "Zhou Yutong", "女"),
    ("吴梦琪", "Wu Mengqi", "女"),
]

_SCHOOLS = [
    {
        "cn": "北京市第四中学", "en": "Beijing No. 4 High School",
        "short_en": "Beijing No. 4", "jp": "北京市第四中学",
        "addr_cn": "北京市西城区西黄城根北街甲2号",
        "addr_en": "No. 2A, Xihuangchenggen North Street, Xicheng District, Beijing",
        "post": "100034",
    },
    {
        "cn": "上海市复兴高级中学", "en": "Shanghai Fuxing Senior High School",
        "short_en": "Shanghai Fuxing", "jp": "上海市復興高級中学",
        "addr_cn": "上海市虹口区国和路323号",
        "addr_en": "No. 323 Guohe Road, Hongkou District, Shanghai",
        "post": "200437",
    },
    {
        "cn": "广州市第二中学", "en": "Guangzhou No. 2 High School",
        "short_en": "Guangzhou No. 2", "jp": "広州市第二中学",
        "addr_cn": "广州市越秀区应元路21号",
        "addr_en": "No. 21 Yingyuan Road, Yuexiu District, Guangzhou",
        "post": "510030",
    },
    {
        "cn": "成都市第七中学", "en": "Chengdu No. 7 High School",
        "short_en": "Chengdu No. 7", "jp": "成都市第七中学",
        "addr_cn": "成都市武侯区林荫中街1号",
        "addr_en": "No. 1 Linyin Middle Street, Wuhou District, Chengdu",
        "post": "610041",
    },
]

_CORE_SUBJECTS = {"语文", "数学", "英语", "Chinese", "Mathematics", "English"}
_PE_SUBJECTS = {"体育", "Physical Education"}
_PASS_SUBJECTS = {"信息科技", "技术", "Technology"}


def _random_score(subject: dict[str, Any]) -> str:
    name = subject.get("name_zh") or subject.get("name") or ""
    if "实验" in name or name in _PASS_SUBJECTS:
        return "PASS"
    if name in _PE_SUBJECTS:
        return "EXCELLENT"
    if name in _CORE_SUBJECTS:
        return str(random.randint(128, 150))
    return str(random.randint(82, 99))


def random_sample() -> dict[str, Any]:
    """基于示例模板生成随机但合理的预置数据（保留科目结构与备注）。"""
    data = default_data()
    name_cn, name_roman, gender = random.choice(_PEOPLE)
    school = random.choice(_SCHOOLS)
    enroll_year = random.randint(2019, 2022)
    grad_year = enroll_year + 3
    birth_year = enroll_year - 15
    birth_month = random.randint(1, 12)
    birth_day = random.randint(1, 28)
    issue_month = random.choice([6, 7])
    issue_day = random.randint(1, 28)

    data.update({
        "language_mode": "en",
        "name_cn": name_cn,
        "name_en": name_roman,
        "name_jp": name_roman,
        "gender_cn": gender,
        "school_cn": school["cn"],
        "school_en": school["en"],
        "school_short_en": school["short_en"],
        "school_short_jp": school["jp"],
        "address_cn": school["addr_cn"],
        "address_en": school["addr_en"],
        "post_code": school["post"],
        "birth_date": f"{birth_year}-{birth_month:02d}-{birth_day:02d}",
        "issue_date": f"{grad_year}-{issue_month:02d}-{issue_day:02d}",
        "study_start_cn": f"{enroll_year} 年 9 月",
        "study_end_cn": f"{grad_year} 年 6 月",
        "study_start_en": f"September {enroll_year}",
        "study_end_en": f"June {grad_year}",
        "study_start_jp": f"{enroll_year}年9月",
        "study_end_jp": f"{grad_year}年6月",
        "enroll_month_en": f"September {enroll_year}",
        "graduate_month_en": f"June {grad_year}",
    })
    for subject in data.get("subjects", []):
        for col in SCORE_COLUMNS:
            subject[col] = _random_score(subject)
    return data


def json_to_data(payload: dict[str, Any]) -> dict[str, Any]:
    """把前端提交的 JSON 合并到示例默认值上，生成 generate_pdf 所需的数据结构。"""
    data = default_data()
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

    为兼容不同运行环境对文件系统前缀的处理（线上平台是否剥离 /api 前缀
    存在不确定性），同一组路由会同时注册到「无前缀」与「/api 前缀」两种路径：
    - /sample      与 /api/sample
    - /generate    与 /api/generate
    - /feedback    与 /api/feedback
    这样无论平台是否剥离 /api，前端的 /api/* 请求都能命中。
    """
    prefixes = {api_prefix.rstrip("/"), "/api", ""}

    def _add(rule: str, view, methods: list[str], name: str) -> None:
        for idx, prefix in enumerate(sorted(prefixes)):
            app.add_url_rule(
                prefix + rule,
                endpoint=f"{name}_{idx}",
                view_func=view,
                methods=methods,
            )

    def sample():
        return jsonify(random_sample())

    def generate():
        try:
            payload = request.get_json(force=True, silent=True) or {}
            data = json_to_data(payload)
            mode_label = MODE_LABELS.get(data.get("language_mode"), "英语版")
            action = str(payload.get("action", "generate"))
            student = data.get("name_cn") or data.get("name_en") or "学生"
            if action == "preview":
                filename = f"preview_{slug(student)}_{mode_label}.pdf"
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

    _add("/sample", sample, ["GET"], "api_sample")
    _add("/generate", generate, ["POST"], "api_generate")
    _add("/feedback", feedback, ["POST"], "api_feedback")

    # 调试兜底：仅在云函数入口（api_prefix="" ）注册，避免与本地 app.py 的 "/" 冲突。
    # 仅当上面的具体路由都没匹配时才触发，返回 Flask 实际收到的路径，
    # 用于定位平台对 /api 前缀的处理方式。定位完成后会移除。
    if api_prefix == "":
        def _debug(subpath: str = ""):
            return jsonify({
                "debug": "no route matched",
                "path": request.path,
                "full_path": request.full_path,
                "script_root": request.script_root,
                "registered": sorted({str(r) for r in app.url_map.iter_rules()}),
            }), 404

        app.add_url_rule(
            "/", endpoint="dbg_root", view_func=_debug,
            methods=["GET", "POST"],
        )
        app.add_url_rule(
            "/<path:subpath>", endpoint="dbg_any", view_func=_debug,
            methods=["GET", "POST"],
        )
