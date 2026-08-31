"""NETSEA 起点 × Keepa 検証の利益スキャン（T-20260831-006）。

⛔ このパッケージが扱う NETSEA データの用途は
   **「NETSEA 内で完結する仕入れ実務」（procurement）のみ**です。
   サプライヤーの発見・外部での連絡・外部での売買契約は会員規約違反で、
   違約金200万円＋売買代金50%＋事業者名の公表の対象になります。
   詳細は adapters/netsea.py の冒頭と T-20260831-005 の法務判定書を読んでください。
"""

from . import paths as _paths  # noqa: E402

# `calc.fees` / `adapters.netsea` を参照するので、パッケージを import した時点で通しておく。
_paths.ensure()
