from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Sequence

import uvicorn

from .contract_v1.models import SystemCreateRequest, SystemUpdateRequest
from .contract_v1.runtime import KnowledgeApiRuntimeError, KnowledgeApiSettings
from .contract_v1.service import KnowledgeDomainService
from .publication import build_publication_request, merge_metadata_file, parse_metadata_values
from .publication_bundle import import_publication_bundle


def _common_parent() -> argparse.ArgumentParser:
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument("--database", help="Knowledge API SQLite database path")
    parent.add_argument(
        "--allowed-root",
        action="append",
        default=[],
        help="Allowed local root for producer-side file:// artifacts; may be repeated",
    )
    parent.add_argument(
        "--artifact-store",
        help="AISL-owned immutable artifact-store root (default: sibling of catalog database)",
    )
    return parent


def _storage_parent() -> argparse.ArgumentParser:
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument("--database", help="Knowledge API SQLite database path")
    parent.add_argument(
        "--artifact-store",
        help="AISL-owned immutable artifact-store root (default: sibling of catalog database)",
    )
    return parent


def _format_parent() -> argparse.ArgumentParser:
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument("--format", choices=("text", "json"), default="text")
    return parent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Publish and serve canonical knowledge artifacts")
    commands = parser.add_subparsers(dest="command", required=True)
    common = _common_parent()
    formatted = _format_parent()

    serve = commands.add_parser("serve", parents=[common], help="Run the Knowledge API HTTP server")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8080)
    serve.add_argument("--log-level", default="info")

    validate = commands.add_parser(
        "validate",
        parents=[common, formatted],
        help="Validate a completed knowledge execution without changing the catalog",
    )
    _add_publication_inputs(validate, include_publish_controls=False)

    publish = commands.add_parser(
        "publish",
        parents=[common, formatted],
        help="Validate and publish an immutable system revision",
    )
    _add_publication_inputs(publish, include_publish_controls=True)
    publish.add_argument("--display-name", help="Display name used only when the system is first created")
    publish.add_argument("--description", help="Description used only when the system is first created")
    publish.add_argument("--dry-run", action="store_true")

    import_bundle = commands.add_parser(
        "import",
        parents=[_storage_parent(), formatted],
        help="Import a self-contained AISL publication bundle and publish its immutable revision",
    )
    import_bundle.add_argument("--bundle", required=True, type=Path)
    import_bundle.add_argument("--base-revision-id")
    import_bundle.add_argument(
        "--activate",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Override bundle activation default",
    )

    system = commands.add_parser("system", help="Manage systems")
    system_commands = system.add_subparsers(dest="system_command", required=True)
    system_list = system_commands.add_parser("list", parents=[common, formatted])
    system_list.add_argument("--search")
    system_list.add_argument("--offset", type=int, default=0)
    system_list.add_argument("--limit", type=int, default=50)
    system_show = system_commands.add_parser("show", parents=[common, formatted])
    system_show.add_argument("--system-id", required=True)
    system_update = system_commands.add_parser("update", parents=[common, formatted])
    system_update.add_argument("--system-id", required=True)
    system_update.add_argument("--display-name")
    description = system_update.add_mutually_exclusive_group()
    description.add_argument("--description")
    description.add_argument("--clear-description", action="store_true")
    system_update.add_argument("--metadata", action="append", default=[], metavar="KEY=VALUE")
    system_update.add_argument("--metadata-file", type=Path)
    system_delete = system_commands.add_parser("delete", parents=[common, formatted])
    system_delete.add_argument("--system-id", required=True)
    system_delete.add_argument(
        "--yes",
        action="store_true",
        help="Confirm irreversible deletion of the system and all revisions",
    )

    revision = commands.add_parser("revision", help="Manage immutable revisions")
    revision_commands = revision.add_subparsers(dest="revision_command", required=True)
    revision_list = revision_commands.add_parser("list", parents=[common, formatted])
    revision_list.add_argument("--system-id", required=True)
    revision_list.add_argument("--offset", type=int, default=0)
    revision_list.add_argument("--limit", type=int, default=50)
    revision_activate = revision_commands.add_parser("activate", parents=[common, formatted])
    revision_activate.add_argument("--system-id", required=True)
    revision_activate.add_argument("--revision-id", required=True)

    consumer_kit = commands.add_parser(
        "consumer-kit",
        parents=[common, formatted],
        help="Export a revision-pinned LLM Integration Profile / Consumer Kit",
    )
    consumer_kit.add_argument("--system-id", "--system", dest="system_id", required=True)
    consumer_kit.add_argument("--revision-id")
    consumer_kit.add_argument("--profile", required=True, dest="profile_id")
    consumer_kit.add_argument("--output", required=True, type=Path)
    return parser


