from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from knowledge_control_plane.api.generic_v1.models import (
    ExecutionScope,
    KnowledgeProfileCopyRequest,
    KnowledgeProfileCreateRequest,
    KnowledgeProfileDefinition,
    KnowledgeProfileListResponse,
    KnowledgeProfileOrigin,
    KnowledgeProfileResolutionResponse,
    KnowledgeProfileUpdateRequest,
    PageMeta,
)

from .configuration import ConfigurationService
from .errors import ResourceNotFound, RuntimeApiError
from .knowledge_contracts import discover_knowledge_contract_paths
from .knowledge_products import KnowledgeProductCatalogService
from .settings import RuntimeSettings
from .store import RuntimeStore


def _fingerprint(*, profile_id: str, name: str, execution_scope: ExecutionScope, description: str | None, knowledge_ids: list[str]) -> str:
    payload = {
        "profile_id": profile_id,
        "name": name,
        "execution_scope": execution_scope.value,
        "description": description or None,
        "knowledge_ids": list(knowledge_ids),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _platform_profile(**kwargs: Any) -> KnowledgeProfileDefinition:
    profile_id = str(kwargs["profile_id"])
    name = str(kwargs["name"])
    scope = kwargs["execution_scope"]
    description = kwargs.get("description")
    knowledge_ids = list(kwargs["knowledge_ids"])
    return KnowledgeProfileDefinition(
        **kwargs,
        origin=KnowledgeProfileOrigin.PLATFORM,
        fingerprint=_fingerprint(
            profile_id=profile_id,
            name=name,
            execution_scope=scope,
            description=description,
            knowledge_ids=knowledge_ids,
        ),
    )


_PLATFORM_PROFILES = (
    _platform_profile(
        profile_id="repository-inventory-v1", name="Технический паспорт репозитория", execution_scope=ExecutionScope.REPOSITORY,
        version="v1", source_path="builtin:knowledge-profile/repository-inventory/v1",
        description="Bounded repository inventory: identity, Bitbucket URL when registered, technologies, concepts, inputs/outputs, coverage, novelty and diagnostics.",
        knowledge_ids=["repository-inventory"],
    ),
    _platform_profile(
        profile_id="data-model-v1", name="Модель данных из кода", execution_scope=ExecutionScope.WORKSPACE,
        version="v1", source_path="builtin:knowledge-profile/data-model/v1",
        description="Переиспользуемая модель типов, полей, наследования и связей, объявленных в коде одного или нескольких репозиториев.",
        knowledge_ids=["code-declared-data-model"],
    ),
    _platform_profile(
        profile_id="effective-data-model-v1", name="Модель данных АС", execution_scope=ExecutionScope.WORKSPACE,
        version="v1", source_path="builtin:knowledge-profile/effective-data-model/v1",
        description="Составная модель данных АС: модель из кода, физическая модель таблиц/колонок/ключей/связей и доказанные логико-физические соответствия.",
        knowledge_ids=["effective-data-model"],
    ),
    _platform_profile(
        profile_id="reference-data-v1", name="Справочные данные / НСИ", execution_scope=ExecutionScope.WORKSPACE,
        version="v1", source_path="builtin:knowledge-profile/reference-data/v1",
        description="Переиспользуемый reference-data context, provenance, usage и gaps.", knowledge_ids=["reference-data"],
    ),
    _platform_profile(
        profile_id="foreign-data-persistence-v1", name="Хранение внешних данных / FDP", execution_scope=ExecutionScope.REPOSITORY,
        version="v1", source_path="builtin:knowledge-profile/foreign-data-persistence/v1",
        description="Технические пути source→storage и storage→access с provenance и gaps.", knowledge_ids=["persistence-lineage"],
    ),
    _platform_profile(
        profile_id="observed-storage-usage-v1", name="Наблюдаемое использование хранилищ", execution_scope=ExecutionScope.REPOSITORY,
        version="v1", source_path="builtin:knowledge-profile/observed-storage-usage/v1",
        description="Наблюдаемые чтения, записи и неразрешённые обращения к хранилищам.", knowledge_ids=["observed-storage-usage"],
    ),
    _platform_profile(
        profile_id="sql-source-inventory-v1", name="SQL Source Inventory", execution_scope=ExecutionScope.REPOSITORY,
        version="v1", source_path="builtin:knowledge-profile/sql-source-inventory/v1",
        description="SQL-источники, поля, роли, lineage и полнота анализа.", knowledge_ids=["sql-source-inventory"],
    ),
    _platform_profile(
        profile_id="s2t-reconstruction-v1", name="S2T из витрины и PDM", execution_scope=ExecutionScope.REPOSITORY,
        version="v1", source_path="builtin:knowledge-profile/s2t-reconstruction/v1",
        description="Source-to-target lineage SQL-витрины вместе с независимой физической моделью назначения.",
        knowledge_ids=["sql-source-inventory", "physical-data-model"],
    ),
    _platform_profile(
        profile_id="workspace-sql-catalog-v1", name="Workspace SQL Catalog", execution_scope=ExecutionScope.WORKSPACE,
        version="v1", source_path="builtin:knowledge-profile/workspace-sql-catalog/v1",
        description="Единый SQL-каталог из уже опубликованных repository SQL revisions.", knowledge_ids=["workspace-sql-source-inventory"],
    ),
    _platform_profile(
        profile_id="data-model-attribute-extension-v1", name="Расширение модели данных и витрины", execution_scope=ExecutionScope.WORKSPACE,
        version="v1", source_path="builtin:knowledge-profile/data-model-attribute-extension/v1",
        description="Технический контекст для добавления атрибутов: логическая модель, физическая модель, SQL-витрина, связи, ключи и наблюдаемые SQL anchors.",
        knowledge_ids=["data-model-attribute-extension"],
    ),
    _platform_profile(
        profile_id="system-description-v1", name="Описание системы", execution_scope=ExecutionScope.WORKSPACE,
        version="v1", source_path="builtin:knowledge-profile/system-description/v1",
        description="Техническое описание системы, coverage и gaps по выбранным репозиториям.", knowledge_ids=["system-description"],
    ),
    _platform_profile(
        profile_id="system-interactions-v1", name="Межсистемные взаимодействия", execution_scope=ExecutionScope.WORKSPACE,
        version="v1", source_path="builtin:knowledge-profile/system-interactions/v1",
        description="Boundary interactions, execution contexts, field contracts и доступный cross-repository attribute lineage.",
        knowledge_ids=["system-interactions", "interaction-field-contracts", "cross-repository-attribute-lineage"],
    ),
)


class KnowledgeProfileService:
    """Persistent Control-Plane registry for reusable knowledge composition.

    Product semantics and dependency resolution remain Runner-owned. Platform and user
    profiles use the same immutable knowledge_profile/v2 execution contract.
    """

    def __init__(self, *, store: RuntimeStore | None = None, products: KnowledgeProductCatalogService | None = None, configuration: ConfigurationService | None = None, settings: RuntimeSettings | None = None) -> None:
        self.store = store
        self.products = products
        self.configuration = configuration
        self.settings = settings
        self._platform = {item.profile_id: item for item in _PLATFORM_PROFILES}

    def all(self) -> list[KnowledgeProfileDefinition]:
        return [*self._platform.values(), *(self.store.list_knowledge_profiles() if self.store is not None else [])]

    def list(self, *, offset: int, limit: int, search: str | None = None, origin: KnowledgeProfileOrigin | None = None) -> KnowledgeProfileListResponse:
        items = self.all()
        if origin is not None:
            items = [item for item in items if item.origin is origin]
        if search:
            needle = search.casefold()
            items = [item for item in items if needle in item.profile_id.casefold() or needle in item.name.casefold() or needle in (item.description or "").casefold()]
        return KnowledgeProfileListResponse(items=items[offset:offset + limit], page=PageMeta(offset=offset, limit=limit, total=len(items)))

    def get(self, profile_id: str) -> KnowledgeProfileDefinition:
        profile = self._platform.get(profile_id) or (self.store.get_knowledge_profile(profile_id) if self.store is not None else None)
        if profile is None:
            raise ResourceNotFound("knowledge profile", profile_id)
        return profile

    def create(self, request: KnowledgeProfileCreateRequest) -> KnowledgeProfileDefinition:
        profile_id = request.profile_id or self._new_profile_id(request.name)
        if self.store is None or self.products is None:
            raise RuntimeError("persistent profile registry is not configured")
        if profile_id in self._platform or self.store.get_knowledge_profile(profile_id) is not None:
            raise RuntimeApiError(409, "knowledge_profile_exists", f"knowledge profile already exists: {profile_id}")
        self._validate_selectable(request.knowledge_ids, request.execution_scope)
        now = datetime.now(UTC)
        profile = KnowledgeProfileDefinition(
            profile_id=profile_id,
            name=request.name,
            execution_scope=request.execution_scope,
            origin=KnowledgeProfileOrigin.USER,
            version="v1",
            description=request.description,
            source_path=f"control-plane:knowledge-profile/{profile_id}",
            knowledge_ids=list(request.knowledge_ids),
            fingerprint=_fingerprint(profile_id=profile_id, name=request.name, execution_scope=request.execution_scope, description=request.description, knowledge_ids=list(request.knowledge_ids)),
            created_at=now,
            updated_at=now,
        )
        self.resolve_definition(profile)
        self.store.upsert_knowledge_profile(profile)
        return profile

    def update(self, profile_id: str, request: KnowledgeProfileUpdateRequest) -> KnowledgeProfileDefinition:
        if self.store is None or self.products is None:
            raise RuntimeError("persistent profile registry is not configured")
        current = self.get(profile_id)
        if current.origin is KnowledgeProfileOrigin.PLATFORM:
            raise RuntimeApiError(409, "platform_profile_read_only", "platform profiles are read-only; copy the profile first")
        if current.fingerprint != request.expected_fingerprint:
            raise RuntimeApiError(409, "knowledge_profile_changed", "knowledge profile changed since it was loaded", details={"current_fingerprint": current.fingerprint})
        scope = request.execution_scope or current.execution_scope
        ids = list(request.knowledge_ids if request.knowledge_ids is not None else current.knowledge_ids)
        name = request.name or current.name
        description = current.description if request.description is None else request.description
        self._validate_selectable(ids, scope)
        updated = current.model_copy(update={
            "name": name,
            "execution_scope": scope,
            "description": description,
            "knowledge_ids": ids,
            "updated_at": datetime.now(UTC),
            "fingerprint": _fingerprint(profile_id=profile_id, name=name, execution_scope=scope, description=description, knowledge_ids=ids),
        })
        self.resolve_definition(updated)
        self.store.upsert_knowledge_profile(updated)
        return updated

    def copy(self, profile_id: str, request: KnowledgeProfileCopyRequest) -> KnowledgeProfileDefinition:
        source = self.get(profile_id)
        return self.create(KnowledgeProfileCreateRequest(
            profile_id=request.profile_id,
            name=request.name or f"{source.name} — копия",
            execution_scope=source.execution_scope,
            description=source.description,
            knowledge_ids=list(source.knowledge_ids),
        ))

    def delete(self, profile_id: str) -> None:
        if self.store is None:
            raise RuntimeError("persistent profile registry is not configured")
        current = self.get(profile_id)
        if current.origin is KnowledgeProfileOrigin.PLATFORM:
            raise RuntimeApiError(409, "platform_profile_read_only", "platform profiles cannot be deleted")
        if not self.store.delete_knowledge_profile(profile_id):
            raise ResourceNotFound("knowledge profile", profile_id)

    def resolve(self, profile_id: str) -> KnowledgeProfileResolutionResponse:
        return self.resolve_definition(self.get(profile_id))

    def resolve_definition(self, profile: KnowledgeProfileDefinition) -> KnowledgeProfileResolutionResponse:
        payload = {
            "schema_version": "knowledge_profile/v2",
            "profile_id": profile.profile_id,
            "title": profile.name,
            "scope": {"kind": profile.execution_scope.value, "scope_id": "profile-preview"},
            "knowledge": [{"knowledge_id": knowledge_id} for knowledge_id in profile.knowledge_ids],
            "presentation": {"include_evidence": True, "include_coverage": True, "include_gaps": True, "include_technical_details": True},
        }
        if self.settings is None or self.configuration is None:
            raise RuntimeError("Runner profile resolver is not configured")
        root = self.settings.runtime_root / "profile-resolution"
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="resolve-", dir=root) as tmp:
            tmp_path = Path(tmp)
            profile_path = tmp_path / "knowledge-profile.json"
            output_path = tmp_path / "knowledge-profile-resolution.json"
            profile_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            command = [
                *self.configuration.command_parts("static_analysis_runner"),
                "knowledge-profile-resolve",
                "--knowledge-catalog", str(discover_knowledge_contract_paths().knowledge_catalog),
                "--profile", str(profile_path),
                "--output", str(output_path),
            ]
            completed = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
            if completed.returncode != 0 or not output_path.is_file():
                message = (completed.stderr or completed.stdout or "Runner profile resolution failed").strip()
                raise RuntimeApiError(422, "knowledge_profile_invalid", message, details={"profile_id": profile.profile_id})
            raw = json.loads(output_path.read_text(encoding="utf-8"))
        status = raw.get("status") if isinstance(raw.get("status"), dict) else {}
        selection = raw.get("resolved_selection") if isinstance(raw.get("resolved_selection"), dict) else {}
        technical = raw.get("technical_plan") if isinstance(raw.get("technical_plan"), dict) else {}
        requested = [str(item) for item in selection.get("requested_knowledge_ids") or []]
        resolved = [str(item) for item in selection.get("resolved_knowledge_ids") or []]
        implicit = [str(item) for item in selection.get("implicit_required_knowledge_ids") or []]
        required_sources = [item for item in technical.get("evidence_requirements") or [] if isinstance(item, dict)]
        planned_materializations = [item for item in technical.get("materializations") or [] if isinstance(item, dict)]
        knowledge_model_dependencies = [item for item in technical.get("knowledge_model_dependencies") or [] if isinstance(item, dict)]
        diagnostics = [item for item in raw.get("diagnostics") or [] if isinstance(item, dict)]
        nodes = [item for item in raw.get("knowledge_preview") or [] if isinstance(item, dict)]
        overall = str(status.get("overall") or "") or None
        return KnowledgeProfileResolutionResponse(
            profile_id=profile.profile_id,
            valid=overall not in {"invalid", "blocked", "error"},
            overall_status=overall,
            plan_fingerprint=str(raw.get("plan_fingerprint") or "") or None,
            requested_knowledge_ids=requested or list(profile.knowledge_ids),
            resolved_knowledge_ids=resolved,
            implicit_dependency_ids=implicit,
            required_sources=required_sources,
            planned_materializations=planned_materializations,
            knowledge_model_dependencies=knowledge_model_dependencies,
            knowledge_nodes=nodes,
            diagnostics=diagnostics,
            raw=raw,
        )

    def _validate_selectable(self, knowledge_ids: list[str], scope: ExecutionScope) -> None:
        for knowledge_id in knowledge_ids:
            if self.products is None:
                raise RuntimeError("knowledge product catalog is not configured")
            product = self.products.get(knowledge_id)
            if not product.profile_v2_selectable:
                raise RuntimeApiError(422, "knowledge_product_not_selectable", f"knowledge product is internal/non-selectable: {knowledge_id}")
            if scope not in product.supported_scopes:
                raise RuntimeApiError(422, "knowledge_product_scope_mismatch", f"knowledge product {knowledge_id} does not support {scope.value}")

    def _new_profile_id(self, name: str) -> str:
        base = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-") or "custom-profile"
        base = base[:100]
        candidate = base
        index = 2
        while candidate in self._platform or (self.store is not None and self.store.get_knowledge_profile(candidate) is not None):
            candidate = f"{base}-{index}"
            index += 1
        return candidate
