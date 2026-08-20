from __future__ import annotations
import base64, hashlib, json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping
try:
    import duckdb
except ModuleNotFoundError:
    duckdb = None
from .database import connect_database
from .evidence_layout import CONFIGURATION_FACT_TYPES
from .io import read_json
from .normalization import normalize_db_identifier, stable_id

class KnowledgeLayerQuery:

    @classmethod
    def from_database(
        cls,
        database: str | Path,
        *,
        manifest: str | Path | Mapping[str, Any] | None = None,
    ) -> "KnowledgeLayerQuery":
        """Open an explicitly identified DuckDB artifact independent of filename.

        AISL physical locators are content-addressed and therefore must not rely
        on producer filenames or suffixes. Manifest metadata is accepted as a
        separate published artifact so declared capabilities remain available
        without coupling database identity to its physical filename/location.
        The ordinary constructor retains existing producer-side discovery.
        """
        instance = cls.__new__(cls)
        root = Path(database).resolve()
        if not root.is_file():
            raise ValueError(f"knowledge-layer database not found: {root}")
        instance.artifact_root = root.parent
        if manifest is None:
            instance._manifest_payload = {}
        elif isinstance(manifest, Mapping):
            instance._manifest_payload = dict(manifest)
        else:
            manifest_path = Path(manifest).resolve()
            if not manifest_path.is_file():
                raise ValueError(f"knowledge-layer manifest not found: {manifest_path}")
            payload = read_json(manifest_path, {})
            if not isinstance(payload, dict):
                raise ValueError(f"knowledge-layer manifest must be a JSON object: {manifest_path}")
            instance._manifest_payload = dict(payload)
        instance.database_path = root
        with instance._connect() as connection:
            instance._relations = {str(row[0]) for row in connection.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='main'\n                   UNION SELECT view_name FROM duckdb_views() WHERE schema_name='main'").fetchall()}
        return instance

    def __init__(self, artifact: str | Path) -> None:
        root = Path(artifact).resolve()
        is_database_file = root.is_file() and root.suffix.lower() in {'.duckdb', '.db'}
        self.artifact_root = root.parent if root.is_file() else root
        if root.is_file() and not is_database_file:
            payload = read_json(root, {})
            self._manifest_payload = dict(payload) if isinstance(payload, dict) else {}
        else:
            self._manifest_payload = self._load_manifest_payload(self.artifact_root)
        if is_database_file:
            database_path = root
        else:
            database_path = self._database_from_manifest(self.artifact_root, self._manifest_payload)
            if database_path is None:
                candidates = (self.artifact_root / 'knowledge-layer.duckdb', self.artifact_root / 'workspace.duckdb')
                database_path = next((candidate for candidate in candidates if candidate.is_file()), candidates[0])
        self.database_path = database_path
        if not self.database_path.is_file():
            raise ValueError(f"knowledge-layer database not found; expected a DuckDB file or one of {self.artifact_root / 'knowledge-layer.duckdb'} and {self.artifact_root / 'workspace.duckdb'}")
        with self._connect() as connection:
            self._relations = {str(row[0]) for row in connection.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='main'\n                   UNION SELECT view_name FROM duckdb_views() WHERE schema_name='main'").fetchall()}

    @staticmethod
    def _database_from_manifest(root: Path, payload: Mapping[str, Any] | None=None) -> Path | None:
        manifest = dict(payload or {})
        if not manifest:
            manifest = KnowledgeLayerQuery._load_manifest_payload(root)
        raw = str(manifest.get('database_path') or (manifest.get('artifacts') or {}).get('database') or '').strip()
        if not raw:
            return None
        candidate = Path(raw)
        return candidate if candidate.is_absolute() else (root / candidate).resolve()

    def _has_relation(self, relation_name: str) -> bool:
        return relation_name in self._relations

    @staticmethod
    def _load_manifest_payload(root: Path) -> dict[str, Any]:
        for name in ('knowledge-layer-manifest.json', 'workspace_data_model_manifest.json'):
            path = root / name
            if not path.is_file():
                continue
            payload = read_json(path, {})
            if isinstance(payload, dict):
                return dict(payload)
        return {}

    def manifest(self) -> dict[str, Any]:
        if self._manifest_payload:
            return dict(self._manifest_payload)
        repository_count = 0
        scope_id = self.artifact_root.name
        with self._connect() as con:
            if self._has_relation('workspace_repository'):
                repository_count = int(con.execute('SELECT count(*) FROM workspace_repository').fetchone()[0])
            elif self._has_relation('sql_analysis_repository'):
                repository_count = int(con.execute('SELECT count(*) FROM sql_analysis_repository').fetchone()[0])
            if self._has_relation('workspace_build'):
                row = con.execute('SELECT workspace_id FROM workspace_build ORDER BY started_at DESC LIMIT 1').fetchone()
            elif self._has_relation('sql_analysis_build'):
                row = con.execute('SELECT scope_id FROM sql_analysis_build ORDER BY started_at DESC LIMIT 1').fetchone()
            else:
                row = None
            if row and row[0]:
                scope_id = str(row[0])
        return {'schema_version': 'knowledge_layer/inferred-v1', 'artifact_id': 'knowledge-layer', 'scope_id': scope_id, 'scope_type': 'repository' if repository_count == 1 else 'workspace', 'repository_count': repository_count, 'database_path': self.database_path.name, 'capabilities': list(self.capabilities()), 'inferred': True}

    def analysis_coverage(self, *, max_limitations: int = 100) -> dict[str, Any]:
        from .analysis_coverage import build_analysis_coverage

        return build_analysis_coverage(self, max_limitations=max_limitations)

    def relation_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._relations))

    def capabilities(self) -> tuple[str, ...]:
        # Published manifest capabilities and read capabilities that are
        # structurally available in the immutable DuckDB are additive. This
        # preserves the pre-AISL runtime behavior after database+manifest bytes
        # are relocated independently into content-addressed storage.
        declared = tuple(
            str(item) for item in (self._manifest_payload.get('capabilities') or ())
            if str(item).strip()
        )
        capabilities: list[str] = list(declared)
        if self._has_relation('data_model_entity'):
            capabilities.append('common.data-model')
        if self._has_relation('effective_entity_field') and self._has_relation('effective_entity_association'):
            capabilities.append('common.effective-model')
        if self._has_relation('db_schema_table'):
            capabilities.append('common.physical-model')
        if self._has_relation('physical_model_table'):
            capabilities.extend((
                'common.physical-model', 'common.physical-model.pdm', 'common.physical-model.query',
                'common.physical-model.tables', 'common.physical-model.columns',
                'common.physical-model.keys', 'common.physical-model.relationships',
                'common.physical-model.gaps',
            ))
        if all(self._has_relation(name) for name in (
            'code_declared_type', 'code_declared_field', 'code_declared_effective_field',
            'code_declared_relationship'
        )):
            capabilities.extend((
                'common.code-declared-data-model',
                'common.code-declared-entities',
                'common.code-declared-fields',
                'common.code-declared-inheritance',
                'common.code-declared-relationships',
            ))
        if self._has_relation('sql_relation') and self._has_relation('sql_column_usage'):
            capabilities.append('common.sql-analysis')
            capabilities.append('common.sql-relation-fields')
            capabilities.append('common.sql-source-inventory-export')
        if self._has_relation('sql_relation_semantic_role'):
            capabilities.append('common.sql-relation-semantic-roles')
        if self._has_relation('sql_recursive_column_lineage'):
            capabilities.append('common.sql-target-column-lineage')
        if self._has_relation('sql_target_value_source_mapping'):
            capabilities.extend(('common.sql-target-source-mapping','common.sql-target-value-source-mapping'))
        if self._has_relation('sql_workflow_binding'):
            capabilities.append('common.sql-workflow-bindings')
        if self._has_relation('sql_placeholder_binding_resolution'):
            capabilities.append('common.sql-workflow-context')
        if all(self._has_relation(name) for name in (
            'sql_workflow_binding', 'sql_workflow_context_file', 'sql_relation', 'sql_write_target'
        )):
            capabilities.append('common.sql-target-resolution')
        if all(self._has_relation(name) for name in (
            'sql_workflow_binding', 'sql_workflow_context_file', 'sql_relation',
            'sql_column_usage', 'sql_statement'
        )):
            capabilities.append('common.sql-attribute-insertion-context')
        if all(self._has_relation(name) for name in (
            'repository_inventory_identity', 'repository_inventory_file',
            'repository_inventory_structural_family', 'repository_inventory_completeness'
        )):
            capabilities.extend((
                'common.repository-inventory', 'common.repository-identity',
                'common.repository-technologies', 'common.repository-interfaces',
                'common.repository-inputs-outputs', 'common.repository-data-footprint',
                'common.repository-storage-footprint', 'common.repository-coverage',
                'common.repository-structural-families', 'common.repository-unknown-primitives',
                'common.repository-discovery', 'common.repository-coverage-gaps',
            ))
            if self._has_relation('repository_inventory_source_occurrence') and self._has_relation('repository_inventory_object_occurrence'):
                capabilities.append('common.repository-source-occurrences')
        if self._has_relation('source_observation'):
            capabilities.append('common.source-observations')
        if self._has_relation('build_module') and self._has_relation('build_dependency'):
            with self._connect() as con:
                row = con.execute(
                    "SELECT (SELECT count(*) FROM build_module) + (SELECT count(*) FROM build_dependency)"
                ).fetchone()
            if row and int(row[0] or 0) > 0:
                capabilities.append('common.build-dependencies')
        if self._has_relation('table_key_observation'):
            capabilities.append('common.keys')
        if self._has_relation('table_relationship_observation'):
            capabilities.append('common.relationships')
        if self._has_relation('type_reference_resolution_candidate') or self._has_relation('data_model_correspondence_observation'):
            capabilities.append('workspace.cross-repository')
        if self._has_relation('repository_interaction_boundary'):
            with self._connect() as con:
                row = con.execute('SELECT count(*) FROM repository_interaction_boundary').fetchone()
            if row and int(row[0] or 0) > 0:
                capabilities.append('workspace.repository-interaction-boundaries')
        if self._has_relation('system_boundary_interaction'):
            with self._connect() as con:
                row = con.execute('SELECT count(*) FROM system_boundary_interaction').fetchone()
            if row and int(row[0] or 0) > 0:
                capabilities.append('workspace.system-interactions')
        if self._has_relation('repository_interaction_island'):
            with self._connect() as con:
                row = con.execute('SELECT count(*) FROM repository_interaction_island').fetchone()
            if row and int(row[0] or 0) > 0:
                capabilities.append('workspace.repository-interaction-islands')
        if self._has_relation('system_interaction_field_contract'):
            with self._connect() as con:
                row = con.execute('SELECT count(*) FROM system_interaction_field_contract').fetchone()
            if row and int(row[0] or 0) > 0:
                capabilities.append('workspace.system-interaction-field-contracts')
        if self._has_relation('repository_value_node'):
            with self._connect() as con:
                row = con.execute('SELECT count(*) FROM repository_value_node').fetchone()
            if row and int(row[0] or 0) > 0:
                capabilities.append('workspace.repository-value-flow')
                capabilities.append('workspace.attribute-path-resolver')
        if self._has_relation('model_relationship_observation') or self._has_relation('v_tsa_reference_operations'):
            capabilities.append('framework.tsa')
        return tuple(dict.fromkeys(capabilities))

    def capability_status(self, capability: str) -> dict[str, Any]:
        available = capability in self.capabilities()
        return {'capability': capability, 'available': available, 'capabilities': list(self.capabilities())}

    def get_overview(self) -> dict[str, Any]:
        return self.overview()

    def list_entities(self, **kwargs: Any) -> dict[str, Any]:
        result = self.entities(**kwargs)
        result['kind'] = 'knowledge-layer-entities'
        return result

    def get_entity(self, entity_id: str) -> dict[str, Any]:
        result = self.entity_detail(entity_id)
        result['kind'] = 'knowledge-layer-entity-detail'
        return result

    def list_effective_fields(self, **kwargs: Any) -> dict[str, Any]:
        result = self.effective_entity_fields(**kwargs)
        result['kind'] = 'knowledge-layer-effective-fields'
        return result

    def list_effective_associations(self, **kwargs: Any) -> dict[str, Any]:
        result = self.effective_entity_associations(**kwargs)
        result['kind'] = 'knowledge-layer-effective-associations'
        return result

    def list_tables(self, **kwargs: Any) -> dict[str, Any]:
        result = self.db_schema_tables(**kwargs)
        result['kind'] = 'knowledge-layer-tables'
        return result

    def get_table(self, table_id: str) -> dict[str, Any]:
        result = self.db_schema_table_detail(table_id)
        result['kind'] = 'knowledge-layer-table-detail'
        return result

    def list_keys(self, **kwargs: Any) -> dict[str, Any]:
        result = self.table_key_observations(**kwargs)
        result['kind'] = 'knowledge-layer-keys'
        return result

    def list_relationships(self, **kwargs: Any) -> dict[str, Any]:
        result = self.observed_table_relationships(**kwargs)
        result['kind'] = 'knowledge-layer-relationships'
        return result

    def get_type_neighborhood(self, type_id: str, max_results: int=50) -> dict[str, Any]:
        return self.type_neighborhood(type_id, max_results=max_results)

    def resolve_attribute_paths(
        self,
        source: str,
        *,
        target: str | None = None,
        selected_repo_ids: list[str] | tuple[str, ...] | str,
        max_hops: int = 20,
        max_paths: int = 20,
        max_branching: int = 20,
        allowed_edge_kinds: list[str] | tuple[str, ...] | str | None = None,
        minimum_confidence: str = "probable",
        knowledge_view: str = "working",
    ) -> dict[str, Any]:
        from .attribute_paths import resolve_attribute_paths

        return resolve_attribute_paths(
            self,
            source,
            target=target,
            selected_repo_ids=selected_repo_ids,
            max_hops=max_hops,
            max_paths=max_paths,
            max_branching=max_branching,
            allowed_edge_kinds=allowed_edge_kinds,
            minimum_confidence=minimum_confidence,
            knowledge_view=knowledge_view,
        )

    def search_source_observations(self, **kwargs: Any) -> dict[str, Any]:
        result = self.source_observations(**kwargs)
        result['kind'] = 'knowledge-layer-source-observations'
        return result

    def list_gaps(self, **kwargs: Any) -> dict[str, Any]:
        result = self.missing_facts(**kwargs)
        result['kind'] = 'knowledge-layer-gaps'
        return result

    @staticmethod
    def _normalize_sql_evidence_limit(max_evidence_per_role: int) -> int:
        if isinstance(max_evidence_per_role, bool) or not isinstance(max_evidence_per_role, int):
            raise ValueError('max_evidence_per_role must be an integer')
        if max_evidence_per_role < 1:
            raise ValueError('max_evidence_per_role must be at least 1')
        return min(max_evidence_per_role, 20)

    @staticmethod
    def _summarize_sql_evidence(
        rows: list[dict[str, Any]],
        *,
        evidence_id_field: str,
        max_evidence_per_role: int,
    ) -> dict[str, Any]:
        """Build deterministic bounded evidence samples grouped by usage role."""
        unique: dict[tuple[Any, ...], dict[str, Any]] = {}
        for row in rows:
            file_value = str(row.get('file') or '').strip()
            if not file_value:
                continue
            role = str(row.get('usage_role') or 'unknown').strip() or 'unknown'
            evidence_id = str(row.get(evidence_id_field) or '').strip()
            line_start = row.get('line_start')
            query_id = str(row.get('query_id') or '').strip()
            scope_id = str(row.get('scope_id') or '').strip()
            key = (evidence_id, role, file_value, line_start, query_id, scope_id)
            unique[key] = {
                'evidence_id': evidence_id or None,
                'file': file_value,
                'line_start': line_start,
                'usage_role': role,
                'query_id': query_id or None,
                'scope_id': scope_id or None,
            }
        ordered = sorted(
            unique.values(),
            key=lambda item: (
                str(item.get('usage_role') or ''),
                str(item.get('file') or ''),
                int(item.get('line_start') or 0),
                str(item.get('query_id') or ''),
                str(item.get('scope_id') or ''),
                str(item.get('evidence_id') or ''),
            ),
        )
        counts_by_role: dict[str, int] = {}
        samples: list[dict[str, Any]] = []
        sampled_by_role: dict[str, int] = {}
        for item in ordered:
            role = str(item['usage_role'])
            counts_by_role[role] = counts_by_role.get(role, 0) + 1
            already = sampled_by_role.get(role, 0)
            if already < max_evidence_per_role:
                samples.append(item)
                sampled_by_role[role] = already + 1
        return {
            'evidence_count': len(ordered),
            'evidence_count_by_role': dict(sorted(counts_by_role.items())),
            'evidence_refs': samples,
            'evidence_truncated': len(samples) < len(ordered),
        }

    def list_sql_relations(
        self,
        *,
        repo_id: str | None = None,
        relation_kind: str | None = None,
        usage_role: str | None = None,
        view: str = 'business_sources',
        token: str = '',
        include_fields: bool = True,
        max_evidence_per_role: int = 3,
        max_results: int = 100,
        page_token: str = '',
    ) -> dict[str, Any]:
        """Return logical SQL relations with actually used fields and bounded evidence.

        Relations are grouped by repository, relation kind and template identity so repeated
        aliases/scopes do not create duplicate API objects. Fields are sourced only from
        ``sql_column_usage`` rows that point to a concrete scoped relation occurrence.
        Evidence samples are deterministic and bounded independently for every usage role;
        aggregate counts preserve the total number of available occurrences.
        """
        evidence_limit = self._normalize_sql_evidence_limit(max_evidence_per_role)
        filters = {
            'repo_id': repo_id,
            'relation_kind': relation_kind,
            'usage_role': usage_role,
            'view': view,
            'token': token,
            'include_fields': bool(include_fields),
            'max_evidence_per_role': evidence_limit,
        }
        query_id = 'sql_relations'
        if view not in {'business_sources', 'technical', 'all'}:
            raise ValueError("view must be one of: business_sources, technical, all")
        if (not self._has_relation('sql_relation') or not self._has_relation('sql_column_usage')
                or not self._has_relation('sql_relation_semantic_role')):
            return self._empty_page(
                kind='knowledge-layer-sql-relations', query_id=query_id, filters=filters,
                max_results=max_results, page_token=page_token,
            )
        clauses = ['1=1']
        args: list[Any] = []
        if repo_id:
            clauses.append('r.repo_id=?')
            args.append(repo_id)
        if relation_kind:
            clauses.append('r.relation_kind=?')
            args.append(relation_kind)
        if usage_role:
            clauses.append('r.usage_role=?')
            args.append(usage_role)
        if view == 'business_sources':
            clauses.append('sr.hidden_by_default=false')
        elif view == 'technical':
            clauses.append('sr.hidden_by_default=true')
        if token:
            clauses.append(
                "lower(coalesce(r.template_name,'') || ' ' || coalesce(r.relation_name,'') || ' ' || "
                "coalesce(r.logical_name,'') || ' ' || coalesce(r.alias,'')) LIKE ?"
            )
            args.append(f'%{token.lower()}%')
        where = ' AND '.join(clauses)
        group_key = "coalesce(nullif(r.template_name,''), r.relation_name)"
        page_size = self._normalize_page_size(max_results)
        offset = self._decode_page_token(page_token, query_id=query_id, filters=filters)
        group_sql = f"""
            SELECT r.repo_id, r.relation_kind, {group_key} AS relation_identity,
                   min(r.template_name) AS template_name,
                   min(r.logical_name) AS logical_name,
                   list_sort(list_distinct(list(r.relation_name))) AS relation_names,
                   list_sort(list_distinct(list(r.usage_role))) AS usage_roles,
                   list_sort(list_distinct(list(r.definition_status))) AS definition_statuses,
                   count(*) AS occurrence_count,
                   count(DISTINCT r.query_id) AS statement_count,
                   min(sr.semantic_role) AS semantic_role,
                   min(sr.classification_status) AS classification_status,
                   bool_or(sr.hidden_by_default) AS hidden_by_default,
                   min(cast(sr.classification_reasons_json AS VARCHAR)) AS classification_reasons_json,
                   max(sr.write_occurrence_count) AS write_occurrence_count,
                   max(sr.downstream_target_count) AS downstream_target_count,
                   bool_or(sr.owned_namespace) AS owned_namespace,
                   bool_or(sr.technical_name_signal) AS technical_name_signal
            FROM sql_relation r
            JOIN sql_relation_semantic_role sr
              ON sr.repo_id=r.repo_id AND sr.relation_kind=r.relation_kind
             AND sr.relation_identity={group_key}
            WHERE {where}
            GROUP BY r.repo_id, r.relation_kind, {group_key}
        """
        with self._connect() as con:
            total_count = int(con.execute(
                f'SELECT count(*) FROM ({group_sql}) grouped_relations', args
            ).fetchone()[0])
            groups = self._rows(con.execute(
                group_sql + ' ORDER BY repo_id, relation_kind, relation_identity LIMIT ? OFFSET ?',
                [*args, page_size, offset],
            ))
            fields_by_key: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
            relation_evidence_by_key: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
            field_evidence_by_key: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
            if groups:
                selected_values = [
                    (str(g['repo_id']), str(g['relation_kind']), str(g['relation_identity']))
                    for g in groups
                ]
                placeholders = ','.join('(?,?,?)' for _ in selected_values)
                selected_args = [value for row in selected_values for value in row]
                relation_evidence_filter = ''
                relation_evidence_args = list(selected_args)
                if usage_role:
                    relation_evidence_filter = ' WHERE r.usage_role=?'
                    relation_evidence_args.append(usage_role)
                relation_evidence_sql = f"""
                    WITH selected(repo_id, relation_kind, relation_identity) AS (VALUES {placeholders})
                    SELECT r.repo_id, r.relation_kind, {group_key} AS relation_identity,
                           r.sql_relation_id, r.usage_role, r.file, r.line_start, r.query_id, r.scope_id
                    FROM sql_relation r
                    JOIN selected s
                      ON s.repo_id=r.repo_id AND s.relation_kind=r.relation_kind
                     AND s.relation_identity={group_key}
                    {relation_evidence_filter}
                    ORDER BY r.repo_id, r.relation_kind, relation_identity,
                             r.usage_role, r.file, r.line_start, r.query_id, r.scope_id, r.sql_relation_id
                """
                for evidence in self._rows(con.execute(relation_evidence_sql, relation_evidence_args)):
                    key = (
                        str(evidence.pop('repo_id')),
                        str(evidence.pop('relation_kind')),
                        str(evidence.pop('relation_identity')),
                    )
                    relation_evidence_by_key.setdefault(key, []).append(evidence)
                if include_fields:
                    field_sql = f"""
                        WITH selected(repo_id, relation_kind, relation_identity) AS (VALUES {placeholders})
                        SELECT r.repo_id, r.relation_kind, {group_key} AS relation_identity,
                               u.column_name,
                               list_sort(list_distinct(list(u.usage_role))) AS usage_roles,
                               list_sort(list_distinct(list(u.resolution_status))) AS resolution_statuses,
                               list_sort(list_distinct(list(u.resolution_basis))) AS resolution_bases,
                               count(*) AS occurrence_count,
                               count(DISTINCT u.query_id) AS statement_count
                        FROM sql_relation r
                        JOIN selected s
                          ON s.repo_id=r.repo_id AND s.relation_kind=r.relation_kind
                         AND s.relation_identity={group_key}
                        JOIN sql_column_usage u
                          ON u.repo_id=r.repo_id AND u.relation_id=r.sql_relation_id
                        GROUP BY r.repo_id, r.relation_kind,
                                 coalesce(nullif(r.template_name,''), r.relation_name), u.column_name
                        ORDER BY r.repo_id, r.relation_kind, relation_identity, u.column_name
                    """
                    field_rows = self._rows(con.execute(field_sql, selected_args))
                    for field in field_rows:
                        key = (
                            str(field.pop('repo_id')),
                            str(field.pop('relation_kind')),
                            str(field.pop('relation_identity')),
                        )
                        field['name'] = field.pop('column_name')
                        fields_by_key.setdefault(key, []).append(field)
                    field_evidence_sql = f"""
                        WITH selected(repo_id, relation_kind, relation_identity) AS (VALUES {placeholders})
                        SELECT r.repo_id, r.relation_kind, {group_key} AS relation_identity,
                               u.column_name, u.sql_column_usage_id, u.usage_role,
                               u.file, u.line_start, u.query_id, u.scope_id
                        FROM sql_relation r
                        JOIN selected s
                          ON s.repo_id=r.repo_id AND s.relation_kind=r.relation_kind
                         AND s.relation_identity={group_key}
                        JOIN sql_column_usage u
                          ON u.repo_id=r.repo_id AND u.relation_id=r.sql_relation_id
                        ORDER BY r.repo_id, r.relation_kind, relation_identity, u.column_name,
                                 u.usage_role, u.file, u.line_start, u.query_id, u.scope_id,
                                 u.sql_column_usage_id
                    """
                    for evidence in self._rows(con.execute(field_evidence_sql, selected_args)):
                        key = (
                            str(evidence.pop('repo_id')),
                            str(evidence.pop('relation_kind')),
                            str(evidence.pop('relation_identity')),
                            str(evidence.pop('column_name')),
                        )
                        field_evidence_by_key.setdefault(key, []).append(evidence)
        items: list[dict[str, Any]] = []
        for group in groups:
            key = (
                str(group['repo_id']),
                str(group['relation_kind']),
                str(group['relation_identity']),
            )
            group['relation_id'] = stable_id('sql_relation_inventory', *key)
            group['classification_reasons'] = list(group.pop('classification_reasons_json', []) or [])
            relation_names = list(group.pop('relation_names', []) or [])
            group['resolved_names'] = relation_names if group.get('relation_kind') == 'physical' else []
            fields = fields_by_key.get(key, []) if include_fields else []
            for field in fields:
                field_key = (*key, str(field['name']))
                field.update(self._summarize_sql_evidence(
                    field_evidence_by_key.get(field_key, []),
                    evidence_id_field='sql_column_usage_id',
                    max_evidence_per_role=evidence_limit,
                ))
            group['fields'] = fields
            group['field_count'] = len(fields) if include_fields else None
            group.update(self._summarize_sql_evidence(
                relation_evidence_by_key.get(key, []),
                evidence_id_field='sql_relation_id',
                max_evidence_per_role=evidence_limit,
            ))
            items.append(group)
        result = self._page_result(
            kind='knowledge-layer-sql-relations', query_id=query_id, filters=filters,
            items=items, total_count=total_count, offset=offset, page_size=page_size,
        )
        result['coverage'] = self.sql_analysis_coverage(repo_id=repo_id)
        result['coverage']['relation_classification'] = self.sql_relation_semantic_role_coverage(repo_id=repo_id)
        result['coverage']['source_inventory'] = self.sql_source_inventory_coverage(repo_id=repo_id)
        return result

    def export_sql_source_inventory(
        self,
        *,
        repo_id: str | None = None,
        relation_kind: str | None = None,
        usage_role: str | None = None,
        view: str = 'business_sources',
        token: str = '',
        max_evidence_per_role: int = 3,
    ) -> dict[str, Any]:
        """Return the complete deterministic external SQL source inventory.

        With no explicit ``relation_kind`` the export includes only physical and
        physical-template relations. CTE, derived and unknown relation kinds remain
        available through ``list_sql_relations`` but are not source-inventory records.
        """
        items: list[dict[str, Any]] = []
        coverage: dict[str, Any] = {}
        relation_kinds = (relation_kind,) if relation_kind else ('physical', 'physical_template')
        for current_kind in relation_kinds:
            page_token = ''
            while True:
                page = self.list_sql_relations(
                    repo_id=repo_id,
                    relation_kind=current_kind,
                    usage_role=usage_role,
                    view=view,
                    token=token,
                    include_fields=True,
                    max_evidence_per_role=max_evidence_per_role,
                    max_results=500,
                    page_token=page_token,
                )
                items.extend(page.get('items') or [])
                coverage = dict(page.get('coverage') or coverage)
                page_token = str(page.get('next_token') or '')
                if not page_token:
                    break
        for item in items:
            fields = list(item.get('fields') or [])
            fields.sort(key=lambda field: (
                str(field.get('name') or '').casefold(),
                str(field.get('name') or ''),
            ))
            item['fields'] = fields
        items.sort(key=lambda item: (
            str(item.get('repo_id') or '').casefold(),
            str(item.get('repo_id') or ''),
            str(item.get('relation_identity') or '').casefold(),
            str(item.get('relation_identity') or ''),
            str(item.get('relation_kind') or ''),
            str(item.get('relation_id') or ''),
        ))
        return {
            'kind': 'knowledge-layer-sql-source-inventory-export',
            'schema_version': 'sql-source-inventory/v1',
            'filters': {
                'repo_id': repo_id,
                'relation_kind': relation_kind,
                'usage_role': usage_role,
                'view': view,
                'token': token,
                'max_evidence_per_role': self._normalize_sql_evidence_limit(max_evidence_per_role),
            },
            'item_count': len(items),
            'items': items,
            'coverage': coverage,
        }

    def write_sql_source_inventory_jsonl(
        self,
        output_path: str | Path,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Write a stable metadata-plus-relation JSONL export and return its checksum."""
        export = self.export_sql_source_inventory(**kwargs)
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        header = {
            'record_type': 'inventory_metadata',
            'schema_version': export['schema_version'],
            'kind': export['kind'],
            'filters': export['filters'],
            'item_count': export['item_count'],
            'coverage': export['coverage'],
        }
        digest = hashlib.sha256()
        byte_size = 0
        record_count = 0
        with path.open('wb') as fh:
            records = [header]
            records.extend({'record_type': 'source_relation', 'relation': item} for item in export['items'])
            for record in records:
                payload = (json.dumps(
                    record, ensure_ascii=False, sort_keys=True, separators=(',', ':'),
                ) + '\n').encode('utf-8')
                fh.write(payload)
                digest.update(payload)
                byte_size += len(payload)
                record_count += 1
        return {
            'kind': 'knowledge-layer-sql-source-inventory-jsonl',
            'schema_version': export['schema_version'],
            'path': str(path),
            'sha256': digest.hexdigest(),
            'byte_size': byte_size,
            'record_count': record_count,
            'source_relation_count': export['item_count'],
        }

    def sql_relations(self, **kwargs: Any) -> dict[str, Any]:
        return self.list_sql_relations(**kwargs)

    def list_sql_workflow_bindings(
        self,
        *,
        repo_id: str | None = None,
        binding_name: str | None = None,
        file: str | None = None,
        resolution_status: str | None = None,
        max_results: int = 100,
        page_token: str = '',
    ) -> dict[str, Any]:
        """Return observed SQL-relevant workflow/configuration scalar bindings.

        This is a read-only projection. It does not apply runtime precedence, inherit
        values across configuration files or resolve SQL placeholders.
        """
        filters = {
            'repo_id': repo_id,
            'binding_name': binding_name,
            'file': file,
            'resolution_status': resolution_status,
        }
        if not self._has_relation('sql_workflow_binding'):
            return {
                'kind': 'knowledge-layer-sql-workflow-bindings',
                'schema_version': 'sql-workflow-bindings/v1',
                'filters': filters,
                'not_available': True,
                'items': [],
                'total_count': 0,
                'returned_count': 0,
                'page_offset': 0,
                'page_size': self._normalize_page_size(max_results),
                'truncated': False,
                'next_token': None,
                'summary': {'by_resolution_status': {}, 'by_binding_name': {}},
            }
        clauses = ['1=1']
        args: list[Any] = []
        for column, value in (
            ('repo_id', repo_id),
            ('binding_name', binding_name),
            ('file', file),
            ('resolution_status', resolution_status),
        ):
            if value is not None:
                text = str(value).strip()
                if not text:
                    raise ValueError(f'{column} must not be empty when provided')
                clauses.append(f'{column}=?')
                args.append(text)
        where = ' AND '.join(clauses)
        query_id = 'sql_workflow_bindings'
        page_size = self._normalize_page_size(max_results)
        offset = self._decode_page_token(page_token, query_id=query_id, filters=filters)
        columns = (
            'sql_workflow_binding_id, repo_id, file, line_start, line_end, config_format, '
            'binding_path, parent_path, binding_name, value_type, scalar_value, value_expression, '
            'referenced_placeholders_json, resolution_status, evidence_maturity_level, evidence_json'
        )
        with self._connect() as con:
            total_count = int(con.execute(
                f'SELECT count(*) FROM sql_workflow_binding WHERE {where}', args
            ).fetchone()[0])
            items = self._rows(con.execute(
                f'SELECT {columns} FROM sql_workflow_binding WHERE {where} '
                'ORDER BY file, line_start, binding_path, sql_workflow_binding_id LIMIT ? OFFSET ?',
                [*args, page_size, offset],
            ))
            status_rows = con.execute(
                f'SELECT resolution_status, count(*) FROM sql_workflow_binding WHERE {where} '
                'GROUP BY resolution_status ORDER BY resolution_status', args
            ).fetchall()
            name_rows = con.execute(
                f'SELECT binding_name, count(*) FROM sql_workflow_binding WHERE {where} '
                'GROUP BY binding_name ORDER BY count(*) DESC, binding_name LIMIT 50', args
            ).fetchall()
        next_offset = offset + len(items)
        truncated = next_offset < total_count
        return {
            'kind': 'knowledge-layer-sql-workflow-bindings',
            'schema_version': 'sql-workflow-bindings/v1',
            'filters': filters,
            'items': items,
            'total_count': total_count,
            'returned_count': len(items),
            'page_offset': offset,
            'page_size': page_size,
            'truncated': truncated,
            'next_token': self._encode_page_token(query_id=query_id, filters=filters, offset=next_offset) if truncated else None,
            'summary': {
                'by_resolution_status': {str(key): int(value) for key, value in status_rows},
                'by_binding_name': {str(key): int(value) for key, value in name_rows},
            },
        }

    def list_sql_workflow_context_files(
        self,
        *,
        repo_id: str | None = None,
        workflow_context_file: str | None = None,
        reachable_file: str | None = None,
        reachable_file_kind: str | None = None,
        resolution_status: str | None = None,
        max_results: int = 100,
        page_token: str = '',
    ) -> dict[str, Any]:
        """Return files reachable from evidence-backed workflow contexts."""
        filters = {
            'repo_id': repo_id,
            'workflow_context_file': workflow_context_file,
            'reachable_file': reachable_file,
            'reachable_file_kind': reachable_file_kind,
            'resolution_status': resolution_status,
        }
        if not self._has_relation('sql_workflow_context_file'):
            return {
                'kind': 'knowledge-layer-sql-workflow-context-files',
                'schema_version': 'sql-workflow-context-file/v1',
                'filters': filters,
                'not_available': True,
                'items': [], 'total_count': 0, 'returned_count': 0,
                'page_offset': 0, 'page_size': self._normalize_page_size(max_results),
                'truncated': False, 'next_token': None,
                'summary': {'by_resolution_status': {}, 'distinct_context_count': 0},
            }
        clauses = ['1=1']
        args: list[Any] = []
        for column, value in (
            ('repo_id', repo_id), ('workflow_context_file', workflow_context_file),
            ('reachable_file', reachable_file), ('reachable_file_kind', reachable_file_kind),
            ('resolution_status', resolution_status),
        ):
            if value is None:
                continue
            text = str(value).strip()
            if not text:
                raise ValueError(f'{column} must not be empty when provided')
            clauses.append(f'{column}=?')
            args.append(text)
        where = ' AND '.join(clauses)
        query_id = 'sql_workflow_context_files'
        page_size = self._normalize_page_size(max_results)
        offset = self._decode_page_token(page_token, query_id=query_id, filters=filters)
        columns = (
            'sql_workflow_context_file_id, repo_id, workflow_context_file, reachable_file, '
            'reachable_file_kind, context_hop_count, context_files_json, context_reference_ids_json, '
            'resolution_status, resolution_reasons_json'
        )
        with self._connect() as con:
            total_count = int(con.execute(
                f'SELECT count(*) FROM sql_workflow_context_file WHERE {where}', args
            ).fetchone()[0])
            items = self._rows(con.execute(
                f'SELECT {columns} FROM sql_workflow_context_file WHERE {where} '
                'ORDER BY workflow_context_file, context_hop_count, reachable_file, '
                'sql_workflow_context_file_id LIMIT ? OFFSET ?',
                [*args, page_size, offset],
            ))
            statuses = con.execute(
                f'SELECT resolution_status, count(*) FROM sql_workflow_context_file WHERE {where} '
                'GROUP BY resolution_status ORDER BY resolution_status', args
            ).fetchall()
            context_count = int(con.execute(
                f'SELECT count(DISTINCT workflow_context_file) FROM sql_workflow_context_file WHERE {where}', args
            ).fetchone()[0])
        next_offset = offset + len(items)
        truncated = next_offset < total_count
        return {
            'kind': 'knowledge-layer-sql-workflow-context-files',
            'schema_version': 'sql-workflow-context-file/v1',
            'filters': filters,
            'items': items, 'total_count': total_count, 'returned_count': len(items),
            'page_offset': offset, 'page_size': page_size, 'truncated': truncated,
            'next_token': self._encode_page_token(query_id=query_id, filters=filters, offset=next_offset) if truncated else None,
            'summary': {
                'by_resolution_status': {str(key): int(value) for key, value in statuses},
                'distinct_context_count': context_count,
            },
        }

    def list_sql_placeholder_binding_resolutions(
        self,
        *,
        repo_id: str | None = None,
        sql_file: str | None = None,
        workflow_context_file: str | None = None,
        placeholder: str | None = None,
        resolved_value: str | None = None,
        resolution_status: str | None = None,
        max_results: int = 100,
        page_token: str = '',
    ) -> dict[str, Any]:
        """Return evidence-backed workflow-context values for SQL placeholders."""
        filters = {
            'repo_id': repo_id,
            'sql_file': sql_file,
            'workflow_context_file': workflow_context_file,
            'placeholder': placeholder,
            'resolved_value': resolved_value,
            'resolution_status': resolution_status,
        }
        if not self._has_relation('sql_placeholder_binding_resolution'):
            return {
                'kind': 'knowledge-layer-sql-placeholder-binding-resolutions',
                'schema_version': 'sql-placeholder-binding-resolution/v1',
                'filters': filters,
                'not_available': True,
                'items': [],
                'total_count': 0,
                'returned_count': 0,
                'page_offset': 0,
                'page_size': self._normalize_page_size(max_results),
                'truncated': False,
                'next_token': None,
                'summary': {'by_resolution_status': {}, 'distinct_context_count': 0, 'distinct_sql_file_count': 0},
            }
        clauses = ['1=1']
        args: list[Any] = []
        for column, value in (
            ('repo_id', repo_id), ('sql_file', sql_file),
            ('workflow_context_file', workflow_context_file), ('placeholder', placeholder),
            ('resolved_value', resolved_value), ('resolution_status', resolution_status),
        ):
            if value is None:
                continue
            text = str(value).strip()
            if not text:
                raise ValueError(f'{column} must not be empty when provided')
            clauses.append(f'{column}=?')
            args.append(text)
        where = ' AND '.join(clauses)
        query_id = 'sql_placeholder_binding_resolutions'
        page_size = self._normalize_page_size(max_results)
        offset = self._decode_page_token(page_token, query_id=query_id, filters=filters)
        columns = (
            'sql_placeholder_binding_resolution_id, repo_id, workflow_context_file, sql_file, query_id, '
            'sql_semantic_placeholder_id, placeholder, usage_roles_json, sql_workflow_binding_id, '
            'binding_file, binding_line_start, binding_path, binding_name, binding_value_expression, '
            'resolved_value, context_hop_count, context_files_json, context_reference_ids_json, '
            'resolution_status, resolution_reasons_json, evidence_json'
        )
        with self._connect() as con:
            total_count = int(con.execute(
                f'SELECT count(*) FROM sql_placeholder_binding_resolution WHERE {where}', args
            ).fetchone()[0])
            items = self._rows(con.execute(
                f'SELECT {columns} FROM sql_placeholder_binding_resolution WHERE {where} '
                'ORDER BY workflow_context_file, sql_file, query_id, placeholder, resolved_value, '
                'sql_placeholder_binding_resolution_id LIMIT ? OFFSET ?',
                [*args, page_size, offset],
            ))
            status_rows = con.execute(
                f'SELECT resolution_status, count(*) FROM sql_placeholder_binding_resolution WHERE {where} '
                'GROUP BY resolution_status ORDER BY resolution_status', args
            ).fetchall()
            context_count, file_count = con.execute(
                f'SELECT count(DISTINCT workflow_context_file), count(DISTINCT sql_file) '
                f'FROM sql_placeholder_binding_resolution WHERE {where}', args
            ).fetchone()
        next_offset = offset + len(items)
        truncated = next_offset < total_count
        return {
            'kind': 'knowledge-layer-sql-placeholder-binding-resolutions',
            'schema_version': 'sql-placeholder-binding-resolution/v1',
            'filters': filters,
            'items': items,
            'total_count': total_count,
            'returned_count': len(items),
            'page_offset': offset,
            'page_size': page_size,
            'truncated': truncated,
            'next_token': self._encode_page_token(query_id=query_id, filters=filters, offset=next_offset) if truncated else None,
            'summary': {
                'by_resolution_status': {str(key): int(value) for key, value in status_rows},
                'distinct_context_count': int(context_count or 0),
                'distinct_sql_file_count': int(file_count or 0),
            },
        }

    def find_sql_target_candidates(
        self,
        *,
        repo_id: str | None = None,
        source_relation_hints: list[str] | tuple[str, ...] | str | None = None,
        source_column_hints: list[str] | tuple[str, ...] | str | None = None,
        business_entity_hints: list[str] | tuple[str, ...] | str | None = None,
        max_results: int = 10,
    ) -> dict[str, Any]:
        from .sql_target_resolution import find_sql_target_candidates

        return find_sql_target_candidates(
            self,
            repo_id=repo_id,
            source_relation_hints=source_relation_hints,
            source_column_hints=source_column_hints,
            business_entity_hints=business_entity_hints,
            max_results=max_results,
        )

    def resolve_sql_attribute_insertion_context(
        self,
        target_relation: str,
        *,
        repo_id: str | None = None,
        source_relation_hints: list[str] | tuple[str, ...] | str | None = None,
        source_column_hints: list[str] | tuple[str, ...] | str | None = None,
        max_results: int = 10,
    ) -> dict[str, Any]:
        from .sql_attribute_insertion import resolve_sql_attribute_insertion_context

        return resolve_sql_attribute_insertion_context(
            self,
            target_relation=target_relation,
            repo_id=repo_id,
            source_relation_hints=source_relation_hints,
            source_column_hints=source_column_hints,
            max_results=max_results,
        )

    def list_sql_target_column_lineage(
        self,
        target_relation_name: str,
        *,
        target_column: str | None = None,
        repo_id: str | None = None,
        lineage_status: str | None = None,
        include_gaps: bool = True,
        max_gaps: int = 500,
        max_results: int = 100,
        page_token: str = '',
    ) -> dict[str, Any]:
        """Return canonical SQL lineage for one exact resolved target relation.

        Direct SQL write lineage remains canonical where it exists. When the exact
        relation is the unique physical recommendation for an observed workflow
        ``main_table_name``, the result also projects the separately materialized
        workflow-target lineage. The query layer does not reconstruct lineage: it
        only maps the already confirmed logical workflow target to its exact
        physical relation identity.
        """
        relation = str(target_relation_name or '').strip()
        if not relation:
            raise ValueError('target_relation_name must not be empty')
        column = None if target_column is None else str(target_column).strip()
        if target_column is not None and not column:
            raise ValueError('target_column must not be empty when provided')
        if isinstance(max_gaps, bool) or not isinstance(max_gaps, int) or max_gaps < 1:
            raise ValueError('max_gaps must be a positive integer')
        gap_limit = min(max_gaps, 500)
        filters = {
            'target_relation_name': relation,
            'target_column': column,
            'repo_id': repo_id,
            'lineage_status': lineage_status,
            'include_gaps': bool(include_gaps),
            'max_gaps': gap_limit,
        }
        if not self._has_relation('sql_recursive_column_lineage'):
            return {
                'kind': 'knowledge-layer-sql-target-column-lineage',
                'schema_version': 'sql-target-column-lineage/v1',
                'filters': filters,
                'not_available': True,
                'items': [],
                'total_count': 0,
                'returned_count': 0,
                'page_offset': 0,
                'page_size': self._normalize_page_size(max_results),
                'truncated': False,
                'next_token': None,
                'summary': {
                    'path_count': 0,
                    'target_column_count': 0,
                    'terminal_source_count': 0,
                    'max_recursion_depth': 0,
                    'by_lineage_status': {},
                    'by_recursive_resolution_status': {},
                    'by_physical_origin_status': {},
                    'by_target_mapping_status': {},
                },
                'gaps': [],
                'gap_count': 0,
                'gaps_truncated': False,
                'gaps_by_kind': {},
            }

        workflow_logical_target: str | None = None
        workflow_resolution_status: str | None = None
        if self._has_relation('sql_workflow_target_column_lineage'):
            resolution = self.find_sql_target_candidates(
                repo_id=repo_id,
                business_entity_hints=[relation],
                max_results=10,
            )
            exact = [
                candidate for candidate in resolution.get('candidates') or []
                if str(candidate.get('recommended_target_relation') or '') == relation
                and str(candidate.get('target_relation_recommendation_status') or '') == 'confirmed_unique'
            ]
            logical_targets = sorted({str(candidate.get('logical_target_name') or '') for candidate in exact if candidate.get('logical_target_name')})
            if len(logical_targets) == 1:
                workflow_logical_target = logical_targets[0]
                workflow_resolution_status = 'workflow_confirmed_unique'

        direct_clauses = ['target_relation_name=?']
        direct_args: list[Any] = [relation]
        if column is not None:
            direct_clauses.append('target_column=?')
            direct_args.append(column)
        if repo_id:
            direct_clauses.append('repo_id=?')
            direct_args.append(repo_id)
        if lineage_status:
            direct_clauses.append('lineage_status=?')
            direct_args.append(lineage_status)
        direct_where = ' AND '.join(direct_clauses)

        direct_select = (
            'SELECT sql_recursive_column_lineage_id, repo_id, query_id, file, line_start, '
            'direct_lineage_id, write_target_id, target_projection_binding_id, '
            'target_relation_name, target_relation_kind, target_column, target_mapping_status, '
            'root_projection_id, root_expression, root_expression_kind, terminal_source_kind, '
            'terminal_column_usage_id, terminal_column, terminal_relation_id, '
            'terminal_relation_name, terminal_relation_kind, terminal_expression, '
            'terminal_expression_kind, recursion_depth, branch_path_json, '
            'transformation_path_json, recursive_resolution_status, physical_origin_status, '
            'lineage_status, evidence_maturity_level, evidence_json '
            f'FROM sql_recursive_column_lineage WHERE {direct_where}'
        )
        combined_args: list[Any] = list(direct_args)
        union_parts = [direct_select]

        if workflow_logical_target is not None:
            workflow_clauses = ['workflow_target_logical_name=?']
            workflow_args: list[Any] = [workflow_logical_target]
            if column is not None:
                workflow_clauses.append('target_column=?')
                workflow_args.append(column)
            if repo_id:
                workflow_clauses.append('repo_id=?')
                workflow_args.append(repo_id)
            if lineage_status:
                workflow_clauses.append('lineage_status=?')
                workflow_args.append(lineage_status)
            workflow_where = ' AND '.join(workflow_clauses)
            union_parts.append(
                "SELECT sql_workflow_target_column_lineage_id AS sql_recursive_column_lineage_id, "
                "repo_id, query_id, file, line_start, "
                "NULL AS direct_lineage_id, NULL AS write_target_id, NULL AS target_projection_binding_id, "
                "? AS target_relation_name, 'workflow_resolved' AS target_relation_kind, target_column, "
                "? AS target_mapping_status, root_projection_id, root_expression, root_expression_kind, "
                "terminal_source_kind, terminal_column_usage_id, terminal_column, terminal_relation_id, "
                "terminal_relation_name, terminal_relation_kind, NULL AS terminal_expression, "
                "NULL AS terminal_expression_kind, recursion_depth, branch_path_json, transformation_path_json, "
                "recursive_resolution_status, physical_origin_status, lineage_status, evidence_maturity_level, evidence_json "
                f"FROM sql_workflow_target_column_lineage WHERE {workflow_where}"
            )
            combined_args.extend([relation, workflow_resolution_status, *workflow_args])

        combined_sql = ' UNION ALL '.join(union_parts)
        query_id = 'sql_target_column_lineage'
        page_size = self._normalize_page_size(max_results)
        offset = self._decode_page_token(page_token, query_id=query_id, filters=filters)
        order_by = (
            'target_column, query_id, root_projection_id, terminal_relation_name, '
            'terminal_column, recursion_depth, sql_recursive_column_lineage_id'
        )

        with self._connect() as con:
            total_count = int(con.execute(
                f'SELECT count(*) FROM ({combined_sql}) combined_lineage', combined_args
            ).fetchone()[0])
            items = self._rows(con.execute(
                f'SELECT * FROM ({combined_sql}) combined_lineage ORDER BY {order_by} LIMIT ? OFFSET ?',
                [*combined_args, page_size, offset],
            ))
            target_column_count = int(con.execute(
                f'SELECT count(DISTINCT target_column) FROM ({combined_sql}) combined_lineage', combined_args
            ).fetchone()[0])
            terminal_source_count = int(con.execute(
                'SELECT count(*) FROM ('
                'SELECT DISTINCT terminal_relation_name, terminal_column '
                f'FROM ({combined_sql}) combined_lineage '
                'WHERE terminal_relation_name IS NOT NULL AND terminal_column IS NOT NULL'
                ') terminal_sources',
                combined_args,
            ).fetchone()[0])
            max_depth_raw = con.execute(
                f'SELECT max(recursion_depth) FROM ({combined_sql}) combined_lineage', combined_args
            ).fetchone()[0]
            lineage_status_rows = con.execute(
                f'SELECT lineage_status, count(*) FROM ({combined_sql}) combined_lineage '
                'GROUP BY lineage_status ORDER BY lineage_status', combined_args
            ).fetchall()
            recursive_status_rows = con.execute(
                f'SELECT recursive_resolution_status, count(*) FROM ({combined_sql}) combined_lineage '
                'GROUP BY recursive_resolution_status ORDER BY recursive_resolution_status', combined_args
            ).fetchall()
            physical_status_rows = con.execute(
                f'SELECT physical_origin_status, count(*) FROM ({combined_sql}) combined_lineage '
                'GROUP BY physical_origin_status ORDER BY physical_origin_status', combined_args
            ).fetchall()
            mapping_status_rows = con.execute(
                f'SELECT target_mapping_status, count(*) FROM ({combined_sql}) combined_lineage '
                'GROUP BY target_mapping_status ORDER BY target_mapping_status', combined_args
            ).fetchall()

            gaps: list[dict[str, Any]] = []
            gap_kind_rows: list[tuple[Any, Any]] = []
            gap_union_parts: list[str] = []
            gap_union_args: list[Any] = []
            if include_gaps and self._has_relation('sql_scoped_lineage_gap'):
                gap_clauses = ['target_relation_name=?']
                gap_args: list[Any] = [relation]
                if column is not None:
                    gap_clauses.append('target_column=?')
                    gap_args.append(column)
                if repo_id:
                    gap_clauses.append('repo_id=?')
                    gap_args.append(repo_id)
                gap_where = ' AND '.join(gap_clauses)
                gap_union_parts.append(
                    'SELECT sql_scoped_lineage_gap_id, repo_id, query_id, file, line_start, '
                    'gap_kind, analysis_status, impact, write_target_id, target_relation_name, '
                    'target_column, target_mapping_status, source_scope_id, projection_id, '
                    'projection_resolution_status, mapping_basis, source_column_usage_id, '
                    'source_column, table_or_alias, direct_lineage_id, source_relation_id, '
                    'source_relation_name, source_relation_kind, recursion_depth, branch_path_json, '
                    'evidence_maturity_level, evidence_json '
                    f'FROM sql_scoped_lineage_gap WHERE {gap_where}'
                )
                gap_union_args.extend(gap_args)

            if include_gaps and workflow_logical_target is not None and self._has_relation('sql_workflow_target_lineage_gap'):
                workflow_gap_clauses = ['workflow_target_logical_name=?']
                workflow_gap_args: list[Any] = [workflow_logical_target]
                if column is not None:
                    workflow_gap_clauses.append('target_column=?')
                    workflow_gap_args.append(column)
                if repo_id:
                    workflow_gap_clauses.append('repo_id=?')
                    workflow_gap_args.append(repo_id)
                workflow_gap_where = ' AND '.join(workflow_gap_clauses)
                gap_union_parts.append(
                    "SELECT sql_workflow_target_lineage_gap_id AS sql_scoped_lineage_gap_id, repo_id, query_id, file, line_start, "
                    "gap_kind, 'partial' AS analysis_status, impact, NULL AS write_target_id, ? AS target_relation_name, "
                    "target_column, ? AS target_mapping_status, NULL AS source_scope_id, projection_id, "
                    "projection_resolution_status, mapping_basis, NULL AS source_column_usage_id, "
                    "NULL AS source_column, NULL AS table_or_alias, NULL AS direct_lineage_id, NULL AS source_relation_id, "
                    "NULL AS source_relation_name, NULL AS source_relation_kind, 0 AS recursion_depth, '[]'::JSON AS branch_path_json, "
                    "evidence_maturity_level, evidence_json "
                    f"FROM sql_workflow_target_lineage_gap WHERE {workflow_gap_where}"
                )
                gap_union_args.extend([relation, workflow_resolution_status, *workflow_gap_args])

            gap_count = 0
            if gap_union_parts:
                combined_gaps_sql = ' UNION ALL '.join(gap_union_parts)
                gap_count = int(con.execute(
                    f'SELECT count(*) FROM ({combined_gaps_sql}) combined_gaps', gap_union_args
                ).fetchone()[0])
                gaps = self._rows(con.execute(
                    f'SELECT * FROM ({combined_gaps_sql}) combined_gaps '
                    'ORDER BY target_column, line_start, gap_kind, sql_scoped_lineage_gap_id LIMIT ?',
                    [*gap_union_args, gap_limit],
                ))
                gap_kind_rows = con.execute(
                    f'SELECT gap_kind, count(*) FROM ({combined_gaps_sql}) combined_gaps '
                    'GROUP BY gap_kind ORDER BY gap_kind', gap_union_args
                ).fetchall()

        page = self._page_result(
            kind='knowledge-layer-sql-target-column-lineage',
            query_id=query_id,
            filters=filters,
            items=items,
            total_count=total_count,
            offset=offset,
            page_size=page_size,
        )
        page.update({
            'schema_version': 'sql-target-column-lineage/v1',
            'filters': filters,
            'summary': {
                'path_count': total_count,
                'target_column_count': target_column_count,
                'terminal_source_count': terminal_source_count,
                'max_recursion_depth': int(max_depth_raw or 0),
                'by_lineage_status': {
                    str(key or 'unknown'): int(value) for key, value in lineage_status_rows
                },
                'by_recursive_resolution_status': {
                    str(key or 'unknown'): int(value) for key, value in recursive_status_rows
                },
                'by_physical_origin_status': {
                    str(key or 'unknown'): int(value) for key, value in physical_status_rows
                },
                'by_target_mapping_status': {
                    str(key or 'unknown'): int(value) for key, value in mapping_status_rows
                },
                'workflow_target_logical_name': workflow_logical_target,
                'workflow_target_resolution_status': workflow_resolution_status,
            },
            'gaps': gaps,
            'gap_count': gap_count,
            'gaps_truncated': len(gaps) < gap_count,
            'gaps_by_kind': {str(key or 'unknown'): int(value) for key, value in gap_kind_rows},
        })
        return page

    def get_sql_field_calculation(
        self,
        target_relation_name: str,
        target_column: str,
        *,
        repo_id: str | None = None,
        include_gaps: bool = True,
        max_gaps: int = 500,
    ) -> dict[str, Any]:
        """Return the observed calculation and terminal origins of one target field.

        This is a deterministic projection over recursive SQL lineage. It preserves
        every branch, transformation and scoped gap and never invents a preferred
        source when several terminal origins are present.
        """
        relation = str(target_relation_name or '').strip()
        column = str(target_column or '').strip()
        if not relation:
            raise ValueError('target_relation_name must not be empty')
        if not column:
            raise ValueError('target_column must not be empty')
        token = ''
        paths: list[dict[str, Any]] = []
        first: dict[str, Any] | None = None
        while True:
            page = self.list_sql_target_column_lineage(
                relation,
                target_column=column,
                repo_id=repo_id,
                include_gaps=include_gaps,
                max_gaps=max_gaps,
                max_results=500,
                page_token=token,
            )
            if page.get('not_available'):
                return {
                    'kind': 'knowledge-layer-sql-field-calculation',
                    'schema_version': 'sql-field-calculation/v1',
                    'target_relation_name': relation,
                    'target_column': column,
                    'repo_id': repo_id,
                    'not_available': True,
                    'calculations': [],
                    'calculation_count': 0,
                    'terminal_sources': [],
                    'terminal_source_count': 0,
                    'lineage_paths': [],
                    'lineage_path_count': 0,
                    'gaps': [],
                    'gap_count': 0,
                    'coverage_status': 'not_available',
                }
            if first is None:
                first = dict(page)
            paths.extend(dict(item) for item in page.get('items') or [])
            next_token = page.get('next_token')
            if not next_token:
                break
            token = str(next_token)

        calculations_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
        terminal_sources_by_key: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        lineage_statuses: set[str] = set()
        physical_statuses: set[str] = set()
        for path in paths:
            projection_id = str(path.get('root_projection_id') or '')
            expression = str(path.get('root_expression') or '')
            expression_kind = str(path.get('root_expression_kind') or '')
            key = (projection_id, expression, expression_kind)
            calculation = calculations_by_key.setdefault(key, {
                'root_projection_id': projection_id or None,
                'expression': expression or None,
                'expression_kind': expression_kind or None,
                'target_mapping_statuses': set(),
                'recursive_resolution_statuses': set(),
                'lineage_statuses': set(),
                'transformation_paths': [],
                'branch_paths': [],
                'terminal_source_keys': set(),
                'evidence_maturity_levels': set(),
            })
            for field, target in (
                ('target_mapping_status', 'target_mapping_statuses'),
                ('recursive_resolution_status', 'recursive_resolution_statuses'),
                ('lineage_status', 'lineage_statuses'),
                ('evidence_maturity_level', 'evidence_maturity_levels'),
            ):
                value = str(path.get(field) or '')
                if value:
                    calculation[target].add(value)
            transformation_path = path.get('transformation_path_json')
            if transformation_path not in (None, [], '') and transformation_path not in calculation['transformation_paths']:
                calculation['transformation_paths'].append(transformation_path)
            branch_path = path.get('branch_path_json')
            if branch_path not in (None, [], '') and branch_path not in calculation['branch_paths']:
                calculation['branch_paths'].append(branch_path)
            source_key = (
                str(path.get('terminal_relation_name') or ''),
                str(path.get('terminal_column') or ''),
                str(path.get('terminal_source_kind') or ''),
                str(path.get('terminal_expression') or ''),
            )
            if any(source_key):
                calculation['terminal_source_keys'].add(source_key)
                source = terminal_sources_by_key.setdefault(source_key, {
                    'relation_name': source_key[0] or None,
                    'column_name': source_key[1] or None,
                    'source_kind': source_key[2] or None,
                    'expression': source_key[3] or None,
                    'relation_kinds': set(),
                    'expression_kinds': set(),
                    'physical_origin_statuses': set(),
                    'lineage_statuses': set(),
                    'column_usage_ids': set(),
                    'path_count': 0,
                })
                source['path_count'] += 1
                for field, target in (
                    ('terminal_relation_kind', 'relation_kinds'),
                    ('terminal_expression_kind', 'expression_kinds'),
                    ('physical_origin_status', 'physical_origin_statuses'),
                    ('lineage_status', 'lineage_statuses'),
                    ('terminal_column_usage_id', 'column_usage_ids'),
                ):
                    value = str(path.get(field) or '')
                    if value:
                        source[target].add(value)
            lineage_value = str(path.get('lineage_status') or '')
            if lineage_value:
                lineage_statuses.add(lineage_value)
            physical_value = str(path.get('physical_origin_status') or '')
            if physical_value:
                physical_statuses.add(physical_value)

        terminal_sources = []
        for key in sorted(terminal_sources_by_key):
            source = terminal_sources_by_key[key]
            terminal_sources.append({
                **{k: v for k, v in source.items() if not isinstance(v, set)},
                'relation_kinds': sorted(source['relation_kinds']),
                'expression_kinds': sorted(source['expression_kinds']),
                'physical_origin_statuses': sorted(source['physical_origin_statuses']),
                'lineage_statuses': sorted(source['lineage_statuses']),
                'column_usage_ids': sorted(source['column_usage_ids']),
            })

        calculations = []
        for key in sorted(calculations_by_key):
            item = calculations_by_key[key]
            source_keys = sorted(item.pop('terminal_source_keys'))
            calculations.append({
                **{k: v for k, v in item.items() if not isinstance(v, set)},
                'target_mapping_statuses': sorted(item['target_mapping_statuses']),
                'recursive_resolution_statuses': sorted(item['recursive_resolution_statuses']),
                'lineage_statuses': sorted(item['lineage_statuses']),
                'evidence_maturity_levels': sorted(item['evidence_maturity_levels']),
                'terminal_sources': [
                    {
                        'relation_name': source_key[0] or None,
                        'column_name': source_key[1] or None,
                        'source_kind': source_key[2] or None,
                        'expression': source_key[3] or None,
                    }
                    for source_key in source_keys
                ],
            })

        gaps = [dict(item) for item in (first or {}).get('gaps') or []]
        if not paths:
            coverage_status = 'not_found'
        elif gaps or any(value not in {'resolved', 'complete', 'confirmed'} for value in lineage_statuses):
            coverage_status = 'partial'
        else:
            coverage_status = 'complete'
        return {
            'kind': 'knowledge-layer-sql-field-calculation',
            'schema_version': 'sql-field-calculation/v1',
            'target_relation_name': relation,
            'target_column': column,
            'repo_id': repo_id,
            'calculations': calculations,
            'calculation_count': len(calculations),
            'terminal_sources': terminal_sources,
            'terminal_source_count': len(terminal_sources),
            'lineage_paths': paths,
            'lineage_path_count': len(paths),
            'lineage_statuses': sorted(lineage_statuses),
            'physical_origin_statuses': sorted(physical_statuses),
            'gaps': gaps,
            'gap_count': int((first or {}).get('gap_count') or 0),
            'gaps_truncated': bool((first or {}).get('gaps_truncated')),
            'gaps_by_kind': dict((first or {}).get('gaps_by_kind') or {}),
            'coverage_status': coverage_status,
        }

    def list_relation_materializations(
        self,
        *,
        output_table_name: str | None = None,
        query_id: str | None = None,
        workflow_context_file: str | None = None,
        max_results: int = 100,
        page_token: str = '',
    ) -> dict[str, Any]:
        """Return observed relation materializations from prepared cross-artifact knowledge.

        This is a thin read projection over ``cross_artifact_relation_materialization``.
        It does not infer producers or reconstruct workflow paths at query time.
        """
        filters = {
            'output_table_name': output_table_name,
            'query_id': query_id,
            'workflow_context_file': workflow_context_file,
        }
        if not self._has_relation('cross_artifact_relation_materialization'):
            result = self._empty_page(
                kind='knowledge-layer-relation-materializations',
                query_id='relation_materializations',
                filters=filters,
                max_results=max_results,
                page_token=page_token,
            )
            result.update({'schema_version': 'relation-materialization-query/v1', 'not_available': True})
            return result
        clauses = ['1=1']
        args: list[Any] = []
        if output_table_name is not None:
            value = str(output_table_name).strip()
            if not value:
                raise ValueError('output_table_name must not be empty when provided')
            clauses.append('lower(output_table_name)=lower(?)')
            args.append(value)
        if query_id is not None:
            value = str(query_id).strip()
            if not value:
                raise ValueError('query_id must not be empty when provided')
            clauses.append('query_id=?')
            args.append(value)
        if workflow_context_file is not None:
            value = str(workflow_context_file).strip()
            if not value:
                raise ValueError('workflow_context_file must not be empty when provided')
            clauses.append('workflow_context_file=?')
            args.append(value)
        where = ' AND '.join(clauses)
        page = self._paged_select(
            kind='knowledge-layer-relation-materializations',
            query_id='relation_materializations',
            select_sql=(
                'SELECT materialization_id,workflow_context_file,materialization_kind,source_file,'
                'source_fact_id,source_symbol,query_file,query_id,source_table_name,output_table_name,'
                'resolution_status,knowledge_class,mapping_basis,provenance_json '
                f'FROM cross_artifact_relation_materialization WHERE {where} '
                'ORDER BY lower(output_table_name),output_table_name,query_file,query_id,materialization_id'
            ),
            count_sql=f'SELECT count(*) FROM cross_artifact_relation_materialization WHERE {where}',
            args=args,
            filters=filters,
            max_results=max_results,
            page_token=page_token,
        )
        page.update({'schema_version': 'relation-materialization-query/v1', 'not_available': False})
        return page

    def get_workspace_sql_catalog(self) -> dict[str, Any]:
        """Return deterministic composition metadata for a workspace SQL catalog."""
        if not self._has_relation('workspace_sql_catalog_source'):
            return {
                'kind': 'knowledge-layer-workspace-sql-catalog',
                'schema_version': 'workspace-sql-catalog/v1',
                'not_available': True,
                'capability': 'common.workspace-sql-catalog',
                'sources': [],
                'source_count': 0,
                'repository_ids': [],
                'repository_count': 0,
            }
        with self._connect() as con:
            rows = self._rows(con.execute(
                """SELECT artifact_id, content_fingerprint, manifest_path, repository_ids_json,
                          source_build_id, source_schema_version
                   FROM workspace_sql_catalog_source ORDER BY artifact_id"""
            ))
        repository_ids: set[str] = set()
        for row in rows:
            values = row.get('repository_ids_json') or []
            if isinstance(values, str):
                try:
                    values = json.loads(values)
                except json.JSONDecodeError:
                    values = []
            row['repository_ids'] = sorted(str(value) for value in values if str(value))
            row.pop('repository_ids_json', None)
            repository_ids.update(row['repository_ids'])
        coverage = self.sql_analysis_coverage()
        return {
            'kind': 'knowledge-layer-workspace-sql-catalog',
            'schema_version': 'workspace-sql-catalog/v1',
            'scope_id': self.manifest().get('scope_id'),
            'sources': rows,
            'source_count': len(rows),
            'repository_ids': sorted(repository_ids),
            'repository_count': len(repository_ids),
            'coverage': coverage,
        }

    def get_sql_column_usage_context(self, sql_column_usage_id: str) -> dict[str, Any]:
        """Return compact deterministic context for one SQL column usage.

        The result intentionally does not infer an owner for unresolved or ambiguous
        unqualified columns. It exposes the statement, SELECT scope, relations and joins
        that were observable in the same scope so an external consumer can correlate the
        SQL facts with another Knowledge API system.
        """
        usage_id = str(sql_column_usage_id or '').strip()
        if not usage_id:
            raise ValueError('sql_column_usage_id is required')
        if not self._has_relation('sql_column_usage'):
            return {
                'kind': 'knowledge-layer-sql-column-usage-context',
                'sql_column_usage_id': usage_id,
                'not_available': True,
                'capability': 'common.sql-analysis',
            }
        with self._connect() as con:
            usage_rows = self._rows(con.execute(
                """SELECT sql_column_usage_id, repo_id, query_id, scope_id, file, line_start,
                          column_name, column_ordinal, usage_role, table_or_alias,
                          relation_id, relation_kind, relation_name,
                          resolution_status, resolution_basis, evidence_maturity_level,
                          evidence_json
                     FROM sql_column_usage
                    WHERE sql_column_usage_id=?""",
                [usage_id],
            ))
            if not usage_rows:
                return {
                    'kind': 'knowledge-layer-sql-column-usage-context',
                    'sql_column_usage_id': usage_id,
                    'not_found': True,
                }
            usage = usage_rows[0]
            repo_id = str(usage.get('repo_id') or '')
            query_id = str(usage.get('query_id') or '')
            scope_id = str(usage.get('scope_id') or '')

            scope_rows = self._rows(con.execute(
                """SELECT sql_select_scope_id, repo_id, query_id, file, line_start,
                          parent_scope_id, scope_kind, scope_name, scope_ordinal,
                          expression_index, relation_count, projection_count,
                          column_usage_count, evidence_maturity_level, evidence_json
                     FROM sql_select_scope
                    WHERE repo_id=? AND query_id=? AND sql_select_scope_id=?""",
                [repo_id, query_id, scope_id],
            )) if self._has_relation('sql_select_scope') else []

            statement_rows = self._rows(con.execute(
                """SELECT sql_statement_id, repo_id, query_id, file, line_start, line_end,
                          operation, statement_type, target_relation_name, unit_kind,
                          evidence_maturity_level, evidence_json
                     FROM sql_statement
                    WHERE repo_id=? AND query_id=?
                    ORDER BY line_start, sql_statement_id
                    LIMIT 1""",
                [repo_id, query_id],
            )) if self._has_relation('sql_statement') else []

            relation_rows = self._rows(con.execute(
                """SELECT sql_relation_id, repo_id, query_id, scope_id, file, line_start,
                          relation_kind, relation_name, template_name, logical_name,
                          alias, usage_role, definition_status, source_scope_ids_json,
                          placeholder_refs_json, evidence_maturity_level, evidence_json
                     FROM sql_relation
                    WHERE repo_id=? AND query_id=? AND scope_id=?
                    ORDER BY relation_kind, relation_name, alias, sql_relation_id""",
                [repo_id, query_id, scope_id],
            )) if self._has_relation('sql_relation') else []

            resolved_usage_rows = self._rows(con.execute(
                """SELECT relation_id, column_name, usage_role, resolution_status
                     FROM sql_column_usage
                    WHERE repo_id=? AND query_id=? AND scope_id=?
                      AND relation_id IS NOT NULL
                    ORDER BY relation_id, column_name, usage_role""",
                [repo_id, query_id, scope_id],
            ))

            join_rows = self._rows(con.execute(
                """SELECT sql_join_edge_id, repo_id, query_id, scope_id, file, line_start,
                          join_ordinal, join_type, condition_kind, predicate,
                          left_relation_id, left_relation_ids_json, left_relation_names_json,
                          right_relation_id, right_relation_kind, right_relation_name,
                          participating_relation_ids_json, column_pairs_json,
                          expression_links_json, using_columns_json,
                          additional_predicates_json, temporal_or_range_predicates_json,
                          resolution_status, resolution_reasons_json,
                          physical_join_confirmed, evidence_maturity_level, evidence_json
                     FROM sql_join_edge
                    WHERE repo_id=? AND query_id=? AND scope_id=?
                    ORDER BY join_ordinal, sql_join_edge_id""",
                [repo_id, query_id, scope_id],
            )) if self._has_relation('sql_join_edge') else []

            projection_rows = self._rows(con.execute(
                """SELECT sql_projection_id, repo_id, query_id, scope_id, file, line_start,
                          projection_ordinal, output_name, expression, expression_kind,
                          is_wildcard, source_column_count, source_column_usage_ids_json,
                          resolution_status, resolution_basis,
                          evidence_maturity_level, evidence_json
                     FROM sql_projection
                    WHERE repo_id=? AND query_id=? AND scope_id=?
                    ORDER BY projection_ordinal, sql_projection_id
                    LIMIT 200""",
                [repo_id, query_id, scope_id],
            )) if self._has_relation('sql_projection') else []

        fields_by_relation: dict[str, dict[str, set[str]]] = {}
        for row in resolved_usage_rows:
            relation_id = str(row.get('relation_id') or '')
            column_name = str(row.get('column_name') or '')
            usage_role = str(row.get('usage_role') or '')
            if not relation_id or not column_name:
                continue
            fields_by_relation.setdefault(relation_id, {}).setdefault(column_name, set())
            if usage_role:
                fields_by_relation[relation_id][column_name].add(usage_role)
        for relation in relation_rows:
            field_map = fields_by_relation.get(str(relation.get('sql_relation_id') or ''), {})
            relation['observed_fields'] = [
                {'name': name, 'usage_roles': sorted(roles)}
                for name, roles in sorted(field_map.items())
            ]

        return {
            'kind': 'knowledge-layer-sql-column-usage-context',
            'sql_column_usage_id': usage_id,
            'usage': usage,
            'statement': statement_rows[0] if statement_rows else None,
            'scope': scope_rows[0] if scope_rows else None,
            'scope_relations': relation_rows,
            'joins': join_rows,
            'projections': projection_rows,
            'counts': {
                'scope_relations': len(relation_rows),
                'joins': len(join_rows),
                'projections': len(projection_rows),
            },
        }

    def get_sql_query_context(
        self,
        *,
        repo_id: str,
        query_id: str,
        scope_id: str | None = None,
    ) -> dict[str, Any]:
        """Return one observed SQL query/scope with its relations, joins and projections.

        Without ``scope_id`` the unique root SELECT scope is selected. Multiple roots are
        returned as explicit candidates rather than guessed. No SQL is parsed at query time.
        """
        repo = str(repo_id or '').strip()
        query = str(query_id or '').strip()
        requested_scope = None if scope_id is None else str(scope_id).strip()
        if not repo:
            raise ValueError('repo_id is required')
        if not query:
            raise ValueError('query_id is required')
        if scope_id is not None and not requested_scope:
            raise ValueError('scope_id must not be empty when provided')
        if not self._has_relation('sql_select_scope'):
            return {
                'kind': 'knowledge-layer-sql-query-context',
                'schema_version': 'sql-query-context/v1',
                'repo_id': repo,
                'query_id': query,
                'not_available': True,
                'capability': 'common.sql-analysis',
            }
        with self._connect() as con:
            all_scope_rows = self._rows(con.execute(
                """SELECT sql_select_scope_id,repo_id,query_id,file,line_start,parent_scope_id,
                          scope_kind,scope_name,scope_ordinal,expression_index,relation_count,
                          projection_count,column_usage_count,evidence_maturity_level,evidence_json
                     FROM sql_select_scope WHERE repo_id=? AND query_id=?
                    ORDER BY scope_ordinal,sql_select_scope_id""",
                [repo, query],
            ))
            if not all_scope_rows:
                return {
                    'kind': 'knowledge-layer-sql-query-context',
                    'schema_version': 'sql-query-context/v1',
                    'repo_id': repo,
                    'query_id': query,
                    'not_found': True,
                    'scope_candidates': [],
                    'diagnostics': ['sql_query_not_found'],
                }
            if requested_scope is not None:
                candidates = [row for row in all_scope_rows if str(row.get('sql_select_scope_id') or '') == requested_scope]
            else:
                candidates = [row for row in all_scope_rows if not row.get('parent_scope_id')]
            if len(candidates) != 1:
                return {
                    'kind': 'knowledge-layer-sql-query-context',
                    'schema_version': 'sql-query-context/v1',
                    'repo_id': repo,
                    'query_id': query,
                    'scope_id': requested_scope,
                    'selection_status': 'not_found' if not candidates else 'ambiguous',
                    'scope_candidates': candidates,
                    'diagnostics': ['sql_scope_not_found' if not candidates else 'multiple_sql_scope_candidates'],
                }
            scope = candidates[0]
            selected_scope = str(scope.get('sql_select_scope_id') or '')
            statement_rows = self._rows(con.execute(
                """SELECT sql_statement_id,repo_id,query_id,file,line_start,line_end,operation,
                          statement_type,target_relation_name,unit_kind,evidence_maturity_level,evidence_json
                     FROM sql_statement WHERE repo_id=? AND query_id=?
                    ORDER BY line_start,sql_statement_id LIMIT 1""",
                [repo, query],
            )) if self._has_relation('sql_statement') else []
            relation_rows = self._rows(con.execute(
                """SELECT sql_relation_id,repo_id,query_id,scope_id,file,line_start,relation_kind,
                          relation_name,template_name,logical_name,alias,usage_role,definition_status,
                          source_scope_ids_json,placeholder_refs_json,evidence_maturity_level,evidence_json
                     FROM sql_relation WHERE repo_id=? AND query_id=? AND scope_id=?
                    ORDER BY relation_kind,relation_name,alias,sql_relation_id""",
                [repo, query, selected_scope],
            )) if self._has_relation('sql_relation') else []
            resolved_usage_rows = self._rows(con.execute(
                """SELECT relation_id,column_name,usage_role,resolution_status
                     FROM sql_column_usage WHERE repo_id=? AND query_id=? AND scope_id=?
                       AND relation_id IS NOT NULL
                    ORDER BY relation_id,column_name,usage_role""",
                [repo, query, selected_scope],
            )) if self._has_relation('sql_column_usage') else []
            join_rows = self._rows(con.execute(
                """SELECT sql_join_edge_id,repo_id,query_id,scope_id,file,line_start,join_ordinal,
                          join_type,condition_kind,predicate,left_relation_id,left_relation_ids_json,
                          left_relation_names_json,right_relation_id,right_relation_kind,right_relation_name,
                          participating_relation_ids_json,column_pairs_json,expression_links_json,using_columns_json,
                          additional_predicates_json,temporal_or_range_predicates_json,resolution_status,
                          resolution_reasons_json,physical_join_confirmed,evidence_maturity_level,evidence_json
                     FROM sql_join_edge WHERE repo_id=? AND query_id=? AND scope_id=?
                    ORDER BY join_ordinal,sql_join_edge_id""",
                [repo, query, selected_scope],
            )) if self._has_relation('sql_join_edge') else []
            projection_rows = self._rows(con.execute(
                """SELECT sql_projection_id,repo_id,query_id,scope_id,file,line_start,projection_ordinal,
                          output_name,expression,expression_kind,is_wildcard,source_column_count,
                          source_column_usage_ids_json,resolution_status,resolution_basis,
                          evidence_maturity_level,evidence_json
                     FROM sql_projection WHERE repo_id=? AND query_id=? AND scope_id=?
                    ORDER BY projection_ordinal,sql_projection_id LIMIT 500""",
                [repo, query, selected_scope],
            )) if self._has_relation('sql_projection') else []

        fields_by_relation: dict[str, dict[str, set[str]]] = {}
        for row in resolved_usage_rows:
            relation_id = str(row.get('relation_id') or '')
            column_name = str(row.get('column_name') or '')
            usage_role = str(row.get('usage_role') or '')
            if not relation_id or not column_name:
                continue
            fields_by_relation.setdefault(relation_id, {}).setdefault(column_name, set())
            if usage_role:
                fields_by_relation[relation_id][column_name].add(usage_role)
        for relation in relation_rows:
            field_map = fields_by_relation.get(str(relation.get('sql_relation_id') or ''), {})
            relation['observed_fields'] = [
                {'name': name, 'usage_roles': sorted(roles)}
                for name, roles in sorted(field_map.items())
            ]
        child_scopes = [
            row for row in all_scope_rows if str(row.get('parent_scope_id') or '') == selected_scope
        ]
        return {
            'kind': 'knowledge-layer-sql-query-context',
            'schema_version': 'sql-query-context/v1',
            'repo_id': repo,
            'query_id': query,
            'scope_id': selected_scope,
            'selection_status': 'selected',
            'statement': statement_rows[0] if statement_rows else None,
            'scope': scope,
            'child_scopes': child_scopes,
            'scope_relations': relation_rows,
            'joins': join_rows,
            'projections': projection_rows,
            'counts': {
                'child_scopes': len(child_scopes),
                'scope_relations': len(relation_rows),
                'joins': len(join_rows),
                'projections': len(projection_rows),
            },
            'diagnostics': [],
        }

    def sql_relation_semantic_role_coverage(self, *, repo_id: str | None = None) -> dict[str, Any]:
        if not self._has_relation('sql_relation_semantic_role'):
            return {'status': 'not_available', 'total_relations': 0, 'hidden_by_default': 0, 'by_role': {}, 'by_status': {}}
        clauses = ['1=1']
        args: list[Any] = []
        if repo_id:
            clauses.append('repo_id=?')
            args.append(repo_id)
        where = ' AND '.join(clauses)
        with self._connect() as con:
            total, hidden = con.execute(
                f'SELECT count(*), count(*) FILTER (WHERE hidden_by_default) FROM sql_relation_semantic_role WHERE {where}',
                args,
            ).fetchone()
            role_rows = con.execute(
                f'SELECT semantic_role, count(*) FROM sql_relation_semantic_role WHERE {where} GROUP BY semantic_role ORDER BY semantic_role',
                args,
            ).fetchall()
            status_rows = con.execute(
                f'SELECT classification_status, count(*) FROM sql_relation_semantic_role WHERE {where} GROUP BY classification_status ORDER BY classification_status',
                args,
            ).fetchall()
        return {
            'status': 'complete',
            'total_relations': int(total or 0),
            'hidden_by_default': int(hidden or 0),
            'visible_by_default': int((total or 0) - (hidden or 0)),
            'by_role': {str(key): int(value) for key, value in role_rows},
            'by_status': {str(key): int(value) for key, value in status_rows},
        }

    def sql_source_inventory_coverage(self, *, repo_id: str | None = None) -> dict[str, Any]:
        """Summarize source-table field resolution without counting non-source values as failures."""
        if not self._has_relation('sql_column_usage'):
            return {
                'status': 'not_available',
                'column_usages': {
                    'total': 0,
                    'relation_field_candidates': 0,
                    'resolved_relation_fields': 0,
                    'unresolved_relation_fields': 0,
                    'relation_field_resolution_rate': 1.0,
                },
                'resolved_by_relation_kind': {},
                'non_source_values': {},
                'limitations': {},
                'coverage_policy': (
                    'semantic parameters, projection outputs and generated LATERAL/EXPLODE values '
                    'do not reduce source-field resolution'
                ),
            }
        clauses = ['1=1']
        args: list[Any] = []
        if repo_id:
            clauses.append('repo_id=?')
            args.append(repo_id)
        where = ' AND '.join(clauses)
        generated_predicate = (
            "(coalesce(relation_kind,'')='generated' "
            "OR coalesce(resolution_basis,'') LIKE 'generated_alias%')"
        )
        with self._connect() as con:
            (total, semantic_parameters, projection_outputs, generated_fields,
             resolved, unresolved) = con.execute(
                f"""
                SELECT count(*),
                       count(*) FILTER (WHERE resolution_status='semantic_parameter'),
                       count(*) FILTER (WHERE resolution_status='projection_output'),
                       count(*) FILTER (WHERE {generated_predicate}),
                       count(*) FILTER (
                           WHERE relation_id IS NOT NULL AND NOT {generated_predicate}
                       ),
                       count(*) FILTER (
                           WHERE relation_id IS NULL
                             AND resolution_status NOT IN ('semantic_parameter', 'projection_output')
                       )
                  FROM sql_column_usage
                 WHERE {where}
                """,
                args,
            ).fetchone()
            kind_rows = con.execute(
                f"""
                SELECT coalesce(relation_kind, 'unknown') AS relation_kind, count(*)
                  FROM sql_column_usage
                 WHERE {where}
                   AND relation_id IS NOT NULL
                   AND NOT {generated_predicate}
                 GROUP BY relation_kind
                 ORDER BY relation_kind
                """,
                args,
            ).fetchall()
            limitation_rows = con.execute(
                f"""
                SELECT coalesce(resolution_basis, 'unknown') AS resolution_basis, count(*)
                  FROM sql_column_usage
                 WHERE {where}
                   AND relation_id IS NULL
                   AND resolution_status NOT IN ('semantic_parameter', 'projection_output')
                 GROUP BY resolution_basis
                 ORDER BY resolution_basis
                """,
                args,
            ).fetchall()
        candidate_count = int((resolved or 0) + (unresolved or 0))
        resolution_rate = 1.0 if candidate_count == 0 else int(resolved or 0) / candidate_count
        return {
            'status': 'complete' if int(unresolved or 0) == 0 else 'partial',
            'column_usages': {
                'total': int(total or 0),
                'relation_field_candidates': candidate_count,
                'resolved_relation_fields': int(resolved or 0),
                'unresolved_relation_fields': int(unresolved or 0),
                'relation_field_resolution_rate': resolution_rate,
            },
            'resolved_by_relation_kind': {str(key): int(value) for key, value in kind_rows},
            'non_source_values': {
                'semantic_parameters': int(semantic_parameters or 0),
                'projection_outputs': int(projection_outputs or 0),
                'generated_fields': int(generated_fields or 0),
            },
            'limitations': {str(key): int(value) for key, value in limitation_rows},
            'coverage_policy': (
                'semantic parameters, projection outputs and generated LATERAL/EXPLODE values '
                'do not reduce source-field resolution'
            ),
        }

    def sql_analysis_coverage(self, *, repo_id: str | None = None) -> dict[str, Any]:
        if not self._has_relation('sql_analysis_repository'):
            return {'analysis_status': 'not_available', 'repositories': []}
        clauses = ['1=1']
        args: list[Any] = []
        if repo_id:
            clauses.append('repo_id=?')
            args.append(repo_id)
        where = ' AND '.join(clauses)
        with self._connect() as con:
            rows = self._rows(con.execute(
                'SELECT repo_id, analysis_status, source_schema_version, '
                'source_content_fingerprint, coverage_json '
                f'FROM sql_analysis_repository WHERE {where} ORDER BY repo_id',
                args,
            ))
        statuses = {str(row.get('analysis_status') or 'unknown') for row in rows}
        overall = next(iter(statuses)) if len(statuses) == 1 else ('partial' if rows else 'not_available')
        return {'analysis_status': overall, 'repositories': rows}

    def search_subject_records(self, *, token: str='', repo_id: str | None=None, materialization_id: str | None=None, artifact_name: str | None=None, record_kind: str | None=None, max_results: int=100, page_token: str='') -> dict[str, Any]:
        filters = {'token': token, 'repo_id': repo_id, 'materialization_id': materialization_id, 'artifact_name': artifact_name, 'record_kind': record_kind}
        if not self._has_relation('subject_knowledge_record'):
            return self._empty_page(kind='knowledge-layer-subject-records', query_id='subject_records', filters=filters, max_results=max_results, page_token=page_token)
        clauses = ['1=1']
        args: list[Any] = []
        if token:
            clauses.append("lower(coalesce(search_text,'')) LIKE ?")
            args.append(f'%{token.lower()}%')
        if repo_id:
            clauses.append('repo_id=?')
            args.append(repo_id)
        if materialization_id:
            clauses.append('materialization_id=?')
            args.append(materialization_id)
        if artifact_name:
            clauses.append('artifact_name=?')
            args.append(artifact_name)
        if record_kind:
            clauses.append('record_kind=?')
            args.append(record_kind)
        where = ' AND '.join(clauses)
        return self._paged_select(kind='knowledge-layer-subject-records', query_id='subject_records', select_sql=f'SELECT * FROM subject_knowledge_record WHERE {where} ORDER BY repo_id, materialization_id, artifact_name, occurrence_ordinal, record_occurrence_id', count_sql=f'SELECT count(*) FROM subject_knowledge_record WHERE {where}', args=args, filters=filters, max_results=max_results, page_token=page_token)

    def system_interfaces(self, **kwargs: Any) -> dict[str, Any]:
        kwargs.setdefault('materialization_id', 'system-description')
        kwargs.setdefault('artifact_name', 'system_interface_catalog.json')
        result = self.search_subject_records(**kwargs)
        result['kind'] = 'knowledge-layer-system-interfaces'
        return result

    def system_scenarios(self, **kwargs: Any) -> dict[str, Any]:
        kwargs.setdefault('materialization_id', 'system-description')
        kwargs.setdefault('artifact_name', 'system_scenarios.json')
        result = self.search_subject_records(**kwargs)
        result['kind'] = 'knowledge-layer-system-scenarios'
        return result

    def system_interactions(
        self,
        *,
        source_repo_id: str | None = None,
        target_repo_id: str | None = None,
        protocol: str | None = None,
        max_results: int = 100,
        page_token: str = '',
    ) -> dict[str, Any]:
        filters = {
            'source_repo_id': source_repo_id,
            'target_repo_id': target_repo_id,
            'protocol': protocol,
        }
        if not self._has_relation('system_interaction'):
            return self._empty_page(
                kind='knowledge-layer-system-interactions',
                query_id='system_interactions',
                filters=filters,
                max_results=max_results,
                page_token=page_token,
            )
        clauses = ['1=1']
        args: list[Any] = []
        if source_repo_id:
            clauses.append('source_repo_id=?')
            args.append(source_repo_id)
        if target_repo_id:
            clauses.append('target_repo_id=?')
            args.append(target_repo_id)
        if protocol:
            clauses.append('protocol=?')
            args.append(protocol)
        where = ' AND '.join(clauses)
        return self._paged_select(
            kind='knowledge-layer-system-interactions',
            query_id='system_interactions',
            select_sql=(
                'SELECT interaction_id, scope_id, source_repo_id, target_repo_id, '
                'protocol, operation_count, execution_context_count, match_status, confidence, boundary_interaction_ids_json '
                f'FROM system_interaction WHERE {where} '
                'ORDER BY source_repo_id, target_repo_id, protocol, interaction_id'
            ),
            count_sql=f'SELECT count(*) FROM system_interaction WHERE {where}',
            args=args,
            filters=filters,
            max_results=max_results,
            page_token=page_token,
        )

    def repository_interaction_boundaries(
        self,
        *,
        repo_id: str | None = None,
        system_id: str | None = None,
        project_id: str | None = None,
        direction: str | None = None,
        protocol: str | None = None,
        http_method: str | None = None,
        service_identity: str | None = None,
        max_results: int = 100,
        page_token: str = '',
    ) -> dict[str, Any]:
        filters = {
            'repo_id': repo_id,
            'system_id': system_id,
            'project_id': project_id,
            'direction': direction,
            'protocol': protocol,
            'http_method': http_method,
            'service_identity': service_identity,
        }
        if not self._has_relation('repository_interaction_boundary'):
            return self._empty_page(
                kind='knowledge-layer-repository-interaction-boundaries',
                query_id='repository_interaction_boundaries',
                filters=filters,
                max_results=max_results,
                page_token=page_token,
            )
        clauses = ['1=1']
        args: list[Any] = []
        for name in ('repo_id', 'system_id', 'project_id', 'direction', 'protocol', 'http_method'):
            value = filters[name]
            if value:
                clauses.append(f'{name}=?')
                args.append(value)
        if service_identity:
            clauses.append('lower(CAST(service_identities_json AS VARCHAR)) LIKE ?')
            args.append(f'%{service_identity.casefold()}%')
        where = ' AND '.join(clauses)
        return self._paged_select(
            kind='knowledge-layer-repository-interaction-boundaries',
            query_id='repository_interaction_boundaries',
            select_sql=(
                'SELECT boundary_id, scope_id, repo_id, system_id, project_id, '
                'configured_service_aliases_json, interface_id, direction, boundary_kind, '
                'protocol, operation, http_method, normalized_paths_json, authorities_json, '
                'service_identities_json, property_identities_json, base_url_property_keys_json, '
                'contract_fingerprint, provenance_json '
                f'FROM repository_interaction_boundary WHERE {where} '
                'ORDER BY repo_id, direction, protocol, operation, interface_id'
            ),
            count_sql=f'SELECT count(*) FROM repository_interaction_boundary WHERE {where}',
            args=args,
            filters=filters,
            max_results=max_results,
            page_token=page_token,
        )

    def system_boundary_interactions(
        self,
        *,
        interaction_id: str | None = None,
        source_repo_id: str | None = None,
        target_repo_id: str | None = None,
        match_status: str | None = None,
        confidence: str | None = None,
        local_execution_status: str | None = None,
        max_results: int = 100,
        page_token: str = '',
    ) -> dict[str, Any]:
        filters = {
            'interaction_id': interaction_id,
            'source_repo_id': source_repo_id,
            'target_repo_id': target_repo_id,
            'match_status': match_status,
            'confidence': confidence,
            'local_execution_status': local_execution_status,
        }
        if not self._has_relation('system_boundary_interaction'):
            return self._empty_page(
                kind='knowledge-layer-system-boundary-interactions',
                query_id='system_boundary_interactions',
                filters=filters,
                max_results=max_results,
                page_token=page_token,
            )
        clauses = ['1=1']
        args: list[Any] = []
        for name, value in filters.items():
            if value:
                clauses.append(f'{name}=?')
                args.append(value)
        where = ' AND '.join(clauses)
        return self._paged_select(
            kind='knowledge-layer-system-boundary-interactions',
            query_id='system_boundary_interactions',
            select_sql=(
                'SELECT boundary_interaction_id, interaction_id, scope_id, source_repo_id, '
                'outbound_interface_id, outbound_operation, http_method, outbound_endpoint, '
                'target_repo_id, target_ingress_interface_id, target_ingress_operation, '
                'target_ingress_endpoint, protocol, match_status, confidence, '
                'local_execution_status, match_basis_json, provenance_json, payload_json '
                f'FROM system_boundary_interaction WHERE {where} '
                'ORDER BY source_repo_id, outbound_operation, target_repo_id, '
                'target_ingress_operation, boundary_interaction_id'
            ),
            count_sql=f'SELECT count(*) FROM system_boundary_interaction WHERE {where}',
            args=args,
            filters=filters,
            max_results=max_results,
            page_token=page_token,
        )

    def system_interaction_execution_contexts(
        self,
        *,
        boundary_interaction_id: str | None = None,
        interaction_id: str | None = None,
        source_repo_id: str | None = None,
        trigger_kind: str | None = None,
        path_status: str | None = None,
        max_results: int = 100,
        page_token: str = '',
    ) -> dict[str, Any]:
        filters = {
            'boundary_interaction_id': boundary_interaction_id,
            'interaction_id': interaction_id,
            'source_repo_id': source_repo_id,
            'trigger_kind': trigger_kind,
            'path_status': path_status,
        }
        if not self._has_relation('system_interaction_execution_context'):
            return self._empty_page(
                kind='knowledge-layer-system-interaction-execution-contexts',
                query_id='system_interaction_execution_contexts',
                filters=filters,
                max_results=max_results,
                page_token=page_token,
            )
        clauses = ['1=1']
        args: list[Any] = []
        for name, value in filters.items():
            if value:
                clauses.append(f'{name}=?')
                args.append(value)
        where = ' AND '.join(clauses)
        return self._paged_select(
            kind='knowledge-layer-system-interaction-execution-contexts',
            query_id='system_interaction_execution_contexts',
            select_sql=(
                'SELECT execution_context_id, boundary_interaction_id, interaction_id, scope_id, '
                'source_repo_id, source_ingress_interface_id, source_ingress_operation, '
                'source_ingress_endpoint, outbound_interface_id, outbound_operation, '
                'trigger_kind, path_status, call_chain_length, call_chain_json, provenance_json, payload_json '
                f'FROM system_interaction_execution_context WHERE {where} '
                'ORDER BY source_repo_id, source_ingress_operation, outbound_operation, execution_context_id'
            ),
            count_sql=f'SELECT count(*) FROM system_interaction_execution_context WHERE {where}',
            args=args,
            filters=filters,
            max_results=max_results,
            page_token=page_token,
        )

    def system_interaction_field_contracts(
        self,
        *,
        boundary_interaction_id: str | None = None,
        interaction_id: str | None = None,
        source_repo_id: str | None = None,
        target_repo_id: str | None = None,
        wire_path: str | None = None,
        match_status: str | None = None,
        max_results: int = 100,
        page_token: str = '',
    ) -> dict[str, Any]:
        filters = {
            'boundary_interaction_id': boundary_interaction_id,
            'interaction_id': interaction_id,
            'source_repo_id': source_repo_id,
            'target_repo_id': target_repo_id,
            'wire_path': wire_path,
            'match_status': match_status,
        }
        if not self._has_relation('system_interaction_field_contract'):
            return self._empty_page(
                kind='knowledge-layer-system-interaction-field-contracts',
                query_id='system_interaction_field_contracts',
                filters=filters,
                max_results=max_results,
                page_token=page_token,
            )
        clauses = ['1=1']
        args: list[Any] = []
        for name, value in filters.items():
            if value:
                clauses.append(f'{name}=?')
                args.append(value)
        where = ' AND '.join(clauses)
        return self._paged_select(
            kind='knowledge-layer-system-interaction-field-contracts',
            query_id='system_interaction_field_contracts',
            select_sql=(
                'SELECT field_contract_id, boundary_interaction_id, interaction_id, scope_id, '
                'source_repo_id, outbound_interface_id, outbound_operation, outbound_payload_type, '
                'outbound_field_path, outbound_attribute_name, outbound_wire_name, outbound_field_type, '
                'outbound_source_schema, target_repo_id, target_ingress_interface_id, '
                'target_ingress_operation, target_payload_type, target_field_path, target_attribute_name, '
                'target_wire_name, target_field_type, target_source_schema, wire_path, match_kind, '
                'match_status, type_compatibility, provenance_json, payload_json '
                f'FROM system_interaction_field_contract WHERE {where} '
                'ORDER BY source_repo_id, outbound_operation, target_repo_id, target_ingress_operation, wire_path, field_contract_id'
            ),
            count_sql=f'SELECT count(*) FROM system_interaction_field_contract WHERE {where}',
            args=args,
            filters=filters,
            max_results=max_results,
            page_token=page_token,
        )

    def repository_value_nodes(
        self,
        *,
        repo_id: str | None = None,
        node_kind: str | None = None,
        operation: str | None = None,
        max_results: int = 100,
        page_token: str = '',
    ) -> dict[str, Any]:
        filters = {
            'repo_id': repo_id,
            'node_kind': node_kind,
            'operation': operation,
        }
        if not self._has_relation('repository_value_node'):
            return self._empty_page(
                kind='knowledge-layer-repository-value-nodes',
                query_id='repository_value_nodes',
                filters=filters,
                max_results=max_results,
                page_token=page_token,
            )
        clauses = ['1=1']
        args: list[Any] = []
        for name, value in filters.items():
            if value:
                clauses.append(f'{name}=?')
                args.append(value)
        where = ' AND '.join(clauses)
        return self._paged_select(
            kind='knowledge-layer-repository-value-nodes',
            query_id='repository_value_nodes',
            select_sql=(
                'SELECT value_node_id, scope_id, repo_id, occurrence_id, node_kind, operation, '
                'owner_ref, display_ref, type_ref, wire_path, source_path, provenance_json '
                f'FROM repository_value_node WHERE {where} '
                'ORDER BY repo_id, operation, node_kind, display_ref, value_node_id'
            ),
            count_sql=f'SELECT count(*) FROM repository_value_node WHERE {where}',
            args=args,
            filters=filters,
            max_results=max_results,
            page_token=page_token,
        )

    def repository_value_flow_edges(
        self,
        *,
        repo_id: str | None = None,
        source_repo_id: str | None = None,
        target_repo_id: str | None = None,
        flow_kind: str | None = None,
        transformation_kind: str | None = None,
        naming_relation: str | None = None,
        value_preservation: str | None = None,
        confidence: str | None = None,
        knowledge_class: str | None = None,
        knowledge_view: str = "exploratory",
        derivation_id: str | None = None,
        derivation_kind: str | None = None,
        max_results: int = 100,
        page_token: str = '',
    ) -> dict[str, Any]:
        knowledge_view = str(knowledge_view or "exploratory").strip().casefold()
        view_relations = {
            "strict": "repository_value_flow_edge_strict",
            "working": "repository_value_flow_edge_working",
            "exploratory": "repository_value_flow_edge_exploratory",
        }
        if knowledge_view not in view_relations:
            raise ValueError("knowledge_view must be one of: strict, working, exploratory")
        if knowledge_class is not None:
            knowledge_class = str(knowledge_class).strip().casefold()
            if knowledge_class not in {"confirmed", "derived", "candidate"}:
                raise ValueError("knowledge_class must be one of: confirmed, derived, candidate")
        relation = view_relations[knowledge_view]
        filters = {
            'repo_id': repo_id,
            'source_repo_id': source_repo_id,
            'target_repo_id': target_repo_id,
            'flow_kind': flow_kind,
            'transformation_kind': transformation_kind,
            'naming_relation': naming_relation,
            'value_preservation': value_preservation,
            'confidence': confidence,
            'knowledge_class': knowledge_class,
            'knowledge_view': knowledge_view,
            'derivation_id': derivation_id,
            'derivation_kind': derivation_kind,
        }
        if not self._has_relation(relation):
            return self._empty_page(
                kind='knowledge-layer-repository-value-flow-edges',
                query_id='repository_value_flow_edges',
                filters=filters,
                max_results=max_results,
                page_token=page_token,
            )
        clauses = ['1=1']
        args: list[Any] = []
        if repo_id:
            clauses.append('(source_repo_id=? OR target_repo_id=?)')
            args.extend([repo_id, repo_id])
        for name, value in filters.items():
            if name in {'repo_id', 'knowledge_view'} or not value:
                continue
            clauses.append(f'{name}=?')
            args.append(value)
        where = ' AND '.join(clauses)
        return self._paged_select(
            kind='knowledge-layer-repository-value-flow-edges',
            query_id='repository_value_flow_edges',
            select_sql=(
                'SELECT value_flow_edge_id, scope_id, source_repo_id, target_repo_id, source_value_node_id, '
                'target_value_node_id, source_occurrence_id, target_occurrence_id, flow_kind, '
                'source_edge_kind, transformation_kind, naming_relation, value_preservation, '
                'confidence, knowledge_class, derivation_id, derivation_kind, derivation_source_count, guards_json, provenance_json, payload_json '
                f'FROM {relation} WHERE {where} '
                'ORDER BY source_repo_id, target_repo_id, flow_kind, source_occurrence_id, target_occurrence_id, value_flow_edge_id'
            ),
            count_sql=f'SELECT count(*) FROM {relation} WHERE {where}',
            args=args,
            filters=filters,
            max_results=max_results,
            page_token=page_token,
        )

    def repository_interaction_coverage(
        self,
        *,
        repo_id: str | None = None,
        system_id: str | None = None,
        project_id: str | None = None,
        coverage_status: str | None = None,
        matching_coverage_status: str | None = None,
        max_results: int = 100,
        page_token: str = '',
    ) -> dict[str, Any]:
        filters = {
            'repo_id': repo_id,
            'system_id': system_id,
            'project_id': project_id,
            'coverage_status': coverage_status,
            'matching_coverage_status': matching_coverage_status,
        }
        if not self._has_relation('repository_interaction_coverage'):
            return self._empty_page(
                kind='knowledge-layer-repository-interaction-coverage',
                query_id='repository_interaction_coverage',
                filters=filters,
                max_results=max_results,
                page_token=page_token,
            )
        clauses = ['1=1']
        args: list[Any] = []
        for name, value in filters.items():
            if value:
                clauses.append(f'{name}=?')
                args.append(value)
        where = ' AND '.join(clauses)
        return self._paged_select(
            kind='knowledge-layer-repository-interaction-coverage',
            query_id='repository_interaction_coverage',
            select_sql=(
                'SELECT coverage_id, scope_id, repo_id, system_id, project_id, analysis_status, '
                'inbound_boundary_count, outbound_boundary_count, matched_outbound_count, '
                'confirmed_outbound_count, probable_outbound_count, ambiguous_outbound_count, '
                'unresolved_outbound_count, matching_coverage_status, coverage_status '
                f'FROM repository_interaction_coverage WHERE {where} '
                'ORDER BY coverage_status DESC, matching_coverage_status DESC, repo_id'
            ),
            count_sql=f'SELECT count(*) FROM repository_interaction_coverage WHERE {where}',
            args=args,
            filters=filters,
            max_results=max_results,
            page_token=page_token,
        )

    def repository_interaction_islands(
        self,
        *,
        mode: str | None = None,
        minimum_node_count: int | None = None,
        coverage_status: str | None = None,
        max_results: int = 100,
        page_token: str = '',
    ) -> dict[str, Any]:
        filters = {
            'mode': mode,
            'minimum_node_count': minimum_node_count,
            'coverage_status': coverage_status,
        }
        if not self._has_relation('repository_interaction_island'):
            return self._empty_page(
                kind='knowledge-layer-repository-interaction-islands',
                query_id='repository_interaction_islands',
                filters=filters,
                max_results=max_results,
                page_token=page_token,
            )
        clauses = ['1=1']
        args: list[Any] = []
        if mode:
            clauses.append('mode=?')
            args.append(mode)
        if minimum_node_count is not None:
            clauses.append('node_count>=?')
            args.append(int(minimum_node_count))
        if coverage_status:
            clauses.append('coverage_status=?')
            args.append(coverage_status)
        where = ' AND '.join(clauses)
        return self._paged_select(
            kind='knowledge-layer-repository-interaction-islands',
            query_id='repository_interaction_islands',
            select_sql=(
                'SELECT island_id, scope_id, mode, node_count, edge_count, project_count, '
                'protocols_json, confirmed_edge_count, probable_edge_count, completed_node_count, '
                'incomplete_node_count, inbound_boundary_count, outbound_boundary_count, '
                'matched_outbound_count, confirmed_outbound_count, probable_outbound_count, '
                'ambiguous_outbound_count, unresolved_outbound_count, analysis_coverage_status, '
                'matching_coverage_status, coverage_status '
                f'FROM repository_interaction_island WHERE {where} '
                'ORDER BY mode, node_count DESC, edge_count DESC, island_id'
            ),
            count_sql=f'SELECT count(*) FROM repository_interaction_island WHERE {where}',
            args=args,
            filters=filters,
            max_results=max_results,
            page_token=page_token,
        )

    def repository_interaction_island_members(
        self,
        *,
        island_id: str | None = None,
        mode: str | None = None,
        repo_id: str | None = None,
        max_results: int = 100,
        page_token: str = '',
    ) -> dict[str, Any]:
        filters = {'island_id': island_id, 'mode': mode, 'repo_id': repo_id}
        if not self._has_relation('repository_interaction_island_member'):
            return self._empty_page(
                kind='knowledge-layer-repository-interaction-island-members',
                query_id='repository_interaction_island_members',
                filters=filters,
                max_results=max_results,
                page_token=page_token,
            )
        clauses = ['1=1']
        args: list[Any] = []
        for name, value in filters.items():
            if value:
                clauses.append(f'{name}=?')
                args.append(value)
        where = ' AND '.join(clauses)
        return self._paged_select(
            kind='knowledge-layer-repository-interaction-island-members',
            query_id='repository_interaction_island_members',
            select_sql=(
                'SELECT island_member_id, island_id, scope_id, mode, node_id, repo_id, '
                'system_id, project_id, inbound_degree, outbound_degree, total_degree, '
                'analysis_status '
                f'FROM repository_interaction_island_member WHERE {where} '
                'ORDER BY island_id, total_degree DESC, repo_id, island_member_id'
            ),
            count_sql=f'SELECT count(*) FROM repository_interaction_island_member WHERE {where}',
            args=args,
            filters=filters,
            max_results=max_results,
            page_token=page_token,
        )

    def system_interaction_diagnostics(
        self,
        *,
        source_repo_id: str | None = None,
        match_status: str | None = None,
        max_results: int = 100,
        page_token: str = '',
    ) -> dict[str, Any]:
        filters = {'source_repo_id': source_repo_id, 'match_status': match_status}
        if not self._has_relation('system_interaction_match_diagnostic'):
            return self._empty_page(
                kind='knowledge-layer-system-interaction-diagnostics',
                query_id='system_interaction_diagnostics',
                filters=filters,
                max_results=max_results,
                page_token=page_token,
            )
        clauses = ['1=1']
        args: list[Any] = []
        if source_repo_id:
            clauses.append('source_repo_id=?')
            args.append(source_repo_id)
        if match_status:
            clauses.append('match_status=?')
            args.append(match_status)
        where = ' AND '.join(clauses)
        return self._paged_select(
            kind='knowledge-layer-system-interaction-diagnostics',
            query_id='system_interaction_diagnostics',
            select_sql=(
                'SELECT diagnostic_id, scope_id, source_repo_id, outbound_interface_id, '
                'outbound_operation, protocol, http_method, outbound_paths_json, '
                'match_status, confidence, candidate_matches_json '
                f'FROM system_interaction_match_diagnostic WHERE {where} '
                'ORDER BY source_repo_id, outbound_operation, outbound_interface_id'
            ),
            count_sql=f'SELECT count(*) FROM system_interaction_match_diagnostic WHERE {where}',
            args=args,
            filters=filters,
            max_results=max_results,
            page_token=page_token,
        )

    def system_interaction_graph(self) -> dict[str, Any]:
        nodes: list[dict[str, Any]] = []
        return {
            'kind': 'knowledge-layer-system-interaction-graph',
            'schema_version': 'workspace_system_interaction/v5',
            'nodes': nodes,
            'system_edges': interactions['items'],
            'boundary_edges': boundary_interactions['items'],
            'execution_contexts': execution_contexts['items'],
            'repository_coverage': repository_coverage['items'],
            'strict_islands': strict_islands['items'],
            'extended_islands': extended_islands['items'],
            'summary': {
                'node_count': len(nodes),
                'system_edge_count': interactions['total_count'],
                'boundary_edge_count': boundary_interactions['total_count'],
                'execution_context_count': execution_contexts['total_count'],
                'repository_coverage_count': repository_coverage['total_count'],
                'strict_island_count': strict_islands['total_count'],
                'extended_island_count': extended_islands['total_count'],
                'request_field_contract_count': field_contracts['total_count'],
                'repository_value_node_count': value_nodes['total_count'],
                'repository_value_flow_edge_count': value_flow_edges['total_count'],
                'outbound_match_status_counts': dict(sorted(status_counts.items())),
            },
        }

    def reference_data_records(self, **kwargs: Any) -> dict[str, Any]:
        kwargs.setdefault('materialization_id', 'reference-data')
        result = self.search_subject_records(**kwargs)
        result['kind'] = 'knowledge-layer-reference-data-records'
        return result


    def persistence_lineage_records(self, **kwargs: Any) -> dict[str, Any]:
        kwargs.setdefault('materialization_id', 'persistence-lineage')
        result = self.search_subject_records(**kwargs)
        result['kind'] = 'knowledge-layer-persistence-lineage-records'
        return result

    def fdp_paths(
        self, *, token: str='', repo_id: str | None=None,
        direction: str | None=None, max_results: int=100, page_token: str=''
    ) -> dict[str, Any]:
        mapping = {
            'source-to-storage': 'source_to_storage_lineage.json',
            'storage-to-access': 'storage_to_access_lineage.json',
        }
        artifact_name = mapping.get(direction) if direction else None
        if direction is not None and direction not in mapping:
            raise ValueError(
                f'unsupported FDP direction: {direction!r}; expected one of: {sorted(mapping)}'
            )
        result = self.search_subject_records(
            token=token, repo_id=repo_id, materialization_id='persistence-lineage',
            artifact_name=artifact_name, max_results=max_results, page_token=page_token,
        )
        result['kind'] = 'knowledge-layer-fdp-paths'
        return result

    def list_sql_target_value_sources(
        self, target_relation: str, **kwargs: Any
    ) -> dict[str, Any]:
        from .sql_target_source_queries import list_sql_target_value_sources
        return list_sql_target_value_sources(self, target_relation, **kwargs)

    def list_attribute_extension_join_semantics(self, **kwargs: Any) -> dict[str, Any]:
        from .attribute_extension_context_queries import list_attribute_extension_join_semantics
        return list_attribute_extension_join_semantics(self, **kwargs)

    def summarize_code_declared_model(self, **kwargs: Any) -> dict[str, Any]:
        from .code_declared_model_queries import summarize_code_declared_model
        return summarize_code_declared_model(self, **kwargs)

    def list_code_declared_objects(self, **kwargs: Any) -> dict[str, Any]:
        from .code_declared_model_queries import list_code_declared_objects
        return list_code_declared_objects(self, **kwargs)

    def get_code_declared_object(self, object_id: str) -> dict[str, Any]:
        from .code_declared_model_queries import get_code_declared_object
        return get_code_declared_object(self, object_id)

    def get_logical_storage_object_context(self, object_id: str) -> dict[str, Any]:
        from .logical_storage_queries import get_logical_storage_object_context
        return get_logical_storage_object_context(self, object_id)

    def get_model_storage_object_context(self, source_fqcn: str) -> dict[str, Any]:
        from .model_storage_queries import get_model_storage_object_context
        return get_model_storage_object_context(self, source_fqcn)

    def repository_inventory_summary(self) -> dict[str, Any]:
        from .repository_inventory_queries import repository_inventory_summary
        return repository_inventory_summary(self)

    def repository_inventory_coverage(self) -> dict[str, Any]:
        from .repository_inventory_queries import repository_inventory_coverage
        return repository_inventory_coverage(self)

    def repository_inventory_portfolio_snapshot(self) -> dict[str, Any]:
        from .repository_inventory_queries import repository_inventory_portfolio_snapshot
        return repository_inventory_portfolio_snapshot(self)

    def list_repository_inventory_technologies(self, **kwargs: Any) -> dict[str, Any]:
        from .repository_inventory_queries import list_repository_inventory_technologies
        return list_repository_inventory_technologies(self, **kwargs)

    def list_repository_inventory_interfaces(self, **kwargs: Any) -> dict[str, Any]:
        from .repository_inventory_queries import list_repository_inventory_interfaces
        return list_repository_inventory_interfaces(self, **kwargs)

    def list_repository_inventory_structural_families(self, **kwargs: Any) -> dict[str, Any]:
        from .repository_inventory_queries import list_repository_inventory_structural_families
        return list_repository_inventory_structural_families(self, **kwargs)

    def list_repository_inventory_discovery(self, **kwargs: Any) -> dict[str, Any]:
        from .repository_inventory_queries import list_repository_inventory_discovery
        return list_repository_inventory_discovery(self, **kwargs)

    def list_repository_inventory_coverage_gaps(self, **kwargs: Any) -> dict[str, Any]:
        from .repository_inventory_queries import list_repository_inventory_coverage_gaps
        return list_repository_inventory_coverage_gaps(self, **kwargs)

    def list_repository_inventory_source_occurrences(self, **kwargs: Any) -> dict[str, Any]:
        from .repository_inventory_queries import list_repository_inventory_source_occurrences
        return list_repository_inventory_source_occurrences(self, **kwargs)

    def get_repository_inventory_source_occurrence(self, occurrence_id: str) -> dict[str, Any] | None:
        from .repository_inventory_queries import get_repository_inventory_source_occurrence
        return get_repository_inventory_source_occurrence(self, occurrence_id)

    def list_repository_inventory_diagnostics(self, **kwargs: Any) -> dict[str, Any]:
        from .repository_inventory_queries import list_repository_inventory_diagnostics
        return list_repository_inventory_diagnostics(self, **kwargs)

    def get_aisl_knowledge_item(self, *, model_kind: str, item_kind: str, local_id: str) -> dict[str, Any]:
        from .aisl_read_queries import get_aisl_knowledge_item
        return get_aisl_knowledge_item(self, model_kind=model_kind, item_kind=item_kind, local_id=local_id)

    def physical_model_summary(self) -> dict[str, Any]:
        from .physical_model_queries import physical_model_summary
        return physical_model_summary(self)

    def list_physical_model_tables(self, **kwargs: Any) -> dict[str, Any]:
        from .physical_model_queries import list_physical_model_tables
        return list_physical_model_tables(self, **kwargs)

    def get_physical_model_table(self, table_id: str) -> dict[str, Any]:
        from .physical_model_queries import get_physical_model_table
        return get_physical_model_table(self, table_id)

    def list_physical_model_columns(self, **kwargs: Any) -> dict[str, Any]:
        from .physical_model_queries import list_physical_model_columns
        return list_physical_model_columns(self, **kwargs)

    def list_physical_model_keys(self, **kwargs: Any) -> dict[str, Any]:
        from .physical_model_queries import list_physical_model_keys
        return list_physical_model_keys(self, **kwargs)

    def list_physical_model_relationships(self, **kwargs: Any) -> dict[str, Any]:
        from .physical_model_queries import list_physical_model_relationships
        return list_physical_model_relationships(self, **kwargs)

    def list_physical_model_gaps(self, **kwargs: Any) -> dict[str, Any]:
        from .physical_model_queries import list_physical_model_gaps
        return list_physical_model_gaps(self, **kwargs)

    def _empty_page(self, *, kind: str, query_id: str, filters: dict[str, Any], max_results: int, page_token: str) -> dict[str, Any]:
        page_size = self._normalize_page_size(max_results)
        offset = self._decode_page_token(page_token, query_id=query_id, filters=filters)
        return self._page_result(kind=kind, query_id=query_id, filters=filters, items=[], total_count=0, offset=offset, page_size=page_size)

    def _connect(self) -> duckdb.DuckDBPyConnection:
        return connect_database(self.database_path, read_only=True, duckdb_module=duckdb, error_message='DuckDB runtime is unavailable. Install `duckdb>=1.1.0` to query workspace.duckdb.')

    @staticmethod
    def _decode(row: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in row.items():
            if key.endswith('_json') and isinstance(value, str):
                try:
                    result[key] = json.loads(value)
                    continue
                except json.JSONDecodeError:
                    pass
            if isinstance(value, (datetime, date)):
                result[key] = value.isoformat()
            else:
                result[key] = value
        return result

    @classmethod
    def _rows(cls, cursor: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
        columns = [item[0] for item in cursor.description]
        return [cls._decode(dict(zip(columns, row))) for row in cursor.fetchall()]

    @staticmethod
    def _normalize_page_size(max_results: int) -> int:
        if isinstance(max_results, bool) or not isinstance(max_results, int):
            raise ValueError('max_results must be an integer')
        if max_results < 1:
            raise ValueError('max_results must be at least 1')
        return min(max_results, 500)

    @staticmethod
    def _page_filter_fingerprint(query_id: str, filters: dict[str, Any]) -> str:
        canonical = json.dumps({'query_id': query_id, 'filters': filters}, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:24]

    @classmethod
    def _decode_page_token(cls, page_token: str, *, query_id: str, filters: dict[str, Any]) -> int:
        if not page_token:
            return 0
        try:
            padded = page_token + '=' * (-len(page_token) % 4)
            payload = json.loads(base64.urlsafe_b64decode(padded.encode('ascii')).decode('utf-8'))
        except Exception as exc:
            raise ValueError('invalid page_token') from exc
        expected = cls._page_filter_fingerprint(query_id, filters)
        if payload.get('v') != 1 or payload.get('q') != query_id or payload.get('f') != expected:
            raise ValueError('page_token does not match this query and filters')
        offset = payload.get('o')
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise ValueError('invalid page_token offset')
        return offset

    @classmethod
    def _encode_page_token(cls, *, query_id: str, filters: dict[str, Any], offset: int) -> str:
        payload = {'v': 1, 'q': query_id, 'f': cls._page_filter_fingerprint(query_id, filters), 'o': offset}
        raw = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')
        return base64.urlsafe_b64encode(raw).decode('ascii').rstrip('=')

    @classmethod
    def _page_result(cls, *, kind: str, query_id: str, filters: dict[str, Any], items: list[dict[str, Any]], total_count: int, offset: int, page_size: int) -> dict[str, Any]:
        next_offset = offset + len(items)
        truncated = next_offset < total_count
        next_token = cls._encode_page_token(query_id=query_id, filters=filters, offset=next_offset) if truncated else None
        return {'kind': kind, 'items': items, 'total_count': total_count, 'returned_count': len(items), 'page_offset': offset, 'page_size': page_size, 'truncated': truncated, 'next_token': next_token}

    def _paged_select(self, *, kind: str, query_id: str, select_sql: str, count_sql: str, args: list[Any], filters: dict[str, Any], max_results: int, page_token: str) -> dict[str, Any]:
        page_size = self._normalize_page_size(max_results)
        offset = self._decode_page_token(page_token, query_id=query_id, filters=filters)
        with self._connect() as con:
            total_count = int(con.execute(count_sql, args).fetchone()[0])
            rows = self._rows(con.execute(select_sql + ' LIMIT ? OFFSET ?', [*args, page_size, offset]))
        return self._page_result(kind=kind, query_id=query_id, filters=filters, items=rows, total_count=total_count, offset=offset, page_size=page_size)

    def overview(self) -> dict[str, Any]:
        with self._connect() as con:
            if self._has_relation('workspace_build'):
                build_rows = self._rows(con.execute('SELECT * FROM workspace_build ORDER BY started_at DESC LIMIT 1'))
            elif self._has_relation('sql_analysis_build'):
                build_rows = self._rows(con.execute('SELECT * FROM sql_analysis_build ORDER BY started_at DESC LIMIT 1'))
            else:
                build_rows = []
            build = build_rows[0] if build_rows else {}
            if self._has_relation('v_repository_summary'):
                repository_relation = 'v_repository_summary'
            elif self._has_relation('workspace_repository'):
                repository_relation = 'workspace_repository'
            elif self._has_relation('sql_analysis_repository'):
                repository_relation = 'sql_analysis_repository'
            else:
                repository_relation = None
            repositories = self._rows(con.execute(f'SELECT * FROM {repository_relation} ORDER BY repo_id')) if repository_relation else []
            correspondence = {row[0]: row[1] for row in con.execute('SELECT observation_kind, count(*) FROM data_model_correspondence_observation GROUP BY observation_kind ORDER BY observation_kind').fetchall()} if self._has_relation('data_model_correspondence_observation') else {}
            source_observations = {row[0]: row[1] for row in con.execute('SELECT fact_type, count(*) FROM source_observation GROUP BY fact_type ORDER BY fact_type').fetchall()} if self._has_relation('source_observation') else {}
            type_resolution_counts = {row[0]: row[1] for row in con.execute('SELECT match_scope, count(*) FROM type_reference_resolution_candidate GROUP BY match_scope ORDER BY match_scope').fetchall()} if self._has_relation('type_reference_resolution_candidate') else {}
            configuration_type_correspondence_counts = {row[0]: row[1] for row in con.execute('SELECT match_scope, count(*) FROM configuration_type_correspondence_observation GROUP BY match_scope ORDER BY match_scope').fetchall()} if self._has_relation('configuration_type_correspondence_observation') else {}
        manifest = self.manifest()
        scope_type = str(manifest.get('scope_type') or ('repository' if len(repositories) == 1 else 'workspace'))
        return {'kind': 'knowledge-layer-overview', 'build': build, 'manifest': manifest, 'repositories': repositories, 'scope_type': scope_type, 'analysis_scope_kind': manifest.get('analysis_scope_kind') or manifest.get('metadata', {}).get('analysis_scope_kind'), 'capabilities': list(self.capabilities()), 'workspace_extensions_available': 'workspace.cross-repository' in self.capabilities(), 'correspondence_observation_counts': correspondence, 'source_observation_counts': source_observations, 'type_reference_resolution_counts': type_resolution_counts, 'configuration_type_correspondence_counts': configuration_type_correspondence_counts}

    def code_types(self, token: str='', repo_id: str | None=None, class_kind: str | None=None, annotation: str | None=None, max_results: int=100, page_token: str='') -> dict[str, Any]:
        """Return observed Java type declarations without conceptual-table classification."""
        clauses = ['1=1']
        args: list[Any] = []
        if token:
            clauses.append("lower(coalesce(fqcn,'') || ' ' || coalesce(simple_name,'') || ' ' || coalesce(package_name,'') || ' ' || coalesce(class_kind,'') || ' ' || coalesce(extends_reference,'') || ' ' || coalesce(implements_json::VARCHAR,'')) LIKE ?")
            args.append(f'%{token.lower()}%')
        if repo_id:
            clauses.append('repo_id=?')
            args.append(repo_id)
        if class_kind:
            clauses.append('class_kind=?')
            args.append(class_kind)
        if annotation:
            clauses.append("lower(coalesce(annotations_json::VARCHAR,'')) LIKE ?")
            args.append(f'%{annotation.lower()}%')
        where = ' AND '.join(clauses)
        filters = {'token': token, 'repo_id': repo_id, 'class_kind': class_kind, 'annotation': annotation}
        return self._paged_select(kind='workspace-data-model-code-types', query_id='code_types', select_sql=f"\n                SELECT java_type_occurrence_id, repo_id, local_type_id, occurrence_ordinal,\n                       fqcn, simple_name, package_name, class_kind, modifiers, is_abstract,\n                       annotations_json, type_parameters_json, extends_reference, implements_json,\n                       source_path, source_scope, syntax_provider, cycle_observed,\n                       json_extract_string(payload_json, '$.display_name') AS display_name,\n                       json_extract_string(payload_json, '$.description') AS description,\n                       (SELECT count(*) FROM code_field_observation f\n                        WHERE f.repo_id=t.repo_id AND f.owner_fqcn=t.fqcn) AS direct_field_count,\n                       (SELECT count(*) FROM java_inheritance_observation i\n                        WHERE i.repo_id=t.repo_id AND i.child_fqcn=t.fqcn) AS declared_inheritance_count\n                FROM java_type_declaration t\n                WHERE {where}\n                ORDER BY repo_id, fqcn, occurrence_ordinal, java_type_occurrence_id\n            ", count_sql=f'SELECT count(*) FROM java_type_declaration WHERE {where}', args=args, filters=filters, max_results=max_results, page_token=page_token)

    def code_fields(self, token: str='', repo_id: str | None=None, owner_fqcn: str | None=None, max_results: int=100, page_token: str='') -> dict[str, Any]:
        clauses = ['1=1']
        args: list[Any] = []
        if token:
            clauses.append("lower(coalesce(owner_fqcn,'') || ' ' || coalesce(owner_name,'') || ' ' || coalesce(field_name,'') || ' ' || coalesce(declared_type,'') || ' ' || coalesce(raw_type,'') || ' ' || coalesce(element_type,'')) LIKE ?")
            args.append(f'%{token.lower()}%')
        if repo_id:
            clauses.append('repo_id=?')
            args.append(repo_id)
        if owner_fqcn:
            clauses.append('owner_fqcn=?')
            args.append(owner_fqcn)
        where = ' AND '.join(clauses)
        filters = {'token': token, 'repo_id': repo_id, 'owner_fqcn': owner_fqcn}
        return self._paged_select(kind='workspace-data-model-code-fields', query_id='code_fields', select_sql=f'SELECT * FROM v_code_field_observation WHERE {where} ORDER BY repo_id, owner_fqcn, occurrence_ordinal, field_name, code_field_occurrence_id', count_sql=f'SELECT count(*) FROM v_code_field_observation WHERE {where}', args=args, filters=filters, max_results=max_results, page_token=page_token)

    def _source_observation_page(self, *, fact_type: str | None=None, token: str='', repo_id: str | None=None, owner_fqcn: str | None=None, target_method: str | None=None, max_results: int=100, page_token: str='', query_id: str='source_observations', kind: str='workspace-data-model-source-observations', source_relation: str='v_source_observation_compact') -> dict[str, Any]:
        clauses = ['1=1']
        args: list[Any] = []
        if fact_type:
            clauses.append('fact_type=?')
            args.append(fact_type)
        if token:
            clauses.append("lower(\n                coalesce(name,'') || ' ' || coalesce(source_path,'') || ' ' ||\n                coalesce(owner_fqcn,'') || ' ' || coalesce(owner_method,'') || ' ' ||\n                coalesce(member_name,'') || ' ' || coalesce(referenced_type,'') || ' ' ||\n                coalesce(resolved_fqcn,'') || ' ' || coalesce(annotation_name,'') || ' ' ||\n                coalesce(configuration_path,'') || ' ' || coalesce(scalar_value_json::VARCHAR,'') || ' ' ||\n                coalesce(target_method,'') || ' ' || coalesce(receiver_expression,'') || ' ' ||\n                coalesce(source_expression,'') || ' ' || coalesce(target_variable,'') || ' ' ||\n                coalesce(expression_text,'') || ' ' || coalesce(coordinate,'')\n            ) LIKE ?")
            args.append(f'%{token.lower()}%')
        if repo_id:
            clauses.append('repo_id=?')
            args.append(repo_id)
        if owner_fqcn:
            clauses.append('owner_fqcn=?')
            args.append(owner_fqcn)
        if target_method:
            clauses.append('target_method=?')
            args.append(target_method)
        where = ' AND '.join(clauses)
        filters = {'fact_type': fact_type, 'token': token, 'repo_id': repo_id, 'owner_fqcn': owner_fqcn, 'target_method': target_method}
        return self._paged_select(kind=kind, query_id=query_id, select_sql=f'SELECT * FROM {source_relation} WHERE {where} ORDER BY repo_id, fact_type, source_path, line_start, occurrence_ordinal, source_observation_occurrence_id', count_sql=f'SELECT count(*) FROM {source_relation} WHERE {where}', args=args, filters=filters, max_results=max_results, page_token=page_token)

    def source_observations(self, token: str='', repo_id: str | None=None, fact_type: str | None=None, owner_fqcn: str | None=None, target_method: str | None=None, max_results: int=100, page_token: str='') -> dict[str, Any]:
        return self._source_observation_page(fact_type=fact_type, token=token, repo_id=repo_id, owner_fqcn=owner_fqcn, target_method=target_method, max_results=max_results, page_token=page_token)

    def code_annotations(self, token: str='', repo_id: str | None=None, owner_fqcn: str | None=None, max_results: int=100, page_token: str='') -> dict[str, Any]:
        return self._source_observation_page(fact_type='code_annotation', token=token, repo_id=repo_id, owner_fqcn=owner_fqcn, max_results=max_results, page_token=page_token, query_id='code_annotations', kind='workspace-data-model-code-annotations', source_relation='v_code_annotations')

    def configuration_entries(self, token: str='', repo_id: str | None=None, max_results: int=100, page_token: str='') -> dict[str, Any]:
        return self._source_observation_page(fact_type='configuration_entry', token=token, repo_id=repo_id, max_results=max_results, page_token=page_token, query_id='configuration_entries', kind='workspace-data-model-configuration-entries')

    def configuration_observations(self, token: str='', repo_id: str | None=None, fact_type: str | None=None, max_results: int=100, page_token: str='') -> dict[str, Any]:
        if fact_type is not None and fact_type not in CONFIGURATION_FACT_TYPES:
            allowed = ', '.join(CONFIGURATION_FACT_TYPES)
            raise ValueError(f'unsupported configuration fact_type: {fact_type!r}; expected one of: {allowed}')
        selected_types = (fact_type,) if fact_type else CONFIGURATION_FACT_TYPES
        type_placeholders = ','.join(('?' for _ in selected_types))
        clauses = [f'fact_type IN ({type_placeholders})']
        args: list[Any] = list(selected_types)
        if token:
            clauses.append("lower(\n                    coalesce(name,'') || ' ' || coalesce(source_path,'') || ' ' ||\n                    coalesce(configuration_path,'') || ' ' || coalesce(parent_path,'') || ' ' ||\n                    coalesce(node_kind,'') || ' ' || coalesce(member_name,'') || ' ' ||\n                    coalesce(referenced_type,'') || ' ' || coalesce(owner_fqcn,'') || ' ' ||\n                    coalesce(scalar_value_json::VARCHAR,'') || ' ' || coalesce(json_extract(payload_json, '$.properties')::VARCHAR,'')\n                ) LIKE ?")
            args.append(f'%{token.lower()}%')
        if repo_id:
            clauses.append('repo_id=?')
            args.append(repo_id)
        where = ' AND '.join(clauses)
        filters = {'token': token, 'repo_id': repo_id, 'fact_type': fact_type}
        return self._paged_select(kind='workspace-data-model-configuration-observations', query_id='configuration_observations', select_sql=f'SELECT * FROM source_observation WHERE {where} ORDER BY repo_id, fact_type, source_path, line_start, configuration_path, occurrence_ordinal, source_observation_occurrence_id', count_sql=f'SELECT count(*) FROM source_observation WHERE {where}', args=args, filters=filters, max_results=max_results, page_token=page_token)

    def artifact_dependencies(self, token: str='', repo_id: str | None=None, max_results: int=100, page_token: str='') -> dict[str, Any]:
        return self._source_observation_page(fact_type='external_dependency', token=token, repo_id=repo_id, max_results=max_results, page_token=page_token, query_id='artifact_dependencies', kind='workspace-data-model-artifact-dependencies')

    def method_calls(self, token: str='', repo_id: str | None=None, owner_fqcn: str | None=None, target_method: str | None=None, max_results: int=100, page_token: str='') -> dict[str, Any]:
        return self._source_observation_page(fact_type='java_method_call_observation', token=token, repo_id=repo_id, owner_fqcn=owner_fqcn, target_method=target_method, max_results=max_results, page_token=page_token, query_id='method_calls', kind='workspace-data-model-method-calls', source_relation='v_java_method_calls')

    def call_argument_flows(self, token: str='', repo_id: str | None=None, owner_fqcn: str | None=None, target_method: str | None=None, max_results: int=100, page_token: str='') -> dict[str, Any]:
        return self._source_observation_page(fact_type='call_argument_flow_observation', token=token, repo_id=repo_id, owner_fqcn=owner_fqcn, target_method=target_method, max_results=max_results, page_token=page_token, query_id='call_argument_flows', kind='workspace-data-model-call-argument-flows')

    def constructed_values(self, token: str='', repo_id: str | None=None, owner_fqcn: str | None=None, max_results: int=100, page_token: str='') -> dict[str, Any]:
        return self._source_observation_page(fact_type='constructed_value_observation', token=token, repo_id=repo_id, owner_fqcn=owner_fqcn, max_results=max_results, page_token=page_token, query_id='constructed_values', kind='workspace-data-model-constructed-values')

    def collection_mutations(self, token: str='', repo_id: str | None=None, owner_fqcn: str | None=None, target_method: str | None=None, max_results: int=100, page_token: str='') -> dict[str, Any]:
        return self._source_observation_page(fact_type='collection_mutation_observation', token=token, repo_id=repo_id, owner_fqcn=owner_fqcn, target_method=target_method, max_results=max_results, page_token=page_token, query_id='collection_mutations', kind='workspace-data-model-collection-mutations', source_relation='v_collection_mutations')

    def type_references(self, token: str='', repo_id: str | None=None, owner_fqcn: str | None=None, max_results: int=100, page_token: str='') -> dict[str, Any]:
        return self._source_observation_page(fact_type='type_reference_observation', token=token, repo_id=repo_id, owner_fqcn=owner_fqcn, max_results=max_results, page_token=page_token, query_id='type_references', kind='workspace-data-model-type-references')

    def source_observation_evidence_batch(self, observation_ids: list[str] | tuple[str, ...]) -> dict[str, Any]:
        """Return compact source locations for many observation identifiers in one query."""
        ids = sorted({str(value) for value in observation_ids if str(value).strip()})
        if not ids:
            return {"kind": "workspace-data-model-source-observation-evidence", "total_count": 0, "items": []}
        placeholders = ",".join("?" for _ in ids)
        with self._connect() as con:
            items = self._rows(con.execute(
                f"""SELECT source_observation_occurrence_id, local_observation_id, repo_id,
                           source_path, line_start, line_end, extractor, fact_type
                    FROM source_observation
                    WHERE source_observation_occurrence_id IN ({placeholders})
                       OR local_observation_id IN ({placeholders})
                    ORDER BY repo_id, source_path, line_start, source_observation_occurrence_id""",
                ids + ids,
            ))
        return {"kind": "workspace-data-model-source-observation-evidence", "total_count": len(items), "items": items}

    def source_observation_detail(self, observation_id: str) -> dict[str, Any]:
        with self._connect() as con:
            observations = self._rows(con.execute('SELECT * FROM source_observation WHERE source_observation_occurrence_id=? OR local_observation_id=? ORDER BY repo_id, occurrence_ordinal', [observation_id, observation_id]))
            if not observations:
                return {'kind': 'workspace-data-model-source-observation-detail', 'observation_id': observation_id, 'not_found': True}
            occurrence_ids = [row['source_observation_occurrence_id'] for row in observations]
            placeholders = ','.join(('?' for _ in occurrence_ids))
            evidence = self._rows(con.execute(f'SELECT * FROM evidence_ref WHERE owner_occurrence_id IN ({placeholders}) ORDER BY owner_occurrence_id, file_path, line_start', occurrence_ids))
            linked: list[dict[str, Any]] = []
            child_pairs = sorted({(str(row['repo_id']), str(row['local_observation_id'])) for row in observations if row.get('repo_id') and row.get('local_observation_id')})
            if child_pairs:
                child_predicate = ' OR '.join(('(repo_id=? AND call_observation_local_id=?)' for _ in child_pairs))
                child_args = [value for pair in child_pairs for value in pair]
                linked.extend(self._rows(con.execute(f'SELECT * FROM v_source_observation_compact WHERE {child_predicate} ORDER BY repo_id, fact_type, occurrence_ordinal', child_args)))
            parent_pairs = sorted({(str(row['repo_id']), str(row['call_observation_local_id'])) for row in observations if row.get('repo_id') and row.get('call_observation_local_id')})
            if parent_pairs:
                parent_predicate = ' OR '.join(('(repo_id=? AND local_observation_id=?)' for _ in parent_pairs))
                parent_args = [value for pair in parent_pairs for value in pair]
                linked.extend(self._rows(con.execute(f'SELECT * FROM v_source_observation_compact WHERE {parent_predicate} ORDER BY repo_id, fact_type, occurrence_ordinal', parent_args)))
            linked = list({row['source_observation_occurrence_id']: row for row in linked}.values())
            linked.sort(key=lambda row: (str(row.get('repo_id') or ''), str(row.get('fact_type') or ''), int(row.get('occurrence_ordinal') or 0), str(row.get('source_observation_occurrence_id') or '')))
            resolution_candidates = []
            if self._has_relation('type_reference_resolution_candidate'):
                resolution_candidates = self._rows(con.execute(f'SELECT * FROM type_reference_resolution_candidate WHERE source_observation_occurrence_id IN ({placeholders}) ORDER BY candidate_fqcn, target_repo_id, target_java_type_occurrence_id', occurrence_ids))
        return {'kind': 'workspace-data-model-source-observation-detail', 'observation_id': observation_id, 'observations': observations, 'linked_call_observations': linked, 'type_reference_resolution_candidates': resolution_candidates, 'evidence': evidence}

    def configuration_type_correspondences(self, token: str='', source_repo_id: str | None=None, target_repo_id: str | None=None, configuration_path: str | None=None, match_scope: str | None=None, max_results: int=100, page_token: str='') -> dict[str, Any]:
        """Return exact FQCN correspondences between configuration references and Java declarations."""
        clauses = ['1=1']
        args: list[Any] = []
        if token:
            clauses.append("lower(coalesce(referenced_fqcn,'') || ' ' || coalesce(configuration_path,'') || ' ' || coalesce(source_repo_id,'') || ' ' || coalesce(target_repo_id,'')) LIKE ?")
            args.append(f'%{token.lower()}%')
        if source_repo_id:
            clauses.append('source_repo_id=?')
            args.append(source_repo_id)
        if target_repo_id:
            clauses.append('target_repo_id=?')
            args.append(target_repo_id)
        if configuration_path:
            clauses.append('configuration_path LIKE ?')
            args.append(configuration_path)
        if match_scope:
            clauses.append('match_scope=?')
            args.append(match_scope)
        where = ' AND '.join(clauses)
        filters = {'token': token, 'source_repo_id': source_repo_id, 'target_repo_id': target_repo_id, 'configuration_path': configuration_path, 'match_scope': match_scope}
        return self._paged_select(kind='workspace-data-model-configuration-type-correspondences', query_id='configuration_type_correspondences', select_sql=f'SELECT observation_id, source_observation_occurrence_id, source_repo_id, configuration_path, referenced_fqcn, target_repo_id, target_java_type_occurrence_id, match_scope, match_basis, payload_json FROM configuration_type_correspondence_observation WHERE {where} ORDER BY source_repo_id, configuration_path, referenced_fqcn, target_repo_id, target_java_type_occurrence_id, observation_id', count_sql=f'SELECT count(*) FROM configuration_type_correspondence_observation WHERE {where}', args=args, filters=filters, max_results=max_results, page_token=page_token)

    def model_object_keys(self, object_id: str='', repo_id: str | None=None, annotation: str | None=None) -> dict[str, Any]:
        """Return annotation-declared object key roles and their resolved direct/inherited fields."""
        clauses = ['1=1']
        args: list[Any] = []
        if object_id:
            clauses.append('(k.key_observation_id=? OR k.object_fqcn=? OR k.java_type_occurrence_id=?)')
            args.extend([object_id, object_id, object_id])
        if repo_id:
            clauses.append('k.repo_id=?')
            args.append(repo_id)
        if annotation:
            clauses.append('lower(k.annotation_name)=lower(?)')
            args.append(annotation)
        where = ' AND '.join(clauses)
        with self._connect() as con:
            keys = self._rows(con.execute(f'SELECT * FROM v_model_object_keys k WHERE {where}\n                    ORDER BY k.repo_id, k.object_fqcn, k.annotation_name, k.key_observation_id', args))
            key_ids = [str(row['key_observation_id']) for row in keys]
            members: list[dict[str, Any]] = []
            if key_ids:
                placeholders = ','.join(('?' for _ in key_ids))
                members = self._rows(con.execute(f'SELECT * FROM model_object_key_member\n                        WHERE key_observation_id IN ({placeholders})\n                        ORDER BY key_observation_id, position, role_name, key_member_id', key_ids))
        members_by_key: dict[str, list[dict[str, Any]]] = {}
        for member in members:
            members_by_key.setdefault(str(member['key_observation_id']), []).append(member)
        for key in keys:
            key['members'] = members_by_key.get(str(key['key_observation_id']), [])
        return {'kind': 'workspace-data-model-object-keys', 'filters': {'object_id': object_id, 'repo_id': repo_id, 'annotation': annotation}, 'total_count': len(keys), 'items': keys}

    def model_embedded_fields(self, source_object_id: str='') -> dict[str, Any]:
        where = '1=1'
        args: list[Any] = []
        if source_object_id:
            where = 'source_object_fqcn=?'
            args.append(source_object_id)
        with self._connect() as con:
            items = self._rows(con.execute(f'SELECT * FROM model_embedded_field_observation WHERE {where} ORDER BY source_object_fqcn, source_field_name, embedded_field_id', args))
        return {'kind': 'workspace-data-model-embedded-fields', 'total_count': len(items), 'items': items}

    def type_neighborhood(self, type_id: str, max_results: int=50) -> dict[str, Any]:
        limit = min(self._normalize_page_size(max_results), 200)
        with self._connect() as con:
            definitions = self._rows(con.execute('SELECT * FROM java_type_declaration\n               WHERE java_type_occurrence_id=? OR fqcn=? OR simple_name=?\n               ORDER BY repo_id, fqcn, occurrence_ordinal', [type_id, type_id, type_id]))
            if not definitions:
                return {'kind': 'knowledge-layer-type-neighborhood', 'type_id': type_id, 'not_found': True}
            fqcns = sorted({str(row['fqcn']) for row in definitions if row.get('fqcn')})
            repo_ids = sorted({str(row['repo_id']) for row in definitions if row.get('repo_id')})
            fqcn_placeholders = ','.join(('?' for _ in fqcns))
            repo_placeholders = ','.join(('?' for _ in repo_ids))

            def section(select_sql: str, count_sql: str, args: list[Any]) -> dict[str, Any]:
                total = int(con.execute(count_sql, args).fetchone()[0])
                items = self._rows(con.execute(select_sql + ' LIMIT ?', [*args, limit]))
                return {'items': items, 'total_count': total, 'returned_count': len(items), 'truncated': len(items) < total}
            code_fields = section(f'SELECT * FROM v_code_field_observation WHERE owner_fqcn IN ({fqcn_placeholders}) ORDER BY repo_id, owner_fqcn, occurrence_ordinal, field_name', f'SELECT count(*) FROM v_code_field_observation WHERE owner_fqcn IN ({fqcn_placeholders})', fqcns)
            effective_fields = section(f'SELECT * FROM effective_entity_field WHERE effective_owner_fqcn IN ({fqcn_placeholders}) ORDER BY repo_id, effective_owner_fqcn, inheritance_depth, field_name', f'SELECT count(*) FROM effective_entity_field WHERE effective_owner_fqcn IN ({fqcn_placeholders})', fqcns)
            effective_associations = section(f'SELECT * FROM effective_entity_association WHERE effective_owner_fqcn IN ({fqcn_placeholders}) OR target_observed_fqcn IN ({fqcn_placeholders}) ORDER BY repo_id, effective_owner_fqcn, source_field', f'SELECT count(*) FROM effective_entity_association WHERE effective_owner_fqcn IN ({fqcn_placeholders}) OR target_observed_fqcn IN ({fqcn_placeholders})', [*fqcns, *fqcns])
            inheritance = section(f'SELECT * FROM java_inheritance_observation WHERE child_fqcn IN ({fqcn_placeholders}) OR resolved_parent_fqcn IN ({fqcn_placeholders}) ORDER BY repo_id, child_fqcn, relation_kind', f'SELECT count(*) FROM java_inheritance_observation WHERE child_fqcn IN ({fqcn_placeholders}) OR resolved_parent_fqcn IN ({fqcn_placeholders})', [*fqcns, *fqcns])
            source_observations = section(f'SELECT * FROM v_source_observation_compact WHERE owner_fqcn IN ({fqcn_placeholders}) OR resolved_fqcn IN ({fqcn_placeholders}) ORDER BY repo_id, fact_type, source_path, line_start, occurrence_ordinal', f'SELECT count(*) FROM v_source_observation_compact WHERE owner_fqcn IN ({fqcn_placeholders}) OR resolved_fqcn IN ({fqcn_placeholders})', [*fqcns, *fqcns])
            dependencies = section(f"SELECT * FROM v_source_observation_compact WHERE fact_type='external_dependency' AND repo_id IN ({repo_placeholders}) ORDER BY repo_id, coordinate, source_observation_occurrence_id", f"SELECT count(*) FROM v_source_observation_compact WHERE fact_type='external_dependency' AND repo_id IN ({repo_placeholders})", repo_ids)
            resolutions = {'items': [], 'total_count': 0, 'returned_count': 0, 'truncated': False}
            if self._has_relation('type_reference_resolution_candidate'):
                resolutions = section(f'SELECT c.* FROM type_reference_resolution_candidate c\n                    JOIN java_type_declaration t ON t.java_type_occurrence_id=c.target_java_type_occurrence_id\n                    WHERE c.owner_fqcn IN ({fqcn_placeholders}) OR t.fqcn IN ({fqcn_placeholders})\n                    ORDER BY c.source_repo_id, c.owner_fqcn, c.candidate_fqcn, c.target_repo_id', f'SELECT count(*) FROM type_reference_resolution_candidate c\n                    JOIN java_type_declaration t ON t.java_type_occurrence_id=c.target_java_type_occurrence_id\n                    WHERE c.owner_fqcn IN ({fqcn_placeholders}) OR t.fqcn IN ({fqcn_placeholders})', [*fqcns, *fqcns])
            owner_ids = [row['java_type_occurrence_id'] for row in definitions]
            owner_ids.extend((row['source_observation_occurrence_id'] for row in source_observations['items']))
            evidence: list[dict[str, Any]] = []
            if owner_ids:
                evidence_placeholders = ','.join(('?' for _ in owner_ids))
                evidence = self._rows(con.execute(f'SELECT * FROM evidence_ref WHERE owner_occurrence_id IN ({evidence_placeholders}) ORDER BY owner_occurrence_id, file_path, line_start LIMIT ?', [*owner_ids, limit]))
        return {'kind': 'knowledge-layer-type-neighborhood', 'type_id': type_id, 'resolved_fqcns': fqcns, 'repositories': repo_ids, 'definitions': definitions, 'code_fields': code_fields, 'effective_fields': effective_fields, 'effective_associations': effective_associations, 'inheritance': inheritance, 'source_observations': source_observations, 'type_reference_resolution_candidates': resolutions, 'repository_artifact_dependencies': dependencies, 'evidence': evidence, 'capabilities': list(self.capabilities()), 'interpretation_policy': 'facts_only_no_semantic_equivalence_or_business_verdict'}

    def repositories(self, token: str='', max_results: int=100, page_token: str='') -> dict[str, Any]:
        q = f'%{token.lower()}%'
        relation = 'v_repository_summary' if self._has_relation('v_repository_summary') else 'workspace_repository'
        where = "?='%%' OR lower(repo_id || ' ' || coalesce(system_name,'') || ' ' || coalesce(project_code,'')) LIKE ?"
        filters = {'token': token}
        return self._paged_select(kind='workspace-data-model-repositories', query_id='repositories', select_sql=f'SELECT * FROM {relation} WHERE {where} ORDER BY repo_id', count_sql=f'SELECT count(*) FROM {relation} WHERE {where}', args=[q, q], filters=filters, max_results=max_results, page_token=page_token)

    def entities(self, token: str='', repo_id: str | None=None, max_results: int=100, page_token: str='') -> dict[str, Any]:
        clauses = ['1=1']
        args: list[Any] = []
        if token:
            clauses.append("lower(name || ' ' || coalesce(canonical_name,'') || ' ' || coalesce(qualified_name,'')) LIKE ?")
            args.append(f'%{token.lower()}%')
        if repo_id:
            clauses.append('repo_id=?')
            args.append(repo_id)
        where = ' AND '.join(clauses)
        filters = {'token': token, 'repo_id': repo_id}
        return self._paged_select(kind='workspace-data-model-entities', query_id='entities', select_sql=f'\n                SELECT entity_occurrence_id, repo_id, local_entity_id, occurrence_ordinal,\n                       canonical_name, name, normalized_name, qualified_name,\n                       normalized_qualified_name, schema_name, domain_name, source_kind,\n                       entity_fact_kind, evidence_level, name_source,\n                       inline_attribute_count, persistent_structure_attribute_count\n                FROM v_data_model_entity\n                WHERE {where}\n                ORDER BY repo_id, normalized_qualified_name, entity_occurrence_id\n            ', count_sql=f'SELECT count(*) FROM v_data_model_entity WHERE {where}', args=args, filters=filters, max_results=max_results, page_token=page_token)

    def entity_detail(self, entity_id: str) -> dict[str, Any]:
        with self._connect() as con:
            rows = self._rows(con.execute('SELECT * FROM data_model_entity WHERE entity_occurrence_id=? OR local_entity_id=? ORDER BY repo_id, occurrence_ordinal', [entity_id, entity_id]))
            if not rows:
                return {'kind': 'workspace-data-model-entity-detail', 'entity_id': entity_id, 'not_found': True}
            occurrence_ids = [item['entity_occurrence_id'] for item in rows]
            placeholders = ','.join(('?' for _ in occurrence_ids))
            attributes = self._rows(con.execute(f'SELECT * FROM data_model_attribute WHERE entity_occurrence_id IN ({placeholders}) ORDER BY entity_occurrence_id, occurrence_ordinal, normalized_name', occurrence_ids))
            local_keys = [(item['repo_id'], item['local_entity_id']) for item in rows]
            association_clause = ' OR '.join(('(repo_id=? AND (from_local_entity_id=? OR to_local_entity_id=?))' for _ in local_keys))
            association_args: list[Any] = []
            for repo_id, local_entity_id in local_keys:
                association_args.extend([repo_id, local_entity_id, local_entity_id])
            associations = self._rows(con.execute(f'SELECT * FROM data_model_association WHERE {association_clause} ORDER BY repo_id, association_occurrence_id', association_args))
            mapping_clause = ' OR '.join(('(repo_id=? AND local_entity_id=?)' for _ in local_keys))
            mapping_args = [value for key in local_keys for value in key]
            mappings = self._rows(con.execute(f'SELECT * FROM entity_physical_mapping WHERE {mapping_clause} ORDER BY repo_id, mapping_occurrence_id', mapping_args))
            structure_rows = self._rows(con.execute(f"\n                    SELECT DISTINCT ps.*\n                    FROM persistent_structure ps\n                    JOIN data_model_local_correspondence_observation o\n                      ON o.left_object_kind='persistent_structure'\n                     AND o.left_occurrence_id=ps.structure_occurrence_id\n                     AND o.right_object_kind='data_model_entity'\n                    WHERE o.right_occurrence_id IN ({placeholders})\n                    ORDER BY ps.repo_id, ps.occurrence_ordinal, ps.structure_occurrence_id\n                    ", occurrence_ids))
            structure_ids = [item['structure_occurrence_id'] for item in structure_rows]
            if structure_ids:
                structure_placeholders = ','.join(('?' for _ in structure_ids))
                structure_attributes = self._rows(con.execute(f'SELECT * FROM persistent_structure_attribute WHERE structure_occurrence_id IN ({structure_placeholders}) ORDER BY structure_occurrence_id, occurrence_ordinal', structure_ids))
            else:
                structure_attributes = []
            evidence_owner_ids = occurrence_ids + [item['attribute_occurrence_id'] for item in attributes]
            evidence_owner_ids.extend(structure_ids)
            evidence_owner_ids.extend((item['structure_attribute_occurrence_id'] for item in structure_attributes))
            evidence_placeholders = ','.join(('?' for _ in evidence_owner_ids))
            evidence = self._rows(con.execute(f'SELECT * FROM evidence_ref WHERE owner_occurrence_id IN ({evidence_placeholders}) ORDER BY owner_occurrence_id, file_path, line_start', evidence_owner_ids))
        return {'kind': 'workspace-data-model-entity-detail', 'entities': rows, 'attributes': attributes, 'associations': associations, 'physical_mappings': mappings, 'persistent_structures': structure_rows, 'persistent_structure_attributes': structure_attributes, 'evidence_refs': evidence}

    def physical_assets(self, token: str='', repo_id: str | None=None, max_results: int=100, page_token: str='') -> dict[str, Any]:
        clauses = ['1=1']
        args: list[Any] = []
        if token:
            clauses.append("lower(name || ' ' || coalesce(qualified_name,'')) LIKE ?")
            args.append(f'%{token.lower()}%')
        if repo_id:
            clauses.append('repo_id=?')
            args.append(repo_id)
        where = ' AND '.join(clauses)
        filters = {'token': token, 'repo_id': repo_id}
        return self._paged_select(kind='workspace-data-model-physical-assets', query_id='physical_assets', select_sql=f'\n                SELECT physical_asset_occurrence_id, repo_id, local_asset_id, occurrence_ordinal,\n                       asset_type, schema_name, name, qualified_name, normalized_qualified_name,\n                       source_type, column_count, conceptual_model_column_count,\n                       fact_occurrence_count, db_table_observation_count, db_schema_column_count\n                FROM v_physical_asset\n                WHERE {where}\n                ORDER BY normalized_qualified_name, repo_id, physical_asset_occurrence_id\n            ', count_sql=f'SELECT count(*) FROM v_physical_asset WHERE {where}', args=args, filters=filters, max_results=max_results, page_token=page_token)

    def physical_asset_detail(self, asset_id: str) -> dict[str, Any]:
        with self._connect() as con:
            assets = self._rows(con.execute('SELECT * FROM physical_asset WHERE physical_asset_occurrence_id=? OR local_asset_id=? OR normalized_qualified_name=? ORDER BY repo_id, occurrence_ordinal', [asset_id, asset_id, normalize_db_identifier(asset_id)]))
            if not assets:
                return {'kind': 'workspace-data-model-physical-asset-detail', 'asset_id': asset_id, 'not_found': True}
            local_keys = [(item['repo_id'], item['local_asset_id']) for item in assets]
            fact_clause = ' OR '.join(('(repo_id=? AND local_asset_id=?)' for _ in local_keys))
            fact_args = [value for key in local_keys for value in key]
            facts = self._rows(con.execute(f'SELECT * FROM physical_asset_fact WHERE {fact_clause} ORDER BY repo_id, occurrence_ordinal, physical_asset_fact_occurrence_id', fact_args))
            fact_ids = [item['physical_asset_fact_occurrence_id'] for item in facts]
            asset_ids = [item['physical_asset_occurrence_id'] for item in assets]
            asset_placeholders = ','.join(('?' for _ in asset_ids))
            db_tables = self._rows(con.execute(f"\n                    SELECT DISTINCT t.*\n                    FROM db_schema_table t\n                    JOIN data_model_local_correspondence_observation o\n                      ON o.left_object_kind='db_schema_table'\n                     AND o.left_occurrence_id=t.db_table_occurrence_id\n                     AND o.right_object_kind='physical_asset'\n                    WHERE o.right_occurrence_id IN ({asset_placeholders})\n                    ORDER BY t.repo_id, t.occurrence_ordinal, t.db_table_occurrence_id\n                    ", asset_ids))
            db_table_ids = [item['db_table_occurrence_id'] for item in db_tables]
            if fact_ids:
                fact_placeholders = ','.join(('?' for _ in fact_ids))
                columns = self._rows(con.execute(f'SELECT * FROM physical_column WHERE physical_asset_fact_occurrence_id IN ({fact_placeholders}) ORDER BY physical_asset_fact_occurrence_id, occurrence_ordinal, normalized_name', fact_ids))
                constraints = self._rows(con.execute(f'SELECT * FROM physical_constraint WHERE physical_asset_fact_occurrence_id IN ({fact_placeholders}) ORDER BY physical_asset_fact_occurrence_id, constraint_kind, constraint_name', fact_ids))
            else:
                columns = []
                constraints = []
            if db_table_ids:
                db_table_placeholders = ','.join(('?' for _ in db_table_ids))
                db_columns = self._rows(con.execute(f'SELECT * FROM db_schema_column WHERE db_table_occurrence_id IN ({db_table_placeholders}) ORDER BY db_table_occurrence_id, occurrence_ordinal', db_table_ids))
                db_keys = self._rows(con.execute(f'SELECT * FROM db_schema_key WHERE db_table_occurrence_id IN ({db_table_placeholders}) ORDER BY db_table_occurrence_id, occurrence_ordinal', db_table_ids))
                db_constraints = self._rows(con.execute(f'SELECT * FROM db_schema_constraint WHERE db_table_occurrence_id IN ({db_table_placeholders}) ORDER BY db_table_occurrence_id, occurrence_ordinal', db_table_ids))
                db_indexes = self._rows(con.execute(f'SELECT * FROM db_schema_index WHERE db_table_occurrence_id IN ({db_table_placeholders}) ORDER BY db_table_occurrence_id, occurrence_ordinal', db_table_ids))
                db_partitioning = self._rows(con.execute(f'SELECT * FROM db_schema_partitioning WHERE db_table_occurrence_id IN ({db_table_placeholders}) ORDER BY db_table_occurrence_id, occurrence_ordinal', db_table_ids))
                db_triggers = self._rows(con.execute(f'SELECT * FROM db_schema_trigger WHERE db_table_occurrence_id IN ({db_table_placeholders}) ORDER BY db_table_occurrence_id, occurrence_ordinal', db_table_ids))
                relationship_clause = ' OR '.join(('json_contains(source_db_table_occurrence_ids_json, ?::JSON) OR json_contains(target_db_table_occurrence_ids_json, ?::JSON)' for _ in db_table_ids))
                relationship_args: list[Any] = []
                for db_table_id in db_table_ids:
                    encoded = json.dumps(db_table_id)
                    relationship_args.extend([encoded, encoded])
                db_relationships = self._rows(con.execute(f'SELECT * FROM db_schema_relationship WHERE {relationship_clause} ORDER BY repo_id, occurrence_ordinal', relationship_args))
            else:
                db_columns = []
                db_keys = []
                db_constraints = []
                db_indexes = []
                db_partitioning = []
                db_triggers = []
                db_relationships = []
            mapping_clause = ' OR '.join(('(repo_id=? AND local_physical_asset_id=?)' for _ in local_keys))
            mappings = self._rows(con.execute(f'SELECT * FROM entity_physical_mapping WHERE {mapping_clause} ORDER BY repo_id, mapping_occurrence_id', fact_args))
            evidence_owner_ids = [item['physical_asset_occurrence_id'] for item in assets]
            evidence_owner_ids.extend(fact_ids)
            evidence_owner_ids.extend((item['physical_column_occurrence_id'] for item in columns))
            evidence_owner_ids.extend((item['physical_constraint_occurrence_id'] for item in constraints))
            evidence_owner_ids.extend((item['mapping_occurrence_id'] for item in mappings))
            evidence_owner_ids.extend(db_table_ids)
            evidence_owner_ids.extend((item['db_column_occurrence_id'] for item in db_columns))
            evidence_owner_ids.extend((item['db_key_occurrence_id'] for item in db_keys))
            evidence_owner_ids.extend((item['db_constraint_occurrence_id'] for item in db_constraints))
            evidence_owner_ids.extend((item['db_index_occurrence_id'] for item in db_indexes))
            evidence_owner_ids.extend((item['db_partitioning_occurrence_id'] for item in db_partitioning))
            evidence_owner_ids.extend((item['db_trigger_occurrence_id'] for item in db_triggers))
            evidence_owner_ids.extend((item['db_relationship_occurrence_id'] for item in db_relationships))
            if evidence_owner_ids:
                evidence_placeholders = ','.join(('?' for _ in evidence_owner_ids))
                evidence = self._rows(con.execute(f'SELECT * FROM evidence_ref WHERE owner_occurrence_id IN ({evidence_placeholders}) ORDER BY owner_type, owner_occurrence_id, file_path, line_start', evidence_owner_ids))
            else:
                evidence = []
        return {'kind': 'workspace-data-model-physical-asset-detail', 'physical_assets': assets, 'physical_asset_facts': facts, 'columns': columns, 'constraints': constraints, 'entity_mappings': mappings, 'db_schema_tables': db_tables, 'db_schema_columns': db_columns, 'db_schema_keys': db_keys, 'db_schema_relationships': db_relationships, 'db_schema_constraints': db_constraints, 'db_schema_indexes': db_indexes, 'db_schema_partitioning': db_partitioning, 'db_schema_triggers': db_triggers, 'evidence_refs': evidence}

    def persistent_structures(self, token: str='', repo_id: str | None=None, max_results: int=100, page_token: str='') -> dict[str, Any]:
        clauses = ['1=1']
        args: list[Any] = []
        if token:
            clauses.append("lower(container_name || ' ' || coalesce(container_fqcn,'') || ' ' || coalesce(storage_target,'')) LIKE ?")
            args.append(f'%{token.lower()}%')
        if repo_id:
            clauses.append('repo_id=?')
            args.append(repo_id)
        where = ' AND '.join(clauses)
        filters = {'token': token, 'repo_id': repo_id}
        return self._paged_select(kind='workspace-data-model-persistent-structures', query_id='persistent_structures', select_sql=f'\n                SELECT structure_occurrence_id, repo_id, local_structure_id, occurrence_ordinal,\n                       storage_kind, storage_target, container_kind, container_name,\n                       container_fqcn, normalized_container_fqcn, normalized_container_name,\n                       field_count, source_scope, source_set, is_test_source, module_name,\n                       entity_occurrence_id, entity_occurrence_ids_json, matching_basis_json\n                FROM persistent_structure\n                WHERE {where}\n                ORDER BY repo_id, normalized_container_name, occurrence_ordinal, structure_occurrence_id\n            ', count_sql=f'SELECT count(*) FROM persistent_structure WHERE {where}', args=args, filters=filters, max_results=max_results, page_token=page_token)

    def persistent_structure_detail(self, structure_id: str) -> dict[str, Any]:
        with self._connect() as con:
            structures = self._rows(con.execute('SELECT * FROM persistent_structure WHERE structure_occurrence_id=? OR local_structure_id=? OR normalized_container_name=? OR normalized_container_fqcn=? ORDER BY repo_id, occurrence_ordinal', [structure_id, structure_id, structure_id.lower().replace('_', ''), normalize_db_identifier(structure_id)]))
            if not structures:
                return {'kind': 'workspace-data-model-persistent-structure-detail', 'structure_id': structure_id, 'not_found': True}
            ids = [item['structure_occurrence_id'] for item in structures]
            placeholders = ','.join(('?' for _ in ids))
            attributes = self._rows(con.execute(f'SELECT * FROM persistent_structure_attribute WHERE structure_occurrence_id IN ({placeholders}) ORDER BY structure_occurrence_id, occurrence_ordinal', ids))
            entity_ids = [item['entity_occurrence_id'] for item in structures if item.get('entity_occurrence_id')]
            entities = self._rows(con.execute(f"SELECT * FROM data_model_entity WHERE entity_occurrence_id IN ({','.join(('?' for _ in entity_ids))}) ORDER BY repo_id, occurrence_ordinal", entity_ids)) if entity_ids else []
            owner_ids = ids + [item['structure_attribute_occurrence_id'] for item in attributes]
            evidence = self._rows(con.execute(f"SELECT * FROM evidence_ref WHERE owner_occurrence_id IN ({','.join(('?' for _ in owner_ids))}) ORDER BY owner_type, owner_occurrence_id, file_path, line_start", owner_ids))
        return {'kind': 'workspace-data-model-persistent-structure-detail', 'persistent_structures': structures, 'attributes': attributes, 'matched_entities': entities, 'evidence_refs': evidence}

    def db_schema_tables(self, token: str='', repo_id: str | None=None, max_results: int=100, page_token: str='') -> dict[str, Any]:
        clauses = ['1=1']
        args: list[Any] = []
        if token:
            clauses.append("lower(table_name || ' ' || coalesce(qualified_table_name,'')) LIKE ?")
            args.append(f'%{token.lower()}%')
        if repo_id:
            clauses.append('repo_id=?')
            args.append(repo_id)
        where = ' AND '.join(clauses)
        filters = {'token': token, 'repo_id': repo_id}
        return self._paged_select(kind='workspace-data-model-db-schema-tables', query_id='db_schema_tables', select_sql=f'\n                SELECT t.db_table_occurrence_id, t.repo_id, t.local_table_id, t.occurrence_ordinal,\n                       t.table_name, t.normalized_table_name, t.schema_name,\n                       t.qualified_table_name, t.normalized_qualified_table_name,\n                       t.source_type, t.source_set, t.is_test_source, t.module_name,\n                       t.evidence_maturity_level, t.physical_asset_occurrence_id,\n                       t.physical_asset_occurrence_ids_json, t.matching_basis_json,\n                       (SELECT count(*) FROM db_schema_column c WHERE c.db_table_occurrence_id=t.db_table_occurrence_id) AS column_count,\n                       (SELECT count(*) FROM db_schema_key k WHERE k.db_table_occurrence_id=t.db_table_occurrence_id) AS key_count,\n                       (SELECT count(*) FROM db_schema_constraint c WHERE c.db_table_occurrence_id=t.db_table_occurrence_id) AS constraint_count,\n                       (SELECT count(*) FROM db_schema_index i WHERE i.db_table_occurrence_id=t.db_table_occurrence_id) AS index_count,\n                       (SELECT count(*) FROM db_schema_partitioning p WHERE p.db_table_occurrence_id=t.db_table_occurrence_id) AS partitioning_count,\n                       (SELECT count(*) FROM db_schema_trigger g WHERE g.db_table_occurrence_id=t.db_table_occurrence_id) AS trigger_count,\n                       (SELECT count(*) FROM db_schema_relationship r\n                         WHERE r.source_db_table_occurrence_id=t.db_table_occurrence_id\n                            OR r.target_db_table_occurrence_id=t.db_table_occurrence_id\n                            OR json_contains(r.source_db_table_occurrence_ids_json, to_json(t.db_table_occurrence_id))\n                            OR json_contains(r.target_db_table_occurrence_ids_json, to_json(t.db_table_occurrence_id))) AS relationship_count,\n                       (SELECT count(*) FROM table_relationship_observation r\n                         WHERE r.left_db_table_occurrence_id=t.db_table_occurrence_id\n                            OR r.right_db_table_occurrence_id=t.db_table_occurrence_id\n                            OR json_contains(r.left_db_table_occurrence_ids_json, to_json(t.db_table_occurrence_id))\n                            OR json_contains(r.right_db_table_occurrence_ids_json, to_json(t.db_table_occurrence_id))) AS observed_relationship_count,\n                       (SELECT count(*) FROM table_key_observation k\n                         WHERE k.db_table_occurrence_id=t.db_table_occurrence_id\n                            OR json_contains(k.db_table_occurrence_ids_json, to_json(t.db_table_occurrence_id))) AS key_observation_count\n                FROM db_schema_table t\n                WHERE {where}\n                ORDER BY t.repo_id, t.normalized_qualified_table_name, t.occurrence_ordinal, t.db_table_occurrence_id\n            ', count_sql=f'SELECT count(*) FROM db_schema_table WHERE {where}', args=args, filters=filters, max_results=max_results, page_token=page_token)

    def db_schema_table_detail(self, table_id: str) -> dict[str, Any]:
        with self._connect() as con:
            tables = self._rows(con.execute('SELECT * FROM db_schema_table WHERE db_table_occurrence_id=? OR local_table_id=? OR normalized_qualified_table_name=? OR normalized_table_name=? ORDER BY repo_id, occurrence_ordinal', [table_id, table_id, normalize_db_identifier(table_id), normalize_db_identifier(table_id).rsplit('.', 1)[-1]]))
            if not tables:
                return {'kind': 'workspace-data-model-db-schema-table-detail', 'table_id': table_id, 'not_found': True}
            ids = [item['db_table_occurrence_id'] for item in tables]
            placeholders = ','.join(('?' for _ in ids))
            columns = self._rows(con.execute(f'SELECT * FROM db_schema_column WHERE db_table_occurrence_id IN ({placeholders}) ORDER BY db_table_occurrence_id, occurrence_ordinal', ids))
            keys = self._rows(con.execute(f'SELECT * FROM db_schema_key WHERE db_table_occurrence_id IN ({placeholders}) ORDER BY db_table_occurrence_id, occurrence_ordinal', ids))
            constraints = self._rows(con.execute(f'SELECT * FROM db_schema_constraint WHERE db_table_occurrence_id IN ({placeholders}) ORDER BY db_table_occurrence_id, occurrence_ordinal', ids))
            indexes = self._rows(con.execute(f'SELECT * FROM db_schema_index WHERE db_table_occurrence_id IN ({placeholders}) ORDER BY db_table_occurrence_id, occurrence_ordinal', ids))
            partitioning = self._rows(con.execute(f'SELECT * FROM db_schema_partitioning WHERE db_table_occurrence_id IN ({placeholders}) ORDER BY db_table_occurrence_id, occurrence_ordinal', ids))
            triggers = self._rows(con.execute(f'SELECT * FROM db_schema_trigger WHERE db_table_occurrence_id IN ({placeholders}) ORDER BY db_table_occurrence_id, occurrence_ordinal', ids))
            rel_clause = ' OR '.join(('json_contains(source_db_table_occurrence_ids_json, ?::JSON) OR json_contains(target_db_table_occurrence_ids_json, ?::JSON)' for _ in ids))
            rel_args = [value for item in ids for value in (json.dumps(item), json.dumps(item))]
            relationships = self._rows(con.execute(f'SELECT * FROM db_schema_relationship WHERE {rel_clause} ORDER BY repo_id, occurrence_ordinal', rel_args))
            observed_rel_clause = ' OR '.join(('json_contains(left_db_table_occurrence_ids_json, ?::JSON) OR json_contains(right_db_table_occurrence_ids_json, ?::JSON)' for _ in ids))
            observed_relationships = self._rows(con.execute(f'SELECT * FROM table_relationship_observation WHERE {observed_rel_clause} ORDER BY repo_id, occurrence_ordinal', rel_args))
            observed_relationship_ids = [item['relationship_observation_occurrence_id'] for item in observed_relationships]
            observed_pairs = self._rows(con.execute(f"SELECT * FROM table_relationship_column_pair WHERE relationship_observation_occurrence_id IN ({','.join(('?' for _ in observed_relationship_ids))}) ORDER BY relationship_observation_occurrence_id, pair_ordinal", observed_relationship_ids)) if observed_relationship_ids else []
            key_obs_clause = ' OR '.join(('json_contains(db_table_occurrence_ids_json, ?::JSON)' for _ in ids))
            key_obs_args = [json.dumps(item) for item in ids]
            key_observations = self._rows(con.execute(f'SELECT * FROM table_key_observation WHERE {key_obs_clause} ORDER BY repo_id, occurrence_ordinal', key_obs_args))
            key_observation_ids = [item['key_observation_occurrence_id'] for item in key_observations]
            key_observation_columns = self._rows(con.execute(f"SELECT * FROM table_key_observation_column WHERE key_observation_occurrence_id IN ({','.join(('?' for _ in key_observation_ids))}) ORDER BY key_observation_occurrence_id, column_ordinal", key_observation_ids)) if key_observation_ids else []
            physical_ids = [item['physical_asset_occurrence_id'] for item in tables if item.get('physical_asset_occurrence_id')]
            physical_assets = self._rows(con.execute(f"SELECT * FROM physical_asset WHERE physical_asset_occurrence_id IN ({','.join(('?' for _ in physical_ids))}) ORDER BY repo_id, occurrence_ordinal", physical_ids)) if physical_ids else []
            owner_ids = ids + [item['db_column_occurrence_id'] for item in columns] + [item['db_key_occurrence_id'] for item in keys] + [item['db_constraint_occurrence_id'] for item in constraints] + [item['db_index_occurrence_id'] for item in indexes] + [item['db_partitioning_occurrence_id'] for item in partitioning] + [item['db_trigger_occurrence_id'] for item in triggers] + [item['db_relationship_occurrence_id'] for item in relationships] + observed_relationship_ids + key_observation_ids
            evidence = self._rows(con.execute(f"SELECT * FROM evidence_ref WHERE owner_occurrence_id IN ({','.join(('?' for _ in owner_ids))}) ORDER BY owner_type, owner_occurrence_id, file_path, line_start", owner_ids)) if owner_ids else []
        return {'kind': 'workspace-data-model-db-schema-table-detail', 'db_schema_tables': tables, 'columns': columns, 'keys': keys, 'relationships': relationships, 'observed_relationships': observed_relationships, 'observed_relationship_column_pairs': observed_pairs, 'key_observations': key_observations, 'key_observation_columns': key_observation_columns, 'constraints': constraints, 'indexes': indexes, 'partitioning': partitioning, 'triggers': triggers, 'matched_physical_assets': physical_assets, 'evidence_refs': evidence}

    def declared_table_relationships(self, token: str='', repo_id: str | None=None, max_results: int=100, page_token: str='') -> dict[str, Any]:
        clauses = ['1=1']
        args: list[Any] = []
        if token:
            clauses.append("lower(coalesce(source_qualified_table_name,source_table) || ' ' || coalesce(target_qualified_table_name,target_table) || ' ' || coalesce(constraint_name,'')) LIKE ?")
            args.append(f'%{token.lower()}%')
        if repo_id:
            clauses.append('repo_id=?')
            args.append(repo_id)
        where = ' AND '.join(clauses)
        filters = {'token': token, 'repo_id': repo_id}
        return self._paged_select(kind='workspace-data-model-declared-table-relationships', query_id='declared_table_relationships', select_sql=f'SELECT db_relationship_occurrence_id, repo_id, local_relationship_id, constraint_name, relationship_kind, source_table, source_qualified_table_name, source_columns_json, target_table, target_qualified_table_name, target_columns_json, source_db_table_occurrence_id, source_db_table_occurrence_ids_json, target_db_table_occurrence_id, target_db_table_occurrence_ids_json, source_set, module_name FROM db_schema_relationship WHERE {where} ORDER BY repo_id, normalized_source_qualified_table_name, normalized_target_qualified_table_name, occurrence_ordinal', count_sql=f'SELECT count(*) FROM db_schema_relationship WHERE {where}', args=args, filters=filters, max_results=max_results, page_token=page_token)

    def observed_table_relationships(self, token: str='', repo_id: str | None=None, relation_kind: str | None=None, source_kind: str | None=None, max_results: int=100, page_token: str='') -> dict[str, Any]:
        clauses = ['1=1']
        args: list[Any] = []
        if token:
            clauses.append("lower(coalesce(left_local_table_id,'') || ' ' || coalesce(left_qualified_table_name,left_table_name,left_unresolved_name,'') || ' ' || coalesce(right_local_table_id,'') || ' ' || coalesce(right_qualified_table_name,right_table_name,right_unresolved_name,'') || ' ' || relation_kind || ' ' || source_kind) LIKE ?")
            args.append(f'%{token.lower()}%')
        if repo_id:
            clauses.append('repo_id=?')
            args.append(repo_id)
        if relation_kind:
            clauses.append('relation_kind=?')
            args.append(relation_kind)
        if source_kind:
            clauses.append('source_kind=?')
            args.append(source_kind)
        where = ' AND '.join(clauses)
        filters = {'token': token, 'repo_id': repo_id, 'relation_kind': relation_kind, 'source_kind': source_kind}
        return self._paged_select(kind='workspace-data-model-observed-table-relationships', query_id='observed_table_relationships', select_sql=f'SELECT r.relationship_observation_occurrence_id, r.repo_id, r.local_observation_id, r.relation_kind, r.source_kind, r.statement_id, r.query_id, r.join_type, r.direction, r.left_local_table_id, r.left_table_name, r.left_schema_name, r.left_qualified_table_name, r.left_unresolved_name, r.left_db_table_occurrence_id, r.left_db_table_occurrence_ids_json, r.right_local_table_id, r.right_table_name, r.right_schema_name, r.right_qualified_table_name, r.right_unresolved_name, r.right_db_table_occurrence_id, r.right_db_table_occurrence_ids_json, r.matched_declared_keys_json, (SELECT count(*) FROM table_relationship_column_pair p WHERE p.relationship_observation_occurrence_id=r.relationship_observation_occurrence_id) AS column_pair_count FROM table_relationship_observation r WHERE {where} ORDER BY r.repo_id, r.relation_kind, r.occurrence_ordinal, r.relationship_observation_occurrence_id', count_sql=f'SELECT count(*) FROM table_relationship_observation WHERE {where}', args=args, filters=filters, max_results=max_results, page_token=page_token)

    def table_relationship_detail(self, observation_id: str) -> dict[str, Any]:
        with self._connect() as con:
            observations = self._rows(con.execute('SELECT * FROM table_relationship_observation WHERE relationship_observation_occurrence_id=? OR local_observation_id=? ORDER BY repo_id, occurrence_ordinal', [observation_id, observation_id]))
            if not observations:
                return {'kind': 'workspace-data-model-table-relationship-detail', 'observation_id': observation_id, 'not_found': True}
            ids = [item['relationship_observation_occurrence_id'] for item in observations]
            placeholders = ','.join(('?' for _ in ids))
            pairs = self._rows(con.execute(f'SELECT * FROM table_relationship_column_pair WHERE relationship_observation_occurrence_id IN ({placeholders}) ORDER BY relationship_observation_occurrence_id, pair_ordinal', ids))
            evidence = self._rows(con.execute(f'SELECT * FROM evidence_ref WHERE owner_occurrence_id IN ({placeholders}) ORDER BY owner_occurrence_id, file_path, line_start', ids))
        return {'kind': 'workspace-data-model-table-relationship-detail', 'observations': observations, 'column_pairs': pairs, 'evidence_refs': evidence}

    def table_neighbors(self, table_id: str, relation_kind: str | None=None, max_results: int=100, page_token: str='') -> dict[str, Any]:
        page_size = self._normalize_page_size(max_results)
        filters = {'table_id': table_id, 'relation_kind': relation_kind}
        offset = self._decode_page_token(page_token, query_id='table_neighbors', filters=filters)
        normalized = normalize_db_identifier(table_id)
        with self._connect() as con:
            table_rows = self._rows(con.execute('SELECT db_table_occurrence_id FROM db_schema_table WHERE db_table_occurrence_id=? OR local_table_id=? OR normalized_qualified_table_name=? OR normalized_table_name=? ORDER BY repo_id, occurrence_ordinal', [table_id, table_id, normalized, normalized.rsplit('.', 1)[-1]]))
            ids = [item['db_table_occurrence_id'] for item in table_rows]
            if not ids:
                return {'kind': 'workspace-data-model-table-neighbors', 'table_id': table_id, 'not_found': True, 'items': [], 'total_count': 0, 'returned_count': 0, 'truncated': False, 'next_token': None}
            encoded = [json.dumps(item) for item in ids]
            clauses = []
            args: list[Any] = []
            for value in encoded:
                clauses.append('json_contains(left_db_table_occurrence_ids_json, ?::JSON) OR json_contains(right_db_table_occurrence_ids_json, ?::JSON)')
                args.extend([value, value])
            where = '(' + ') OR ('.join(clauses) + ')'
            if relation_kind:
                where = f'({where}) AND relation_kind=?'
                args.append(relation_kind)
            rows = self._rows(con.execute(f'SELECT * FROM table_relationship_observation WHERE {where} ORDER BY repo_id, relation_kind, occurrence_ordinal', args))
        items = []
        idset = set(ids)
        for row in rows:
            left_ids = set(row.get('left_db_table_occurrence_ids_json') or [])
            right_ids = set(row.get('right_db_table_occurrence_ids_json') or [])
            role = 'left' if idset & left_ids else 'right'
            other_name = row.get('right_qualified_table_name') or row.get('right_table_name') or row.get('right_unresolved_name') or row.get('right_local_table_id') if role == 'left' else row.get('left_qualified_table_name') or row.get('left_table_name') or row.get('left_unresolved_name') or row.get('left_local_table_id')
            items.append({'relationship_observation_occurrence_id': row['relationship_observation_occurrence_id'], 'repo_id': row['repo_id'], 'relation_kind': row['relation_kind'], 'source_kind': row['source_kind'], 'table_role': role, 'other_table_name': other_name, 'other_db_table_occurrence_ids': row.get('right_db_table_occurrence_ids_json') if role == 'left' else row.get('left_db_table_occurrence_ids_json')})
        page = items[offset:offset + page_size]
        return self._page_result(kind='workspace-data-model-table-neighbors', query_id='table_neighbors', filters=filters, items=page, total_count=len(items), offset=offset, page_size=page_size)

    def data_movement_observations(self, token: str='', repo_id: str | None=None, max_results: int=100, page_token: str='') -> dict[str, Any]:
        return self.observed_table_relationships(token=token, repo_id=repo_id, relation_kind='data_movement', max_results=max_results, page_token=page_token)

    def declared_primary_keys(self, token: str='', repo_id: str | None=None, max_results: int=100, page_token: str='') -> dict[str, Any]:
        clauses = ["lower(coalesce(constraint_kind,'')) IN ('primary_key','primary key','pk')"]
        args: list[Any] = []
        if token:
            clauses.append("lower(coalesce(qualified_table_name,table_name) || ' ' || coalesce(constraint_name,'')) LIKE ?")
            args.append(f'%{token.lower()}%')
        if repo_id:
            clauses.append('repo_id=?')
            args.append(repo_id)
        where = ' AND '.join(clauses)
        filters = {'token': token, 'repo_id': repo_id}
        return self._paged_select(kind='workspace-data-model-declared-primary-keys', query_id='declared_primary_keys', select_sql=f'SELECT db_key_occurrence_id, repo_id, local_key_id, constraint_name, constraint_kind, table_name, qualified_table_name, columns_json, db_table_occurrence_id, db_table_occurrence_ids_json, source_set, module_name FROM db_schema_key WHERE {where} ORDER BY repo_id, normalized_qualified_table_name, occurrence_ordinal', count_sql=f'SELECT count(*) FROM db_schema_key WHERE {where}', args=args, filters=filters, max_results=max_results, page_token=page_token)

    def table_key_observations(self, token: str='', repo_id: str | None=None, key_kind: str | None=None, source_kind: str | None=None, max_results: int=100, page_token: str='') -> dict[str, Any]:
        clauses = ['1=1']
        args: list[Any] = []
        if token:
            clauses.append("lower(coalesce(local_table_id,'') || ' ' || coalesce(qualified_table_name,table_name,unresolved_table_name,'') || ' ' || key_kind || ' ' || source_kind || ' ' || coalesce(entity_name,'')) LIKE ?")
            args.append(f'%{token.lower()}%')
        if repo_id:
            clauses.append('repo_id=?')
            args.append(repo_id)
        if key_kind:
            clauses.append('key_kind=?')
            args.append(key_kind)
        if source_kind:
            clauses.append('source_kind=?')
            args.append(source_kind)
        where = ' AND '.join(clauses)
        filters = {'token': token, 'repo_id': repo_id, 'key_kind': key_kind, 'source_kind': source_kind}
        return self._paged_select(kind='workspace-data-model-table-key-observations', query_id='table_key_observations', select_sql=f'SELECT k.key_observation_occurrence_id, k.repo_id, k.local_observation_id, k.key_kind, k.source_kind, k.local_table_id, k.table_name, k.schema_name, k.qualified_table_name, k.unresolved_table_name, k.db_table_occurrence_id, k.db_table_occurrence_ids_json, k.constraint_name, k.index_name, k.entity_name, k.observation_basis_json, (SELECT count(*) FROM table_key_observation_column c WHERE c.key_observation_occurrence_id=k.key_observation_occurrence_id) AS column_count FROM table_key_observation k WHERE {where} ORDER BY k.repo_id, k.key_kind, k.occurrence_ordinal', count_sql=f'SELECT count(*) FROM table_key_observation WHERE {where}', args=args, filters=filters, max_results=max_results, page_token=page_token)

    def table_key_detail(self, observation_id: str) -> dict[str, Any]:
        with self._connect() as con:
            observations = self._rows(con.execute('SELECT * FROM table_key_observation WHERE key_observation_occurrence_id=? OR local_observation_id=? ORDER BY repo_id, occurrence_ordinal', [observation_id, observation_id]))
            if not observations:
                return {'kind': 'workspace-data-model-table-key-detail', 'observation_id': observation_id, 'not_found': True}
            ids = [item['key_observation_occurrence_id'] for item in observations]
            placeholders = ','.join(('?' for _ in ids))
            columns = self._rows(con.execute(f'SELECT * FROM table_key_observation_column WHERE key_observation_occurrence_id IN ({placeholders}) ORDER BY key_observation_occurrence_id, column_ordinal', ids))
            evidence = self._rows(con.execute(f'SELECT * FROM evidence_ref WHERE owner_occurrence_id IN ({placeholders}) ORDER BY owner_occurrence_id, file_path, line_start', ids))
        return {'kind': 'workspace-data-model-table-key-detail', 'observations': observations, 'columns': columns, 'evidence_refs': evidence}

    def tables_without_declared_key(self, token: str='', repo_id: str | None=None, max_results: int=100, page_token: str='') -> dict[str, Any]:
        clauses = ["NOT EXISTS (SELECT 1 FROM db_schema_key k WHERE k.db_table_occurrence_id=t.db_table_occurrence_id AND lower(coalesce(k.constraint_kind,'')) IN ('primary_key','primary key','pk'))"]
        args: list[Any] = []
        if token:
            clauses.append('lower(coalesce(t.qualified_table_name,t.table_name)) LIKE ?')
            args.append(f'%{token.lower()}%')
        if repo_id:
            clauses.append('t.repo_id=?')
            args.append(repo_id)
        where = ' AND '.join(clauses)
        filters = {'token': token, 'repo_id': repo_id}
        return self._paged_select(kind='workspace-data-model-tables-without-declared-key', query_id='tables_without_declared_key', select_sql=f'SELECT t.db_table_occurrence_id, t.repo_id, t.local_table_id, t.table_name, t.schema_name, t.qualified_table_name, t.source_type, t.source_set, t.module_name FROM db_schema_table t WHERE {where} ORDER BY t.repo_id, t.normalized_qualified_table_name, t.occurrence_ordinal', count_sql=f'SELECT count(*) FROM db_schema_table t WHERE {where}', args=args, filters=filters, max_results=max_results, page_token=page_token)

    def entity_inheritance(self, token: str='', repo_id: str | None=None, relation_kind: str | None=None, max_results: int=100, page_token: str='') -> dict[str, Any]:
        clauses = ['1=1']
        args: list[Any] = []
        if token:
            clauses.append("lower(child_fqcn || ' ' || coalesce(resolved_parent_fqcn,'') || ' ' || coalesce(declared_parent_reference,'')) LIKE ?")
            args.append(f'%{token.lower()}%')
        if repo_id:
            clauses.append('repo_id=?')
            args.append(repo_id)
        if relation_kind:
            clauses.append('relation_kind=?')
            args.append(relation_kind)
        where = ' AND '.join(clauses)
        filters = {'token': token, 'repo_id': repo_id, 'relation_kind': relation_kind}
        return self._paged_select(kind='workspace-data-model-entity-inheritance', query_id='entity_inheritance', select_sql=f'\n                SELECT inheritance_occurrence_id, repo_id, local_observation_id,\n                       child_fqcn, child_java_type_occurrence_id, relation_kind,\n                       declared_parent_reference, declared_parent_type,\n                       declared_parent_type_arguments_json, resolution_kind,\n                       resolved_parent_fqcn, parent_java_type_occurrence_id,\n                       candidate_parent_fqcns_json, source_path, source_scope,\n                       line_start, line_end\n                FROM java_inheritance_observation\n                WHERE {where}\n                ORDER BY repo_id, child_fqcn, relation_kind, coalesce(resolved_parent_fqcn, declared_parent_reference), inheritance_occurrence_id\n            ', count_sql=f'SELECT count(*) FROM java_inheritance_observation WHERE {where}', args=args, filters=filters, max_results=max_results, page_token=page_token)

    def effective_entity_fields(self, token: str='', repo_id: str | None=None, entity_id: str | None=None, inherited: bool | None=None, model_exclusion_observed: bool | None=None, max_results: int=100, page_token: str='') -> dict[str, Any]:
        clauses = ['1=1']
        args: list[Any] = []
        if token:
            clauses.append("lower(effective_owner_fqcn || ' ' || field_name || ' ' || coalesce(effective_type,'') || ' ' || coalesce(declaration_owner_fqcn,'')) LIKE ?")
            args.append(f'%{token.lower()}%')
        if repo_id:
            clauses.append('repo_id=?')
            args.append(repo_id)
        if entity_id:
            clauses.append('(effective_owner_entity_occurrence_id=? OR effective_owner_fqcn=? OR effective_owner_entity_occurrence_id IN (SELECT entity_occurrence_id FROM data_model_entity WHERE local_entity_id=? OR qualified_name=?))')
            args.extend([entity_id, entity_id, entity_id, entity_id])
        if inherited is not None:
            clauses.append('inherited=?')
            args.append(bool(inherited))
        if model_exclusion_observed is not None:
            clauses.append('model_exclusion_observed=?')
            args.append(bool(model_exclusion_observed))
        where = ' AND '.join(clauses)
        filters = {'token': token, 'repo_id': repo_id, 'entity_id': entity_id, 'inherited': inherited, 'model_exclusion_observed': model_exclusion_observed}
        return self._paged_select(kind='workspace-data-model-effective-entity-fields', query_id='effective_entity_fields', select_sql=f'\n                SELECT effective_field_occurrence_id, repo_id, local_effective_field_id,\n                       effective_owner_fqcn, effective_owner_name, effective_owner_kind,\n                       effective_owner_entity_occurrence_id, field_name,\n                       declared_type, effective_type, declaration_owner_fqcn,\n                       declaration_java_type_occurrence_id, association_origin,\n                       inherited, inheritance_depth, inheritance_path_json,\n                       container_kind, element_type, field_annotations_json,\n                       model_exclusion_observed, model_exclusion_annotations_json,\n                       source_path, source_scope, syntax_provider\n                FROM effective_entity_field\n                WHERE {where}\n                ORDER BY repo_id, effective_owner_fqcn, inherited, field_name, effective_field_occurrence_id\n            ', count_sql=f'SELECT count(*) FROM effective_entity_field WHERE {where}', args=args, filters=filters, max_results=max_results, page_token=page_token)

    def effective_entity_associations(self, token: str='', repo_id: str | None=None, entity_id: str | None=None, target_entity_id: str | None=None, inherited: bool | None=None, model_exclusion_observed: bool | None=None, max_results: int=100, page_token: str='') -> dict[str, Any]:
        clauses = ['1=1']
        args: list[Any] = []
        if token:
            clauses.append("lower(effective_owner_fqcn || ' ' || source_field || ' ' || coalesce(target_observed_fqcn,'') || ' ' || coalesce(target_type_reference,'')) LIKE ?")
            args.append(f'%{token.lower()}%')
        if repo_id:
            clauses.append('repo_id=?')
            args.append(repo_id)
        if entity_id:
            clauses.append('(effective_owner_entity_occurrence_id=? OR effective_owner_fqcn=? OR effective_owner_entity_occurrence_id IN (SELECT entity_occurrence_id FROM data_model_entity WHERE local_entity_id=? OR qualified_name=?))')
            args.extend([entity_id, entity_id, entity_id, entity_id])
        if target_entity_id:
            clauses.append('(target_entity_occurrence_id=? OR target_observed_fqcn=? OR target_entity_occurrence_id IN (SELECT entity_occurrence_id FROM data_model_entity WHERE local_entity_id=? OR qualified_name=?))')
            args.extend([target_entity_id, target_entity_id, target_entity_id, target_entity_id])
        if inherited is not None:
            clauses.append('inherited=?')
            args.append(bool(inherited))
        if model_exclusion_observed is not None:
            clauses.append('model_exclusion_observed=?')
            args.append(bool(model_exclusion_observed))
        where = ' AND '.join(clauses)
        filters = {'token': token, 'repo_id': repo_id, 'entity_id': entity_id, 'target_entity_id': target_entity_id, 'inherited': inherited, 'model_exclusion_observed': model_exclusion_observed}
        return self._paged_select(kind='workspace-data-model-effective-entity-associations', query_id='effective_entity_associations', select_sql=f'\n                SELECT effective_association_occurrence_id, repo_id, local_effective_association_id,\n                       effective_owner_fqcn, effective_owner_name, effective_owner_kind,\n                       effective_owner_entity_occurrence_id, source_field,\n                       declared_type, effective_type, target_type_reference,\n                       target_type_reference_observed, target_observed_fqcn,\n                       target_entity_occurrence_id, target_model_kind,\n                       target_resolution_kind, target_candidates_json,\n                       declaration_owner_fqcn, declaration_java_type_occurrence_id,\n                       association_origin, inherited, inheritance_depth,\n                       inheritance_path_json, container_kind, element_type,\n                       model_exclusion_observed, model_exclusion_annotations_json,\n                       evidence_maturity_level, syntax_provider\n                FROM effective_entity_association\n                WHERE {where}\n                ORDER BY repo_id, effective_owner_fqcn, source_field, coalesce(target_observed_fqcn,target_type_reference), effective_association_occurrence_id\n            ', count_sql=f'SELECT count(*) FROM effective_entity_association WHERE {where}', args=args, filters=filters, max_results=max_results, page_token=page_token)

    def effective_entity_model(self, entity_id: str) -> dict[str, Any]:
        with self._connect() as con:
            entities = self._rows(con.execute('SELECT * FROM data_model_entity\n                   WHERE entity_occurrence_id=? OR local_entity_id=? OR qualified_name=? OR name=?\n                   ORDER BY repo_id, occurrence_ordinal, entity_occurrence_id', [entity_id, entity_id, entity_id, entity_id]))
            if not entities:
                return {'kind': 'workspace-data-model-effective-entity-model', 'entity_id': entity_id, 'not_found': True}
            occurrence_ids = [row['entity_occurrence_id'] for row in entities]
            fqcns = [row['qualified_name'] for row in entities if row.get('qualified_name')]
            occ_placeholders = ','.join(('?' for _ in occurrence_ids))
            fqcn_placeholders = ','.join(('?' for _ in fqcns)) if fqcns else 'NULL'
            fields = self._rows(con.execute(f'SELECT * FROM effective_entity_field\n                    WHERE effective_owner_entity_occurrence_id IN ({occ_placeholders})\n                       OR effective_owner_fqcn IN ({fqcn_placeholders})\n                    ORDER BY repo_id, inherited, field_name, effective_field_occurrence_id', [*occurrence_ids, *fqcns]))
            associations = self._rows(con.execute(f'SELECT * FROM effective_entity_association\n                    WHERE effective_owner_entity_occurrence_id IN ({occ_placeholders})\n                       OR effective_owner_fqcn IN ({fqcn_placeholders})\n                    ORDER BY repo_id, inherited, source_field, effective_association_occurrence_id', [*occurrence_ids, *fqcns]))
            inheritance = self._rows(con.execute(f'SELECT * FROM java_inheritance_observation\n                    WHERE child_fqcn IN ({fqcn_placeholders})\n                    ORDER BY repo_id, child_fqcn, relation_kind, inheritance_occurrence_id', fqcns)) if fqcns else []
            owner_ids = [row['effective_field_occurrence_id'] for row in fields]
            owner_ids.extend((row['effective_association_occurrence_id'] for row in associations))
            owner_ids.extend((row['inheritance_occurrence_id'] for row in inheritance))
            if owner_ids:
                evidence_placeholders = ','.join(('?' for _ in owner_ids))
                evidence = self._rows(con.execute(f'SELECT * FROM evidence_ref WHERE owner_occurrence_id IN ({evidence_placeholders}) ORDER BY owner_occurrence_id, file_path, line_start', owner_ids))
            else:
                evidence = []
        return {'kind': 'workspace-data-model-effective-entity-model', 'entities': entities, 'effective_fields': fields, 'effective_associations': associations, 'direct_inheritance': inheritance, 'counts': {'entities': len(entities), 'effective_fields': len(fields), 'inherited_fields': sum((1 for row in fields if row.get('inherited'))), 'effective_associations': len(associations), 'inherited_associations': sum((1 for row in associations if row.get('inherited'))), 'direct_inheritance': len(inheritance)}, 'evidence_refs': evidence}

    def entity_neighbors(self, entity_id: str, max_results: int=100, page_token: str='') -> dict[str, Any]:
        filters = {'entity_id': entity_id}
        where = 'effective_owner_entity_occurrence_id=? OR effective_owner_fqcn=?\n                   OR target_entity_occurrence_id=? OR target_observed_fqcn=?\n                   OR effective_owner_entity_occurrence_id IN (SELECT entity_occurrence_id FROM data_model_entity WHERE local_entity_id=? OR qualified_name=?)\n                   OR target_entity_occurrence_id IN (SELECT entity_occurrence_id FROM data_model_entity WHERE local_entity_id=? OR qualified_name=?)'
        args = [entity_id, entity_id, entity_id, entity_id, entity_id, entity_id, entity_id, entity_id]
        return self._paged_select(kind='workspace-data-model-entity-neighbors', query_id='entity_neighbors', select_sql=f'\n                SELECT effective_association_occurrence_id, repo_id,\n                       effective_owner_fqcn, effective_owner_entity_occurrence_id,\n                       source_field, target_observed_fqcn, target_entity_occurrence_id,\n                       target_model_kind, target_resolution_kind,\n                       declaration_owner_fqcn, association_origin, inherited,\n                       inheritance_depth, inheritance_path_json, container_kind,\n                       model_exclusion_observed, model_exclusion_annotations_json\n                FROM effective_entity_association\n                WHERE {where}\n                ORDER BY repo_id, effective_owner_fqcn, source_field, coalesce(target_observed_fqcn,target_type_reference), effective_association_occurrence_id\n            ', count_sql=f'SELECT count(*) FROM effective_entity_association WHERE {where}', args=args, filters=filters, max_results=max_results, page_token=page_token)

    def associations(self, token: str='', repo_id: str | None=None, max_results: int=100, page_token: str='') -> dict[str, Any]:
        clauses = ['1=1']
        args: list[Any] = []
        if token:
            clauses.append("lower(\n                coalesce(local_association_id,'') || ' ' || coalesce(from_local_entity_id,'') || ' ' ||\n                coalesce(to_local_entity_id,'') || ' ' || coalesce(evidence_type,'') || ' ' ||\n                coalesce(relationship_kind,'') || ' ' || coalesce(from_role,'') || ' ' || coalesce(to_role,'')\n            ) LIKE ?")
            args.append(f'%{token.lower()}%')
        if repo_id:
            clauses.append('repo_id=?')
            args.append(repo_id)
        where = ' AND '.join(clauses)
        filters = {'token': token, 'repo_id': repo_id}
        return self._paged_select(kind='workspace-data-model-associations', query_id='associations', select_sql=f'\n                SELECT association_occurrence_id, repo_id, local_association_id,\n                       from_local_entity_id, to_local_entity_id,\n                       from_entity_occurrence_id, to_entity_occurrence_id,\n                       from_entity_occurrence_ids_json, to_entity_occurrence_ids_json,\n                       evidence_type, relationship_kind, from_multiplicity, to_multiplicity,\n                       from_role, to_role\n                FROM data_model_association\n                WHERE {where}\n                ORDER BY repo_id, association_occurrence_id\n            ', count_sql=f'SELECT count(*) FROM data_model_association WHERE {where}', args=args, filters=filters, max_results=max_results, page_token=page_token)

    def missing_facts(self, token: str='', repo_id: str | None=None, missing_fact_kind: str | None=None, max_results: int=100, page_token: str='') -> dict[str, Any]:
        clauses = ['1=1']
        args: list[Any] = []
        if token:
            clauses.append("lower(description || ' ' || coalesce(missing_fact_kind,'')) LIKE ?")
            args.append(f'%{token.lower()}%')
        if repo_id:
            clauses.append('repo_id=?')
            args.append(repo_id)
        if missing_fact_kind:
            clauses.append('missing_fact_kind=?')
            args.append(missing_fact_kind)
        where = ' AND '.join(clauses)
        filters = {'token': token, 'repo_id': repo_id, 'missing_fact_kind': missing_fact_kind}
        return self._paged_select(kind='workspace-data-model-missing-facts', query_id='missing_facts', select_sql=f'\n                SELECT gap_occurrence_id, repo_id, local_gap_id, category, missing_fact_kind,\n                       required_for_operation, description,\n                       affected_entity_ids_json, affected_physical_asset_ids_json\n                FROM workspace_missing_fact\n                WHERE {where}\n                ORDER BY repo_id, missing_fact_kind, gap_occurrence_id\n            ', count_sql=f'SELECT count(*) FROM workspace_missing_fact WHERE {where}', args=args, filters=filters, max_results=max_results, page_token=page_token)

    def missing_fact_detail(self, gap_id: str) -> dict[str, Any]:
        """Return one missing fact with its complete projected source-gap payload."""
        with self._connect() as con:
            gaps = self._rows(con.execute(
                """SELECT * FROM workspace_missing_fact
                   WHERE gap_occurrence_id=? OR local_gap_id=?
                   ORDER BY repo_id, gap_occurrence_id""",
                [gap_id, gap_id],
            ))
            if not gaps:
                return {
                    'kind': 'workspace-data-model-missing-fact-detail',
                    'gap_id': gap_id,
                    'not_found': True,
                    'gaps': [],
                    'evidence_refs': [],
                }
            occurrence_ids = [item['gap_occurrence_id'] for item in gaps]
            placeholders = ','.join('?' for _ in occurrence_ids)
            evidence = self._rows(con.execute(
                f"""SELECT * FROM evidence_ref
                    WHERE owner_type='workspace_missing_fact'
                      AND owner_occurrence_id IN ({placeholders})
                    ORDER BY owner_occurrence_id, file_path, line_start, line_end""",
                occurrence_ids,
            ))
        return {
            'kind': 'workspace-data-model-missing-fact-detail',
            'gap_id': gap_id,
            'gaps': gaps,
            'evidence_refs': evidence,
        }

    def missing_fact_summary(self, token: str='', repo_id: str | None=None, max_results: int=100, page_token: str='') -> dict[str, Any]:
        clauses = ['1=1']
        args: list[Any] = []
        if token:
            clauses.append("lower(coalesce(category,'') || ' ' || coalesce(missing_fact_kind,'') || ' ' || coalesce(required_for_operation,'')) LIKE ?")
            args.append(f'%{token.lower()}%')
        if repo_id:
            clauses.append('repo_id=?')
            args.append(repo_id)
        where = ' AND '.join(clauses)
        filters = {'token': token, 'repo_id': repo_id}
        grouped = f'\n            SELECT repo_id, category, missing_fact_kind, required_for_operation,\n                   count(*) AS missing_fact_count\n            FROM workspace_missing_fact\n            WHERE {where}\n            GROUP BY repo_id, category, missing_fact_kind, required_for_operation\n        '
        return self._paged_select(kind='workspace-data-model-missing-fact-summary', query_id='missing_fact_summary', select_sql=f'SELECT * FROM ({grouped}) grouped\n                ORDER BY repo_id, category, missing_fact_kind, required_for_operation', count_sql=f'SELECT count(*) FROM ({grouped}) grouped', args=args, filters=filters, max_results=max_results, page_token=page_token)

    def entity_evidence(self, entity_id: str, max_results: int=200) -> dict[str, Any]:
        detail = self.entity_detail(entity_id)
        if detail.get('not_found'):
            return {'kind': 'workspace-data-model-entity-evidence', 'entity_id': entity_id, 'not_found': True, 'items': []}
        owner_ids = [item['entity_occurrence_id'] for item in detail['entities']]
        owner_ids.extend((item['attribute_occurrence_id'] for item in detail['attributes']))
        if not owner_ids:
            return {'kind': 'workspace-data-model-entity-evidence', 'entity_id': entity_id, 'items': []}
        placeholders = ','.join(('?' for _ in owner_ids))
        with self._connect() as con:
            rows = self._rows(con.execute(f'SELECT * FROM evidence_ref WHERE owner_occurrence_id IN ({placeholders}) ORDER BY owner_type, owner_occurrence_id, file_path, line_start LIMIT ?', owner_ids + [max_results]))
        return {'kind': 'workspace-data-model-entity-evidence', 'entity_id': entity_id, 'items': rows}


    def list_modules(self, *, token: str='', repo_id: str | None=None, max_results: int=100, page_token: str='') -> dict[str, Any]:
        filters = {'token': token, 'repo_id': repo_id}
        if not self._has_relation('v_build_module'):
            return self._empty_page(kind='knowledge-layer-build-modules', query_id='build_modules', filters=filters, max_results=max_results, page_token=page_token)
        clauses = ['1=1']
        args: list[Any] = []
        if token:
            clauses.append("lower(coalesce(module_path,'') || ' ' || coalesce(module_name,'') || ' ' || coalesce(project_directory,'') || ' ' || coalesce(build_file,'')) LIKE ?")
            args.append(f'%{token.lower()}%')
        if repo_id:
            clauses.append('repo_id=?')
            args.append(repo_id)
        where = ' AND '.join(clauses)
        return self._paged_select(kind='knowledge-layer-build-modules', query_id='build_modules', select_sql=f'SELECT * FROM v_build_module WHERE {where} ORDER BY repo_id, module_path', count_sql=f'SELECT count(*) FROM v_build_module WHERE {where}', args=args, filters=filters, max_results=max_results, page_token=page_token)

    def module_dependencies(self, *, repo_id: str | None=None, source_module_path: str | None=None, target_module_path: str | None=None, configuration: str | None=None, max_results: int=100, page_token: str='') -> dict[str, Any]:
        filters = {'repo_id': repo_id, 'source_module_path': source_module_path, 'target_module_path': target_module_path, 'configuration': configuration}
        if not self._has_relation('v_build_dependency'):
            return self._empty_page(kind='knowledge-layer-module-dependencies', query_id='module_dependencies', filters=filters, max_results=max_results, page_token=page_token)
        clauses = ["target_module_path IS NOT NULL"]
        args: list[Any] = []
        for column, value in [('repo_id', repo_id), ('source_module_path', source_module_path), ('target_module_path', target_module_path), ('configuration', configuration)]:
            if value:
                clauses.append(f'{column}=?')
                args.append(value)
        where = ' AND '.join(clauses)
        return self._paged_select(kind='knowledge-layer-module-dependencies', query_id='module_dependencies', select_sql=f'SELECT * FROM v_build_dependency WHERE {where} ORDER BY repo_id, source_module_path, target_module_path, configuration, dependency_occurrence_id', count_sql=f'SELECT count(*) FROM v_build_dependency WHERE {where}', args=args, filters=filters, max_results=max_results, page_token=page_token)

    def external_dependencies(self, *, token: str='', repo_id: str | None=None, source_module_path: str | None=None, configuration: str | None=None, include_test: bool=True, max_results: int=100, page_token: str='') -> dict[str, Any]:
        filters = {'token': token, 'repo_id': repo_id, 'source_module_path': source_module_path, 'configuration': configuration, 'include_test': include_test}
        if not self._has_relation('v_build_dependency'):
            return self._empty_page(kind='knowledge-layer-external-dependencies', query_id='external_dependencies', filters=filters, max_results=max_results, page_token=page_token)
        clauses = ["target_module_path IS NULL", "coordinate IS NOT NULL"]
        args: list[Any] = []
        if token:
            clauses.append("lower(coalesce(coordinate,'') || ' ' || coalesce(group_id,'') || ' ' || coalesce(artifact_id,'') || ' ' || coalesce(alias,'')) LIKE ?")
            args.append(f'%{token.lower()}%')
        for column, value in [('repo_id', repo_id), ('source_module_path', source_module_path), ('configuration', configuration)]:
            if value:
                clauses.append(f'{column}=?')
                args.append(value)
        if not include_test:
            clauses.append('coalesce(is_test_source,false)=false')
        where = ' AND '.join(clauses)
        return self._paged_select(kind='knowledge-layer-external-dependencies', query_id='external_dependencies', select_sql=f'SELECT * FROM v_build_dependency WHERE {where} ORDER BY repo_id, source_module_path, coordinate, configuration, dependency_occurrence_id', count_sql=f'SELECT count(*) FROM v_build_dependency WHERE {where}', args=args, filters=filters, max_results=max_results, page_token=page_token)

    def build_plugins(self, *, repo_id: str | None=None, module_path: str | None=None, max_results: int=100, page_token: str='') -> dict[str, Any]:
        filters = {'repo_id': repo_id, 'module_path': module_path}
        if not self._has_relation('build_plugin'):
            return self._empty_page(kind='knowledge-layer-build-plugins', query_id='build_plugins', filters=filters, max_results=max_results, page_token=page_token)
        clauses = ['1=1']
        args: list[Any] = []
        if repo_id:
            clauses.append('repo_id=?'); args.append(repo_id)
        if module_path:
            clauses.append('module_path=?'); args.append(module_path)
        where = ' AND '.join(clauses)
        return self._paged_select(kind='knowledge-layer-build-plugins', query_id='build_plugins', select_sql=f'SELECT * FROM build_plugin WHERE {where} ORDER BY repo_id, module_path, plugin_id, plugin_occurrence_id', count_sql=f'SELECT count(*) FROM build_plugin WHERE {where}', args=args, filters=filters, max_results=max_results, page_token=page_token)

    def module_neighborhood(self, module_path: str, *, repo_id: str | None=None, max_results: int=200) -> dict[str, Any]:
        if not self._has_relation('v_build_module'):
            return {'kind': 'knowledge-layer-module-neighborhood', 'module_path': module_path, 'not_available': True, 'capability': 'common.build-dependencies'}
        clauses = ['module_path=?']
        args: list[Any] = [module_path]
        if repo_id:
            clauses.append('repo_id=?'); args.append(repo_id)
        where = ' AND '.join(clauses)
        with self._connect() as con:
            modules = self._rows(con.execute(f'SELECT * FROM v_build_module WHERE {where} ORDER BY repo_id, module_path', args))
            dep_clauses = ['(source_module_path=? OR target_module_path=?)']
            dep_args: list[Any] = [module_path, module_path]
            if repo_id:
                dep_clauses.append('repo_id=?'); dep_args.append(repo_id)
            dependencies = self._rows(con.execute(f'SELECT * FROM v_build_dependency WHERE {" AND ".join(dep_clauses)} ORDER BY repo_id, source_module_path, target_module_path, coordinate LIMIT ?', dep_args + [max_results]))
            plugin_clauses = ['module_path=?']
            plugin_args: list[Any] = [module_path]
            if repo_id:
                plugin_clauses.append('repo_id=?'); plugin_args.append(repo_id)
            plugins = self._rows(con.execute(f'SELECT * FROM build_plugin WHERE {" AND ".join(plugin_clauses)} ORDER BY plugin_id LIMIT ?', plugin_args + [max_results]))
        return {'kind': 'knowledge-layer-module-neighborhood', 'module_path': module_path, 'modules': modules, 'dependencies': dependencies, 'plugins': plugins, 'counts': {'modules': len(modules), 'dependencies': len(dependencies), 'plugins': len(plugins)}}
