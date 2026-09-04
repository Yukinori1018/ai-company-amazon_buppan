# -*- coding: utf-8 -*-
"""resolver パッケージ。import した時点で自己登録される。

TEMPLATE_source.py は雛形なので読み込まない。
"""
from .base import Resolver, register, get, available, clear  # noqa: F401
from . import seed_contacts  # noqa: F401  （import 副作用で register される）
from . import exa_lookup     # noqa: F401

__all__ = ["Resolver", "register", "get", "available", "clear"]
