"""飞书输出:建 docx 文档 + 把 Markdown 解析成飞书 block 树写入。

注意:飞书的"导入 markdown"接口(ccm_import_open)只认 user_access_token,
不支持自建应用的 tenant_access_token。所以这里改用:
  1. docx/v1/documents 建空文档(应用 token 可用)
  2. 解析 Markdown → 飞书 block 树 → blocks/{id}/descendant 批量写入

block_type:2=文本 3..11=heading1..9 12=无序列表 13=有序列表 19=高亮块(callout)
            22=分割线 31=表格 32=单元格

子 bullet 走真·嵌套(parent.children),表格走真·表格 block(31+32),
都用 descendant 接口一次性建好层级(单次请求后代块总数 ≤ 50)。
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

_API = "https://open.feishu.cn/open-apis"
_MAX_DESC = 50   # descendant 接口单次后代块总数上限


def _token(app_id: str, app_secret: str) -> str:
    req = urllib.request.Request(
        f"{_API}/auth/v3/tenant_access_token/internal/",
        data=json.dumps({"app_id": app_id, "app_secret": app_secret}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    r = json.loads(urllib.request.urlopen(req, timeout=20).read())
    if r.get("code") != 0:
        raise RuntimeError(f"飞书认证失败: {r.get('code')} {r.get('msg')}")
    return r["tenant_access_token"]


def _post(token: str, path: str, body: dict) -> dict:
    req = urllib.request.Request(
        _API + path, data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json"}, method="POST")
    try:
        return json.loads(urllib.request.urlopen(req, timeout=30).read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"飞书 API {path} 失败: HTTP {e.code} "
                           f"{e.read().decode()[:200]}") from e


# ── block 构造(返回不含 block_id / children 的纯 block dict)──────

def _elements(text: str) -> list[dict]:
    """行内文本 → text_run 列表,处理 **加粗**。"""
    out: list[dict] = []
    for part in re.split(r"(\*\*[^*]+\*\*)", text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            out.append({"text_run": {"content": part[2:-2],
                                     "text_element_style": {"bold": True}}})
        else:
            out.append({"text_run": {"content": part}})
    return out or [{"text_run": {"content": text}}]


def _heading(level: int, text: str) -> dict:
    return {"block_type": level + 2, f"heading{level}": {"elements": _elements(text)}}


def _bullet(text: str) -> dict:
    return {"block_type": 12, "bullet": {"elements": _elements(text)}}


def _ordered(text: str) -> dict:
    return {"block_type": 13, "ordered": {"elements": _elements(text)}}


def _callout() -> dict:
    return {"block_type": 19,
            "callout": {"background_color": 1, "border_color": 1,
                        "emoji_id": "speech_balloon"}}


def _text(text: str) -> dict:
    return {"block_type": 2, "text": {"elements": _elements(text)}}


def _divider() -> dict:
    return {"block_type": 22, "divider": {}}


# ── 节点树:{"block": <block dict>, "children": [node, ...]} ───────

def _node(block: dict, children: list | None = None) -> dict:
    return {"block": block, "children": children or []}


def _col_width(cells_text: list[str]) -> int:
    """按列内最长内容估算列宽(px),让短内容不被挤成多行、长内容有余量。

    中英混排按"全角约 16px / 半角约 9px"粗算,clamp 到 [90, 440]。
    """
    def visual_len(s: str) -> int:
        return sum(16 if ord(c) > 0x2E80 else 9 for c in s)
    maxw = max((visual_len(t) for t in cells_text if t), default=0)
    return min(max(maxw + 28, 90), 440)


def _table_node(rows: list[list[str]]) -> dict:
    """rows(含表头)→ 真·表格 block 节点(31 → 32 单元格 → 2 文本)。"""
    row_size = len(rows)
    col_size = max(len(r) for r in rows)
    cells: list[dict] = []
    for r in rows:
        for ci in range(col_size):
            val = r[ci] if ci < len(r) else ""
            cells.append(_node({"block_type": 32, "table_cell": {}},
                               [_node(_text(val))]))
    widths = [_col_width([r[ci] for r in rows if ci < len(r)])
              for ci in range(col_size)]
    block = {"block_type": 31,
             "table": {"property": {"row_size": row_size,
                                    "column_size": col_size,
                                    "column_width": widths,
                                    "header_row": True}}}
    return _node(block, cells)


# ── Markdown → 节点树 ─────────────────────────────────────────────

def _strip_frontmatter(md: str) -> str:
    """剥离开头的 YAML frontmatter(--- ... ---)。

    本地输出会给 .md 加 frontmatter 供 Obsidian 用;若这种内容被原样喂给
    飞书(飞书不认 frontmatter,会渲染成可见文字),在此防御性剥离。
    """
    lines = md.splitlines()
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return "\n".join(lines[i + 1:]).lstrip("\n")
    return md


def _md_to_nodes(markdown: str) -> tuple[str, list[dict]]:
    """返回 (文档标题, 顶层节点列表)。第一行 # 标题作 doc title。"""
    lines = _strip_frontmatter(markdown).splitlines()
    title = "总裁速览文档"
    top: list[dict] = []
    # bullet 嵌套栈:[(indent, node), ...]
    bullet_stack: list[tuple[int, dict]] = []
    table_buf: list[str] = []
    quote_buf: list[str] = []

    def flush_table():
        nonlocal table_buf
        rows_raw = [r for r in table_buf
                    if not re.match(r"^\s*\|[\s\-:|]+\|\s*$", r)]
        rows = [[c.strip() for c in r.strip().strip("|").split("|")]
                for r in rows_raw]
        if rows:
            top.append(_table_node(rows))
        table_buf = []
        bullet_stack.clear()

    def flush_quote():
        # 连续 > 行 → 一个高亮块,每行一个内嵌文本
        nonlocal quote_buf
        lines_ = [t for t in quote_buf if t]
        if lines_:
            top.append(_node(_callout(), [_node(_text(t)) for t in lines_]))
        quote_buf = []
        bullet_stack.clear()

    def add_top(node: dict):
        top.append(node)
        bullet_stack.clear()

    def add_bullet(indent: int, node: dict):
        while bullet_stack and bullet_stack[-1][0] >= indent:
            bullet_stack.pop()
        if bullet_stack:
            bullet_stack[-1][1]["children"].append(node)
        else:
            top.append(node)
        bullet_stack.append((indent, node))

    for raw in lines:
        line = raw.rstrip()
        s = line.strip()
        # 表格行累积
        if s.startswith("|") and s.endswith("|"):
            if quote_buf:
                flush_quote()
            table_buf.append(line)
            continue
        # 引用/高亮块累积
        if s.startswith(">"):
            if table_buf:
                flush_table()
            quote_buf.append(s.lstrip(">").strip())
            continue
        # 其余行:先收尾任何累积中的块
        if table_buf:
            flush_table()
        if quote_buf:
            flush_quote()

        if not s:
            continue
        if s == "---":
            add_top(_node(_divider()))
        elif s.startswith("# "):
            t = s[2:].strip()
            if title == "总裁速览文档":
                title = t[:80]
            else:
                add_top(_node(_heading(1, t)))
        elif s.startswith("### "):
            add_top(_node(_heading(3, s[4:].strip())))
        elif s.startswith("## "):
            add_top(_node(_heading(2, s[3:].strip())))
        elif re.match(r"^\s*[-*]\s+", line):
            indent = len(line) - len(line.lstrip())
            text = re.sub(r"^\s*[-*]\s+", "", line)
            add_bullet(indent, _node(_bullet(text)))
        elif re.match(r"^\s*\d+\.\s+", line):
            indent = len(line) - len(line.lstrip())
            text = re.sub(r"^\s*\d+\.\s+", "", line)
            add_bullet(indent, _node(_ordered(text)))
        else:
            add_top(_node(_text(s)))

    if table_buf:
        flush_table()
    if quote_buf:
        flush_quote()
    return title, top


