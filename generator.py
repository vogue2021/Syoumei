"""命令行入口（兼容旧用法 `python3 generator.py sample_data.json`）。

PDF 生成核心已迁移到 cloud-functions/api/generator.py（单一事实来源，
云函数打包仅包含 cloud-functions/ 内文件）。本文件作为薄壳重新导出，
保证本地命令行生成仍可用。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "cloud-functions" / "api"))

from generator import *  # noqa: F401,F403,E402
from generator import generate_pdf, generate_pdf_bytes, load_data, main  # noqa: F401,E402


if __name__ == "__main__":
    main()
