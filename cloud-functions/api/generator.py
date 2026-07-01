from __future__ import annotations

import argparse
import io
import json
from datetime import date
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "output" / "pdf"
FONT_DIR = ROOT / "fonts"

PAGE_W, PAGE_H = A4
RED = colors.HexColor("#ff0000")
BLACK = colors.black

# 字体名称为模块级全局，register_fonts() 会按运行环境重新赋值；
# 各 draw_* 函数在调用时读取这些全局，因此重新赋值后即生效。
FONT_CJK = "STSong-Light"
FONT_CJK_BOLD = "STSong-Light"
FONT_JP = "HeiseiMin-W3"
FONT_JP_BOLD = "HeiseiKakuGo-W5"
FONT_SERIF = "Times-Roman"
FONT_SERIF_BOLD = "Times-Bold"

SCORE_COLUMNS = ["g1_t1", "g1_t2", "g2_t1", "g2_t2", "g3_t1", "g3_t2"]

_FONTS_READY = False


def _try_ttf(name: str, path: str, subfont_index: int = 0) -> bool:
    """尝试注册 TrueType 字体，成功返回 True。"""
    if name in pdfmetrics.getRegisteredFontNames():
        return True
    if not Path(path).exists():
        return False
    try:
        pdfmetrics.registerFont(TTFont(name, path, subfontIndex=subfont_index))
        return True
    except Exception:
        return False


def _try_cid(name: str) -> bool:
    if name in pdfmetrics.getRegisteredFontNames():
        return True
    try:
        pdfmetrics.registerFont(UnicodeCIDFont(name))
        return True
    except Exception:
        return False


def register_fonts() -> None:
    """三级字体回退：

    1) macOS 系统字体（本地开发，保持原有渲染效果不变）；
    2) 项目内置 TTF（fonts/，可选）；
    3) ReportLab 内置 CID 字体（无需字体文件，Linux/Serverless 也能渲染中日文）。
    拉丁文统一回退到标准 14 内置字体 Times-Roman / Times-Bold。
    """
    global FONT_CJK, FONT_CJK_BOLD, FONT_JP, FONT_JP_BOLD, FONT_SERIF, FONT_SERIF_BOLD
    global _FONTS_READY
    if _FONTS_READY:
        return

    # ---- Tier 1: macOS 系统字体 ----
    if _try_ttf("SongtiRegular", "/System/Library/Fonts/Supplemental/Songti.ttc", 6) and \
            _try_ttf("STHeiti", "/System/Library/Fonts/STHeiti Medium.ttc", 0):
        FONT_CJK = "SongtiRegular"
        FONT_CJK_BOLD = "STHeiti"
        FONT_JP = "SongtiRegular"
        FONT_JP_BOLD = "STHeiti"
        FONT_SERIF = "TimesNewRoman" if _try_ttf(
            "TimesNewRoman", "/System/Library/Fonts/Supplemental/Times New Roman.ttf"
        ) else "Times-Roman"
        FONT_SERIF_BOLD = "TimesNewRomanBold" if _try_ttf(
            "TimesNewRomanBold", "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf"
        ) else "Times-Bold"
        _FONTS_READY = True
        return

    # ---- Tier 2: 项目内置 TTF（可选） ----
    bundled = {
        "BundledCJK": FONT_DIR / "cjk-serif.ttf",
        "BundledCJKBold": FONT_DIR / "cjk-bold.ttf",
        "BundledJP": FONT_DIR / "jp-serif.ttf",
        "BundledJPBold": FONT_DIR / "jp-bold.ttf",
    }
    if bundled["BundledCJK"].exists():
        ok_cjk = _try_ttf("BundledCJK", str(bundled["BundledCJK"]))
        cjk_bold = "BundledCJKBold" if _try_ttf("BundledCJKBold", str(bundled["BundledCJKBold"])) else "BundledCJK"
        jp = "BundledJP" if _try_ttf("BundledJP", str(bundled["BundledJP"])) else "BundledCJK"
        jp_bold = "BundledJPBold" if _try_ttf("BundledJPBold", str(bundled["BundledJPBold"])) else cjk_bold
        if ok_cjk:
            FONT_CJK = "BundledCJK"
            FONT_CJK_BOLD = cjk_bold
            FONT_JP = jp
            FONT_JP_BOLD = jp_bold
            FONT_SERIF = "Times-Roman"
            FONT_SERIF_BOLD = "Times-Bold"
            _FONTS_READY = True
            return

    # ---- Tier 3: ReportLab 内置 CID 字体（无文件依赖） ----
    if _try_cid("STSong-Light") and _try_cid("HeiseiMin-W3") and _try_cid("HeiseiKakuGo-W5"):
        FONT_CJK = "STSong-Light"
        FONT_CJK_BOLD = "STSong-Light"   # CID 无独立粗体，复用常规字重
        FONT_JP = "HeiseiMin-W3"
        FONT_JP_BOLD = "HeiseiKakuGo-W5"
    else:
        # 最后兜底，避免抛错（极端环境）
        FONT_CJK = FONT_CJK_BOLD = FONT_JP = FONT_JP_BOLD = "Helvetica"
    FONT_SERIF = "Times-Roman"
    FONT_SERIF_BOLD = "Times-Bold"
    _FONTS_READY = True


