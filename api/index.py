"""Vercel Serverless 入口：把 FastAPI 应用包装为单 Python Function。

Vercel 函数环境只有 /tmp 可写且随冷启动重置 —— 因此线上为「演示模式」：
- 数据落在 /tmp（SQLite + 工作区文件），每次冷启动自动 seed 重建演示数据；
- 登录用户 / Agent 记忆 / 工作区文件为临时性，不适合正式使用；
- 正式持久部署请使用带 Volume 的平台（见 README / Dockerfile）。
"""
import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
_root = os.path.dirname(_here)
if _root not in sys.path:
    sys.path.insert(0, _root)

os.environ.setdefault("EAP_DATA_DIR", "/tmp/eap-data")
os.environ.setdefault("EAP_DATABASE_URL", "sqlite:////tmp/eap.db")
os.environ.setdefault("EAP_FRONTEND_DIR", os.path.join(_root, "frontend"))

# 幂等建表 + 演示数据（本地已有库时自动跳过）
from backend.app.seed import seed as _seed  # noqa: E402

_seed()

from backend.app.main import app  # noqa: E402,F401  (Vercel Python 自动发现 ASGI app)
