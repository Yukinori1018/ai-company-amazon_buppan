"""`calc/` `adapters/`（T-20260521-005 の成果物）を import 可能にする。

コピーせず参照するのは意図的です。料率表が2箇所に増えた瞬間、どちらが正か分からなくなります
（T-20260817-004 で実際に起きた事故）。`calc/fees.py` が料率の唯一の正であり続けます。
"""

import sys
from pathlib import Path

# .../workspace/output/deliverables/T-20260831-006/pipeline/paths.py → リポジトリルート
REPO = Path(__file__).resolve().parents[5]
LEGACY_CODE = REPO / "workspace" / "output" / "deliverables" / "T-20260521-005" / "code"


def ensure() -> None:
    """sys.path に一度だけ足す。何度呼んでも安全。"""
    p = str(LEGACY_CODE)
    if p not in sys.path:
        sys.path.insert(0, p)
