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
from urllib.parse import urlsplit

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents import analyst, coordinator, extractor, report_writer, search_planner, verifier
from ..agents.browser_researcher import read_source
from ..agents.coordinator import MAX_EXTRA_WAVES
from ..browser.pool import get_pool
from ..contracts import EvidenceRef, SearchHit, SearchQuery, SourceDoc, TaskSpec
from ..core.config import get_settings
from ..core.ids import iso, new_id, sha256_bytes, utcnow
from ..core.storage import get_storage
from ..db.models import Artifact, Evidence, SourceCandidate, SourceRevision
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

    def public(self) -> dict[str, Any]:
        return {"n": self.n, "source_revision_id": self.source_revision_id, "url": self.url, "title": self.title,
                "site_name": self.site_name, "publish_time_text": self.publish_time_text,
                "retrieved_time": self.retrieved_time, "access_method": self.access_method}


@dataclass
class PipelineOutcome:
    parts: list[dict] = field(default_factory=list)
    artifact_ids: list[str] = field(default_factory=list)
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
        self.findings: list[EvidenceRef] = []
        self.records: list[dict] = []
        self.blocked = 0
        self.failed = 0
        self.blocked_engines: set[str] = set()
        self.coverage_missing: list[str] = []
        self._next_n = 1
        self._llm_sem = asyncio.Semaphore(LLM_CONCURRENCY)
        self.storage = get_storage()

    # ------------------------------------------------------------ 进度
    async def _stage(self, stage: str, status: str = "running", **inc: int) -> None:
        await update_progress(self.ctx.task_id, stage=stage, stage_status=status, inc=inc or None)

    async def _inc(self, **inc: int) -> None:
        await update_progress(self.ctx.task_id, inc=inc)

    # ------------------------------------------------------------ 主流程
    async def run(self) -> PipelineOutcome:
        await self._init_next_n()
        await self._stage("plan")
        planned = await self.ctx.step("plan", self._plan_fn, agent_role="search_planner",
                                      input_json={"limits": self.spec.limits.model_dump()})
        self.intent = planned.get("intent") or self.spec.requirement_text
        self.preferred_sources = planned.get("preferred_sources", [])
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
                await self._stage("coverage")
                extra: list[str] = []
                if self.sources and MAX_EXTRA_WAVES > 0:
                    review = await self.ctx.step("coverage:w1", self._coverage_fn, agent_role="coordinator")
                    extra = review["extra_queries"]
                    self.coverage_missing = review.get("missing_aspects", [])
                if extra:
                    await self._inc(queries=len(extra))
                    extra_limit = min(4, max(2, self.spec.limits.max_sources // 2))
                    await self._wave(2, [self._as_query(q) for q in extra], extra_limit, get_sessions,
                                     settings.task_read_concurrency)
                await self._stage("coverage", "done" if extra else "skipped")
        await update_progress(self.ctx.task_id, browser_available=True)  # 会话已关闭，保留最后帧供查看

        outcome = PipelineOutcome(technical_failures=self.failed)
        if not self.sources:
            for st in self.stages[self.stages.index("verify"):]:
                await self._stage(st, "skipped")
            outcome.error_code = "no_sources"
            engines = f"（被拦截的搜索引擎：{', '.join(sorted(self.blocked_engines))}）" if self.blocked_engines else ""
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
            outcome.artifact_ids += built["artifact_ids"]
            await self._stage("build", "done")
        if "analyze" in self.stages:
            await self._stage("analyze")
            res = await self.ctx.step("analyze", lambda c: self._analyze_fn(c, rows), agent_role="analyst")
            analysis = res["results"]
            outcome.artifact_ids += res.get("artifact_ids", [])
            await self._stage("analyze", "done")
        if "write" in self.stages:
            await self._stage("write")
            written = await self.ctx.step("write", lambda c: self._write_fn(c, verified, analysis, rows),
                                          agent_role="report_writer")
            outcome.artifact_ids += written.get("artifact_ids", [])
            await self._stage("write", "done")
            used = written["used"]
            outcome.parts.append({
                "type": "text", "part_id": f"answer-{self.ctx.task_id}", "text": written["markdown"],
                "citations": [self._citation(n) for n in used if self._citation(n)]})
        else:
            outcome.parts.append({"type": "text", "part_id": f"answer-{self.ctx.task_id}",
                                  "text": self._dataset_summary(rows), "citations": []})
        outcome.parts.append({"type": "source", "part_id": f"sources-{self.ctx.task_id}", "task_id": self.ctx.task_id,
                              "sources": [s.public() for s in sorted(self.sources.values(), key=lambda s: s.n)]})
        outcome.delivered = True
        return outcome

    def _citation(self, n: int) -> dict | None:
        for s in self.sources.values():
            if s.n == n:
                return {"n": n, "source_revision_id": s.source_revision_id, "url": s.url, "title": s.title}
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
        self.read_urls.add(normalize_url(out["final_url"] or out["url"]))
        self.sources[out["source_revision_id"]] = SourceInfo(
            n=out["n"], source_revision_id=out["source_revision_id"], url=out["final_url"] or out["url"],
            title=out.get("title"), site_name=out.get("site_name"), publish_time_text=out.get("publish_time_text"),
            retrieved_time=out["retrieved_time"], access_method=out["access_method"], content_ref=out["content_ref"])

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
                           "preferred_sources": plan.preferred_sources,
                           "queries": [q.model_dump() for q in plan.queries]})

    async def _search_fn(self, c: TaskExecContext, sess, queries: list[SearchQuery], *, refine: bool) -> StepResult:
        report = await browser_search(sess, queries, exclude_domains=self.spec.scope.exclude_domains,
                                      before_each=c.check)
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
                                             before_each=c.check)
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
            ranked.sort(key=lambda h: 0 if any((urlsplit(h.url).hostname or "").endswith(d) for d in pref) else 1)
            by_url = {h["url"]: h for h in hits}
            return [by_url[h.url] for h in ranked[:limit]]

        if len(hits) <= limit:
            return fallback()

        async def select_fn(c: TaskExecContext) -> StepResult:
            picked = await search_planner.select_candidates(self.spec, self.intent, objs, limit, c)
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
        r = await read_source(sess, url, goal=goal, ctx=c)
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
                                                text=text), self.spec, c)
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

    async def _coverage_fn(self, c: TaskExecContext) -> StepResult:
        digest = "\n".join(f"[{e.n}] {e.claim}" for e in self.findings[:60])
        if self.records:
            digest += "\n记录：" + "；".join(
                f"{r['entity_name']}（{sum(v is not None for v in r['values'].values())}个字段有值）"
                for r in self.records[:30])
        review = await coordinator.review_coverage(self.spec, self.used_queries, digest, c)
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

        return StepResult({"rows": rows, "artifact_ids": [a.artifact_id for a in arts]}, persist)

    async def _analyze_fn(self, c: TaskExecContext, rows: list[dict]) -> StepResult:
        results = await analyst.analyze(self.spec, [r["values"] for r in rows], c)
        data = [r.model_dump() for r in results]
        arts: list[Artifact] = []
        if "write" not in self.stages and data:
            md = "# 数据分析\n\n" + "\n\n".join(r.to_markdown() for r in results)
            arts.append(await self._save_artifact(c, "report", "数据分析.md", "text/markdown", md.encode("utf-8")))

        async def persist(s: AsyncSession) -> None:
            s.add_all(arts)

        return StepResult({"results": data, "artifact_ids": [a.artifact_id for a in arts]}, persist)

    async def _write_fn(self, c: TaskExecContext, verified: dict, analysis: list[dict],
                        rows: list[dict]) -> StepResult:
        rejected = set(verified.get("rejected", []))
        conflicted = set(verified.get("conflicted", []))
        by_n: dict[int, list[EvidenceRef]] = {}
        for e in self.findings:
            if e.evidence_id not in rejected:
                by_n.setdefault(e.n, []).append(e)
        blocks = []
        for src in sorted(self.sources.values(), key=lambda s: s.n):
            evs = by_n.get(src.n, [])
            if not evs:
                continue
            pub = f"，页面声明发布时间 {src.publish_time_text}" if src.publish_time_text else "，发布时间未知"
            lines = [f"[{src.n}] {src.title or ''}（{src.site_name or ''}{pub}）{src.url}"]
            for e in evs[:10]:
                flag = "【存在冲突】" if e.evidence_id in conflicted else ""
                lines.append(f"- {flag}{e.claim}：「{e.quote[:200]}」")
            blocks.append("\n".join(lines))
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
        is_answer = self.spec.mode == "quick_search"
        report = self.spec.report
        draft, used = await report_writer.write(
            kind="answer" if is_answer else "report",
            question=report.question if report else "；".join(self.spec.scope.questions) or self.spec.requirement_text,
            outline=report.outline if report else [], audience=report.audience if report else None,
            evidence_block="\n\n".join(blocks), valid_ns={s.n for s in self.sources.values()},
            analysis_block=analysis_block, conflicts_block=conflicts_block, gaps_block="\n".join(gaps), ctx=c)
        markdown = draft.markdown
        if draft.limitations and is_answer:
            markdown += "\n\n> 说明：" + "；".join(draft.limitations)
        arts: list[Artifact] = []
        if not is_answer:
            cited = [s.public() for s in sorted(self.sources.values(), key=lambda s: s.n) if s.n in used]
            doc = markdown
            if draft.limitations and "局限" not in doc:
                doc += "\n\n## 局限与缺口\n\n" + "\n".join(f"- {x}" for x in draft.limitations)
            doc += "\n\n" + exporters.render_sources_md(cited)
            doc += f"\n\n---\n*由云搜浏览器生成；机器核验（machine_checked），未经人工审核。生成时间 {iso(utcnow())}*\n"
            name = re.sub(r"[\\/:*?\"<>|\s]+", "_", draft.title or self.spec.title)[:60] + ".md"
            arts.append(await self._save_artifact(c, "report", name, "text/markdown", doc.encode("utf-8")))

        async def persist(s: AsyncSession) -> None:
            s.add_all(arts)

        return StepResult({"title": draft.title, "markdown": markdown, "used": used,
                           "limitations": draft.limitations, "artifact_ids": [a.artifact_id for a in arts]}, persist)


def task_stages_from_spec(spec: TaskSpec) -> list[str]:
    return coordinator.stages_for(spec.mode, has_analysis=bool(spec.dataset and spec.dataset.analysis_request))

