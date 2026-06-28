from __future__ import annotations

import html
import json
import os
import re
import smtplib
import ssl
import traceback
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote

from generator import OUTPUT_DIR, SCORE_COLUMNS, generate_pdf, load_data


ROOT = Path(__file__).resolve().parent
SAMPLE_PATH = ROOT / "sample_data.json"


def load_env(path: Path = ROOT / ".env") -> None:
    """把 .env 中的键值读进 os.environ（不覆盖已存在的真实环境变量）。"""
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


load_env()

FEEDBACK_TYPES = {"功能建议", "商务合作", "印章 / 公章需求", "问题反馈 / 报错", "其他"}


def _clean_header(text: str) -> str:
    """去除可能的换行，防止邮件头注入。"""
    return re.sub(r"[\r\n]+", " ", str(text or "")).strip()


def send_feedback_email(ftype: str, contact: str, content: str) -> None:
    """通过 Gmail SMTP 把反馈发送到 FEEDBACK_TO。密钥仅来自环境变量。"""
    user = os.environ.get("SMTP_USER", "").strip()
    password = os.environ.get("SMTP_PASS", "").strip()
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com").strip()
    port = int(os.environ.get("SMTP_PORT", "587") or "587")
    to_addr = os.environ.get("FEEDBACK_TO", user).strip() or user
    if not user or not password:
        raise RuntimeError("SMTP 未配置：请在 .env 中填写 SMTP_USER / SMTP_PASS")

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
    cleaned = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", text.strip())
    return cleaned or "certificate"


