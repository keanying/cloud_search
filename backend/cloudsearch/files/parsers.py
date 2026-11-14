"""文件解析：把上传的文件转成 Markdown。

解析器（config.yaml 的 files.parser 选择，默认 auto）：
- builtin       内置：PDF 文本层（pypdf）、Word（python-docx）、Excel/CSV（表格）、TXT/Markdown/HTML/JSON。
                不做 OCR：扫描件、图片、PPT 需要 MinerU。
- mineru_api    自部署 MinerU（推荐）：`mineru-kit file-parse-server` 的 POST /v1/file_parse（4.x，返回 zip），
                兼容旧版 `mineru-api` 的 POST /file_parse（返回 JSON md_content）。
- mineru_cloud  mineru.net 精准解析 API（需 Token；文件会上传到 mineru.net）。
- mineru_agent  mineru.net 免登录轻量接口（≤10MB/20 页，按 IP 限流；文件会上传到 mineru.net，需显式选择）。
- mineru_cli    本机 `mineru` 命令行（命令模板见 mineru.cli_command）。
auto：表格与纯文本类文件总是内置解析（更快、数值不经 OCR）；其余按 自部署 → 云端(已配 Token) → 命令行 → 内置 的顺序。
MinerU 不可用时，内置能解析的格式会自动回退到内置解析，并在解析说明里注明。
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import re
import shutil
import tempfile
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from ..core.config import get_settings

TEXT_EXT = {"txt", "md", "markdown", "json", "jsonl", "ndjson", "log", "xml", "yaml", "yml"}
HTML_EXT = {"html", "htm"}
TABLE_EXT = {"csv", "tsv", "xlsx", "xlsm"}
PDF_EXT = {"pdf"}
WORD_EXT = {"docx"}
IMAGE_EXT = {"png", "jpg", "jpeg", "webp", "bmp", "gif", "tif", "tiff", "jp2"}
MINERU_ONLY_EXT = {"doc", "ppt", "pptx", "xls", "rtf", "odt", "ods", "odp", "epub", "ofd", "mhtml", "mht"} | IMAGE_EXT
ALLOWED_EXT = TEXT_EXT | HTML_EXT | TABLE_EXT | PDF_EXT | WORD_EXT | MINERU_ONLY_EXT

PARSER_LABELS = {"builtin": "内置解析", "mineru_api": "MinerU（自部署）", "mineru_cloud": "MinerU 云端",
                 "mineru_agent": "MinerU 轻量接口", "mineru_cli": "MinerU 命令行"}


class ParseError(Exception):
    """解析失败（message 为给用户看的中文说明）。"""


@dataclass
class ParseResult:
    markdown: str
    parser: str
    detail: str = ""
    page_qty: int | None = None
    image_qty: int = 0
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- 内置解析
def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "gb18030", "utf-16"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", "replace")


def _md_table(rows: list[list], max_rows: int = 1000) -> tuple[str, bool]:
    rows = [[("" if c is None else str(c)).replace("|", "\\|").replace("\n", " ").strip() for c in r] for r in rows]
    rows = [r for r in rows if any(r)]
    if not rows:
        return "", False
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    cut = len(rows) - 1 > max_rows
    body = rows[1:max_rows + 1]
    lines = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * width] + ["| " + " | ".join(r) + " |" for r in body]
    return "\n".join(lines), cut


def _pdf(data: bytes) -> tuple[str, int]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    parts = []
    for i, page in enumerate(reader.pages, 1):
        try:
            text = page.extract_text() or ""
        except Exception:  # noqa: BLE001
            text = ""
        parts.append(f"〔第 {i} 页〕\n{text.strip()}")
    return "\n\n".join(parts), len(reader.pages)


def pdf_page_count(data: bytes) -> int | None:
    try:
        from pypdf import PdfReader

        return len(PdfReader(io.BytesIO(data)).pages)
    except Exception:  # noqa: BLE001
        return None


def _docx(data: bytes) -> str:
    from docx import Document

    doc = Document(io.BytesIO(data))
    out: list[str] = []
    body = doc.element.body
    tables = {t._tbl: t for t in doc.tables}
    paras = {p._p: p for p in doc.paragraphs}
    for child in body.iterchildren():
        if child in paras:
            p = paras[child]
            text = p.text.strip()
            if not text:
                continue
            style = (p.style.name or "").lower() if p.style is not None else ""
            m = re.search(r"heading\s*(\d)|标题\s*(\d)", style)
            if m:
                level = int(m.group(1) or m.group(2))
                out.append("#" * min(level + 1, 6) + " " + text)
            elif "list" in style:
                out.append("- " + text)
            else:
                out.append(text)
        elif child in tables:
            t = tables[child]
            md, _ = _md_table([[c.text for c in row.cells] for row in t.rows])
            if md:
                out.append(md)
    return "\n\n".join(out)


def _table_doc(rows: list[list], title: str) -> tuple[str, bool]:
    """表格：程序统计概览 + 前 1000 行明细。"""
    from .profile import profile_records, table_rows_to_records

    md, cut = _md_table(rows)
    if not md:
        return "", False
    recs = table_rows_to_records(rows)
    prof = profile_records(recs, name=title) if len(recs) >= 2 else ""
    detail = f"# 明细（{title}{'，前 1000 行' if cut else ''}）\n\n{md}"
    return (prof + "\n\n" + detail) if prof else detail, cut


def _xlsx(data: bytes) -> tuple[str, list[str]]:
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    out, notes = [], []
    for ws in wb.worksheets:
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        md, cut = _table_doc(rows, f"工作表：{ws.title}")
        if not md:
            continue
        out.append(md)
        if cut:
            notes.append(f"工作表「{ws.title}」超过 1000 行：统计覆盖全部行，明细只列出前 1000 行")
    return "\n\n".join(out), notes


def _csv(data: bytes, delimiter: str) -> tuple[str, list[str]]:
    text = _decode(data)
    rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    md, cut = _table_doc(rows, "表格")
    return md, (["超过 1000 行：统计覆盖全部行，明细只列出前 1000 行"] if cut else [])


def _json_doc(text: str, name: str) -> str | None:
    """JSON / JSONL 数据集：程序统计概览 + 全部记录（每条一行）。不是记录列表时返回 None。"""
    from .profile import load_json_records, profile_records, records_section

    loaded = load_json_records(text)
    if loaded is None:
        return None
    records, where = loaded
    if len(records) < 2:
        return None
    return profile_records(records, name=name, where=where) + "\n\n" + records_section(records)


def _html(data: bytes) -> str:
    import trafilatura

    text = _decode(data)
    return trafilatura.extract(text, output_format="markdown", include_tables=True) or ""


def builtin_parse(data: bytes, ext: str, name: str = "") -> ParseResult:
    notes: list[str] = []
    pages = None
    if ext in PDF_EXT:
        md, pages = _pdf(data)
        body = re.sub(r"〔第 \d+ 页〕", "", md)
        if len(body.strip()) < max(60, 30 * pages):
            raise ParseError("这个 PDF 几乎没有可提取的文字（可能是扫描件或图片版），需要配置 MinerU 才能识别。")
    elif ext in WORD_EXT:
        md = _docx(data)
    elif ext in {"xlsx", "xlsm"}:
        md, notes = _xlsx(data)
    elif ext in {"csv", "tsv"}:
        md, notes = _csv(data, "\t" if ext == "tsv" else ",")
    elif ext in HTML_EXT:
        md = _html(data)
    elif ext in TEXT_EXT:
        md = _decode(data)
        if ext in ("json", "jsonl", "ndjson"):
            doc = _json_doc(md, name or f"数据.{ext}")
            if doc is not None:
                md = doc
            else:
                try:
                    md = "```json\n" + json.dumps(json.loads(md), ensure_ascii=False, indent=1) + "\n```"
                except ValueError:
                    pass
    elif ext in MINERU_ONLY_EXT:
        kind = "图片" if ext in IMAGE_EXT else f".{ext} 文件"
        raise ParseError(f"{kind}需要 MinerU 才能识别（内置解析只支持 PDF 文字版、Word、Excel/CSV 与文本）。"
                         "请管理员在 config.yaml 配置 mineru.api_url 或 mineru.cloud_token。")
    else:
        raise ParseError(f"不支持的文件类型：.{ext}")
    if not md.strip():
        raise ParseError("没有从文件中读到文字内容。")
    return ParseResult(markdown=md, parser="builtin", detail=PARSER_LABELS["builtin"], page_qty=pages, notes=notes)


# ---------------------------------------------------------------- MinerU：结果整理
_IMG = re.compile(r"!\[([^\]]*)\]\((?!https?:)[^)]*\)")


def _clean_md(md: str) -> tuple[str, int]:
    """去掉指向压缩包内图片的引用（模型看不到图片），保留图片说明文字。"""
    n = 0

    def repl(m: re.Match) -> str:
        nonlocal n
        n += 1
        return f"〔图片{('：' + m.group(1)) if m.group(1).strip() else ''}〕"

    return _IMG.sub(repl, md), n


def _md_from_zip(data: bytes) -> tuple[str, int]:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = [n for n in z.namelist() if n.lower().endswith(".md")]
        if not names:
            raise ParseError("MinerU 返回的结果里没有 Markdown 文件。")
        pick = next((n for n in names if n.rsplit("/", 1)[-1] in ("full.md", "markdown.md")), None) or \
            max(names, key=lambda n: z.getinfo(n).file_size)
        md = _decode(z.read(pick))
        images = sum(1 for n in z.namelist() if re.search(r"(^|/)images/.+\.(png|jpe?g|webp|gif|bmp)$", n, re.I))
    clean, refs = _clean_md(md)
    return clean, max(images, refs)


def _client(timeout: float, **kw):
    import httpx

    return httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=15), follow_redirects=True, **kw)


def _err(resp) -> str:
    try:
        j = resp.json()
        e = j.get("error") or {}
        return e.get("message") if isinstance(e, dict) else str(j.get("msg") or j.get("detail") or j)[:200]
    except Exception:  # noqa: BLE001
        return resp.text[:200]


# ---------------------------------------------------------------- MinerU：自部署 HTTP
def api_url() -> str | None:
    """自部署 MinerU 地址：显式配置优先；开启 mineru.local 时为本机托管的服务。"""
    s = get_settings()
    if s.mineru_api_url:
        return s.mineru_api_url
    return f"http://127.0.0.1:{s.mineru_local_port}" if s.mineru_local else None


EXTERNAL_PARSERS = {"mineru_cloud", "mineru_agent"}


def _abs(base: str, url: str) -> str:
    return base + url if url.startswith("/") else url


async def _tasks_api(c, base: str, data: bytes, name: str, ext: str, deadline: float) -> bytes | None:
    """MinerU 4.x 主服务（mineru-kit api-server）的 Tasks API：建任务 → PUT 上传 → 轮询 → 下载结果 zip。
    服务不支持该接口时返回 None。"""
    s = get_settings()
    body: dict = {"files": [{"file_name": name, "bytes": len(data)}], "tier": s.mineru_tier,
                  "output_formats": ["default"]}
    if ext in PDF_EXT:
        body["page_range"] = "all"  # 默认只解析前 10 页
    r = await c.post(f"{base}/v1/tasks", json=body)
    if r.status_code in (404, 405):
        return None
    if r.status_code not in (200, 201, 202):
        raise ParseError(f"MinerU 服务返回 {r.status_code}：{_err(r)}")
    try:
        task = r.json()
    except ValueError:
        return None
    task_id = task.get("task_id") if isinstance(task, dict) else None
    if not task_id:
        return None  # 不是 Tasks API（例如旧版服务对未知路径的响应）
    for f in task.get("files") or []:
        up = f.get("upload")
        if up and up.get("url"):
            u = await c.put(_abs(base, up["url"]), content=data, headers=up.get("headers") or {})
            if u.status_code >= 300:
                raise ParseError(f"上传到 MinerU 失败（HTTP {u.status_code}）：{_err(u)}")
    while True:
        if time.monotonic() > deadline:
            raise ParseError("MinerU 解析超时。")
        await asyncio.sleep(3)
        r = await c.get(f"{base}/v1/tasks/{task_id}")
        if r.status_code != 200:
            continue
        t = r.json()
        if not isinstance(t, dict) or not (t.get("status") or t.get("files")):
            raise ParseError(f"MinerU 任务状态返回异常：{str(t)[:160]}")
        files = t.get("files") or []
        f = files[0] if files else {}
        status = f.get("status") or t.get("status")
        if status in ("failed", "canceled"):
            e = f.get("error") or t.get("error") or {}
            raise ParseError(f"MinerU 解析失败：{e.get('message') if isinstance(e, dict) else e or status}")
        if status == "completed" and f.get("result_url"):
            res = await c.get(_abs(base, f["result_url"]))
            if res.status_code != 200:
                raise ParseError(f"下载 MinerU 结果失败（HTTP {res.status_code}）")
            return res.content


async def mineru_api_parse(data: bytes, name: str, *, deadline: float, ext: str = "") -> ParseResult:
    """自部署 MinerU。按顺序兼容三种服务：
    1) mineru-kit file-parse-server（POST /v1/file_parse，同步返回 zip）；
    2) mineru-kit api-server 主服务（Tasks API：/v1/tasks）——只启动这一个进程即可；
    3) 旧版 mineru-api（POST /file_parse，返回 JSON）。"""
    s = get_settings()
    base = (api_url() or "").rstrip("/")
    if not base:
        raise ParseError("未配置 mineru.api_url")
    ext = ext or Path(name).suffix.lower().lstrip(".")
    headers = {"Authorization": f"Bearer {s.mineru_api_key}"} if s.mineru_api_key else {}
    remaining = max(30.0, deadline - time.monotonic())
    label = f"{PARSER_LABELS['mineru_api']} · {s.mineru_tier}"
    async with _client(remaining, headers=headers) as c:
        form = {"tier": s.mineru_tier, "output_formats": "default", "wait_timeout": str(int(min(3600, remaining)))}
        if ext in PDF_EXT:
            form["page_range"] = "all"
        r = await c.post(f"{base}/v1/file_parse", data=form, files={"file": (name, data)})
        if r.status_code in (404, 405):
            z = await _tasks_api(c, base, data, name, ext, deadline)
            if z is not None:
                md, imgs = _md_from_zip(z)
                return ParseResult(md, "mineru_api", label, image_qty=imgs)
            r = await c.post(f"{base}/file_parse", data={"return_md": "true", "lang_list": s.mineru_language},
                             files={"files": (name, data)})
            if r.status_code != 200:
                raise ParseError(f"MinerU 服务返回 {r.status_code}：{_err(r)}")
            res = (r.json().get("results") or {})
            md = next((v.get("md_content") for v in res.values() if isinstance(v, dict) and v.get("md_content")), "")
            if not md:
                raise ParseError("MinerU 没有返回 Markdown 内容。")
            clean, imgs = _clean_md(md)
            return ParseResult(clean, "mineru_api", f"{PARSER_LABELS['mineru_api']} · 旧版接口", image_qty=imgs)
        if r.status_code == 202:  # 超过等待时间：轮询结果地址
            info = r.json()
            result_url = _abs(base, info.get("result_url") or f"/v1/file_parse/{info.get('request_id')}/result")
            while True:
                if time.monotonic() > deadline:
                    raise ParseError("MinerU 解析超时。")
                await asyncio.sleep(3)
                r = await c.get(result_url)
                if r.status_code == 200:
                    break
                if r.status_code not in (202, 409):
                    raise ParseError(f"MinerU 解析失败：{_err(r)}")
        if r.status_code != 200:
            raise ParseError(f"MinerU 服务返回 {r.status_code}：{_err(r)}")
        md, imgs = _md_from_zip(r.content)
    return ParseResult(md, "mineru_api", label, image_qty=imgs)


# ---------------------------------------------------------------- MinerU：mineru.net 精准解析
CLOUD_BASE = "https://mineru.net"


async def mineru_cloud_parse(data: bytes, name: str, *, deadline: float, data_id: str = "") -> ParseResult:
    s = get_settings()
    if not s.mineru_cloud_token:
        raise ParseError("未配置 mineru.cloud_token")
    auth = {"Authorization": f"Bearer {s.mineru_cloud_token}"}
    async with _client(120) as c:
        r = await c.post(f"{CLOUD_BASE}/api/v4/file-urls/batch", headers=auth, json={
            "files": [{"name": name, "data_id": data_id or name[:64]}], "model_version": s.mineru_cloud_model,
            "language": s.mineru_language, "enable_formula": True, "enable_table": True})
        j = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if r.status_code != 200 or j.get("code") != 0:
            raise ParseError(f"MinerU 云端拒绝了请求：{j.get('msg') or _err(r)}")
        batch_id, url = j["data"]["batch_id"], j["data"]["file_urls"][0]
        up = await c.put(url, content=data)  # 预签名地址，不设置 Content-Type
        if up.status_code not in (200, 201):
            raise ParseError(f"上传到 MinerU 云端失败（HTTP {up.status_code}）")
        while True:
            if time.monotonic() > deadline:
                raise ParseError("MinerU 云端解析超时。")
            await asyncio.sleep(4)
            r = await c.get(f"{CLOUD_BASE}/api/v4/extract-results/batch/{batch_id}", headers=auth)
            items = ((r.json().get("data") or {}).get("extract_result") or []) if r.status_code == 200 else []
            if not items:
                continue
            it = items[0]
            if it.get("state") == "failed":
                raise ParseError(f"MinerU 云端解析失败：{it.get('err_msg') or '未知原因'}")
            if it.get("state") == "done" and it.get("full_zip_url"):
                z = await c.get(it["full_zip_url"])
                md, imgs = _md_from_zip(z.content)
                return ParseResult(md, "mineru_cloud", f"{PARSER_LABELS['mineru_cloud']} · {s.mineru_cloud_model}",
                                   image_qty=imgs)


async def mineru_agent_parse(data: bytes, name: str, *, deadline: float) -> ParseResult:
    """mineru.net 免登录轻量接口（≤10MB/20 页，IP 限流）。"""
    if len(data) > 10 * 1024 * 1024:
        raise ParseError("MinerU 轻量接口只支持 10MB 以内的文件。")
    async with _client(120) as c:
        r = await c.post(f"{CLOUD_BASE}/api/v1/agent/parse/file", json={"file_name": name})
        if r.status_code == 429:
            raise ParseError("MinerU 轻量接口请求过于频繁（按 IP 限流），请稍后重试或配置 Token。")
        j = r.json()
        d = j.get("data") or j
        task_id, url = d.get("task_id"), d.get("file_url")
        if not task_id or not url:
            raise ParseError(f"MinerU 轻量接口返回异常：{str(j)[:160]}")
        up = await c.put(url, content=data)
        if up.status_code not in (200, 201):
            raise ParseError(f"上传到 MinerU 失败（HTTP {up.status_code}）")
        while True:
            if time.monotonic() > deadline:
                raise ParseError("MinerU 解析超时。")
            await asyncio.sleep(3)
            r = await c.get(f"{CLOUD_BASE}/api/v1/agent/parse/{task_id}")
            d = (r.json().get("data") or r.json()) if r.status_code == 200 else {}
            state = str(d.get("state") or d.get("status") or "")
            if state in ("failed", "error"):
                raise ParseError(f"MinerU 解析失败：{d.get('err_msg') or d.get('message') or '未知原因'}")
            if d.get("markdown_url"):
                md = (await c.get(d["markdown_url"])).text
                clean, imgs = _clean_md(md)
                return ParseResult(clean, "mineru_agent", PARSER_LABELS["mineru_agent"], image_qty=imgs)


# ---------------------------------------------------------------- MinerU：本机命令行
def cli_available() -> bool:
    cmd = get_settings().mineru_cli_command
    return bool(cmd) and shutil.which(cmd[0]) is not None


async def mineru_cli_parse(data: bytes, name: str, *, deadline: float) -> ParseResult:
    cmd = get_settings().mineru_cli_command
    if not cli_available():
        raise ParseError(f"没有找到 MinerU 命令行（{cmd[0] if cmd else '未配置'}）")
    with tempfile.TemporaryDirectory(prefix="cs-mineru-") as tmp:
        src = Path(tmp) / ("input" + Path(name).suffix.lower())
        src.write_bytes(data)
        out_dir = Path(tmp) / "out"
        out_dir.mkdir()
        out_md = out_dir / "output.md"
        args = [a.format(input=str(src), output=str(out_md), output_dir=str(out_dir)) for a in cmd]
        proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE,
                                                    stderr=asyncio.subprocess.PIPE)
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), max(30.0, deadline - time.monotonic()))
        except TimeoutError:
            proc.kill()
            raise ParseError("MinerU 命令行解析超时。") from None
        if proc.returncode != 0:
            raise ParseError(f"MinerU 命令行出错：{_decode(stderr or b'').strip()[-300:]}")
        mds = [out_md] if out_md.exists() else sorted(out_dir.rglob("*.md"), key=lambda p: p.stat().st_size)
        md = mds[-1].read_text(encoding="utf-8", errors="replace") if mds else _decode(stdout or b"")
        if not md.strip():
            raise ParseError("MinerU 命令行没有输出内容。")
        clean, imgs = _clean_md(md)
        imgs = max(imgs, len(list(out_dir.rglob("images/*"))))
    return ParseResult(clean, "mineru_cli", PARSER_LABELS["mineru_cli"], image_qty=imgs)


# ---------------------------------------------------------------- 选择解析器
def candidates(ext: str) -> list[str]:
    """该格式按顺序尝试的解析器。"""
    s = get_settings()
    choice = s.files_parser
    builtin_ok = ext not in MINERU_ONLY_EXT
    if choice != "auto":
        order = [choice]
    elif ext in TABLE_EXT | TEXT_EXT | HTML_EXT:
        order = ["builtin"]  # 表格/文本不需要版面识别，内置解析更快、数值不经 OCR
    else:
        order = []
        if api_url():
            order.append("mineru_api")
        if s.mineru_cloud_token:
            order.append("mineru_cloud")
        if cli_available():
            order.append("mineru_cli")
    from ..core import privacy

    # 本机托管 MinerU 或数据不出域：文件绝不发往 mineru.net（即使误配了云端 Token 或 files.parser）
    if s.mineru_local and choice in EXTERNAL_PARSERS:
        order = ["mineru_api"]
    if privacy.enabled() or s.mineru_local:
        order = [p for p in order if p not in EXTERNAL_PARSERS] or (["builtin"] if builtin_ok else [])
        if not order:
            raise ParseError("文件只在本机解析（不使用 MinerU 云端）；请确认本机 MinerU 已启动（mineru.local）"
                             "或配置自部署 MinerU（mineru.api_url）")
    if builtin_ok and "builtin" not in order:
        order.append("builtin")  # MinerU 不可用时的兜底
    return order or ["builtin"]


async def parse_bytes(data: bytes, name: str, ext: str, *, data_id: str = "") -> ParseResult:
    s = get_settings()
    deadline = time.monotonic() + s.files_parse_timeout_s
    errors: list[str] = []
    for p in candidates(ext):
        try:
            if p == "builtin":
                res = await asyncio.to_thread(builtin_parse, data, ext, name)
            elif p == "mineru_api":
                res = await mineru_api_parse(data, name, deadline=deadline, ext=ext)
            elif p == "mineru_cloud":
                res = await mineru_cloud_parse(data, name, deadline=deadline, data_id=data_id)
            elif p == "mineru_agent":
                res = await mineru_agent_parse(data, name, deadline=deadline)
            elif p == "mineru_cli":
                res = await mineru_cli_parse(data, name, deadline=deadline)
            else:
                raise ParseError(f"未知的解析器：{p}（files.parser 可选 auto/builtin/mineru_api/mineru_cloud/"
                                 "mineru_cli/mineru_agent）")
        except ParseError as e:
            errors.append(f"{PARSER_LABELS.get(p, p)}：{e}")
            continue
        except Exception as e:  # noqa: BLE001 —— 网络不通等
            errors.append(f"{PARSER_LABELS.get(p, p)}：{type(e).__name__} {str(e)[:160]}")
            continue
        if res.page_qty is None and ext in PDF_EXT:
            res.page_qty = pdf_page_count(data)
        if errors:  # 前面的解析器失败、回退成功
            res.notes.insert(0, "；".join(errors) + "，已改用" + PARSER_LABELS.get(res.parser, res.parser))
        return res
    raise ParseError("；".join(errors) or "无法解析该文件")