def load_data(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def split_date(value: str) -> tuple[int, int, int]:
    value = value.strip().replace("/", "-")
    return tuple(map(int, value.split("-")))  # type: ignore[return-value]


def en_date(value: str) -> str:
    y, m, d = split_date(value)
    return date(y, m, d).strftime("%B %-d, %Y")


def slash_date(value: str) -> str:
    y, m, d = split_date(value)
    return f"{y:04d}/{m:02d}/{d:02d}"


def cn_date(value: str) -> str:
    y, m, d = split_date(value)
    return f"{y} 年 {m} 月 {d} 日"


def jp_date(value: str) -> str:
    y, m, d = split_date(value)
    return f"{y}年{m}月{d}日"


def text_width(text: str, font: str, size: float) -> float:
    return pdfmetrics.stringWidth(str(text), font, size)


def wrap_words(text: str, font: str, size: float, max_width: float) -> list[str]:
    text = " ".join(str(text).split())
    lines: list[str] = []
    current = ""
    for word in text.split(" "):
        candidate = word if not current else f"{current} {word}"
        if text_width(candidate, font, size) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def wrap_chars(text: str, font: str, size: float, max_width: float) -> list[str]:
    lines: list[str] = []
    current = ""
    for ch in str(text).strip():
        candidate = current + ch
        if text_width(candidate, font, size) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = ch
    if current:
        lines.append(current)
    return lines


def draw_wrapped(
    c: canvas.Canvas,
    text: str,
    x: float,
    y: float,
    max_width: float,
    font: str,
    size: float,
    leading: float,
    by_char: bool = False,
) -> float:
    lines = wrap_chars(text, font, size, max_width) if by_char else wrap_words(text, font, size, max_width)
    c.setFillColor(BLACK)
    c.setFont(font, size)
    for line in lines:
        c.drawString(x, y, line)
        y -= leading
    return y


def draw_center(c: canvas.Canvas, text: str, y: float, font: str, size: float, color=BLACK) -> None:
    c.setFillColor(color)
    c.setFont(font, size)
    c.drawCentredString(PAGE_W / 2, y, text)


def draw_right(c: canvas.Canvas, text: str, x: float, y: float, font: str, size: float, color=BLACK) -> None:
    c.setFillColor(color)
    c.setFont(font, size)
    c.drawRightString(x, y, text)


def draw_template_frame(c: canvas.Canvas, data: dict[str, Any]) -> None:
    school_cn = data.get("school_cn", "")
    school_en = data.get("school_en", "")
    address_cn = data.get("address_cn", "")
    address_en = data.get("address_en", "")
    post_code = data.get("post_code", "")

    draw_center(c, school_cn, 796, FONT_CJK_BOLD, 20, RED)
    if school_en:
        size = 16
        lines = wrap_words(school_en, FONT_SERIF_BOLD, size, 470)
        while (len(lines) > 2 or any(text_width(line, FONT_SERIF_BOLD, size) > 470 for line in lines)) and size > 11:
            size -= 0.5
            lines = wrap_words(school_en, FONT_SERIF_BOLD, size, 470)
        y = 762
        leading = size + 4
        for line in lines:
            draw_center(c, line, y, FONT_SERIF_BOLD, size, RED)
            y -= leading
        line_y = y - 4
    else:
        line_y = 746

    c.setStrokeColor(RED)
    c.setLineWidth(4)
    c.line(72, line_y, PAGE_W - 72, line_y)
    c.line(72, 55, PAGE_W - 72, 55)

    c.setFillColor(RED)
    c.setFont(FONT_CJK, 11)
    c.drawString(72, 35, f"地址:{address_cn}")
    if post_code:
        c.drawRightString(PAGE_W - 72, 35, f"邮编(Post Code):{post_code}")
    if address_en:
        c.setFont(FONT_SERIF, 10)
        c.drawString(72, 18, f"Add:{address_en}")
    c.setFillColor(BLACK)


def cell_text(c: canvas.Canvas, text: str, x: float, y: float, w: float, h: float, font: str, size: float) -> None:
    text = str(text)
    while size > 6.5 and text_width(text, font, size) > w - 8:
        size -= 0.5
    c.setFont(font, size)
    if text_width(text, font, size) > w - 8:
        lines = wrap_chars(text, font, size, w - 8)
    elif any(ord(ch) > 127 for ch in text):
        lines = wrap_chars(text, font, size, w - 8)
    else:
        lines = wrap_words(text, font, size, w - 8)
    lines = lines[:3]
    total_h = (len(lines) - 1) * (size + 2)
    start_y = y + h / 2 + total_h / 2 - size / 3
    for i, line in enumerate(lines):
        c.drawCentredString(x + w / 2, start_y - i * (size + 2), line)


def header_cell_text(c: canvas.Canvas, text: str, x: float, y: float, w: float, h: float, font: str, size: float) -> None:
    text = str(text)
    while size > 6.5 and text_width(text, font, size) > w - 8:
        size -= 0.5
    c.setFont(font, size)
    c.drawCentredString(x + w / 2, y + h / 2 - size / 3, text)


def draw_score_table(
    c: canvas.Canvas,
    subjects: list[dict[str, str]],
    x0: float,
    y_top: float,
    width: float,
    lang: str,
    bottom_limit: float = 125,
) -> float:
    rows = [s for s in subjects if s.get("name", "").strip()]
    if not rows:
        rows = [{"name": "", **{col: "" for col in SCORE_COLUMNS}}]
    subject_w = 112 if lang != "en" else 105
    col_w = (width - subject_w) / 6
    h1 = 18
    h2 = 21
    row_h = max(13.5, min(24, (y_top - bottom_limit - h1 - h2) / max(len(rows), 1)))
    table_h = h1 + h2 + row_h * len(rows)
    y_bottom = y_top - table_h

    c.setStrokeColor(BLACK)
    c.setLineWidth(0.8)
    full_height_xs = [
        x0,
        x0 + subject_w,
        x0 + subject_w + col_w * 2,
        x0 + subject_w + col_w * 4,
        x0 + width,
    ]
    term_only_xs = [
        x0 + subject_w + col_w,
        x0 + subject_w + col_w * 3,
        x0 + subject_w + col_w * 5,
    ]
    for x in full_height_xs:
        c.line(x, y_top, x, y_bottom)
    for x in term_only_xs:
        c.line(x, y_top - h1, x, y_bottom)

    ys = [y_top, y_top - h1, y_top - h1 - h2] + [y_top - h1 - h2 - row_h * i for i in range(1, len(rows) + 1)]
    for y in ys:
        if y == y_top - h1:
            c.line(x0 + subject_w, y, x0 + width, y)
        else:
            c.line(x0, y, x0 + width, y)
    c.setLineWidth(1.2)
    c.line(x0 + subject_w, y_top, x0 + subject_w, y_bottom)
    for i in (2, 4):
        c.line(x0 + subject_w + col_w * i, y_top, x0 + subject_w + col_w * i, y_bottom)
    c.line(x0, y_top, x0 + width, y_top)
    c.line(x0, y_bottom, x0 + width, y_bottom)

    if lang == "ja":
        grade_titles = ["第一学年", "第二学年", "第三学年"]
        term_titles = ["前期", "後期"] * 3
        left1, left2, font, size = "学年", "成績", FONT_JP, 12
    elif lang == "zh":
        grade_titles = ["高一", "高二", "高三"]
        term_titles = ["上学期", "下学期"] * 3
        left1, left2, font, size = "学年", "科目", FONT_CJK, 12
    elif lang == "zh_ja":
        grade_titles = ["第一学年", "第二学年", "第三学年"]
        term_titles = ["前期", "後期"] * 3
        left1, left2, font, size = "学年", "科目", FONT_CJK, 11
    elif lang == "zh_en":
        grade_titles = ["1st / 高一", "2nd / 高二", "3rd / 高三"]
        term_titles = ["1st", "2nd"] * 3
        left1, left2, font, size = "Grade", "Subject", FONT_CJK, 10
    else:
        grade_titles = ["1st Academic year", "2nd Academic year", "3rd Academic year"]
        term_titles = ["1st Term", "2nd Term"] * 3
        left1, left2, font, size = "Grade", "Subject", FONT_SERIF, 10

    header_cell_text(c, left1, x0, y_top - h1, subject_w, h1, font, size)
    header_cell_text(c, left2, x0, y_top - h1 - h2, subject_w, h2, font, size)
    for i, title in enumerate(grade_titles):
        header_cell_text(c, title, x0 + subject_w + col_w * i * 2, y_top - h1, col_w * 2, h1, font, size)
    for i, title in enumerate(term_titles):
        header_cell_text(c, title, x0 + subject_w + col_w * i, y_top - h1 - h2, col_w, h2, font, size)

    for r, subject in enumerate(rows):
        y = y_top - h1 - h2 - row_h * (r + 1)
        cell_text(c, subject.get("name", ""), x0, y, subject_w, row_h, font, min(10, row_h - 4) if lang != "ja" else min(10.5, row_h - 3))
        for i, col in enumerate(SCORE_COLUMNS):
            cell_text(c, subject.get(col, ""), x0 + subject_w + col_w * i, y, col_w, row_h, font, min(10, row_h - 4))
    return y_bottom


def apply_derived_fields(data: dict[str, Any]) -> dict[str, Any]:
    gender = str(data.get("gender_cn", "")).strip()
    if gender == "男":
        data["gender_en"] = "male"
        data["gender_en_title"] = "Male"
        data["gender_jp"] = "男"
        data["pronoun_en"] = "He"
        data["possessive_en"] = "his"
    else:
        data["gender_en"] = "female"
        data["gender_en_title"] = "Female"
        data["gender_jp"] = "女"
        data["pronoun_en"] = "She"
        data["possessive_en"] = "her"
    return data


def normalized_subjects(data: dict[str, Any]) -> list[dict[str, str]]:
    if "subjects" in data:
        return data["subjects"]
    legacy = data.get("scores", {})
    labels = {
        "chinese": "Chinese",
        "mathematics": "Mathematics",
        "english": "English",
        "politics": "Politics",
        "history": "History",
        "geography": "Geography",
        "physics": "Physics",
        "chemistry": "Chemistry",
        "biology": "Biology",
        "pe": "Physical Education",
        "art": "Art",
        "it": "Technology",
    }
    subjects = []
    for key, row in legacy.items():
        subjects.append({
            "name": labels.get(key, key),
            "g1_t1": row.get("g10_t1", ""),
            "g1_t2": row.get("g10_t2", ""),
            "g2_t1": row.get("g11_t1", ""),
            "g2_t2": row.get("g11_t2", ""),
            "g3_t1": row.get("g12_t1", ""),
            "g3_t2": row.get("g12_t2", ""),
        })
    return subjects


def subject_name_for(subject: dict[str, str], lang: str) -> str:
    name_en = subject.get("name_en") or subject.get("name") or ""
    name_ja = subject.get("name_ja") or subject.get("name_jp") or ""
    name_zh = subject.get("name_zh") or subject.get("name_cn") or ""
    if lang == "ja":
        return name_ja or name_zh or name_en
    if lang == "zh":
        return name_zh or name_en
    if lang == "zh_en":
        if name_zh and name_en and name_zh != name_en:
            return f"{name_zh} / {name_en}"
        return name_zh or name_en
    if lang == "zh_ja":
        if name_zh and name_ja and name_zh != name_ja:
            return f"{name_zh} / {name_ja}"
        return name_zh or name_ja or name_en
    return name_en or name_zh


def localized_subjects(data: dict[str, Any], lang: str) -> list[dict[str, str]]:
    subjects = []
    for subject in normalized_subjects(data):
        row = dict(subject)
        row["name"] = subject_name_for(subject, lang)
        subjects.append(row)
    return subjects


def draw_english_transcript(c: canvas.Canvas, data: dict[str, Any]) -> None:
    draw_template_frame(c, data)
    draw_center(c, "Official Transcript", 674, FONT_SERIF_BOLD, 19)
    pronoun = data.get("pronoun_en", "She")
    possessive = data.get("possessive_en", "her")
    intro = (
        f"This is to certify that {data['name_en']}, {data['gender_en_title']}, born on {slash_date(data['birth_date'])}. "
        f"{pronoun} has completed {possessive} high school courses in {data['school_short_en']} High School, "
        f"from {data['study_start_en']} to {data['study_end_en']}."
    )
    y = draw_wrapped(c, intro, 72, 622, 450, FONT_SERIF, 13.5, 20)
    c.setFont(FONT_SERIF, 13.5)
    c.drawString(72, y - 12, "The student's grades are as follows:")
    y_bottom = draw_score_table(c, localized_subjects(data, "en"), 72, y - 28, 450, "en", bottom_limit=150)
    note = data.get("notes_en", "The full score is 150 for Chinese, Mathematics, and English, and 100 for the other subjects.")
    y = draw_wrapped(c, f"Notes: {note}", 72, y_bottom - 16, 450, FONT_SERIF, 9.2, 12)
    y_sig = y - 14
    draw_right(c, data["school_short_en"] + " High School", 520, y_sig, FONT_SERIF, 12)
    draw_right(c, en_date(data["issue_date"]), 520, y_sig - 18, FONT_SERIF, 12)


def draw_english_graduation(c: canvas.Canvas, data: dict[str, Any]) -> None:
    draw_template_frame(c, data)
    draw_center(c, "Certificate of Graduation", 650, FONT_SERIF_BOLD, 20)
    text = (
        f"This is to certify that {data['name_en']}, {data['gender_en_title']}, born on {slash_date(data['birth_date'])}, "
        f"was enrolled in our school in {data['enroll_month_en']}, and graduated in {data['graduate_month_en']}."
    )
    draw_wrapped(c, text, 72, 560, 460, FONT_SERIF, 16, 30)
    draw_right(c, data["school_short_en"] + " High School", 520, 400, FONT_SERIF, 15)
    draw_right(c, en_date(data["issue_date"]), 520, 370, FONT_SERIF, 15)


def draw_japanese_graduation(c: canvas.Canvas, data: dict[str, Any]) -> None:
    draw_template_frame(c, data)
    draw_center(c, "卒業証明書", 575, FONT_JP_BOLD, 20)
    c.setFont(FONT_JP, 16)
    c.drawString(85, 500, f"学生：{data.get('name_jp') or data['name_en']}")
    c.drawString(85, 460, f"性別：{data.get('gender_jp', '女')}")
    c.drawString(85, 420, f"生年月日：{jp_date(data['birth_date'])}")
    text = (
        f"上記の者は、{data['study_start_jp']}から{data['study_end_jp']}まで本校にて三年間在籍し、"
        "成績も基準を満たし、卒業したことを証する。"
    )
    draw_wrapped(c, text, 85, 340, 430, FONT_JP, 16, 32, by_char=True)
    draw_right(c, data["school_short_jp"], 520, 160, FONT_JP, 15)
    draw_right(c, jp_date(data["issue_date"]), 520, 125, FONT_JP, 15)


def draw_japanese_transcript(c: canvas.Canvas, data: dict[str, Any]) -> None:
    draw_template_frame(c, data)
    draw_center(c, "高校成績証明", 605, FONT_JP_BOLD, 18)
    name = data.get("name_jp") or data["name_en"]
    intro = (
        f"{name}、{data.get('gender_jp', '女')}、{jp_date(data['birth_date'])}生まれ。"
        f"{name}さんが{data['study_start_jp']}から{data['study_end_jp']}までの当校での学習成績は以下の通り："
    )
    y = draw_wrapped(c, intro, 72, 562, 450, FONT_JP, 10.5, 15, by_char=True)
    y_bottom = draw_score_table(c, localized_subjects(data, "ja"), 72, y - 8, 450, "ja", bottom_limit=170)
    note = data.get("notes_jp", "この表の点数は国語、英語、数学は150点を満点とし、他の科目の点数は100点を満点とする。")
    y = draw_wrapped(c, f"（注：{note}）", 72, y_bottom - 10, 450, FONT_JP, 9.5, 13, by_char=True)
    y = draw_wrapped(c, "上記の通り相違ないことを証する。", 72, y - 6, 300, FONT_JP, 10, 14, by_char=True)
    y_sig = y - 12
    draw_right(c, data["school_short_jp"], 520, y_sig, FONT_JP, 11)
    draw_right(c, jp_date(data["issue_date"]), 520, y_sig - 18, FONT_JP, 11)


def draw_bilingual_transcript(c: canvas.Canvas, data: dict[str, Any]) -> None:
    draw_template_frame(c, data)
    draw_center(c, "学生成绩证明", 662, FONT_CJK_BOLD, 16)
    draw_center(c, "Certificate of Student Academic Achievements", 639, FONT_SERIF_BOLD, 17)
    cn = (
        f"{data['name_cn']}同学，{data['gender_cn']}，{cn_date(data['birth_date'])}出生，于"
        f"{data['study_start_cn']}至{data['study_end_cn']}在我校高中部学习。现摘录该生高中阶段各科成绩："
    )
    y = draw_wrapped(c, cn, 72, 600, 450, FONT_CJK, 10.5, 15, by_char=True)
    en = (
        f"Student {data['name_en']}, {data['gender_en']}, born on {en_date(data['birth_date'])}, "
        f"studied in the Senior High School Division of our school from {data['study_start_en']} "
        f"to {data['study_end_en']}. The student's grades are as follows:"
    )
    y = draw_wrapped(c, en, 72, y - 2, 450, FONT_SERIF, 10, 13)
    y_bottom = draw_score_table(c, localized_subjects(data, "zh_en"), 72, y - 12, 450, "zh_en", bottom_limit=150)
    y = draw_wrapped(c, f"注 / Notes: {data.get('notes_en', '')}", 72, y_bottom - 14, 450, FONT_CJK, 8.8, 12, by_char=True)
    y_sig = y - 12
    draw_right(c, data["school_cn"], 520, y_sig, FONT_CJK, 11)
    draw_right(c, data["school_en"], 520, y_sig - 16, FONT_SERIF, 9)
    draw_right(c, slash_date(data["issue_date"]), 520, y_sig - 30, FONT_SERIF, 10)


def draw_bilingual_graduation(c: canvas.Canvas, data: dict[str, Any]) -> None:
    draw_template_frame(c, data)
    draw_center(c, "高中毕业证明", 665, FONT_CJK_BOLD, 18)
    cn = (
        f"学生{data['name_cn']}，性别{data['gender_cn']}，{cn_date(data['birth_date'])}出生，于"
        f"{data['study_start_cn']}至{data['study_end_cn']}在本校高中部学习。修业期满，成绩合格，准予毕业。"
    )
    y = draw_wrapped(c, cn, 85, 600, 430, FONT_CJK, 14, 28, by_char=True)
    draw_right(c, data["school_cn"], 520, y - 55, FONT_CJK, 13)
    draw_right(c, slash_date(data["issue_date"]), 520, y - 82, FONT_SERIF, 13)
    draw_center(c, "Certificate of Graduation", 360, FONT_SERIF_BOLD, 18)
    en = (
        f"This is to certify that {data['name_en']}, {data['gender_en_title']}, born on {slash_date(data['birth_date'])}, "
        f"was enrolled in our school in {data['enroll_month_en']}, and graduated in {data['graduate_month_en']}."
    )
    draw_wrapped(c, en, 72, 305, 460, FONT_SERIF, 14, 25)
    draw_right(c, data["school_en"], 520, 185, FONT_SERIF, 13)
    draw_right(c, en_date(data["issue_date"]), 520, 158, FONT_SERIF, 13)


def draw_chinese_graduation(c: canvas.Canvas, data: dict[str, Any]) -> None:
    draw_template_frame(c, data)
    draw_center(c, "高中毕业证明", 650, FONT_CJK_BOLD, 22)
    cn = (
        f"学生{data['name_cn']}，性别{data['gender_cn']}，{cn_date(data['birth_date'])}出生，于"
        f"{data['study_start_cn']}至{data['study_end_cn']}在本校高中部学习。修业期满，成绩合格，准予毕业。"
    )
    draw_wrapped(c, cn, 85, 555, 430, FONT_CJK, 15, 30, by_char=True)
    draw_right(c, data["school_cn"], 520, 380, FONT_CJK, 14)
    draw_right(c, cn_date(data["issue_date"]), 520, 350, FONT_CJK, 14)


def draw_chinese_transcript(c: canvas.Canvas, data: dict[str, Any]) -> None:
    draw_template_frame(c, data)
    draw_center(c, "高中成绩证明", 674, FONT_CJK_BOLD, 18)
    intro = (
        f"{data['name_cn']}同学，{data['gender_cn']}，{cn_date(data['birth_date'])}出生，于"
        f"{data['study_start_cn']}至{data['study_end_cn']}在我校高中部学习。现摘录该生高中阶段各科成绩："
    )
    y = draw_wrapped(c, intro, 72, 630, 450, FONT_CJK, 12, 18, by_char=True)
    y_bottom = draw_score_table(c, localized_subjects(data, "zh"), 72, y - 10, 450, "zh", bottom_limit=150)
    note = data.get("notes_zh", "本表中语文、数学、英语满分为150分，其他科目满分为100分。")
    y = draw_wrapped(c, f"注：{note}", 72, y_bottom - 14, 450, FONT_CJK, 9, 13, by_char=True)
    y_sig = y - 14
    draw_right(c, data["school_cn"], 520, y_sig, FONT_CJK, 12)
    draw_right(c, cn_date(data["issue_date"]), 520, y_sig - 20, FONT_CJK, 12)


def draw_zh_ja_graduation(c: canvas.Canvas, data: dict[str, Any]) -> None:
    draw_template_frame(c, data)
    draw_center(c, "高中毕业证明", 665, FONT_CJK_BOLD, 18)
    cn = (
        f"学生{data['name_cn']}，性别{data['gender_cn']}，{cn_date(data['birth_date'])}出生，于"
        f"{data['study_start_cn']}至{data['study_end_cn']}在本校高中部学习。修业期满，成绩合格，准予毕业。"
    )
    y = draw_wrapped(c, cn, 85, 600, 430, FONT_CJK, 14, 28, by_char=True)
    draw_right(c, data["school_cn"], 520, y - 55, FONT_CJK, 13)
    draw_right(c, cn_date(data["issue_date"]), 520, y - 82, FONT_CJK, 13)

    draw_center(c, "卒業証明書", 360, FONT_JP_BOLD, 18)
    name = data.get("name_jp") or data["name_en"]
    jp = (
        f"上記の者（{name}、{data.get('gender_jp', '女')}、{jp_date(data['birth_date'])}生まれ）は、"
        f"{data['study_start_jp']}から{data['study_end_jp']}まで本校にて三年間在籍し、"
        "成績も基準を満たし、卒業したことを証する。"
    )
    draw_wrapped(c, jp, 72, 305, 460, FONT_JP, 13, 24, by_char=True)
    draw_right(c, data["school_short_jp"], 520, 175, FONT_JP, 13)
    draw_right(c, jp_date(data["issue_date"]), 520, 148, FONT_JP, 13)


def draw_zh_ja_transcript(c: canvas.Canvas, data: dict[str, Any]) -> None:
    draw_template_frame(c, data)
    draw_center(c, "学生成绩证明", 660, FONT_CJK_BOLD, 16)
    draw_center(c, "成績証明書", 636, FONT_JP_BOLD, 17)
    cn = (
        f"{data['name_cn']}同学，{data['gender_cn']}，{cn_date(data['birth_date'])}出生，于"
        f"{data['study_start_cn']}至{data['study_end_cn']}在我校高中部学习。现摘录该生高中阶段各科成绩："
    )
    y = draw_wrapped(c, cn, 72, 598, 450, FONT_CJK, 10.5, 15, by_char=True)
    name = data.get("name_jp") or data["name_en"]
    jp = (
        f"{name}、{data.get('gender_jp', '女')}、{jp_date(data['birth_date'])}生まれ。"
        f"{data['study_start_jp']}から{data['study_end_jp']}までの当校での学習成績は以下の通り："
    )
    y = draw_wrapped(c, jp, 72, y - 2, 450, FONT_JP, 10, 14, by_char=True)
    y_bottom = draw_score_table(c, localized_subjects(data, "zh_ja"), 72, y - 12, 450, "zh_ja", bottom_limit=160)
    note_zh = data.get("notes_zh", "本表中语文、数学、英语满分为150分，其他科目满分为100分。")
    y = draw_wrapped(c, f"注：{note_zh}", 72, y_bottom - 12, 450, FONT_CJK, 8.8, 12, by_char=True)
    note_jp = data.get("notes_jp", "")
    if note_jp:
        y = draw_wrapped(c, f"（注：{note_jp}）", 72, y - 1, 450, FONT_JP, 8.8, 12, by_char=True)
    y_sig = y - 12
    draw_right(c, data["school_cn"], 520, y_sig, FONT_CJK, 11)
    draw_right(c, data["school_short_jp"], 520, y_sig - 16, FONT_JP, 10)
    draw_right(c, jp_date(data["issue_date"]), 520, y_sig - 30, FONT_JP, 10)


def _render(c: canvas.Canvas, data: dict[str, Any]) -> None:
    """按语言模式在画布上绘制两页（毕业证明 + 成绩证明）。"""
    data = apply_derived_fields(data)
    mode = data.get("language_mode", "en")
    if mode == "ja":
        draw_japanese_graduation(c, data)
        c.showPage()
        draw_japanese_transcript(c, data)
    elif mode == "zh_en":
        draw_bilingual_graduation(c, data)
        c.showPage()
        draw_bilingual_transcript(c, data)
    elif mode == "zh":
        draw_chinese_graduation(c, data)
        c.showPage()
        draw_chinese_transcript(c, data)
    elif mode == "zh_ja":
        draw_zh_ja_graduation(c, data)
        c.showPage()
        draw_zh_ja_transcript(c, data)
    else:
        draw_english_transcript(c, data)
        c.showPage()
        draw_english_graduation(c, data)


def generate_pdf_bytes(data: dict[str, Any]) -> bytes:
    """在内存中生成 PDF 并返回字节流（Serverless 无持久磁盘时使用）。"""
    register_fonts()
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    _render(c, data)
    c.save()
    return buf.getvalue()


def generate_pdf(data: dict[str, Any], output_path: str | Path) -> Path:
    register_fonts()
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(output), pagesize=A4)
    _render(c, data)
    c.save()
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate high school certificate PDF.")
    parser.add_argument("input", nargs="?", default="sample_data.json", help="JSON data file")
    parser.add_argument("-o", "--output", help="Output PDF path")
    args = parser.parse_args()
    data = load_data(args.input)
    output = args.output or OUTPUT_DIR / f"{data['name_cn']}_高中证明资料.pdf"
    print(generate_pdf(data, output))


if __name__ == "__main__":
    main()