def esc(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


_MONTH_LOOKUP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def parse_year_month(text: object) -> str:
    """把各语言的年月文本（September 2021 / 2021 年 9 月 / 2021年9月）解析为 YYYY-MM。"""
    if not text:
        return ""
    t = str(text)
    year_match = re.search(r"(\d{4})", t)
    if not year_match:
        return ""
    year = year_match.group(1)
    month = None
    name_match = re.search(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)", t.lower())
    if name_match:
        month = _MONTH_LOOKUP[name_match.group(1)]
    else:
        for num in re.findall(r"\d+", t):
            if num != year and 1 <= int(num) <= 12:
                month = int(num)
                break
    return f"{year}-{month:02d}" if month else ""


def render_subject_rows(subjects: list[dict]) -> str:
    rows = []
    for subject in subjects:
        name_en = subject.get("name_en") or subject.get("name") or ""
        name_ja = subject.get("name_ja") or subject.get("name_jp") or subject.get("name") or ""
        name_zh = subject.get("name_zh") or subject.get("name_cn") or subject.get("name") or ""
        cells = [
            f'<td><input name="subject_name_en" value="{esc(name_en)}" class="subject-name" data-modes="en,zh_en">'
            f'<input name="subject_name_ja" value="{esc(name_ja)}" class="subject-name" data-modes="ja,zh_ja">'
            f'<input name="subject_name_zh" value="{esc(name_zh)}" class="subject-name" data-modes="zh,zh_en,zh_ja"></td>'
        ]
        for col in SCORE_COLUMNS:
            cells.append(f'<td><input name="{col}" value="{esc(subject.get(col, ""))}"></td>')
        cells.append('<td><button type="button" class="icon-btn danger" onclick="removeRow(this)">删除</button></td>')
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return "\n".join(rows)


def render_form(data: dict, message: str = "", error: str = "", preview_url: str = "") -> bytes:
    fields_left = [
        ("name_cn", "中文姓名", "zh_en,zh,zh_ja"),
        ("name_en", "英文姓名/护照姓名", "en,ja,zh_en,zh_ja"),
        ("name_jp", "日文版姓名", "ja,zh_ja"),
        ("gender_cn", "中文性别", "en,ja,zh_en,zh,zh_ja", "select:男,女"),
        ("birth_date", "出生日期", "en,ja,zh_en,zh,zh_ja", "date"),
        ("issue_date", "落款日期", "en,ja,zh_en,zh,zh_ja", "date"),
    ]
    fields_right = [
        ("school_cn", "页眉中文学校名", "en,ja,zh_en,zh,zh_ja"),
        ("school_en", "页眉英文学校名", "en,ja,zh_en,zh,zh_ja"),
        ("school_short_en", "正文英文学校简称", "en"),
        ("school_short_jp", "正文日文学校名", "ja,zh_ja"),
        ("address_cn", "页脚中文地址", "en,ja,zh_en,zh,zh_ja"),
        ("address_en", "页脚英文地址", "en,ja,zh_en,zh,zh_ja"),
        ("post_code", "邮编", "en,ja,zh_en,zh,zh_ja"),
        ("study_start_cn", "中文入学时间", "zh_en,zh,zh_ja", "monthfmt:cn"),
        ("study_end_cn", "中文毕业时间", "zh_en,zh,zh_ja", "monthfmt:cn"),
        ("study_start_en", "英文入学时间", "en,zh_en", "monthfmt:en"),
        ("study_end_en", "英文毕业时间", "en,zh_en", "monthfmt:en"),
        ("study_start_jp", "日文入学时间", "ja,zh_ja", "monthfmt:jp"),
        ("study_end_jp", "日文毕业时间", "ja,zh_ja", "monthfmt:jp"),
        ("enroll_month_en", "英文毕业证明入学月份", "en,zh_en", "monthfmt:en"),
        ("graduate_month_en", "英文毕业证明毕业月份", "en,zh_en", "monthfmt:en"),
    ]

    def control(key: str, ftype: str) -> str:
        value = data.get(key, "")
        if ftype == "date":
            return f'<input type="date" name="{key}" value="{esc(value)}">'
        if ftype.startswith("monthfmt:"):
            lang = ftype.split(":", 1)[1]
            ym = parse_year_month(value)
            display = esc(value) if value else "—"
            return (
                f'<input type="month" class="month-pick" data-lang="{lang}" value="{ym}">'
                f'<input type="hidden" name="{key}" value="{esc(value)}">'
                f'<small class="month-out">输出：{display}</small>'
            )
        if ftype.startswith("select:"):
            options = "".join(
                f'<option value="{esc(opt)}"{" selected" if str(value) == opt else ""}>{esc(opt)}</option>'
                for opt in ftype.split(":", 1)[1].split(",")
            )
            return f'<select name="{key}">{options}</select>'
        return f'<input name="{key}" value="{esc(value)}">'

    def inputs(fields: list[tuple]) -> str:
        parts = []
        for field in fields:
            key, label, modes = field[0], field[1], field[2]
            ftype = field[3] if len(field) > 3 else "text"
            parts.append(
                f'<label data-modes="{modes}"><span>{label}</span>{control(key, ftype)}</label>'
            )
        return "".join(parts)

    mode = data.get("language_mode", "en")
    rows = render_subject_rows(data.get("subjects", []))
    body = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>高中证明文书生成台</title>
  <link rel="icon" href="data:image/svg+xml,%3Csvg%20xmlns='http://www.w3.org/2000/svg'%20viewBox='0%200%2064%2064'%3E%3Crect%20x='6'%20y='6'%20width='52'%20height='52'%20rx='12'%20fill='%23b23a24'/%3E%3Crect%20x='11'%20y='11'%20width='42'%20height='42'%20rx='8'%20fill='none'%20stroke='%23fff'%20stroke-opacity='.55'%20stroke-width='2'/%3E%3Ctext%20x='32'%20y='45'%20font-size='34'%20text-anchor='middle'%20fill='%23fff'%20font-family='Songti%20SC,STSong,serif'%20font-weight='700'%3E%E8%A8%BC%3C/text%3E%3C/svg%3E">
  <style>
    :root {{
      --paper: oklch(0.968 0.012 80);
      --surface: oklch(0.997 0.004 90);
      --surface-2: oklch(0.985 0.008 80);
      --ink: oklch(0.28 0.018 50);
      --ink-soft: oklch(0.49 0.02 55);
      --line: oklch(0.87 0.014 70);
      --vermilion: oklch(0.56 0.20 30);
      --vermilion-deep: oklch(0.46 0.17 30);
      --vermilion-wash: oklch(0.95 0.035 45);
      --radius: 14px;
      --shadow-sm: 0 1px 2px rgba(80,30,15,.05);
      --shadow: 0 2px 4px rgba(80,30,15,.05), 0 14px 30px -18px rgba(150,50,25,.35);
      --serif: "Songti SC","STSong","Noto Serif CJK SC","Source Han Serif SC",Georgia,serif;
      --sans: -apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;
      --ease: cubic-bezier(0.22,1,0.36,1);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0; font-family: var(--sans); color: var(--ink); line-height: 1.5;
      background-color: var(--paper);
      background-image:
        linear-gradient(oklch(0.5 0.02 60 / 0.025) 1px, transparent 1px),
        linear-gradient(90deg, oklch(0.5 0.02 60 / 0.025) 1px, transparent 1px);
      background-size: 26px 26px;
    }}
    .site-header {{
      position: relative; overflow: hidden;
      background: linear-gradient(120deg, var(--vermilion-deep), var(--vermilion));
      color: oklch(0.99 0.01 85);
      padding: clamp(20px, 4vw, 34px) clamp(18px, 5vw, 56px);
      display: flex; align-items: center; justify-content: space-between; gap: 20px; flex-wrap: wrap;
      box-shadow: 0 2px 0 oklch(0.99 0.01 85 / 0.5), 0 5px 0 var(--vermilion-deep);
    }}
    .site-header::before {{
      content: ""; position: absolute; left: 0; right: 0; top: 0; height: 4px;
      background: repeating-linear-gradient(90deg, oklch(1 0 0 / 0.32) 0 14px, transparent 14px 28px);
      pointer-events: none;
    }}
    .site-header::after {{
      content: ""; position: absolute; inset: 0;
      background: radial-gradient(120% 140% at 88% -10%, oklch(1 0 0 / 0.18), transparent 55%);
      pointer-events: none;
    }}
    .brand {{ display: flex; align-items: center; gap: 18px; z-index: 1; }}
    .seal {{
      flex: none; width: 60px; height: 60px; border-radius: 10px;
      border: 2.5px solid oklch(0.99 0.01 85 / 0.92);
      display: grid; place-items: center;
      font-family: var(--serif); font-size: 30px; font-weight: 700;
      color: oklch(0.99 0.01 85); transform: rotate(-4deg);
      box-shadow: inset 0 0 0 1px oklch(1 0 0 / 0.25);
    }}
    .brand h1 {{ margin: 0; font-family: var(--serif); font-size: clamp(20px, 3vw, 28px); font-weight: 700; letter-spacing: 1px; }}
    .subtitle {{ margin: 5px 0 0; font-size: 13px; opacity: 0.85; letter-spacing: 2px; }}
    .header-meta {{ z-index: 1; font-size: 12px; letter-spacing: 1px; opacity: 0.92; border: 1px solid oklch(1 0 0 / 0.4); padding: 6px 13px; border-radius: 999px; }}
    main {{ max-width: 1240px; margin: clamp(18px,3vw,32px) auto clamp(40px,6vw,72px); padding: 0 clamp(14px,4vw,28px); }}
    form {{ display: grid; grid-template-columns: 1fr 1fr; gap: clamp(14px,2vw,20px); }}
    .card {{
      background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius);
      padding: clamp(16px,2vw,24px); position: relative; box-shadow: var(--shadow-sm);
      transition: box-shadow .35s var(--ease), transform .35s var(--ease), border-color .35s var(--ease);
    }}
    .card::before {{
      content: ""; position: absolute; left: 0; top: 18px; bottom: 18px; width: 3px; border-radius: 0 3px 3px 0;
      background: linear-gradient(var(--vermilion), var(--vermilion-deep)); opacity: 0; transition: opacity .35s var(--ease);
    }}
    .card:focus-within {{ box-shadow: var(--shadow); border-color: oklch(0.78 0.08 35); transform: translateY(-1px); }}
    .card:focus-within::before {{ opacity: 1; }}
    .card.hidden, label.hidden, input.hidden, select.hidden {{ display: none; }}
    h2 {{
      margin: 0 0 16px; font-family: var(--serif); font-size: 17px; font-weight: 700; letter-spacing: .5px;
      display: flex; align-items: baseline; gap: 10px; color: var(--ink);
      padding-bottom: 12px; border-bottom: 1px solid var(--line);
    }}
    h2 .idx {{ font-size: 12px; font-weight: 600; color: var(--vermilion); letter-spacing: 1px; font-family: var(--serif); }}
    label {{ display: grid; gap: 6px; margin-bottom: 13px; font-size: 12.5px; color: var(--ink-soft); letter-spacing: .3px; }}
    label span {{ font-weight: 500; }}
    input, select, textarea {{
      width: 100%; border: 1px solid var(--line); border-radius: 9px; padding: 9px 11px; font: inherit;
      background: var(--surface-2); color: var(--ink);
      transition: border-color .2s var(--ease), box-shadow .2s var(--ease), background .2s var(--ease);
    }}
    input:hover, select:hover, textarea:hover {{ border-color: oklch(0.80 0.04 50); }}
    input:focus, select:focus, textarea:focus {{
      outline: none; border-color: var(--vermilion); background: var(--surface);
      box-shadow: 0 0 0 3px var(--vermilion-wash);
    }}
    textarea {{ min-height: 88px; resize: vertical; }}
    select {{ cursor: pointer; }}
    .month-pick {{ cursor: pointer; }}
    .month-out {{ font-size: 11px; color: var(--ink-soft); letter-spacing: .3px; opacity: .9; }}
    .mode-card {{ grid-column: 1 / -1; background: linear-gradient(135deg, var(--surface), var(--vermilion-wash)); }}
    .mode-row {{ display: flex; align-items: center; gap: 20px; flex-wrap: wrap; }}
    .mode-row label {{ margin: 0; min-width: 240px; }}
    .mode-hint {{ font-size: 12.5px; color: var(--ink-soft); max-width: 480px; }}
    .wide {{ grid-column: 1 / -1; }}
    .toolbar {{ display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 14px; }}
    .toolbar h2 {{ margin: 0; border: 0; padding: 0; }}
    table {{ width: 100%; border-collapse: separate; border-spacing: 0; table-layout: fixed; font-size: 13px; }}
    thead th {{
      background: linear-gradient(var(--vermilion), var(--vermilion-deep)); color: oklch(0.99 0.01 85);
      font-size: 11.5px; font-weight: 600; letter-spacing: .5px; padding: 10px 6px; border: 0;
    }}
    thead th:first-child {{ border-radius: 9px 0 0 0; }}
    thead th:last-child {{ border-radius: 0 9px 0 0; }}
    tbody td {{ border-bottom: 1px solid var(--line); border-right: 1px solid var(--line); padding: 4px; }}
    tbody td:first-child {{ border-left: 1px solid var(--line); }}
    tbody tr:nth-child(even) td {{ background: var(--surface-2); }}
    tbody tr:hover td {{ background: var(--vermilion-wash); }}
    td input {{ border: 1px solid transparent; background: transparent; padding: 7px; border-radius: 6px; }}
    td input:focus {{ border-color: var(--vermilion); background: var(--surface); box-shadow: none; }}
    .subject-name {{ min-width: 150px; font-weight: 500; }}
    button {{
      border: 0; border-radius: 10px; background: linear-gradient(var(--vermilion), var(--vermilion-deep));
      color: oklch(0.99 0.01 85); padding: 11px 20px; font: inherit; font-weight: 600; letter-spacing: .5px; cursor: pointer;
      transition: transform .2s var(--ease), box-shadow .2s var(--ease), filter .2s var(--ease);
      box-shadow: 0 6px 16px -8px var(--vermilion-deep);
    }}
    button:hover {{ transform: translateY(-1px); filter: brightness(1.05); box-shadow: 0 10px 22px -8px var(--vermilion-deep); }}
    button:active {{ transform: translateY(0); }}
    .btn-ghost {{ background: transparent; color: var(--vermilion-deep); border: 1.5px solid var(--vermilion); box-shadow: none; }}
    .btn-ghost:hover {{ background: var(--vermilion-wash); filter: none; box-shadow: none; }}
    .icon-btn {{ padding: 7px 13px; font-size: 12px; font-weight: 600; }}
    .danger {{ background: transparent; color: var(--ink-soft); border: 1px solid var(--line); box-shadow: none; font-weight: 500; }}
    .danger:hover {{ background: oklch(0.95 0.04 25); color: var(--vermilion-deep); border-color: var(--vermilion); filter: none; box-shadow: none; }}
    .actions {{ grid-column: 1 / -1; display: flex; gap: 14px; align-items: center; padding: 4px 2px; flex-wrap: wrap; }}
    .actions .hint {{ font-size: 12px; color: var(--ink-soft); margin-left: auto; }}
    a {{ color: var(--vermilion-deep); text-decoration: none; border-bottom: 1px solid var(--vermilion-wash); }}
    a:hover {{ border-bottom-color: var(--vermilion); }}
    .notice {{ grid-column: 1 / -1; padding: 13px 16px; border-radius: 10px; font-size: 13.5px; margin-bottom: clamp(14px,2vw,20px); }}
    .message {{ background: oklch(0.96 0.04 150); border: 1px solid oklch(0.80 0.10 150); color: oklch(0.40 0.10 150); }}
    .error {{ background: oklch(0.96 0.04 25); border: 1px solid oklch(0.80 0.12 25); color: oklch(0.45 0.15 25); white-space: pre-wrap; font-family: ui-monospace, monospace; font-size: 12px; }}
    .preview {{ grid-column: 1 / -1; }}
    .preview iframe {{ width: 100%; height: 780px; border: 1px solid var(--line); border-radius: var(--radius); background: white; box-shadow: var(--shadow); }}
    .site-footer {{
      position: relative; overflow: hidden;
      margin-top: clamp(30px, 5vw, 60px);
      background: linear-gradient(120deg, var(--vermilion-deep), var(--vermilion));
      color: oklch(0.99 0.01 85);
      padding: clamp(22px, 4vw, 36px) clamp(18px, 5vw, 56px);
      display: flex; align-items: center; justify-content: space-between; gap: 24px; flex-wrap: wrap;
      box-shadow: 0 -2px 0 oklch(0.99 0.01 85 / 0.5), 0 -5px 0 var(--vermilion-deep);
    }}
    .site-footer::after {{
      content: ""; position: absolute; inset: 0;
      background: radial-gradient(120% 150% at 10% 120%, oklch(1 0 0 / 0.16), transparent 55%);
      pointer-events: none;
    }}
    .foot-brand {{ display: flex; align-items: center; gap: 16px; z-index: 1; }}
    .seal-sm {{ width: 46px; height: 46px; font-size: 23px; border-radius: 9px; }}
    .foot-brand strong {{ font-family: var(--serif); font-size: 16px; font-weight: 700; letter-spacing: .8px; }}
    .foot-brand p {{ margin: 4px 0 0; font-size: 12px; opacity: .82; letter-spacing: 1.2px; }}
    .foot-meta {{ z-index: 1; display: flex; flex-direction: column; align-items: flex-end; gap: 11px; text-align: right; }}
    .foot-langs {{ display: flex; gap: 7px; flex-wrap: wrap; justify-content: flex-end; }}
    .foot-langs span {{ font-size: 11px; letter-spacing: 1px; border: 1px solid oklch(1 0 0 / 0.42); padding: 4px 11px; border-radius: 999px; }}
    .foot-copy {{ margin: 0; font-size: 11.5px; opacity: .8; letter-spacing: .8px; }}
    .contact-fab {{
      position: fixed; right: clamp(16px,3vw,30px); bottom: clamp(16px,3vw,30px); z-index: 40;
      display: inline-flex; align-items: center; gap: 8px; padding: 12px 18px; border-radius: 999px;
      box-shadow: 0 12px 28px -8px var(--vermilion-deep);
    }}
    .contact-fab svg {{ width: 17px; height: 17px; }}
    .modal-mask {{
      position: fixed; inset: 0; z-index: 50; display: none; align-items: center; justify-content: center;
      padding: 20px; background: oklch(0.28 0.018 50 / 0.45); backdrop-filter: blur(3px);
    }}
    .modal-mask.open {{ display: flex; }}
    .modal {{
      width: min(460px, 100%); background: var(--surface); border: 1px solid var(--line);
      border-radius: var(--radius); box-shadow: var(--shadow); overflow: hidden; animation: pop .3s var(--ease);
    }}
    @keyframes pop {{ from {{ transform: translateY(12px) scale(.98); opacity: 0; }} to {{ transform: none; opacity: 1; }} }}
    .modal-head {{
      background: linear-gradient(120deg, var(--vermilion-deep), var(--vermilion)); color: oklch(0.99 0.01 85);
      padding: 15px 20px; display: flex; align-items: center; justify-content: space-between;
    }}
    .modal-head h3 {{ margin: 0; font-family: var(--serif); font-size: 16px; letter-spacing: .5px; }}
    .modal-close {{ background: transparent; box-shadow: none; padding: 2px 9px; font-size: 20px; line-height: 1; }}
    .modal-close:hover {{ background: oklch(1 0 0 / 0.16); filter: none; box-shadow: none; transform: none; }}
    .modal-body {{ padding: 20px; }}
    .modal-body label {{ margin-bottom: 14px; }}
    .contact-note {{ font-size: 12px; color: var(--ink-soft); margin: 0 0 16px; letter-spacing: .2px; line-height: 1.6; }}
    .modal-actions {{ display: flex; gap: 10px; justify-content: flex-end; margin-top: 2px; }}
    @media (max-width: 900px) {{
      form {{ grid-template-columns: 1fr; }}
      table {{ min-width: 840px; }}
      .table-scroll {{ overflow-x: auto; border-radius: var(--radius); }}
      .mode-row label {{ min-width: 100%; }}
      .site-footer {{ flex-direction: column; align-items: flex-start; }}
      .foot-meta {{ align-items: flex-start; text-align: left; }}
      .foot-langs {{ justify-content: flex-start; }}
    }}
  </style>
