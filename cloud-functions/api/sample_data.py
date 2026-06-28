"""示例/默认数据（内嵌为 Python 模块）。

EdgeOne Pages 云函数仅保证 `.py` 辅助模块会随入口一起打包，
非 .py 数据文件（如 sample_data.json）在线上可能缺失。
因此把默认数据内嵌到本模块，保证 `random_sample()` / `json_to_data()`
在任何环境下都能取到默认结构，避免线上 500 导致预置数据无法预览。

注意：内容与 sample_data.json 保持一致，二者择一即可，本模块为权威来源。
"""
from __future__ import annotations

import copy
import json

_SAMPLE_JSON = r"""
{
  "language_mode": "en",
  "school_cn": "明学中学",
  "school_en": "The Second High School Attached to Beijing Normal University",
  "school_short_en": "XX",
  "school_short_jp": "XXXXXX中学",
  "address_cn": "中国北京市西城区新街口外大街12号",
  "address_en": "No. 12, Xinjiekouwai Street, Xicheng Dist. Beijing, P. R. China",
  "post_code": "100088",
  "name_cn": "夏圆涵",
  "name_en": "Xia Yuanhan",
  "name_jp": "Xia Yuanhan",
  "gender_cn": "女",
  "gender_en": "female",
  "gender_en_title": "Female",
  "gender_jp": "女",
  "pronoun_en": "She",
  "possessive_en": "her",
  "birth_date": "2005-11-18",
  "study_start_cn": "2021 年 9 月",
  "study_end_cn": "2024 年 6 月",
  "study_start_en": "September 2021",
  "study_end_en": "June 2024",
  "study_start_jp": "2021年9月",
  "study_end_jp": "2024年6月",
  "enroll_month_en": "September 2021",
  "graduate_month_en": "June 2024",
  "issue_date": "2026-07-24",
  "notes_en": "The full score is 150 for Chinese, Mathematics, and English, and 100 for the other subjects.",
  "notes_jp": "この表の点数は国語、英語、数学は150点を満点とし、他の科目の点数は100点を満点とする。",
  "notes_zh": "本表中语文、数学、英语满分为150分，其他科目满分为100分。",
  "subjects": [
    {"name": "Chinese", "g1_t1": "150", "g1_t2": "150", "g2_t1": "150", "g2_t2": "150", "g3_t1": "150", "g3_t2": "150", "name_en": "Chinese", "name_ja": "国語（中国語）", "name_zh": "语文"},
    {"name": "Mathematics", "g1_t1": "150", "g1_t2": "150", "g2_t1": "150", "g2_t2": "150", "g3_t1": "150", "g3_t2": "150", "name_en": "Mathematics", "name_ja": "数学", "name_zh": "数学"},
    {"name": "English", "g1_t1": "150", "g1_t2": "150", "g2_t1": "150", "g2_t2": "150", "g3_t1": "150", "g3_t2": "150", "name_en": "English", "name_ja": "英語", "name_zh": "英语"},
    {"name": "Politics", "g1_t1": "100", "g1_t2": "100", "g2_t1": "100", "g2_t2": "100", "g3_t1": "100", "g3_t2": "100", "name_en": "Politics", "name_ja": "政治", "name_zh": "政治"},
    {"name": "History", "g1_t1": "100", "g1_t2": "100", "g2_t1": "100", "g2_t2": "100", "g3_t1": "100", "g3_t2": "100", "name_en": "History", "name_ja": "歴史", "name_zh": "历史"},
    {"name": "Geography", "g1_t1": "100", "g1_t2": "100", "g2_t1": "100", "g2_t2": "100", "g3_t1": "100", "g3_t2": "100", "name_en": "Geography", "name_ja": "地理", "name_zh": "地理"},
    {"name": "Physics", "g1_t1": "100", "g1_t2": "100", "g2_t1": "100", "g2_t2": "100", "g3_t1": "/", "g3_t2": "/", "name_en": "Physics", "name_ja": "物理", "name_zh": "物理"},
    {"name": "Chemistry", "g1_t1": "100", "g1_t2": "100", "g2_t1": "100", "g2_t2": "100", "g3_t1": "/", "g3_t2": "/", "name_en": "Chemistry", "name_ja": "化学", "name_zh": "化学"},
    {"name": "Biology", "g1_t1": "100", "g1_t2": "100", "g2_t1": "100", "g2_t2": "100", "g3_t1": "/", "g3_t2": "/", "name_en": "Biology", "name_ja": "生物", "name_zh": "生物"},
    {"name": "Physical Education", "g1_t1": "EXCELLENT", "g1_t2": "EXCELLENT", "g2_t1": "EXCELLENT", "g2_t2": "EXCELLENT", "g3_t1": "EXCELLENT", "g3_t2": "EXCELLENT", "name_en": "Physical Education", "name_ja": "体育", "name_zh": "体育"},
    {"name": "Biological lab", "g1_t1": "PASS", "g1_t2": "PASS", "g2_t1": "PASS", "g2_t2": "PASS", "g3_t1": "PASS", "g3_t2": "PASS", "name_en": "Biological lab", "name_ja": "生物実験", "name_zh": "生物实验"},
    {"name": "Chemical lab", "g1_t1": "PASS", "g1_t2": "PASS", "g2_t1": "PASS", "g2_t2": "PASS", "g3_t1": "PASS", "g3_t2": "PASS", "name_en": "Chemical lab", "name_ja": "化学実験", "name_zh": "化学实验"},
    {"name": "Physical lab", "g1_t1": "PASS", "g1_t2": "PASS", "g2_t1": "PASS", "g2_t2": "PASS", "g3_t1": "PASS", "g3_t2": "PASS", "name_en": "Physical lab", "name_ja": "物理実験", "name_zh": "物理实验"},
    {"name": "Technology", "g1_t1": "PASS", "g1_t2": "PASS", "g2_t1": "PASS", "g2_t2": "PASS", "g3_t1": "PASS", "g3_t2": "PASS", "name_en": "Technology", "name_ja": "技術", "name_zh": "信息科技"}
  ]
}
"""

SAMPLE_DATA: dict = json.loads(_SAMPLE_JSON)


def default_data() -> dict:
    """返回默认数据的深拷贝，调用方可安全修改。"""
    return copy.deepcopy(SAMPLE_DATA)
