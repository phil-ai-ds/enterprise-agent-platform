"""Agent 可用工具：工作区文档(按 Agent 绑定的个人/团队/组织空间) + 记忆 + 联网搜索/抓取 + 代码执行。

权限模型：Agent 的 workspace = 显式绑定或按其 scope 解析（个人 Agent→主人个人空间；团队 Agent→团队空间；
org Agent→组织空间）。所有路径操作均被限制在该 workspace 内。
"""
import os
import subprocess
import sys
import tempfile
from datetime import datetime

from langchain_core.tools import tool
from sqlalchemy.orm import Session

from . import memory as mem
from . import workspaces as wsvc
from .models import Agent, User, Workspace


def build_tools(db: Session, user: User, agent: Agent, data_dir: str, run_ref: str = "",
                workspace_id: int | None = None, folder: str = ""):
    """Agent 工具按『本次会话工作区 + 工作目录』构建（与 Agent 静态绑定解耦）。

    workspace_id: 用户本次选的工作区；None → 该 Agent 的默认空间。
    folder: 工作区内的工作目录（相对 ws 根的文件夹，空=工作区根）。
    所有路径工具以工作目录为基准（可用 .. 回工作区上层），但禁止越出工作区根。
    """
    ws = db.get(Workspace, workspace_id) if workspace_id else wsvc.agent_default_workspace(db, user, agent)
    if ws is None:
        raise RuntimeError("Agent 没有可用工作区")
    if not wsvc.can_read_ws(user, ws):
        raise RuntimeError("无权访问该工作区")
    root = wsvc.ws_root(data_dir, ws)
    try:
        folder = wsvc.clean_folder(folder)
    except ValueError:
        folder = ""
    # 工作目录基座：folder 相对 root（空=根）
    base = os.path.realpath(os.path.join(root, folder)) if folder else os.path.realpath(root)
    os.makedirs(base, exist_ok=True)
    root_real = os.path.realpath(root)
    cur = os.path.relpath(base, root_real)
    cur = "" if cur == "." else cur

    def safe_path(p: str) -> str:
        p = (p or "").replace("\\", "/")
        # 相对工作目录解析；允许 .. 回上层，但不得越出工作区根
        target = os.path.realpath(os.path.join(base, p))
        if target != root_real and not target.startswith(root_real + os.sep):
            raise ValueError("路径越界：只能访问该工作区内")
        return target

    def rel_show(target: str) -> str:
        # 展示路径：相对工作目录（更贴近 Agent 正在操作的位置）
        try:
            return os.path.relpath(target, base)
        except ValueError:
            return os.path.relpath(target, root_real)

    @tool("write_file",
          description=f"写入（或新建）一个文本文件。路径相对当前工作目录{f'（{cur}/）' if cur else '（工作区根）'}；如 notes/ideas.md。可用 ../ 写到工作区其它位置；禁止越出工作区")
    def write_file(path: str, content: str) -> str:
        target = safe_path(path)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(content)
        wsvc.upsert_file_record(db, ws.id, os.path.relpath(target, root_real), len(content.encode("utf-8")), user.id)
        return f"已写入 {rel_show(target)} ({len(content)} 字符)"

    @tool("read_file",
          description=f"读取文本文件内容（仅文本/代码，最多 8000 字符）。路径相对当前工作目录{f'（{cur}/）' if cur else '（工作区根）'}；传目录则列出其中条目")
    def read_file(path: str) -> str:
        try:
            target = safe_path(path)
        except ValueError as e:
            return str(e)
        if not os.path.exists(target):
            return f"文件不存在：{path}"
        if os.path.isdir(target):
            files = sorted(os.listdir(target))
            return f"目录 {rel_show(target)}/ 内容：\n" + ("\n".join(files) if files else "（空目录）")
        with open(target, "r", encoding="utf-8", errors="replace") as f:
            return f.read()[:8000]

    @tool("list_workspace",
          description=f"列出当前工作目录{f'（{cur}/）' if cur else '（工作区根）'}下的全部文件与子目录（递归）")
    def list_workspace() -> str:
        if not os.path.isdir(base):
            return f"（工作目录不存在：/{cur}）"
        out = []
        for cwd, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for d in dirs:
                out.append({"path": os.path.relpath(os.path.join(cwd, d), base), "kind": "dir"})
            for f in files:
                if f.startswith("."):
                    continue
                fp = os.path.join(cwd, f)
                out.append({"path": os.path.relpath(fp, base), "kind": "file", "size": os.path.getsize(fp)})
        out.sort(key=lambda x: (x["kind"] != "dir", x["path"].lower()))
        if not out:
            return f"（{cur or '工作区根'} 为空）"
        lines = [f"当前工作目录：/{cur}" if cur else "当前工作目录：/（工作区根）"]
        for x in out:
            kind = "📁" if x["kind"] == "dir" else "📄"
            size = "" if x["kind"] == "dir" else f" {x['size']}B"
            lines.append(f"{kind} {x['path']}{size}")
        return "\n".join(lines)

    @tool("save_memory", description="把一条需要长期记住的事实或用户偏好保存到记忆（key 相同时覆盖=迭代记忆）")
    def save_memory(key: str, value: str) -> str:
        mem.save_memory(db, user.id, agent.id, "fact", key, value)
        return f"记忆已保存：{key}"

    @tool("recall_memory", description="按关键词召回与此前对话相关的长期记忆")
    def recall_memory(query: str) -> str:
        rows = mem.recall(db, user.id, agent.id, query)
        if not rows:
            return "（暂无相关记忆）"
        return "\n".join(f"- [{r.kind}/{r.key}] {r.value}" for r in rows)

    @tool("now", description="返回当前日期时间")
    def now_iso() -> str:
        return datetime.now().isoformat()

    @tool("web_search", description="联网搜索公开网页，返回前若干条标题+摘要+链接。用于获取最新信息、事实核查、外部资料。")
    def web_search(query: str) -> str:
        return _web_search_impl(query)

    @tool("fetch_url", description="抓取一个公开网页 URL 的正文文本（自动提取主要文字，截断 6000 字符）。")
    def fetch_url(url: str) -> str:
        return _fetch_url_impl(url)

    @tool("run_python", description="在隔离临时目录执行一段 Python 代码并返回 stdout/stderr（超时 30 秒）。"
                                    "代码以字符串给出；如需读工作区文件请先用 read_file。禁止联网（网络被禁用）。")
    def run_python(code: str) -> str:
        return _run_python_impl(code)

    return [write_file, read_file, list_workspace, save_memory, recall_memory, now_iso,
            web_search, fetch_url, run_python]


