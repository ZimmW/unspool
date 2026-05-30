"""Notion 输出:把 Markdown 解析成 Notion block,写入数据库(或子页面)。

授权:internal integration token(应用级,无需逐用户 OAuth)。
- database 模式(推荐):每篇 = 数据库里一条,带「平台/时长(分)/日期/原链接」属性,
  可在 Notion 里筛选、排序、检索。库不存在则自动建在 parent_page_id 下并缓存 id。
- page 模式:在 parent_page_id 下建一个子页面。

block:heading_1..3 / bulleted_list_item / numbered_list_item(均支持嵌套 children)
       / callout(真高亮块)/ table + table_row / divider / paragraph
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

_API = "https://api.notion.com/v1"
_VER = "2022-06-28"
_MAX = 90   # 单次请求 block 数(含嵌套)保守上限
_CACHE = os.path.expanduser("~/.总裁速览/cache/notion_db.json")

# 自动建库时的属性 schema(database 模式)
_PROPS = ["平台", "时长(分)", "日期", "原链接"]


def _req(token: str, method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        _API + path, data=data, method=method,
        headers={"Authorization": f"Bearer {token}",
                 "Notion-Version": _VER, "Content-Type": "application/json"})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=60).read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Notion {method} {path} 失败: HTTP {e.code} "
                           f"{e.read().decode()[:300]}") from e


# ── 行内 ──────────────────────────────────────────────────────────

def _rich(text: str) -> list[dict]:
    out: list[dict] = []
    for part in re.split(r"(\*\*[^*]+\*\*)", text):
        if not part:
            continue
        bold = part.startswith("**") and part.endswith("**")
        content = part[2:-2] if bold else part
        item = {"type": "text", "text": {"content": content[:2000]}}
        if bold:
            item["annotations"] = {"bold": True}
        out.append(item)
    return out or [{"type": "text", "text": {"content": text[:2000]}}]


# ── 节点树:{"kind","text"/"rows"/"lines","level","children"} ──────

def _node(kind: str, **kw) -> dict:
    kw.setdefault("children", [])
    kw["kind"] = kind
    return kw


def _md_to_nodes(markdown: str) -> tuple[str, list[dict]]:
    lines = markdown.splitlines()
    title = "总裁速览文档"
    top: list[dict] = []
    stack: list[tuple[int, dict]] = []   # bullet/ordered 嵌套栈
    table_buf: list[str] = []
    quote_buf: list[str] = []

    def flush_table():
        nonlocal table_buf
        rows = [[c.strip() for c in r.strip().strip("|").split("|")]
                for r in table_buf
                if not re.match(r"^\s*\|[\s\-:|]+\|\s*$", r)]
        if rows:
            top.append(_node("table", rows=rows))
        table_buf = []
        stack.clear()

    def flush_quote():
        nonlocal quote_buf
        ls = [q for q in quote_buf if q]
        if ls:
            top.append(_node("callout", lines=ls))
        quote_buf = []
        stack.clear()

    def add_top(node: dict):
        top.append(node)
        stack.clear()

    def add_list(indent: int, node: dict):
        while stack and stack[-1][0] >= indent:
            stack.pop()
        (stack[-1][1]["children"] if stack else top).append(node)
        stack.append((indent, node))

    for raw in lines:
        line = raw.rstrip()
        s = line.strip()
        if s.startswith("|") and s.endswith("|"):
            if quote_buf:
                flush_quote()
            table_buf.append(line)
            continue
        if s.startswith(">"):
            if table_buf:
                flush_table()
            quote_buf.append(s.lstrip(">").strip())
            continue
        if table_buf:
            flush_table()
        if quote_buf:
            flush_quote()

        m_ul = re.match(r"^(\s*)[-*]\s+(.*)", line)
        m_ol = re.match(r"^(\s*)\d+\.\s+(.*)", line)
        if not s:
            continue
        if m_ul or m_ol:
            m = m_ul or m_ol
            add_list(len(m.group(1)),
                     _node("ordered" if m_ol else "bullet", text=m.group(2)))
        elif s == "---":
            add_top(_node("divider"))
        elif s.startswith("# "):
            t = s[2:].strip()
            if title == "总裁速览文档":
                title = t[:120]
            else:
                add_top(_node("heading", level=1, text=t))
        elif s.startswith("### "):
            add_top(_node("heading", level=3, text=s[4:].strip()))
        elif s.startswith("## "):
            add_top(_node("heading", level=2, text=s[3:].strip()))
        else:
            add_top(_node("para", text=s))

    if table_buf:
        flush_table()
    if quote_buf:
        flush_quote()
    return title, top


# ── 节点 → Notion block ───────────────────────────────────────────

def _block(node: dict) -> dict:
    k = node["kind"]
    if k == "heading":
        key = f"heading_{node['level']}"
        return {"type": key, key: {"rich_text": _rich(node["text"])}}
    if k == "para":
        return {"type": "paragraph",
                "paragraph": {"rich_text": _rich(node["text"])}}
    if k == "divider":
        return {"type": "divider", "divider": {}}
    if k == "callout":
        joined = "\n".join(node["lines"])
        return {"type": "callout",
                "callout": {"rich_text": _rich(joined),
                            "icon": {"emoji": "💬"},
                            "color": "gray_background"}}
    if k == "table":
        rows = node["rows"]
        width = max(len(r) for r in rows)
        children = []
        for r in rows:
            cells = [_rich(c) for c in r] + [[]] * (width - len(r))
            children.append({"type": "table_row", "table_row": {"cells": cells}})
        return {"type": "table",
                "table": {"table_width": width, "has_column_header": True,
                          "has_row_header": False, "children": children}}
    # bullet / ordered
    key = "numbered_list_item" if k == "ordered" else "bulleted_list_item"
    payload = {"rich_text": _rich(node["text"])}
    if node["children"]:
        payload["children"] = [_block(c) for c in node["children"]]
    return {"type": key, key: payload}


def _count(node: dict) -> int:
    if node["kind"] == "table":
        return 1 + len(node["rows"])
    return 1 + sum(_count(c) for c in node["children"])


def _batches(top: list[dict]) -> list[list[dict]]:
    out, cur, n = [], [], 0
    for node in top:
        c = _count(node)
        if cur and n + c > _MAX:
            out.append(cur)
            cur, n = [], 0
        cur.append(node)
        n += c
    if cur:
        out.append(cur)
    return out


# ── 属性解析(database 模式)──────────────────────────────────────

def _parse_meta(markdown: str) -> dict:
    def find(label):
        m = re.search(rf"\*\*{label}\*\*[:：]\s*(.+)", markdown)
        return m.group(1).strip() if m else ""
    meta = {}
    src = find("来源")
    if src:
        meta["平台"] = re.split(r"[·|]", src)[0].strip()
    dur = find("时长")
    if dur:
        h = re.search(r"(\d+)\s*时", dur)
        mi = re.search(r"(\d+)\s*分", dur)
        sec = re.search(r"(\d+)\s*秒", dur)
        total = (int(h.group(1)) * 60 if h else 0) + (int(mi.group(1)) if mi else 0)
        if sec and int(sec.group(1)) >= 30:
            total += 1
        meta["时长(分)"] = total
    url = find("原链接")
    if url:
        meta["原链接"] = url
    t = find("处理时间")
    dm = re.search(r"(\d{4}-\d{2}-\d{2})", t)
    if dm:
        meta["日期"] = dm.group(1)
    return meta


def _props_for_db(token: str, db_id: str, title: str, meta: dict) -> dict:
    """按数据库实际 schema 构造 properties,只填存在且类型匹配的属性。"""
    db = _req(token, "GET", f"/databases/{db_id}")
    schema = db.get("properties", {})
    props: dict = {}
    for name, spec in schema.items():
        if spec.get("type") == "title":
            props[name] = {"title": [{"text": {"content": title[:2000]}}]}
    type_map = {"平台": "select", "时长(分)": "number",
                "日期": "date", "原链接": "url"}
    for name, val in meta.items():
        spec = schema.get(name)
        if not spec or spec.get("type") != type_map.get(name):
            continue
        if name == "平台":
            props[name] = {"select": {"name": str(val)}}
        elif name == "时长(分)":
            props[name] = {"number": val}
        elif name == "日期":
            props[name] = {"date": {"start": val}}
        elif name == "原链接":
            props[name] = {"url": val}
    return props


# ── 数据库自动建立 + 缓存 ─────────────────────────────────────────

def _cache_get(parent: str) -> str:
    try:
        return json.load(open(_CACHE)).get(parent, "")
    except Exception:
        return ""


def _cache_put(parent: str, db_id: str):
    try:
        os.makedirs(os.path.dirname(_CACHE), exist_ok=True)
        data = {}
        if os.path.exists(_CACHE):
            data = json.load(open(_CACHE))
        data[parent] = db_id
        json.dump(data, open(_CACHE, "w"))
    except Exception:
        pass


def _ensure_database(token: str, parent_page: str) -> str:
    cached = _cache_get(parent_page)
    if cached:
        return cached
    schema = {"Name": {"title": {}},
              "平台": {"select": {}},
              "时长(分)": {"number": {}},
              "日期": {"date": {}},
              "原链接": {"url": {}}}
    db = _req(token, "POST", "/databases", {
        "parent": {"type": "page_id", "page_id": parent_page},
        "title": [{"type": "text", "text": {"content": "总裁速览"}}],
        "properties": schema})
    _cache_put(parent_page, db["id"])
    return db["id"]


# ── 入口 ─────────────────────────────────────────────────────────

def upload(*, markdown: str, filename: str, notion_cfg: dict) -> str:
    token = notion_cfg["token"]
    mode = notion_cfg.get("mode", "database")
    title, top = _md_to_nodes(markdown)
    batches = _batches(top)
    first = [_block(n) for n in batches[0]] if batches else []

    if mode == "page":
        parent_page = notion_cfg.get("parent_page_id")
        if not parent_page:
            raise RuntimeError("page 模式需要 parent_page_id")
        page = _req(token, "POST", "/pages", {
            "parent": {"type": "page_id", "page_id": parent_page},
            "properties": {"title": [{"text": {"content": title[:2000]}}]},
            "children": first})
    else:
        db_id = notion_cfg.get("database_id")
        if not db_id:
            parent_page = notion_cfg.get("parent_page_id")
            if not parent_page:
                raise RuntimeError("database 模式需要 database_id 或 parent_page_id")
            db_id = _ensure_database(token, parent_page)
        props = _props_for_db(token, db_id, title, _parse_meta(markdown))
        page = _req(token, "POST", "/pages", {
            "parent": {"type": "database_id", "database_id": db_id},
            "properties": props, "children": first})

    page_id = page["id"]
    for batch in batches[1:]:
        _req(token, "PATCH", f"/blocks/{page_id}/children",
             {"children": [_block(n) for n in batch]})

    return page.get("url") or f"https://www.notion.so/{page_id.replace('-', '')}"