def _add_publication_inputs(parser: argparse.ArgumentParser, *, include_publish_controls: bool) -> None:
    parser.add_argument("--system-id", required=True)
    parser.add_argument("--execution-result", required=True, type=Path)
    parser.add_argument(
        "--base-revision-id",
        help="Explicit prior revision to retain as the immutable snapshot base",
    )
    parser.add_argument("--label", action="append", default=[])
    parser.add_argument("--metadata", action="append", default=[], metavar="KEY=VALUE")
    parser.add_argument("--metadata-file", type=Path)
    if include_publish_controls:
        parser.add_argument(
            "--activate",
            action=argparse.BooleanOptionalAction,
            default=True,
            help="Activate the revision after publication (default: true)",
        )


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = _run(args)
    except KnowledgeApiRuntimeError as exc:
        payload = {"status": "error", "code": exc.code, "message": exc.message, "details": exc.details}
        if getattr(args, "format", "text") == "json":
            print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        else:
            print(f"Error [{exc.code}]: {exc.message}", file=sys.stderr)
            if exc.details:
                print(json.dumps(exc.details, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        raise SystemExit(1) from exc
    if result is not None:
        _emit(result, getattr(args, "format", "text"))


def _run(args: argparse.Namespace) -> dict[str, Any] | None:
    if args.command == "serve":
        from .app import create_app

        application = create_app(settings=_settings(args))
        uvicorn.run(application, host=args.host, port=args.port, log_level=args.log_level)
        return None

    settings = _settings(args)
    database_existed = settings.database_path.exists()
    if args.command == "import":
        return import_publication_bundle(
            settings=settings,
            bundle_path=args.bundle,
            activate=args.activate,
            base_revision_id=args.base_revision_id,
        )
    service = KnowledgeDomainService(settings)
    if args.command in {"validate", "publish"}:
        metadata = merge_metadata_file(parse_metadata_values(args.metadata), args.metadata_file)
        request, warnings = build_publication_request(
            execution_result=args.execution_result,
            base_revision_id=args.base_revision_id,
            labels=args.label,
            metadata=metadata,
            activate=getattr(args, "activate", False),
        )
        validation = service.validate_publication(args.system_id, request)
        if args.command == "validate":
            result = {"status": "valid", **validation, "warnings": warnings}
            if not database_existed:
                _remove_sqlite_files(settings.database_path)
            return result
        existing_system = service.store.get_system(args.system_id)
        existing_revision = service.store.get_revision(args.system_id, str(validation["revision_id"]))
        if args.dry_run:
            result = {
                "status": "dry_run",
                **validation,
                "system_action": "create" if existing_system is None else "reuse",
                "revision_action": "reuse" if existing_revision is not None else "publish",
                "activate": request.activate,
                "warnings": warnings,
            }
            if not database_existed:
                _remove_sqlite_files(settings.database_path)
            return result
        created_system = False
        if existing_system is None:
            service.create_system(
                SystemCreateRequest(
                    system_id=args.system_id,
                    display_name=args.display_name or args.system_id,
                    description=args.description,
                )
            )
            created_system = True
        else:
            if args.display_name or args.description:
                warnings.append("existing system metadata was not changed; use `knowledge-api system update`")
        try:
            response = service.publish_revision(args.system_id, request, validated=validation)
        except Exception:
            if created_system:
                service.store.delete_system(args.system_id)
            raise
        revision = response.revision
        return {
            "status": "already_published" if existing_revision is not None else "published",
            "system_id": args.system_id,
            "revision_id": revision.revision_id,
            "state": revision.state.value,
            "active": revision.state.value == "active",
            **validation,
            "warnings": warnings,
        }

    if args.command == "system":
        if args.system_command == "list":
            return service.list_systems(offset=args.offset, limit=args.limit, search=args.search).model_dump(mode="json")
        if args.system_command == "show":
            return service.get_system(args.system_id).model_dump(mode="json")
        if args.system_command == "update":
            payload: dict[str, Any] = {}
            if args.display_name is not None:
                payload["display_name"] = args.display_name
            if args.description is not None:
                payload["description"] = args.description
            elif args.clear_description:
                payload["description"] = None
            metadata = merge_metadata_file(parse_metadata_values(args.metadata), args.metadata_file)
            if metadata:
                payload["metadata"] = metadata
            if not payload:
                raise KnowledgeApiRuntimeError(400, "system_update_empty", "no system fields were supplied")
            return service.update_system(args.system_id, SystemUpdateRequest.model_validate(payload)).model_dump(mode="json")
        if args.system_command == "delete":
            if not args.yes:
                raise KnowledgeApiRuntimeError(
                    400,
                    "system_delete_confirmation_required",
                    "system deletion is irreversible; repeat the command with --yes",
                )
            return service.delete_system(args.system_id).model_dump(mode="json")

    if args.command == "revision":
        if args.revision_command == "list":
            return service.list_revisions(
                args.system_id,
                offset=args.offset,
                limit=args.limit,
            ).model_dump(mode="json")
        if args.revision_command == "activate":
            revision = service.activate_revision(args.system_id, args.revision_id)
            return {"status": "active", "revision": revision.model_dump(mode="json")}

    if args.command == "consumer-kit":
        from knowledge_integration import export_consumer_kit
        profile = service.llm_integration_profile(
            args.system_id, revision_id=args.revision_id, profile_id=args.profile_id
        )
        output = export_consumer_kit(profile, args.output)
        return {
            "status": "exported",
            "system_id": profile["scope"]["system_id"],
            "revision_id": profile["scope"]["revision_id"],
            "profile_id": profile["integration_profile"]["profile_id"],
            "fingerprint": profile["integration_profile"]["fingerprint"],
            "output": str(output),
            "files": sorted(path.name for path in output.iterdir() if path.is_file()),
        }
    raise KnowledgeApiRuntimeError(400, "command_invalid", "unsupported command")




def _remove_sqlite_files(path: Path) -> None:
    for candidate in (path, Path(f"{path}-wal"), Path(f"{path}-shm")):
        try:
            candidate.unlink()
        except FileNotFoundError:
            pass


def _settings(args: argparse.Namespace) -> KnowledgeApiSettings:
    database = Path(
        args.database
        or os.environ.get("KNOWLEDGE_API_DATABASE", "outputs/knowledge-api/knowledge-api.sqlite3")
    ).expanduser().resolve()
    roots = tuple(Path(value).expanduser().resolve() for value in getattr(args, "allowed_root", []))
    if not roots:
        configured = os.environ.get("KNOWLEDGE_API_ALLOWED_ROOTS", "outputs")
        roots = tuple(
            Path(value.strip()).expanduser().resolve()
            for value in configured.split(os.pathsep)
            if value.strip()
        )
    artifact_store = Path(
        args.artifact_store
        or os.environ.get("KNOWLEDGE_API_ARTIFACT_STORE", str(database.parent / "artifact-store"))
    ).expanduser().resolve()
    return KnowledgeApiSettings(database_path=database, allowed_roots=roots, artifact_store_path=artifact_store)


def _emit(payload: dict[str, Any], output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return
    if "system_id" in payload:
        print(f"System:           {payload['system_id']}")
    if "revision_id" in payload:
        print(f"Revision:         {payload['revision_id']}")
    if "status" in payload:
        print(f"Status:           {payload['status']}")
    if "state" in payload:
        print(f"State:            {payload['state']}")
    if "execution_result_path" in payload:
        print(f"Execution result: {payload['execution_result_path']}")
    if "execution_result_sha256" in payload:
        print(f"SHA-256:          {payload['execution_result_sha256']}")
    if "knowledge_artifact_count" in payload:
        print(f"Knowledge models: {payload['knowledge_artifact_count']}")
    if "capabilities" in payload and isinstance(payload["capabilities"], list):
        print(f"Capabilities:     {len(payload['capabilities'])}")
    if "table_count" in payload:
        print(f"Tables:           {payload['table_count']}")
    if "field_count" in payload:
        print(f"Fields:           {payload['field_count']}")
    if "relationship_count" in payload:
        print(f"Relationships:    {payload['relationship_count']}")
    if "display_name" in payload:
        print(f"Display name:     {payload['display_name']}")
    if "description" in payload and payload["description"] is not None:
        print(f"Description:      {payload['description']}")
    if "active_revision_id" in payload:
        print(f"Active revision:  {payload['active_revision_id'] or '-'}")
    if "revision_count" in payload:
        print(f"Revisions:        {payload['revision_count']}")
    if "revision" in payload and isinstance(payload["revision"], dict):
        revision = payload["revision"]
        print(f"System:           {revision.get('system_id', '-')}")
        print(f"Revision:         {revision.get('revision_id', '-')}")
        print(f"State:            {revision.get('state', '-')}")
    if "deleted_revision_count" in payload:
        print(f"Deleted revisions: {payload['deleted_revision_count']}")
    if not any(
        key in payload
        for key in (
            "system_id",
            "revision_id",
            "status",
            "execution_result_path",
            "deleted_revision_count",
        )
    ):
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    for warning in payload.get("warnings", []):
        print(f"Warning: {warning}", file=sys.stderr)


if __name__ == "__main__":
    main()
