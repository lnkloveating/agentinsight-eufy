"""将外部搜索命中保存为候选线索，禁止越过 Source 和 Evidence 门禁。"""

from datetime import UTC, datetime
from hashlib import sha256
from urllib.parse import urlsplit
from uuid import uuid4

from app.application.events import ProjectEventBroker
from app.core.errors import AppError
from app.infrastructure.database.models import ProjectEventModel, SearchDiscoveryRunModel
from app.infrastructure.database.repositories import ProjectRepository
from app.infrastructure.database.search_discovery_repository import SearchDiscoveryRepository
from app.infrastructure.database.session import Database
from app.schemas.search_discovery import (
    SearchDiscoveryCandidate,
    SearchDiscoveryCreate,
    SearchDiscoveryEvidenceStatus,
    SearchDiscoveryRun,
    SearchDiscoveryRunPage,
    SearchDiscoveryRunStatus,
)
from app.sources.search_discovery import (
    SearchDiscoveryProviderCandidate,
    SearchDiscoveryProviderError,
    SearchDiscoveryProviderRequest,
    SearchDiscoveryRegistry,
)
from app.sources.validation import normalize_public_url


class SearchDiscoveryService:
    def __init__(
        self,
        database: Database,
        registry: SearchDiscoveryRegistry,
        event_broker: ProjectEventBroker,
        trace_id: str,
    ) -> None:
        self.database = database
        self.registry = registry
        self.event_broker = event_broker
        self.trace_id = trace_id

    async def create(
        self, project_id: str, payload: SearchDiscoveryCreate
    ) -> SearchDiscoveryRun:
        connector = self.registry.resolve(payload.provider_id)
        now = datetime.now(UTC)
        run = SearchDiscoveryRunModel(
            search_discovery_run_id=f"search_{uuid4().hex[:16]}",
            project_id=project_id,
            provider_id=payload.provider_id,
            status=SearchDiscoveryRunStatus.RUNNING,
            query=payload.query,
            intent=payload.intent,
            max_results=payload.max_results,
            include_domains_json=payload.include_domains,
            exclude_domains_json=payload.exclude_domains,
            candidates_json=[],
            result_count=0,
            provider_request_id=None,
            error_code=None,
            error_message=None,
            retryable=False,
            requested_by=payload.requested_by,
            purpose=payload.purpose,
            trace_id=self.trace_id,
            created_at=now,
            completed_at=None,
        )
        async with self.database.session() as session:
            project_repository = ProjectRepository(session)
            if await project_repository.get_project(project_id) is None:
                raise self._project_not_found(project_id)
            if connector is None:
                raise AppError(
                    code="SEARCH_PROVIDER_NOT_FOUND",
                    message="请求的搜索 Provider 未注册。",
                    status_code=422,
                    details={"provider_id": payload.provider_id},
                )
            if not connector.available:
                run.status = SearchDiscoveryRunStatus.BLOCKED
                run.error_code = connector.unavailable_reason or "SEARCH_PROVIDER_UNAVAILABLE"
                run.error_message = "搜索 Provider 未启用或缺少本地凭据。"
                run.completed_at = now
                await SearchDiscoveryRepository(session).add(run)
                await self._add_event(project_repository, run)
                await project_repository.commit()
                await self.event_broker.notify(project_id)
                return self._to_schema(run)
            await SearchDiscoveryRepository(session).add(run)
            await self._add_event(project_repository, run)
            await project_repository.commit()
        await self.event_broker.notify(project_id)

        request = SearchDiscoveryProviderRequest(
            query=payload.query,
            max_results=payload.max_results,
            include_domains=tuple(payload.include_domains),
            exclude_domains=tuple(payload.exclude_domains),
        )
        try:
            response = await connector.search(request)
        except SearchDiscoveryProviderError as exc:
            return await self._complete_with_error(project_id, run.search_discovery_run_id, exc)
        except Exception:
            return await self._complete_with_error(
                project_id,
                run.search_discovery_run_id,
                SearchDiscoveryProviderError(
                    "SEARCH_PROVIDER_INTERNAL_ERROR",
                    "搜索 Provider 出现未分类错误，未生成任何候选结果。",
                    blocked=False,
                    retryable=False,
                ),
            )

        candidates = self._normalize_candidates(
            run.search_discovery_run_id,
            response.candidates,
            include_domains=tuple(payload.include_domains),
            exclude_domains=tuple(payload.exclude_domains),
            max_results=payload.max_results,
        )
        async with self.database.session() as session:
            repository = SearchDiscoveryRepository(session)
            saved = await repository.get_by_project(project_id, run.search_discovery_run_id)
            if saved is None:
                raise AppError(
                    code="SEARCH_DISCOVERY_RUN_NOT_FOUND",
                    message="搜索发现运行记录不存在。",
                    status_code=404,
                    details={"search_discovery_run_id": run.search_discovery_run_id},
                )
            saved.status = SearchDiscoveryRunStatus.SUCCEEDED
            saved.candidates_json = [item.model_dump(mode="json") for item in candidates]
            saved.result_count = len(candidates)
            saved.provider_request_id = (
                response.provider_request_id[:160] if response.provider_request_id else None
            )
            saved.completed_at = datetime.now(UTC)
            project_repository = ProjectRepository(session)
            await self._add_event(project_repository, saved)
            await repository.commit()
        await self.event_broker.notify(project_id)
        return self._to_schema(saved)

    async def get(self, project_id: str, search_discovery_run_id: str) -> SearchDiscoveryRun:
        async with self.database.session() as session:
            if await ProjectRepository(session).get_project(project_id) is None:
                raise self._project_not_found(project_id)
            model = await SearchDiscoveryRepository(session).get_by_project(
                project_id, search_discovery_run_id
            )
        if model is None:
            raise AppError(
                code="SEARCH_DISCOVERY_RUN_NOT_FOUND",
                message="搜索发现运行记录不存在。",
                status_code=404,
                details={"search_discovery_run_id": search_discovery_run_id},
            )
        return self._to_schema(model)

    async def list_runs(self, project_id: str, *, limit: int) -> SearchDiscoveryRunPage:
        async with self.database.session() as session:
            if await ProjectRepository(session).get_project(project_id) is None:
                raise self._project_not_found(project_id)
            models, total = await SearchDiscoveryRepository(session).list_by_project(
                project_id, limit=limit
            )
        return SearchDiscoveryRunPage(
            items=[self._to_schema(model) for model in models],
            total=total,
        )

    async def _complete_with_error(
        self,
        project_id: str,
        search_discovery_run_id: str,
        error: SearchDiscoveryProviderError,
    ) -> SearchDiscoveryRun:
        async with self.database.session() as session:
            repository = SearchDiscoveryRepository(session)
            saved = await repository.get_by_project(project_id, search_discovery_run_id)
            if saved is None:
                raise AppError(
                    code="SEARCH_DISCOVERY_RUN_NOT_FOUND",
                    message="搜索发现运行记录不存在。",
                    status_code=404,
                    details={"search_discovery_run_id": search_discovery_run_id},
                )
            saved.status = (
                SearchDiscoveryRunStatus.BLOCKED
                if error.blocked
                else SearchDiscoveryRunStatus.FAILED
            )
            saved.error_code = error.code
            saved.error_message = error.message[:1_000]
            saved.retryable = error.retryable
            saved.completed_at = datetime.now(UTC)
            project_repository = ProjectRepository(session)
            await self._add_event(project_repository, saved)
            await repository.commit()
        await self.event_broker.notify(project_id)
        return self._to_schema(saved)

    @staticmethod
    def _normalize_candidates(
        search_discovery_run_id: str,
        candidates: tuple[SearchDiscoveryProviderCandidate, ...],
        *,
        include_domains: tuple[str, ...],
        exclude_domains: tuple[str, ...],
        max_results: int,
    ) -> list[SearchDiscoveryCandidate]:
        normalized: list[SearchDiscoveryCandidate] = []
        seen_urls: set[str] = set()
        for candidate in candidates:
            try:
                source_url = normalize_public_url(candidate.source_url)
            except AppError:
                continue
            domain = (urlsplit(source_url).hostname or "").lower()
            if not domain or source_url in seen_urls:
                continue
            if include_domains and not any(
                SearchDiscoveryService._domain_matches(domain, allowed)
                for allowed in include_domains
            ):
                continue
            if any(
                SearchDiscoveryService._domain_matches(domain, excluded)
                for excluded in exclude_domains
            ):
                continue
            title = " ".join(candidate.title.split())[:500]
            if not title:
                continue
            seen_urls.add(source_url)
            digest = sha256(f"{search_discovery_run_id}:{source_url}".encode()).hexdigest()
            normalized.append(
                SearchDiscoveryCandidate.model_validate(
                    {
                        "candidate_id": f"candidate_{digest[:16]}",
                        "rank": len(normalized) + 1,
                        "title": title,
                        "source_url": source_url,
                        "normalized_source_url": source_url,
                        "source_domain": domain,
                        "snippet": " ".join(candidate.snippet.split())[:2_000],
                        "score": candidate.score,
                        "evidence_status": SearchDiscoveryEvidenceStatus.CANDIDATE_ONLY,
                    }
                )
            )
            if len(normalized) >= max_results:
                break
        return normalized

    @staticmethod
    def _domain_matches(hostname: str, configured_domain: str) -> bool:
        return hostname == configured_domain or hostname.endswith(f".{configured_domain}")

    async def _add_event(
        self, project_repository: ProjectRepository, run: SearchDiscoveryRunModel
    ) -> None:
        await project_repository.add_event(
            ProjectEventModel(
                event_id=f"evt_{uuid4().hex[:16]}",
                project_id=run.project_id,
                sequence_number=0,
                event_type=f"search_discovery_{run.status}",
                data_json={
                    "search_discovery_run_id": run.search_discovery_run_id,
                    "provider_id": run.provider_id,
                    "intent": run.intent,
                    "status": run.status,
                    "result_count": run.result_count,
                    "error_code": run.error_code,
                    "retryable": run.retryable,
                },
                trace_id=self.trace_id,
                created_at=datetime.now(UTC),
            )
        )

    @staticmethod
    def _to_schema(model: SearchDiscoveryRunModel) -> SearchDiscoveryRun:
        return SearchDiscoveryRun.model_validate(
            {
                "search_discovery_run_id": model.search_discovery_run_id,
                "project_id": model.project_id,
                "provider_id": model.provider_id,
                "status": model.status,
                "query": model.query,
                "intent": model.intent,
                "max_results": model.max_results,
                "include_domains": model.include_domains_json,
                "exclude_domains": model.exclude_domains_json,
                "candidates": model.candidates_json,
                "result_count": model.result_count,
                "provider_request_id": model.provider_request_id,
                "error_code": model.error_code,
                "error_message": model.error_message,
                "retryable": model.retryable,
                "requested_by": model.requested_by,
                "purpose": model.purpose,
                "created_at": model.created_at,
                "completed_at": model.completed_at,
            }
        )

    @staticmethod
    def _project_not_found(project_id: str) -> AppError:
        return AppError(
            code="PROJECT_NOT_FOUND",
            message="研究项目不存在。",
            status_code=404,
            details={"project_id": project_id},
        )