</head>
<body>
  <header class="site-header">
    <div class="brand">
      <div class="seal">証</div>
      <div class="brand-text">
        <h1>高中证明文书生成台</h1>
        <p class="subtitle">毕业证明 · 成绩证明 · 多语种公文排版</p>
      </div>
    </div>
    <div class="header-meta">中 · 英 · 日 · 中英 · 中日</div>
  </header>
  <main>
    {f'<div class="notice message">{message}</div>' if message else ''}
    {f'<div class="notice error">{html.escape(error)}</div>' if error else ''}
    <form method="post" onsubmit="return true">
      <section class="card mode-card">
        <h2><span class="idx">01</span>生成版本</h2>
        <div class="mode-row">
          <label><span>语言版本</span>
            <select name="language_mode" id="languageMode" onchange="syncModeFields()">
              <option value="en" {"selected" if mode == "en" else ""}>英语版</option>
              <option value="ja" {"selected" if mode == "ja" else ""}>日语版</option>
              <option value="zh" {"selected" if mode == "zh" else ""}>中文版</option>
              <option value="zh_en" {"selected" if mode == "zh_en" else ""}>中英双语版</option>
              <option value="zh_ja" {"selected" if mode == "zh_ja" else ""}>中日双语版</option>
            </select>
          </label>
          <p class="mode-hint">选择版本后，下方字段、成绩表科目名与备注会按所选语言自动切换显示。</p>
        </div>
      </section>
      <section class="card">
        <h2><span class="idx">02</span>学生信息</h2>
        {inputs(fields_left)}
      </section>
      <section class="card">
        <h2><span class="idx">03</span>学校与时间</h2>
        {inputs(fields_right)}
      </section>
      <section class="card wide">
        <div class="toolbar">
          <h2><span class="idx">04</span>成绩表</h2>
          <button type="button" class="btn-ghost icon-btn" onclick="addRow()">+ 新增科目</button>
        </div>
        <div class="table-scroll">
          <table id="scoreTable">
            <thead>
              <tr>
                <th id="subjectHeader">科目名</th><th>第一学年 前期</th><th>第一学年 后期</th><th>第二学年 前期</th><th>第二学年 后期</th><th>第三学年 前期</th><th>第三学年 后期</th><th>操作</th>
              </tr>
            </thead>
            <tbody>{rows}</tbody>
          </table>
        </div>
      </section>
      <section class="card" data-modes="en,zh_en">
        <h2><span class="idx">注</span>英文备注</h2>
        <textarea name="notes_en">{html.escape(data.get("notes_en", ""))}</textarea>
      </section>
      <section class="card" data-modes="ja,zh_ja">
        <h2><span class="idx">注</span>日文备注</h2>
        <textarea name="notes_jp">{html.escape(data.get("notes_jp", ""))}</textarea>
      </section>
      <section class="card" data-modes="zh">
        <h2><span class="idx">注</span>中文备注</h2>
        <textarea name="notes_zh">{html.escape(data.get("notes_zh", ""))}</textarea>
      </section>
      <div class="actions">
        <button type="submit" name="action" value="generate">生成 PDF</button>
        <button type="submit" name="action" value="preview" class="btn-ghost">预览 PDF</button>
        <span class="hint">生成的文件会保存到 output/pdf 目录</span>
      </div>
      {f'<section class="card preview"><h2><span class="idx">★</span>预览</h2><iframe src="{preview_url}"></iframe></section>' if preview_url else ''}
    </form>
  </main>
  <footer class="site-footer">
    <div class="foot-brand">
      <div class="seal seal-sm">証</div>
      <div>
        <strong>高中证明文书生成台</strong>
        <p>毕业证明 · 成绩证明 · 留学申请公文排版</p>
      </div>
    </div>
    <div class="foot-meta">
      <div class="foot-langs"><span>中</span><span>英</span><span>日</span><span>中英</span><span>中日</span></div>
      <p class="foot-copy">&copy; <span id="footYear"></span> 文书生成台 · 仅用于学校核发证明排版</p>
    </div>
  </footer>
  <button type="button" class="contact-fab" onclick="openContact()">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 6-10 7L2 6"/></svg>
    联系作者
  </button>
  <div class="modal-mask" id="contactMask" onclick="if(event.target===this)closeContact()">
    <div class="modal" role="dialog" aria-modal="true">
      <div class="modal-head">
        <h3>联系作者 · 反馈与合作</h3>
        <button type="button" class="modal-close" onclick="closeContact()" aria-label="关闭">&times;</button>
      </div>
      <div class="modal-body">
        <p class="contact-note">选择类型并填写内容后点击发送，反馈会直接送达作者邮箱，作者会尽快回复。</p>
        <label><span>反馈类型</span>
          <select id="ctType">
            <option value="功能建议">功能建议</option>
            <option value="商务合作">商务合作</option>
            <option value="印章 / 公章需求">印章 / 公章需求</option>
            <option value="问题反馈 / 报错">问题反馈 / 报错</option>
            <option value="其他">其他</option>
          </select>
        </label>
        <label><span>你的联系方式（邮箱 / 微信，选填）</span>
          <input id="ctContact" placeholder="方便作者回复你">
        </label>
        <label><span>具体内容</span>
          <textarea id="ctBody" placeholder="请描述你的建议、合作意向或需求…"></textarea>
        </label>
        <div class="modal-actions">
          <button type="button" class="danger" onclick="closeContact()">取消</button>
          <button type="button" onclick="sendContact()">发送邮件</button>
        </div>
      </div>
    </div>
  </div>
  <script>
    const cols = {json.dumps(SCORE_COLUMNS)};
    function addRow() {{
      const tr = document.createElement('tr');
      tr.innerHTML = '<td><input name="subject_name_en" class="subject-name" data-modes="en,zh_en">' +
        '<input name="subject_name_ja" class="subject-name" data-modes="ja,zh_ja">' +
        '<input name="subject_name_zh" class="subject-name" data-modes="zh,zh_en,zh_ja"></td>' +
        cols.map(c => `<td><input name="${{c}}"></td>`).join('') +
        '<td><button type="button" class="icon-btn danger" onclick="removeRow(this)">删除</button></td>';
      document.querySelector('#scoreTable tbody').appendChild(tr);
      syncModeFields();
    }}
    function removeRow(button) {{
      const tbody = document.querySelector('#scoreTable tbody');
      if (tbody.rows.length > 1) button.closest('tr').remove();
    }}
    function syncModeFields() {{
      const mode = document.getElementById('languageMode').value;
      document.querySelectorAll('[data-modes]').forEach(el => {{
        const modes = el.getAttribute('data-modes').split(',');
        el.classList.toggle('hidden', !modes.includes(mode));
      }});
      const labels = {{
        en: '科目名（英语版）',
        ja: '科目名（日语版）',
        zh: '科目名（中文版）',
        zh_en: '科目名（中英双语版：中文 + 英文）',
        zh_ja: '科目名（中日双语版：中文 + 日文）'
      }};
      document.getElementById('subjectHeader').textContent = labels[mode] || '科目名';
    }}
    syncModeFields();
    document.getElementById('footYear').textContent = new Date().getFullYear();
    const MONTHS_EN = ['January','February','March','April','May','June','July','August','September','October','November','December'];
    function fmtMonth(lang, ym) {{
      if (!ym) return '';
      const parts = ym.split('-');
      const y = parts[0], mi = parseInt(parts[1], 10);
      if (lang === 'en') return MONTHS_EN[mi - 1] + ' ' + y;
      if (lang === 'cn') return y + ' 年 ' + mi + ' 月';
      if (lang === 'jp') return y + '年' + mi + '月';
      return ym;
    }}
    document.querySelectorAll('.month-pick').forEach(function (pick) {{
      pick.addEventListener('change', function () {{
        const txt = fmtMonth(pick.dataset.lang, pick.value);
        const hidden = pick.parentElement.querySelector('input[type=hidden]');
        if (hidden) hidden.value = txt;
        const out = pick.parentElement.querySelector('.month-out');
        if (out) out.textContent = '输出：' + (txt || '—');
      }});
    }});
    const CONTACT_EMAIL = 'jiangpeng527@gmail.com';
    function openContact() {{ document.getElementById('contactMask').classList.add('open'); }}
    function closeContact() {{ document.getElementById('contactMask').classList.remove('open'); }}
    async function sendContact() {{
      const type = document.getElementById('ctType').value;
      const contact = document.getElementById('ctContact').value.trim();
      const content = document.getElementById('ctBody').value.trim();
      if (!content) {{ alert('请先填写具体内容'); return; }}
      const btns = document.querySelectorAll('.modal-actions button');
      btns.forEach(b => b.disabled = true);
      try {{
        const resp = await fetch('/api/feedback', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ type: type, contact: contact, content: content }})
        }});
        const result = await resp.json();
        if (resp.ok && result.ok) {{
          alert('发送成功，感谢你的反馈！');
          document.getElementById('ctBody').value = '';
          document.getElementById('ctContact').value = '';
          closeContact();
        }} else {{
          alert('发送失败：' + (result.error || '请稍后重试') + '\\n你也可邮件联系 ' + CONTACT_EMAIL);
        }}
      }} catch (err) {{
        alert('发送失败，请检查网络或稍后重试。\\n你也可邮件联系 ' + CONTACT_EMAIL);
      }} finally {{
        btns.forEach(b => b.disabled = false);
      }}
    }}
    document.addEventListener('keydown', e => {{ if (e.key === 'Escape') closeContact(); }});
  </script></body>