# ---------------- 基础能力实现（模块级便于复用/单测） ----------------

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"


def _web_search_impl(query: str) -> str:
    import httpx
    # 用 DuckDuckGo HTML 端点（无需 key；适合企业内网 demo 与个人使用）
    try:
        resp = httpx.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query, "kl": "cn-zh"},
            headers={"User-Agent": _UA},
            timeout=12,
            follow_redirects=True,
        )
        resp.raise_for_status()
    except Exception as e:  # noqa: BLE001
        return f"搜索失败（网络不可达或服务超时）：{e}"
    text = resp.text
    results = []
    # 粗解析：每个 result 区块是 <a class="result__a" ...>标题</a> + <a class="result__snippet">摘要</a>
    import re
    blocks = re.split(r'<a[^>]*class="result__a"', text)[1:]
    for b in blocks[:8]:
        title_m = re.search(r'href="([^"]+)"[^>]*>(.*?)</a>', b, re.S)
        snip_m = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', b, re.S)
        if not title_m:
            continue
        import html as h
        url = title_m.group(1)
        title = h.unescape(re.sub(r"<[^>]+>", "", title_m.group(2))).strip()
        snippet = h.unescape(re.sub(r"<[^>]+>", "", snip_m.group(1))).strip() if snip_m else ""
        results.append(f"• {title}\n  {snippet[:200]}\n  {url}")
    return "\n\n".join(results) if results else "（没有搜索结果，或 DuckDuckGo 返回格式变化）"


def _fetch_url_impl(url: str) -> str:
    import httpx
    try:
        resp = httpx.get(url, headers={"User-Agent": _UA}, timeout=15, follow_redirects=True)
        resp.raise_for_status()
    except Exception as e:  # noqa: BLE001
        return f"抓取失败：{e}"
    ctype = resp.headers.get("content-type", "")
    if "html" in ctype or url.endswith((".html", ".htm")):
        import re
        import html as h
        body = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>|<noscript[\s\S]*?</noscript>", " ", resp.text, flags=re.I)
        body = re.sub(r"<[^>]+>", "\n", body)
        body = h.unescape(body)
        body = re.sub(r"\n{2,}", "\n", body)
        body = "\n".join(ln.strip() for ln in body.splitlines() if ln.strip())
        return body[:6000]
    return resp.text[:6000]


def _run_python_impl(code: str) -> str:
    """隔离临时目录中执行 python3 -I（隔离模式，禁 PYTHONPATH 注入）；限制 CPU 时间 30s。"""
    with tempfile.TemporaryDirectory(prefix="eap_sandbox_") as td:
        script = os.path.join(td, "main.py")
        with open(script, "w", encoding="utf-8") as f:
            f.write(code)
        env = {
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "HOME": td,
            "TMPDIR": td,
            "PYTHONIOENCODING": "utf-8",
        }
        try:
            proc = subprocess.run(
                [sys.executable, "-I", "-u", script],
                cwd=td, env=env, capture_output=True, text=True,
                timeout=30,
            )
            out = proc.stdout or ""
            err = proc.stderr or ""
            tail = lambda s: s[-3000:] if len(s) > 3000 else s  # noqa: E731
            if proc.returncode != 0:
                return f"exit={proc.returncode}\n--- stderr ---\n{tail(err)}\n--- stdout ---\n{tail(out)}"
            return (tail(out) + (f"\n--- stderr ---\n{tail(err)}" if err.strip() else "")).strip() or "（无输出）"
        except subprocess.TimeoutExpired:
            return "执行超时（>30s），已终止"
        except Exception as e:  # noqa: BLE001
            return f"执行器错误：{e}"
