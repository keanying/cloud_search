"""四种模式的执行流水线。阶段由 coordinator.plan 确定；每个节点通过 ctx.step 持久化并可在恢复时复用。

并发：搜索在会话1中串行进行；读取使用多个独立 BrowserContext 并发（单 context 内串行）；
抽取在读取完成后立即并发进行（受模型并发上限约束）。
"""

from __future__ import annotations

import asyncio
import logging
import re
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents import analyst, coordinator, extractor, report_writer, search_planner, verifier
from ..agents.browser_researcher import read_source
from ..browser.pool import get_pool
from ..contracts import EvidenceRef, SearchHit, SearchQuery, SourceDoc, TaskSpec
from ..core.config import get_settings
from ..core.ids import iso, new_id, sha256_bytes, utcnow
from ..core.storage import get_storage
from ..db.models import Artifact, Evidence, SourceCandidate, SourceRevision
from ..search import credibility
from ..search.service import browser_search, normalize_url, rank_hits
from . import exporters
from .context import BudgetExhausted, LeaseLost, StepResult, TaskExecContext, TaskInterrupted
from .progress import update_progress

log = logging.getLogger(__name__)

CONTROL_EXC = (TaskInterrupted, LeaseLost, BudgetExhausted)
LLM_CONCURRENCY = 3


@dataclass
class SourceInfo:
    n: int
    source_revision_id: str
    url: str
    title: str | None
    site_name: str | None
    publish_time_text: str | None
    retrieved_time: str
    access_method: str
    content_ref: str
    text: str | None = None
    credibility: str = "unknown"
    file_id: str | None = None

    def public(self) -> dict[str, Any]:
        return {"n": self.n, "source_revision_id": self.source_revision_id, "url": self.url, "title": self.title,
                "site_name": self.site_name, "publish_time_text": self.publish_time_text,
                "retrieved_time": self.retrieved_time, "access_method": self.access_method,
                "credibility": self.credibility, "credibility_label": credibility.LABELS[self.credibility],
                "file_id": self.file_id}


@dataclass
class PipelineOutcome:
    parts: list[dict] = field(default_factory=list)
    artifact_ids: list[str] = field(default_factory=list)
    bundles: list[dict] = field(default_factory=list)  # 同一成果的多种格式：{primary, formats:[{format, artifact_id, byte_qty}]}
    delivered: bool = False
    technical_failures: int = 0
    error_code: str | None = None
    error_desc: str | None = None


def _norm_entity(name: str) -> str:
    return re.sub(r"[\s\W_]+", "", (name or "").lower())


def _unwrap_group(eg: BaseExceptionGroup) -> BaseException:
    for exc in eg.exceptions:
        if isinstance(exc, BaseExceptionGroup):
            return _unwrap_group(exc)
        if isinstance(exc, CONTROL_EXC):
            return exc
    return eg.exceptions[0]