# ── 节点树 → descendant 请求(分批,单次后代总数 ≤ 50)───────────

def _count(node: dict) -> int:
    return 1 + sum(_count(c) for c in node["children"])


def _flatten(nodes: list[dict], descendants: list[dict],
             counter: list[int]) -> list[str]:
    """递归展开,父在前;返回这批节点的顶层 temp id 列表。"""
    ids: list[str] = []
    for node in nodes:
        tid = f"b{counter[0]}"
        counter[0] += 1
        entry = {"block_id": tid, **node["block"]}
        descendants.append(entry)
        ids.append(tid)
        if node["children"]:
            entry["children"] = _flatten(node["children"], descendants, counter)
    return ids


def _write_nodes(token: str, doc_id: str, top: list[dict]):
    counter = [0]
    index = 0           # 文档顶层插入位置
    batch: list[dict] = []
    batch_total = 0
    path = f"/docx/v1/documents/{doc_id}/blocks/{doc_id}/descendant"

    def flush():
        nonlocal index, batch, batch_total
        if not batch:
            return
        descendants: list[dict] = []
        ids = _flatten(batch, descendants, counter)
        _post(token, path, {"index": index, "children_id": ids,
                            "descendants": descendants})
        index += len(batch)
        batch = []
        batch_total = 0

    for node in top:
        c = _count(node)
        if batch and batch_total + c > _MAX_DESC:
            flush()
        batch.append(node)
        batch_total += c
        # 单个节点(如大表格)超限:只能单独发,飞书会自行校验
        if batch_total >= _MAX_DESC:
            flush()
    flush()


# ── 入口 ─────────────────────────────────────────────────────────

def upload(*, markdown: str, filename: str, feishu_cfg: dict) -> str:
    """建 docx + 写入 markdown,返回文档 URL。"""
    token = _token(feishu_cfg["app_id"], feishu_cfg["app_secret"])
    folder = feishu_cfg.get("folder_token") or ""
    tenant = feishu_cfg.get("tenant_domain") or "feishu.cn"

    title, top = _md_to_nodes(markdown)

    create_body = {"title": title}
    if folder:
        create_body["folder_token"] = folder
    doc = _post(token, "/docx/v1/documents", create_body)
    doc_id = doc["data"]["document"]["document_id"]

    _write_nodes(token, doc_id, top)

    return f"https://{tenant}.feishu.cn/docx/{doc_id}"