</html>"""
    return body.encode("utf-8")


def form_to_data(raw: bytes) -> dict:
    params = parse_qs(raw.decode("utf-8"), keep_blank_values=True)
    data = load_data(SAMPLE_PATH)
    scalar_keys = [key for key in data.keys() if key != "subjects"]
    for key in scalar_keys:
        if key in params:
            data[key] = params[key][0].strip()

    names_en = params.get("subject_name_en", [])
    names_ja = params.get("subject_name_ja", [])
    names_zh = params.get("subject_name_zh", [])
    row_count = max(len(names_en), len(names_ja), len(names_zh))
    subjects = []
    for i in range(row_count):
        name_en = names_en[i].strip() if i < len(names_en) else ""
        name_ja = names_ja[i].strip() if i < len(names_ja) else ""
        name_zh = names_zh[i].strip() if i < len(names_zh) else ""
        row = {"name": name_en or name_ja or name_zh, "name_en": name_en, "name_ja": name_ja, "name_zh": name_zh}
        for col in SCORE_COLUMNS:
            values = params.get(col, [])
            row[col] = values[i].strip() if i < len(values) else ""
        if row["name"] or row["name_ja"] or row["name_zh"] or any(row[col] for col in SCORE_COLUMNS):
            subjects.append(row)
    data["subjects"] = subjects
    gender = data.get("gender_cn", "").strip()
    if gender == "男":
        data.update({"gender_en": "male", "gender_en_title": "Male", "gender_jp": "男", "pronoun_en": "He", "possessive_en": "his"})
    else:
        data.update({"gender_en": "female", "gender_en_title": "Female", "gender_jp": "女", "pronoun_en": "She", "possessive_en": "her"})
    return data


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path.startswith("/output/"):
            path = ROOT / unquote(self.path).lstrip("/")
            if path.exists() and path.is_file():
                self.send_response(200)
                self.send_header("Content-Type", "application/pdf")
                self.send_header("Content-Disposition", f"inline; filename*=UTF-8''{quote(path.name)}")
                self.send_header("Content-Length", str(path.stat().st_size))
                self.end_headers()
                self.wfile.write(path.read_bytes())
                return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(render_form(load_data(SAMPLE_PATH)))

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        if self.path == "/api/feedback":
            self.handle_feedback(raw)
            return
        try:
            data = form_to_data(raw)
            mode_label = {"en": "英语版", "ja": "日语版", "zh": "中文版", "zh_en": "中英双语版", "zh_ja": "中日双语版"}.get(data.get("language_mode"), "英语版")
            action = parse_qs(raw.decode("utf-8"), keep_blank_values=True).get("action", ["generate"])[0]
            if action == "preview":
                filename = f"preview_{slug(data.get('name_cn') or data.get('name_en') or 'student')}_{mode_label}.pdf"
            else:
                filename = f"{slug(data.get('name_cn') or data.get('name_en') or '学生')}_高中证明资料_{mode_label}.pdf"
            output = OUTPUT_DIR / filename
            generate_pdf(data, output)
            link = f"/output/pdf/{quote(filename)}"
            if action == "preview":
                message = f'已生成预览：<a href="{link}" target="_blank">{html.escape(filename)}</a>'
                response = render_form(data, message=message, preview_url=link)
            else:
                message = f'已生成：<a href="{link}" target="_blank">{html.escape(filename)}</a>'
                response = render_form(data, message=message, preview_url=link)
        except Exception:
            response = render_form(load_data(SAMPLE_PATH), error=traceback.format_exc())
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(response)

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def handle_feedback(self, raw: bytes) -> None:
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
            content = str(payload.get("content", "")).strip()
            if not content:
                self._send_json(400, {"ok": False, "error": "内容不能为空"})
                return
            ftype = str(payload.get("type", "其他"))
            if ftype not in FEEDBACK_TYPES:
                ftype = "其他"
            send_feedback_email(ftype, str(payload.get("contact", "")), content)
            self._send_json(200, {"ok": True})
        except RuntimeError as exc:
            self._send_json(500, {"ok": False, "error": str(exc)})
        except Exception:
            traceback.print_exc()
            self._send_json(500, {"ok": False, "error": "邮件发送失败，请稍后重试"})


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 8765), Handler)
    print("Open http://127.0.0.1:8765")
    server.serve_forever()


if __name__ == "__main__":
    main()