class Pipeline:
    def __init__(self, ctx: TaskExecContext, spec: TaskSpec, *, conversation_id: str | None):
        self.ctx = ctx
        self.spec = spec
        self.conversation_id = conversation_id
        self.stages = task_stages_from_spec(spec)
        self.sources: dict[str, SourceInfo] = {}
        self.read_urls: set[str] = set()
        self.used_queries: list[str] = []
        self.intent: str = spec.requirement_text
        self.preferred_sources: list[str] = []
        self.sub_questions: list[str] = list(spec.scope.questions)
        self.key_entities: list[str] = []
        self.findings: list[EvidenceRef] = []
        self.records: list[dict] = []
        self.blocked = 0
        self.failed = 0
        self.blocked_engines: set[str] = set()
        self.coverage_missing: list[str] = []
        self._next_n = 1
        self._llm_sem = asyncio.Semaphore(LLM_CONCURRENCY)
        self.file_failures: list[dict] = []
        self.storage = get_storage()

    # ------------------------------------------------------------ 进度
    async def _stage(self, stage: str, status: str = "running", **inc: int) -> None:
        await update_progress(self.ctx.task_id, stage=stage, stage_status=status, inc=inc or None)

    async def _inc(self, **inc: int) -> None:
        await update_progress(self.ctx.task_id, inc=inc)

    # ------------------------------------------------------------ 主流程
    async def run(self) -> PipelineOutcome:
        await self._init_next_n()
        if "files" in self.stages:
            await self._files_phase()
        if "plan" in self.stages:
            await self._web_phase()

        outcome = PipelineOutcome(technical_failures=self.failed)
        if not self.sources:
            for st in self.stages[self.stages.index("verify"):]:
                await self._stage(st, "skipped")
            outcome.error_code = "no_sources"
            engines = f"（被拦截的搜索引擎：{', '.join(sorted(self.blocked_engines))}）" if self.blocked_engines else ""
            if "plan" not in self.stages:  # 只基于上传文件
                why = "；".join(f"{x['name']}：{x['reason']}" for x in self.file_failures) or "文件没有可用内容"
                outcome.error_desc = f"没能读取上传的文件：{why}"
            else:
                outcome.error_desc = (f"未能读取到可用的网页正文：受限 {self.blocked} 个、失败 {self.failed} 个{engines}。"
                                      "可以稍后重试，或换一种说法/指定网站。")
            outcome.parts.append({"type": "error", "part_id": f"error-{self.ctx.task_id}", "code": "no_sources",
                                  "message": outcome.error_desc, "task_id": self.ctx.task_id})
            return outcome

        # 核验
        await self._stage("verify")
        verified = await self.ctx.step("verify", self._verify_fn, agent_role="verifier")
        await self._stage("verify", "done")

        rows: list[dict] = []
        analysis: list[dict] = []
        if "build" in self.stages:
            await self._stage("build")
            built = await self.ctx.step("build", lambda c: self._build_fn(c, verified), node_kind="deterministic")
            rows = built["rows"]
            self._built = (rows, [s.public() for s in sorted(self.sources.values(), key=lambda s: s.n)])
            outcome.artifact_ids += built.get("artifact_ids", [])
            outcome.bundles += built.get("bundles", [])
            await self._stage("build", "done")
        if "analyze" in self.stages:
            await self._stage("analyze")
            res = await self.ctx.step("analyze", lambda c: self._analyze_fn(c, rows), agent_role="analyst")
            analysis = res["results"]
            outcome.artifact_ids += res.get("artifact_ids", [])
            if res.get("xlsx") and outcome.bundles:  # 含分析的 Excel 作为数据成果的主文件
                b = outcome.bundles[0]
                b["formats"] = [res["xlsx"]] + [f for f in b["formats"] if f["format"] != "xlsx"]
                b["primary"] = res["xlsx"]["artifact_id"]
            await self._stage("analyze", "done")
        if "write" in self.stages:
            await self._stage("write")
            written = await self.ctx.step("write", lambda c: self._write_fn(c, verified, analysis, rows),
                                          agent_role="report_writer")
            outcome.artifact_ids += written.get("artifact_ids", [])
            outcome.bundles += written.get("bundles", [])
            await self._stage("write", "done")
            used = written["used"]
            if written.get("highlights"):
                outcome.parts.append({"type": "highlights", "part_id": f"highlights-{self.ctx.task_id}",
                                      "items": [{**h, "url": (self._citation(h["source_n"]) or {}).get("url")}
                                                for h in written["highlights"]]})
            outcome.parts.append({
                "type": "text", "part_id": f"answer-{self.ctx.task_id}", "text": written["markdown"],
                "citations": written.get("citations") or [self._citation(n) for n in used if self._citation(n)]})
        else:
            text = self._dataset_summary(rows)
            if analysis:
                text += "\n\n" + exporters.analysis_markdown(analysis)
            outcome.parts.append({"type": "text", "part_id": f"answer-{self.ctx.task_id}", "text": text,
                                  "citations": []})
        outcome.parts.append({"type": "source", "part_id": f"sources-{self.ctx.task_id}", "task_id": self.ctx.task_id,
                              "sources": [s.public() for s in sorted(self.sources.values(), key=lambda s: s.n)]})
        if "write" in self.stages and written.get("follow_ups"):
            outcome.parts.append({"type": "suggestions", "part_id": f"suggestions-{self.ctx.task_id}",
                                  "items": written["follow_ups"]})
        outcome.delivered = True
        return outcome

    async def _web_phase(self) -> None:
        """规划 → 浏览器搜索/读取/抽取 → 覆盖评估与补查。"""
        await self._stage("plan")
        planned = await self.ctx.step("plan", self._plan_fn, agent_role="search_planner",
                                      input_json={"limits": self.spec.limits.model_dump()})
        self.intent = planned.get("intent") or self.spec.requirement_text
        self.preferred_sources = planned.get("preferred_sources", [])
        self.sub_questions = planned.get("sub_questions") or list(self.spec.scope.questions) or [self.spec.requirement_text]
        self.key_entities = planned.get("key_entities", [])
        queries = [self._as_query(q) for q in planned["queries"]]
        await self._stage("plan", "done", queries=len(queries))

        pool = get_pool()
        settings = get_settings()
        async with AsyncExitStack() as stack:
            sessions = []

            async def get_sessions(n: int):
                while len(sessions) < n:
                    sessions.append(await stack.enter_async_context(pool.session(
                        project_id=self.ctx.project_id, task_id=self.ctx.task_id, run_id=self.ctx.run_id,
                        worker_id=self.ctx.worker_id, label=f"会话{len(sessions) + 1}")))
                    if len(sessions) == 1:
                        await update_progress(self.ctx.task_id, browser_available=True)
                return sessions[:n]

            await self._wave(1, queries, self.spec.limits.max_sources, get_sessions, settings.task_read_concurrency)

            if "coverage" in self.stages:
                # 规划 → 搜索 → 反思（按子问题评估覆盖）→ 针对缺口补查，最多 max_waves 轮
                await self._stage("coverage")
                max_waves = settings.task_max_extra_waves if self.spec.mode in ("research", "hybrid") else \
                    min(1, settings.task_max_extra_waves)
                did_extra = False
                for w in range(1, max_waves + 1):
                    if not self.sources:
                        break
                    review = await self.ctx.step(f"coverage:w{w}", lambda c, w=w: self._coverage_fn(c, w, max_waves),
                                                 agent_role="coordinator")
                    self.coverage_missing = review.get("missing_aspects", [])
                    extra = review["extra_queries"]
                    if not extra:
                        break
                    did_extra = True
                    await self._inc(queries=len(extra))
                    extra_limit = min(4, max(2, self.spec.limits.max_sources // 2))
                    await self._wave(w + 1, [self._as_query(q) for q in extra], extra_limit, get_sessions,
                                     settings.task_read_concurrency)
                    await self._stage("coverage")
                await self._stage("coverage", "done" if did_extra else "skipped")
        await update_progress(self.ctx.task_id, browser_available=True)  # 会话已关闭，保留最后帧供查看

    async def _files_phase(self) -> None:
        """上传文件：等待解析完成 → 每个文件（长文档按章节/页码分段）登记为可引用的来源 → 抽取。"""
        await self._stage("files")
        out = await self.ctx.step("files", self._files_fn, node_kind="deterministic",
                                  input_json={"file_ids": self.spec.scope.file_ids})
        self.file_failures = out.get("failed", [])
        for o in out["sources"]:
            self._register_source(o)
        await self._stage("files", "done", sources_read=len(out["sources"]),
                          sources_failed=len(self.file_failures))
        if out["sources"]:
            await self._stage("extract")
            try:
                async with asyncio.TaskGroup() as tg:
                    for o in out["sources"]:
                        tg.create_task(self._extract_one(o["source_revision_id"]))
            except BaseExceptionGroup as eg:
                raise _unwrap_group(eg) from None
            if "plan" not in self.stages:
                await self._stage("extract", "done")

    async def _files_fn(self, c: TaskExecContext) -> StepResult:
        from ..db.base import session_scope
        from ..db.models import UploadedFile
        from ..files.service import load_markdown, segments

        ids = list(dict.fromkeys(self.spec.scope.file_ids))
        deadline = asyncio.get_running_loop().time() + get_settings().files_parse_timeout_s + 120
        while True:  # 等待解析完成（解析在后台进行，任务可能比解析先开始）
            await c.check()
            async with session_scope() as s:
                rows = [f for f in [await s.get(UploadedFile, i) for i in ids]
                        if f is not None and f.project_id == c.project_id and f.file_status == "active"]
            pending = [f for f in rows if f.parse_status in ("queued", "parsing")]
            if not pending or asyncio.get_running_loop().time() > deadline:
                break
            await asyncio.sleep(2)
        sources, failed, persist_rows = [], [], []
        now = utcnow()
        for f in rows:
            if f.parse_status != "parsed":
                failed.append({"name": f.display_name, "reason": f.parse_error or "解析未完成"})
                continue
            md = await load_markdown(f)
            segs = segments(md)
            for k, (label, text) in enumerate(segs, 1):
                srid = new_id("srcrev")
                ref, chash = await self.storage.put(f"sources/{c.task_id}/{srid}.txt", text.encode("utf-8"))
                n = self._next_n
                self._next_n += 1
                url = f"file:{f.file_id}#{k}"
                title = f.display_name + (f" · {label}" if len(segs) > 1 and label else "")
                persist_rows.append(SourceRevision(
                    source_revision_id=srid, project_id=c.project_id, task_id=c.task_id, source_no=n,
                    request_url=url, final_url=url, title=title[:512], site_name="上传的文件", retrieved_time=now,
                    access_method="user_file", content_hash=chash, content_ref=ref, text_char_qty=len(text),
                    revision_status="captured"))
                sources.append({"source_revision_id": srid, "n": n, "url": url, "final_url": url, "title": title,
                                "site_name": "上传的文件", "publish_time_text": None, "retrieved_time": iso(now),
                                "access_method": "user_file", "content_ref": ref, "file_id": f.file_id})
        missing = [i for i in ids if i not in {f.file_id for f in rows}]
        failed += [{"name": i, "reason": "文件不存在或已删除"} for i in missing]

        async def persist(s: AsyncSession) -> None:
            s.add_all(persist_rows)

        return StepResult({"sources": sources, "failed": failed}, persist)

    def _citation(self, n: int) -> dict | None:
        for s in self.sources.values():
            if s.n == n:
                return {"n": n, "source_revision_id": s.source_revision_id, "url": s.url, "title": s.title,
                        "site_name": s.site_name, "publish_time_text": s.publish_time_text,
                        "credibility": s.credibility, "credibility_label": credibility.LABELS[s.credibility]}
        return None

    def _dataset_summary(self, rows: list[dict]) -> str:
        assert self.spec.dataset is not None
        fields = self.spec.dataset.fields
        missing = sum(1 for r in rows for f in fields if r["values"].get(f.key) is None)
        total = len(rows) * len(fields)
        text = (f"已整理 **{len(rows)}** 条记录（{self.spec.dataset.entity}），{len(fields)} 个字段，"
                f"来自 {len(self.sources)} 个实际读取的来源。")
        if total:
            text += f"空值 {missing}/{total} 处，原因已在文件“缺失说明”列标注，未做推测填充。"
        if self.blocked or self.failed:
            text += f"\n\n另有 {self.blocked} 个来源访问受限、{self.failed} 个读取失败，未计入。"
        return text

    async def _init_next_n(self) -> None:
        from ..db.base import session_scope

        async with session_scope() as s:
            mx = (await s.execute(select(func.max(SourceRevision.source_no))
                                  .where(SourceRevision.task_id == self.ctx.task_id))).scalar()
        self._next_n = (mx or 0) + 1

    # ------------------------------------------------------------ 波次：搜索 → 读取 → 抽取
    def _handoff(self, c: TaskExecContext):
        """遇到人机验证/登录墙时请求人工接管（见 orchestrator/takeover.py）。"""
        from .takeover import request_takeover

        async def cb(sess, reason: str) -> bool:
            return await request_takeover(c, sess.browser_session_id, reason)

        return cb

    def _as_query(self, q) -> SearchQuery:
        """兼容旧格式（纯字符串）与新格式（SearchQuery 字典）。"""
        if isinstance(q, SearchQuery):
            return q
        if isinstance(q, dict):
            return SearchQuery.model_validate(q)
        lang = "zh" if self.spec.scope.language.startswith("zh") else "en"
        return SearchQuery(query=str(q), language=lang)

    async def _wave(self, w: int, queries: list[SearchQuery], limit: int, get_sessions, concurrency: int) -> None:
        self.used_queries += [q.query for q in queries]
        await self._stage("search")
        main = (await get_sessions(1))[0]
        searched = await self.ctx.step(f"search:w{w}", lambda c: self._search_fn(c, main, queries, refine=(w == 1)),
                                       node_kind="browser",
                                       input_json={"queries": [q.model_dump() for q in queries]})
        self.blocked_engines.update(searched.get("blocked_engines", []))
        self.used_queries += searched.get("refined_queries", [])
        hits = [h for h in searched["hits"] if normalize_url(h["url"]) not in self.read_urls]
        await self._stage("search", "done", candidates=len(searched["hits"]) if w == 1 else len(hits),
                          queries=len(searched.get("refined_queries", [])))

        picked = await self._pick(w, hits, limit)
        cand_by_url = {h["url"]: h["candidate_id"] for h in hits}
        if not picked:
            return
        await self._stage("read")
        await self._stage("extract")
        sessions = await get_sessions(max(1, min(concurrency, len(picked))))
        queue: asyncio.Queue = asyncio.Queue()
        for h in picked:
            queue.put_nowait((cand_by_url[h["url"]], SearchHit(**{k: h[k] for k in SearchHit.model_fields})))

        async def reader(sess):
            while True:
                try:
                    cid, hit = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                try:
                    out = await self.ctx.step(f"read:{cid}", lambda c: self._read_fn(c, sess, cid, hit.url),
                                              node_kind="browser", agent_role="browser_researcher",
                                              input_json={"url": hit.url})
                except CONTROL_EXC:
                    raise
                except Exception as e:  # noqa: BLE001
                    log.warning("read failed %s: %s", hit.url, e)
                    self.failed += 1
                    await self._inc(sources_failed=1)
                    continue
                if out["status"] == "captured":
                    self._register_source(out)
                    await self._inc(sources_read=1)
                    tg.create_task(self._extract_one(out["source_revision_id"]))
                elif out["status"] in ("blocked", "failed", "no_content"):
                    if out["status"] == "blocked":
                        self.blocked += 1
                    elif out["status"] == "failed":
                        self.failed += 1
                    await self._inc(sources_failed=1)

        try:
            async with asyncio.TaskGroup() as tg:
                for sess in sessions:
                    tg.create_task(reader(sess))
        except BaseExceptionGroup as eg:
            raise _unwrap_group(eg) from None
        await self._stage("read", "done")
        await self._stage("extract", "done")

    def _register_source(self, out: dict) -> None:
        if out["source_revision_id"] in self.sources:
            return
        user_file = out.get("access_method") == "user_file"
        if not user_file:
            self.read_urls.add(normalize_url(out["final_url"] or out["url"]))
        self.sources[out["source_revision_id"]] = SourceInfo(
            n=out["n"], source_revision_id=out["source_revision_id"], url=out["final_url"] or out["url"],
            title=out.get("title"), site_name=out.get("site_name"), publish_time_text=out.get("publish_time_text"),
            retrieved_time=out["retrieved_time"], access_method=out["access_method"], content_ref=out["content_ref"],
            credibility="user_file" if user_file else
            credibility.classify(out["final_url"] or out["url"], preferred=self.preferred_sources),
            file_id=out.get("file_id"))

    async def _extract_one(self, srid: str) -> None:
        async with self._llm_sem:
            try:
                out = await self.ctx.step(f"extract:{srid}", lambda c: self._extract_fn(c, srid),
                                          agent_role="extractor")
            except CONTROL_EXC:
                raise
            except Exception as e:  # noqa: BLE001  单个来源抽取失败不终止任务
                log.warning("extract failed %s: %s", srid, e)
                self.failed += 1
                return
        src = self.sources[srid]
        for f in out["findings"]:
            self.findings.append(EvidenceRef(**f))
        for r in out["records"]:
            self.records.append({**r, "n": src.n})
        await self._inc(evidence=len(out["findings"]) + sum(len(r["evidence_ids"]) for r in out["records"]))

    # ------------------------------------------------------------ 节点实现
    async def _plan_fn(self, c: TaskExecContext) -> StepResult:
        plan = await search_planner.plan_queries(self.spec, c)
        return StepResult({"intent": plan.intent, "key_entities": plan.key_entities,
                           "preferred_sources": plan.preferred_sources, "sub_questions": plan.sub_questions,
                           "queries": [q.model_dump() for q in plan.queries]})

    async def _search_fn(self, c: TaskExecContext, sess, queries: list[SearchQuery], *, refine: bool) -> StepResult:
        report = await browser_search(sess, queries, exclude_domains=self.spec.scope.exclude_domains,
                                      before_each=c.check, on_blocked=self._handoff(c))
        refined: list[str] = []
        # 无结果 / 结果全部无关的查询：参考实际返回改写一次再搜（仅第一轮，最多 3 条）
        weak = [q.query for q in queries if report.hit_counts.get(q.query, 0) == 0]
        if refine and weak:
            titles = {q: [h.title or "" for h in report.hits if h.query == q] for q in weak}
            try:
                new_qs = await search_planner.refine_queries(self.spec, self.intent, [(q, titles[q]) for q in weak],
                                                             self.used_queries, c)
            except CONTROL_EXC:
                raise
            except Exception as e:  # noqa: BLE001  改写失败不影响已有结果
                log.warning("refine queries failed: %s", e)
                new_qs = []
            if new_qs:
                extra = await browser_search(sess, new_qs, exclude_domains=self.spec.scope.exclude_domains,
                                             before_each=c.check, on_blocked=self._handoff(c))
                seen = {normalize_url(h.url) for h in report.hits}
                report.hits += [h for h in extra.hits if normalize_url(h.url) not in seen]
                report.per_query.update(extra.per_query)
                report.blocked_engines += extra.blocked_engines
                refined = [q.query for q in new_qs]
        hits = []
        rows = []
        for h in report.hits:
            cid = new_id("cand")
            hits.append({**h.model_dump(), "candidate_id": cid})
            rows.append(SourceCandidate(candidate_id=cid, task_id=c.task_id, query_text=h.query[:512],
                                        engine_name=h.engine, rank_no=h.rank, url=h.url[:2048],
                                        url_hash=sha256_bytes(normalize_url(h.url).encode()), title=h.title,
                                        snippet=h.snippet))

        async def persist(s: AsyncSession) -> None:
            existing = set((await s.execute(select(SourceCandidate.url_hash).where(
                SourceCandidate.task_id == c.task_id))).scalars().all())
            for r in rows:
                if r.url_hash not in existing:
                    existing.add(r.url_hash)
                    s.add(r)

        return StepResult({"hits": hits, "per_query": report.per_query, "refined_queries": refined,
                           "blocked_engines": sorted(set(report.blocked_engines))}, persist)

    async def _pick(self, w: int, hits: list[dict], limit: int) -> list[dict]:
        """选择要读取的候选：候选多于上限时由搜索规划智能体按意图与权威性挑选；失败则按排名+权威站点加权。"""
        if not hits:
            return []
        objs = [SearchHit(**{k: h[k] for k in SearchHit.model_fields}) for h in hits]

        def fallback() -> list[dict]:
            pref = set(self.preferred_sources) | {d.lower() for d in self.spec.scope.include_domains}
            ranked = rank_hits(objs, len(objs))
            # 稳定排序：先按可信度（含规划认定的权威站点），同档内保持搜索排名交错顺序
            ranked.sort(key=lambda h: -credibility.score(h.url, preferred=list(pref)))
            by_url = {h["url"]: h for h in hits}
            return [by_url[h.url] for h in ranked[:limit]]

        if len(hits) <= limit:
            return fallback()

        async def select_fn(c: TaskExecContext) -> StepResult:
            picked = await search_planner.select_candidates(self.spec, self.intent, objs, limit, c,
                                                            preferred=self.preferred_sources)
            return StepResult({"candidate_ids": [hits[i]["candidate_id"] for i, _ in picked],
                               "reasons": [r for _, r in picked]})

        try:
            out = await self.ctx.step(f"select:w{w}", select_fn, agent_role="search_planner")
        except CONTROL_EXC:
            raise
        except Exception as e:  # noqa: BLE001
            log.warning("candidate selection failed, falling back to ranking: %s", e)
            return fallback()
        by_id = {h["candidate_id"]: h for h in hits}
        chosen = [by_id[cid] for cid in out["candidate_ids"] if cid in by_id]
        return chosen or fallback()

    async def _read_fn(self, c: TaskExecContext, sess, candidate_id: str, url: str) -> StepResult:
        goal = "；".join(self.spec.scope.questions) or self.spec.requirement_text
        r = await read_source(sess, url, goal=goal, ctx=c, on_blocked=self._handoff(c))
        final = r.final_url or url
        if r.status == "captured" and normalize_url(final) in self.read_urls:
            return StepResult({"status": "duplicate", "url": url, "final_url": final})
        srid = new_id("srcrev")
        now = utcnow()
        content_ref, chash = None, None
        n = None
        if r.status == "captured":
            content_ref, chash = await self.storage.put(f"sources/{c.task_id}/{srid}.txt", r.text.encode("utf-8"))
            n = self._next_n
            self._next_n += 1
            self.read_urls.add(normalize_url(final))
        row = SourceRevision(source_revision_id=srid, project_id=c.project_id, task_id=c.task_id,
                             candidate_id=candidate_id, source_no=n, request_url=url[:2048], final_url=final[:2048],
                             title=(r.title or None) and r.title[:512], site_name=r.site_name, author=r.author,
                             publish_time_text=r.publish_time_text, retrieved_time=now, access_method="browser",
                             browser_session_id=sess.browser_session_id, content_hash=chash, content_ref=content_ref,
                             text_char_qty=len(r.text), revision_status=r.status,
                             failure_reason=(r.reason or None) and r.reason[:256])

        async def persist(s: AsyncSession) -> None:
            s.add(row)
            cand = await s.get(SourceCandidate, candidate_id)
            if cand:
                cand.candidate_status = {"captured": "accepted", "blocked": "blocked"}.get(r.status, "rejected")

        return StepResult({"status": r.status, "source_revision_id": srid, "n": n, "url": url, "final_url": final,
                           "title": r.title, "site_name": r.site_name, "publish_time_text": r.publish_time_text,
                           "retrieved_time": iso(now), "access_method": "browser", "content_ref": content_ref,
                           "reason": r.reason}, persist)

    async def _load_text(self, src: SourceInfo) -> str:
        if src.text is None:
            src.text = (await self.storage.get(src.content_ref)).decode("utf-8")
        return src.text

    async def _extract_fn(self, c: TaskExecContext, srid: str) -> StepResult:
        src = self.sources[srid]
        text = await self._load_text(src)
        out = await extractor.extract(SourceDoc(n=src.n, source_revision_id=srid, url=src.url, title=src.title,
                                                site_name=src.site_name, publish_time_text=src.publish_time_text,
                                                text=text), self.spec, c, sub_questions=self.sub_questions,
                                      key_entities=self.key_entities)
        ev_rows: list[Evidence] = []
        findings, records = [], []

        def add_evidence(quote: str, claim: str) -> str | None:
            loc = verifier.locate_quote(text, quote)
            if loc is None:
                return None
            eid = new_id("evd")
            ev_rows.append(Evidence(evidence_id=eid, task_id=c.task_id, source_revision_id=srid,
                                    quote_text=text[loc[0]:loc[1]], char_start_no=loc[0], char_end_no=loc[1],
                                    claim_text=claim[:2000]))
            return eid

        if out.relevant:
            for f in out.findings:
                eid = add_evidence(f.quote, f.claim)
                if eid:
                    findings.append({"evidence_id": eid, "n": src.n, "claim": f.claim, "quote": f.quote,
                                     "aspect": f.aspect})
            labels = {f.key: f.label for f in (self.spec.dataset.fields if self.spec.dataset else [])}
            for rec in out.records:
                values, missing, eids = {}, dict(rec.missing_reasons), {}
                for k, v in rec.values.items():
                    if v is None or v == "":
                        values[k] = None
                        missing.setdefault(k, "not_found")
                        continue
                    q = rec.quotes.get(k)
                    eid = add_evidence(q, f"{rec.entity_name} {labels.get(k, k)}：{v}") if q else None
                    if eid is None:  # 无可校验原文的值不采用
                        values[k] = None
                        missing[k] = "unverified"
                    else:
                        values[k] = v
                        eids[k] = eid
                        missing.pop(k, None)
                records.append({"entity_name": rec.entity_name, "values": values, "missing_reasons": missing,
                                "evidence_ids": eids})

        async def persist(s: AsyncSession) -> None:
            s.add_all(ev_rows)

        return StepResult({"relevant": out.relevant, "findings": findings, "records": records}, persist)

    def _aspect_of(self, aspect: str | None) -> str | None:
        """把抽取结果的 aspect 归到最接近的子问题（原文照抄优先，其次包含关系/字面重合）。"""
        if not aspect:
            return None
        if aspect in self.sub_questions:
            return aspect
        for q in self.sub_questions:
            if aspect in q or q in aspect:
                return q
        best, score = None, 0.0
        a = set(aspect)
        for q in self.sub_questions:
            sc = len(a & set(q)) / (len(a | set(q)) or 1)
            if sc > score:
                best, score = q, sc
        return best if score >= 0.35 else None

    def _evidence_digest(self, per_aspect: int = 8) -> tuple[str, list[str]]:
        cred = {s.n: credibility.LABELS[s.credibility] for s in self.sources.values()}
        groups: dict[str, list[EvidenceRef]] = {q: [] for q in self.sub_questions}
        other: list[EvidenceRef] = []
        for e in self.findings:
            q = self._aspect_of(e.aspect)
            (groups[q] if q else other).append(e)
        lines = []
        for q, evs in groups.items():
            n_src = len({e.n for e in evs})
            lines.append(f"## {q}（证据 {len(evs)} 条，来源 {n_src} 个）")
            lines += [f"[{e.n}·{cred.get(e.n, '')}] {e.claim}" for e in evs[:per_aspect]]
        if other:
            lines.append("## 其他")
            lines += [f"[{e.n}·{cred.get(e.n, '')}] {e.claim}" for e in other[:per_aspect]]
        if self.records:
            lines.append("## 已采集记录")
            lines.append("；".join(f"{r['entity_name']}（{sum(v is not None for v in r['values'].values())}个字段有值）"
                                  for r in self.records[:30]))
        empty = [q for q, evs in groups.items() if not evs] if self.spec.mode != "dataset" else []
        return "\n".join(lines), empty

    async def _coverage_fn(self, c: TaskExecContext, wave: int = 1, max_waves: int = 1) -> StepResult:
        digest, empty = self._evidence_digest()
        review = await coordinator.review_coverage(self.spec, self.used_queries, digest, c,
                                                   sub_questions=self.sub_questions, empty_aspects=empty,
                                                   wave=wave, max_waves=max_waves)
        return StepResult(review.model_dump())

    async def _verify_fn(self, c: TaskExecContext) -> StepResult:
        evidence = list(self.findings)
        for r in self.records:
            for k, eid in r["evidence_ids"].items():
                evidence.append(EvidenceRef(evidence_id=eid, n=r["n"], claim=f"{r['entity_name']} {k}：{r['values'][k]}",
                                            quote="", aspect=k))
        if not evidence:
            return StepResult({"conflicts": [], "rejected": [], "conflicted": []})
        # 记录字段的摘录从数据库补齐
        from ..db.base import session_scope

        async with session_scope() as s:
            ids = [e.evidence_id for e in evidence if not e.quote]
            if ids:
                rows = (await s.execute(select(Evidence).where(Evidence.evidence_id.in_(ids)))).scalars().all()
                qmap = {r.evidence_id: r.quote_text for r in rows}
                for e in evidence:
                    if not e.quote:
                        e.quote = qmap.get(e.evidence_id, "")
        report = await verifier.cross_check(evidence, c)
        rejected = [evidence[i - 1].evidence_id for i in report.unsupported]
        conflicts = [{"evidence_ids": [evidence[i - 1].evidence_id for i in cf.evidence_nos],
                      "source_nos": sorted({evidence[i - 1].n for i in cf.evidence_nos}),
                      "description": cf.description} for cf in report.conflicts]
        conflicted = sorted({eid for cf in conflicts for eid in cf["evidence_ids"]} - set(rejected))
        all_ids = [e.evidence_id for e in evidence]

        async def persist(s: AsyncSession) -> None:
            rows = (await s.execute(select(Evidence).where(Evidence.evidence_id.in_(all_ids)))).scalars().all()
            for r in rows:
                r.verification_status = ("rejected" if r.evidence_id in rejected else
                                         "conflicted" if r.evidence_id in conflicted else "machine_checked")

        return StepResult({"conflicts": conflicts, "rejected": rejected, "conflicted": conflicted,
                           "notes": report.notes}, persist)

    async def _save_artifact(self, c: TaskExecContext, kind: str, name: str, mime: str, data: bytes,
                             record_qty: int | None = None) -> Artifact:
        aid = new_id("art")
        ref, h = await self.storage.put(f"artifacts/{c.task_id}/{aid}/{name}", data)
        return Artifact(artifact_id=aid, project_id=c.project_id, task_id=c.task_id, artifact_kind=kind,
                        display_name=name, mime_name=mime, storage_ref=ref, byte_qty=len(data), content_hash=h,
                        record_qty=record_qty, quality_status="machine_checked")

    async def _build_fn(self, c: TaskExecContext, verified: dict) -> StepResult:
        assert self.spec.dataset is not None
        ds = self.spec.dataset
        rejected = set(verified.get("rejected", []))
        groups: dict[str, list[dict]] = {}
        order: list[str] = []
        for r in self.records:
            k = _norm_entity(r["entity_name"])
            if not k:
                continue
            if k not in groups:
                groups[k] = []
                order.append(k)
            groups[k].append(r)
        rows = []
        for k in order[: ds.max_records]:
            recs = groups[k]
            values, missing, nos, conflicts = {}, {}, set(), {}
            for f in ds.fields:
                cands = [(r["values"].get(f.key), r["n"]) for r in recs
                         if r["values"].get(f.key) is not None and r["evidence_ids"].get(f.key) not in rejected]
                distinct = {str(v).strip() for v, _ in cands}
                if len(distinct) == 1:
                    values[f.key] = cands[0][0]
                    nos.update(n for _, n in cands)
                elif len(distinct) > 1:
                    values[f.key] = None
                    missing[f.key] = "source_conflict"
                    conflicts[f.key] = [{"value": v, "n": n} for v, n in cands]
                    nos.update(n for _, n in cands)
                else:
                    values[f.key] = None
                    reasons = [r["missing_reasons"].get(f.key) for r in recs if r["missing_reasons"].get(f.key)]
                    missing[f.key] = reasons[0] if reasons else "not_found"
            rows.append({"entity_name": recs[0]["entity_name"], "values": values, "missing_reasons": missing,
                         "source_nos": sorted(nos), "conflicts": conflicts})
        sources = [s.public() for s in sorted(self.sources.values(), key=lambda s: s.n)]
        self._built = (rows, sources)
        arts: list[Artifact] = []
        base = re.sub(r"[\\/:*?\"<>|\s]+", "_", self.spec.title)[:40] or "dataset"
        fmts = self.spec.output_formats or ["csv"]
        if "csv" in fmts:
            arts.append(await self._save_artifact(c, "dataset", f"{base}.csv", "text/csv",
                                                  exporters.render_csv(ds.fields, rows), len(rows)))
        if "xlsx" in fmts:
            arts.append(await self._save_artifact(
                c, "dataset", f"{base}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                exporters.render_xlsx(ds.fields, rows, sources, ds.entity), len(rows)))
        if "json" in fmts:
            arts.append(await self._save_artifact(c, "dataset", f"{base}.json", "application/json",
                                                  exporters.render_json(ds.fields, rows, sources), len(rows)))

        async def persist(s: AsyncSession) -> None:
            s.add_all(arts)

        # 数据文件作为一个成果、多种格式：Excel 为主（含字段字典/来源/分析），CSV、JSON 可选下载
        order = {"xlsx": 0, "csv": 1, "json": 2}
        ordered = sorted(arts, key=lambda a: order.get(a.display_name.rsplit(".", 1)[-1], 9))
        bundle = {"primary": ordered[0].artifact_id,
                  "formats": [{"format": a.display_name.rsplit(".", 1)[-1], "artifact_id": a.artifact_id,
                               "byte_qty": a.byte_qty} for a in ordered]} if ordered else None
        return StepResult({"rows": rows, "artifact_ids": [], "bundles": [bundle] if bundle else []}, persist)

    async def _analyze_fn(self, c: TaskExecContext, rows: list[dict]) -> StepResult:
        results = await analyst.analyze(self.spec, [r["values"] for r in rows], c)
        data = [r.model_dump() for r in results]
        arts: list[Artifact] = []
        xlsx = None
        built = getattr(self, "_built", None)
        if data and self.spec.dataset and built and "xlsx" in (self.spec.output_formats or ["xlsx"]):
            # 新版 Excel：在原数据基础上加“分析”表与原生图表（原文件保留，不覆盖）
            b_rows, b_sources = built
            base = re.sub(r"[\\/:*?\"<>|\s]+", "_", self.spec.title)[:40] or "dataset"
            a = await self._save_artifact(
                c, "dataset", f"{base}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                exporters.render_xlsx(self.spec.dataset.fields, b_rows, b_sources, self.spec.dataset.entity, data),
                len(b_rows))
            arts.append(a)
            xlsx = {"format": "xlsx", "artifact_id": a.artifact_id, "byte_qty": a.byte_qty}

        async def persist(s: AsyncSession) -> None:
            s.add_all(arts)

        return StepResult({"results": data, "artifact_ids": [], "xlsx": xlsx}, persist)

    def _writer_evidence(self, verified: dict, budget: int = 40000) -> tuple[str, dict[int, str], dict[int, str]]:
        """给撰写智能体的证据块：按来源分组，标注可信度与发布时间；超出预算时优先保留高可信来源，
        并让每个子问题至少有来源入选。返回 (证据块, 每来源全部摘录文本, 每来源代表摘录)。"""
        rejected = set(verified.get("rejected", []))
        conflicted = set(verified.get("conflicted", []))
        by_n: dict[int, list[EvidenceRef]] = {}
        for e in self.findings:
            if e.evidence_id not in rejected:
                by_n.setdefault(e.n, []).append(e)
        srcs = [s for s in sorted(self.sources.values(), key=lambda s: s.n) if by_n.get(s.n)]
        blocks: dict[int, str] = {}
        for src in srcs:
            pub = f"发布于 {src.publish_time_text}" if src.publish_time_text else "发布时间未知"
            lines = [f"[{src.n}] {src.title or ''}（{credibility.LABELS[src.credibility]}；{src.site_name or ''}；"
                     f"{pub}）{src.url}"]
            for e in by_n[src.n][:10]:
                flag = "【存在冲突】" if e.evidence_id in conflicted else ""
                aspect = f"〔{e.aspect}〕" if getattr(e, "aspect", None) else ""
                lines.append(f"- {flag}{aspect}{e.claim}：「{e.quote[:200]}」")
            blocks[src.n] = "\n".join(lines)
        chosen: list[int] = [s.n for s in srcs]
        if sum(len(b) for b in blocks.values()) > budget:
            ranked = sorted(srcs, key=lambda s: (-credibility.SCORES[s.credibility], -len(by_n[s.n]), s.n))
            chosen, used, covered = [], 0, set()
            # 先保证每个子问题至少一个来源，再按可信度填满预算
            for s in ranked:
                aspects = {self._aspect_of(getattr(e, "aspect", None)) for e in by_n[s.n]} - {None}
                if aspects - covered and used + len(blocks[s.n]) <= budget:
                    chosen.append(s.n)
                    used += len(blocks[s.n])
                    covered |= aspects
            for s in ranked:
                if s.n not in chosen and used + len(blocks[s.n]) <= budget:
                    chosen.append(s.n)
                    used += len(blocks[s.n])
            chosen.sort()
        evidence_text = {n: "\n".join(f"{e.claim} {e.quote}" for e in by_n[n]) for n in chosen}
        best_quote = {}
        for n in chosen:
            evs = sorted(by_n[n], key=lambda e: (e.evidence_id in conflicted, -len(e.quote)))
            best_quote[n] = evs[0].quote[:240] if evs else ""
        return "\n\n".join(blocks[n] for n in chosen), evidence_text, best_quote

    async def _write_fn(self, c: TaskExecContext, verified: dict, analysis: list[dict],
                        rows: list[dict]) -> StepResult:
        evidence_block, evidence_text, best_quote = self._writer_evidence(verified)
        analysis_block = ""
        if rows and self.spec.dataset:
            analysis_block = f"数据集：共 {len(rows)} 条记录（{self.spec.dataset.entity}）。\n"
        from ..agents.analyst import AnalysisResult

        analysis_block += "\n\n".join(AnalysisResult(**a).to_markdown() for a in analysis if a.get("columns"))
        conflicts_block = "\n".join(f"- 来源 {cf['source_nos']}：{cf['description']}"
                                    for cf in verified.get("conflicts", []))
        gaps = []
        if self.blocked or self.failed:
            gaps.append(f"{self.blocked} 个来源访问受限、{self.failed} 个读取失败，未纳入")
        gaps += [f"覆盖不足：{m}" for m in self.coverage_missing]
        gaps += [f"文件「{x['name']}」未能读取：{x['reason']}" for x in self.file_failures]
        is_answer = self.spec.mode == "quick_search"
        report = self.spec.report
        outline = (report.outline if report and report.outline else []) or list(self.sub_questions)
        draft, used, charts = await report_writer.write(
            kind="answer" if is_answer else "report",
            question=report.question if report else "；".join(self.spec.scope.questions) or self.spec.requirement_text,
            outline=outline, audience=report.audience if report else None,
            evidence_block=evidence_block, valid_ns=set(evidence_text) or {s.n for s in self.sources.values()},
            analysis_block=analysis_block, conflicts_block=conflicts_block, gaps_block="\n".join(gaps), ctx=c,
            today=utcnow().strftime("%Y-%m-%d"), evidence_by_n=evidence_text)
        title = draft.title or self.spec.title
        full_md = report_writer.assemble_markdown(draft, charts, include_title=True, with_highlights=True)
        if is_answer:
            chat_md = report_writer.assemble_markdown(draft, charts, include_title=False)
        else:
            # 报告：对话中展示摘要、要点与图表，完整报告见文件/右侧预览
            brief = draft.model_copy(update={"markdown": "", "limitations": []})
            chat_md = (f"### {title}\n\n" + report_writer.assemble_markdown(brief, charts, include_title=False)
                       + "\n完整报告（含正文、图表与参考来源）可在下方下载 Word / PDF，或点「查看完整报告」。")
        cited = [s.public() for s in sorted(self.sources.values(), key=lambda s: s.n) if s.n in used]
        bundle = await self._save_report_bundle(c, title, full_md, cited)
        citations = []
        for n in used:
            cit = self._citation(n)
            if cit:
                cit["quote"] = best_quote.get(n, "")
                citations.append(cit)

        async def persist(s: AsyncSession) -> None:
            s.add_all(bundle["rows"])

        return StepResult({"title": title, "markdown": chat_md, "used": used, "limitations": draft.limitations,
                           "citations": citations,
                           "highlights": [h.model_dump() for h in draft.highlights],
                           "follow_ups": draft.follow_ups,
                           "bundles": [bundle["part"]]}, persist)

    async def _save_report_bundle(self, c: TaskExecContext, title: str, markdown: str, sources: list[dict]) -> dict:
        """同一份报告生成 HTML / Word / PDF / Markdown 四种格式（PDF 需要浏览器，不可用时省略）。"""
        from . import report_render

        mode_label = {"quick_search": "搜索结果", "research": "研究报告", "hybrid": "数据分析报告"}.get(
            self.spec.mode, "报告")
        meta = (f"{mode_label} · 生成于 {utcnow().strftime('%Y-%m-%d %H:%M')} UTC · 引用来源 {len(sources)} 个 · "
                f"机器核验，未经人工审核")
        files = await report_render.build_report_bundle(title=title, markdown=markdown, sources=sources,
                                                        meta_line=meta)
        base = re.sub(r"[\\/:*?\"<>|\s]+", "_", title)[:60] or "report"
        mimes = {"html": "text/html", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                 "pdf": "application/pdf", "md": "text/markdown"}
        rows, formats = [], []
        for fmt in ("html", "docx", "pdf", "md"):
            if fmt in files:
                a = await self._save_artifact(c, "report", f"{base}.{fmt}", mimes[fmt], files[fmt])
                rows.append(a)
                formats.append({"format": fmt, "artifact_id": a.artifact_id, "byte_qty": a.byte_qty})
        return {"rows": rows, "part": {"primary": rows[0].artifact_id, "formats": formats}}


def task_stages_from_spec(spec: TaskSpec) -> list[str]:
    return coordinator.stages_for(spec.mode, has_analysis=bool(spec.dataset and spec.dataset.analysis_request),
                                  has_files=bool(spec.scope.file_ids), use_web=spec.scope.web_enabled())

