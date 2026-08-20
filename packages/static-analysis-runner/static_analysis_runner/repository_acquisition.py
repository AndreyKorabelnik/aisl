from __future__ import annotations

import base64
import json
import os
import re
import shutil
import ssl
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import quote, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

from .execution import run_process
from .io_utils import now_utc, read_json, write_json
from .repository_sources import PortfolioRepositorySource, PortfolioRepositorySources

_TEMPORARY_MARKER = ".repository-acquisition-temporary"
_TEMPORARY_MARKER_SCHEMA = "repository_acquisition_temporary/v1"

def _normalize_repo_id(value: str) -> str:
    normalized = re.sub(r"([a-z])([A-Z])", r"\1_\2", str(value or ""))
    normalized = normalized.replace("-", "_").replace(" ", "_")
    normalized = re.sub(r"[^a-zA-Z0-9_]", "_", normalized)
    return re.sub(r"_+", "_", normalized).strip("_").lower()

def _sanitize_repository_url(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("repository URL must not be empty")
    parsed = urlparse(raw)
    if parsed.scheme in {"http", "https", "ssh"} and parsed.hostname:
        host = parsed.hostname
        if parsed.port is not None:
            host = f"{host}:{parsed.port}"
        return urlunparse((parsed.scheme, host, parsed.path, parsed.params, parsed.query, parsed.fragment))
    return raw

def _project_coordinates(project_url: str) -> tuple[str, str]:
    parsed = urlparse(str(project_url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"unsupported Bitbucket project URL: {project_url!r}")
    segments = [segment for segment in parsed.path.split("/") if segment]
    project_key: str | None = None
    for index, segment in enumerate(segments[:-1]):
        if segment.lower() == "projects":
            project_key = segments[index + 1]
            break
    if not project_key:
        raise ValueError(
            "Bitbucket project URL must contain /projects/<project-key>: "
            f"{project_url!r}"
        )
    origin = urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))
    return origin.rstrip("/"), project_key

def _authorization_headers(
    *,
    auth_mode: str,
    token_env: str,
    username_env: str,
    password_env: str,
) -> dict[str, str]:
    mode = str(auth_mode or "auto").strip().lower()
    if mode not in {"auto", "token", "basic", "credential-helper", "ssh", "none"}:
        raise ValueError(f"unsupported auth_mode: {auth_mode!r}")
    token = os.environ.get(token_env, "")
    username = os.environ.get(username_env, "")
    password = os.environ.get(password_env, "")
    if mode == "token" or (mode == "auto" and token):
        if not token:
            raise ValueError(f"authentication token environment variable is empty: {token_env}")
        return {"Authorization": f"Bearer {token}"}
    if mode == "basic" or (mode == "auto" and username and password):
        if not username or not password:
            raise ValueError(
                "basic authentication requires both environment variables: "
                f"{username_env}, {password_env}"
            )
        encoded = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        return {"Authorization": f"Basic {encoded}"}
    return {}

def _ssl_context(*, ca_bundle: Path | None, insecure_skip_tls_verify: bool) -> ssl.SSLContext:
    if insecure_skip_tls_verify:
        return ssl._create_unverified_context()  # noqa: SLF001 - explicit CLI opt-in
    if ca_bundle is not None:
        return ssl.create_default_context(cafile=str(ca_bundle))
    return ssl.create_default_context()

def _clone_url_from_repository(row: Mapping[str, Any], *, auth_mode: str) -> str:
    links = row.get("links")
    clone_rows = links.get("clone") if isinstance(links, Mapping) else None
    candidates: list[tuple[str, str]] = []
    if isinstance(clone_rows, list):
        for item in clone_rows:
            if not isinstance(item, Mapping):
                continue
            href = str(item.get("href") or "").strip()
            name = str(item.get("name") or "").strip().lower()
            if href:
                candidates.append((name, href))
    preferred = "ssh" if str(auth_mode).strip().lower() == "ssh" else "http"
    for name, href in candidates:
        if name == preferred or (preferred == "http" and name == "https"):
            return _sanitize_repository_url(href)
    if candidates:
        return _sanitize_repository_url(candidates[0][1])
    raise ValueError(f"Bitbucket repository has no clone links: {row.get('slug') or row.get('name')}")

def discover_bitbucket_project_repositories(
    *,
    project_url: str,
    auth_mode: str = "auto",
    token_env: str = "BITBUCKET_TOKEN",
    username_env: str = "BITBUCKET_USERNAME",
    password_env: str = "BITBUCKET_PASSWORD",
    api_base_path: str = "/rest/api/latest",
    ca_bundle: str | Path | None = None,
    insecure_skip_tls_verify: bool = False,
    timeout_seconds: float = 60.0,
    page_size: int = 100,
    max_repositories: int | None = None,
    opener: Callable[..., Any] = urlopen,
) -> PortfolioRepositorySources:
    """List every repository in one Bitbucket Data Center project."""
    if page_size < 1:
        raise ValueError("page_size must be at least 1")
    if max_repositories is not None and max_repositories < 1:
        raise ValueError("max_repositories must be at least 1")
    origin, project_key = _project_coordinates(project_url)
    headers = {
        "Accept": "application/json",
        **_authorization_headers(
            auth_mode=auth_mode,
            token_env=token_env,
            username_env=username_env,
            password_env=password_env,
        ),
    }
    context = _ssl_context(
        ca_bundle=Path(ca_bundle).expanduser().resolve() if ca_bundle is not None else None,
        insecure_skip_tls_verify=insecure_skip_tls_verify,
    )
    start = 0
    repositories: list[PortfolioRepositorySource] = []
    seen_ids: set[str] = set()
    while True:
        query = urlencode({"limit": page_size, "start": start})
        url = (
            f"{origin}{api_base_path.rstrip('/')}/projects/{quote(project_key, safe='')}/repos?{query}"
        )
        request = Request(url, headers=headers, method="GET")
        with opener(request, timeout=timeout_seconds, context=context) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, Mapping):
            raise ValueError("Bitbucket repository response must be a JSON object")
        values = payload.get("values")
        if not isinstance(values, list):
            raise ValueError("Bitbucket repository response has no values array")
        for row in values:
            if not isinstance(row, Mapping):
                continue
            slug = str(row.get("slug") or row.get("name") or "").strip()
            repo_id = _normalize_repo_id(slug)
            if not repo_id:
                raise ValueError(f"Bitbucket repository has invalid identity: {slug!r}")
            if repo_id in seen_ids:
                raise ValueError(
                    f"duplicate repository id after normalization in project {project_key}: {repo_id}"
                )
            seen_ids.add(repo_id)
            display_name = str(row.get("name") or slug).strip()
            aliases = tuple(
                value
                for value in dict.fromkeys((slug, display_name, repo_id))
                if value
            )
            repositories.append(
                PortfolioRepositorySource(
                    repo_id=repo_id,
                    clone_url=_clone_url_from_repository(row, auth_mode=auth_mode),
                    ref=None,
                    system_id=None,
                    project_id=project_key,
                    service_aliases=aliases,
                    metadata={
                        "bitbucket_repository_id": row.get("id"),
                        "slug": slug,
                        "name": display_name,
                        "public": row.get("public"),
                        "forkable": row.get("forkable"),
                    },
                )
            )
            if max_repositories is not None and len(repositories) >= max_repositories:
                break
        if max_repositories is not None and len(repositories) >= max_repositories:
            break
        if bool(payload.get("isLastPage")):
            break
        next_start = payload.get("nextPageStart")
        if next_start is None:
            if not values:
                break
            next_start = start + len(values)
        start = int(next_start)
    if not repositories:
        raise ValueError(f"Bitbucket project contains no repositories: {project_url}")
    return PortfolioRepositorySources(
        source={
            "kind": "bitbucket-data-center",
            "project_url": project_url,
            "project_key": project_key,
            "api_base_path": api_base_path,
            "repository_selection": {
                "mode": "api_order_prefix",
                "limit": max_repositories,
                "selected_count": len(repositories),
                "limit_reached": (
                    max_repositories is not None
                    and len(repositories) >= max_repositories
                ),
            },
        },
        repositories=tuple(repositories),
    )

def load_repository_sources(path: str | Path) -> PortfolioRepositorySources:
    return PortfolioRepositorySources.from_dict(read_json(path))


def select_repository_sources(
    *,
    bitbucket_project_url: str | None,
    repository_sources: str | Path | None,
    auth_mode: str,
    token_env: str,
    username_env: str,
    password_env: str,
    api_base_path: str,
    ca_bundle: str | Path | None,
    insecure_skip_tls_verify: bool,
    timeout_seconds: float,
    page_size: int,
    max_repositories: int | None,
) -> PortfolioRepositorySources:
    """Resolve one repository-list source without acquiring repository contents.

    The returned contract is only an operational repository membership list.  It does
    not create a multi-repository analysis scope; callers still process each repository
    independently.
    """
    if (bitbucket_project_url is None) == (repository_sources is None):
        raise ValueError(
            "provide exactly one repository source: bitbucket_project_url or repository_sources"
        )
    if bitbucket_project_url is not None:
        sources = discover_bitbucket_project_repositories(
            project_url=bitbucket_project_url,
            auth_mode=auth_mode,
            token_env=token_env,
            username_env=username_env,
            password_env=password_env,
            api_base_path=api_base_path,
            ca_bundle=ca_bundle,
            insecure_skip_tls_verify=insecure_skip_tls_verify,
            timeout_seconds=timeout_seconds,
            page_size=page_size,
            max_repositories=max_repositories,
        )
    else:
        assert repository_sources is not None
        loaded = load_repository_sources(repository_sources)
        source_count = len(loaded.repositories)
        selected = (
            loaded.repositories[:max_repositories]
            if max_repositories is not None
            else loaded.repositories
        )
        sources = PortfolioRepositorySources(
            source={
                **dict(loaded.source),
                "repository_selection": {
                    "mode": "manifest_order_prefix",
                    "limit": max_repositories,
                    "selected_count": len(selected),
                    "source_count": source_count,
                    "limit_reached": (
                        max_repositories is not None and source_count >= max_repositories
                    ),
                    "truncated": len(selected) < source_count,
                },
            },
            repositories=selected,
        )
    return PortfolioRepositorySources(
        source=sources.source,
        repositories=tuple(
            PortfolioRepositorySource(
                repo_id=item.repo_id,
                clone_url=_sanitize_repository_url(item.clone_url),
                ref=item.ref,
                system_id=item.system_id,
                project_id=item.project_id,
                service_aliases=item.service_aliases,
                metadata=item.metadata,
            )
            for item in sources.repositories
        ),
    )


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _cleanup_stale_temporary_runs(base: Path) -> list[str]:
    removed: list[str] = []
    for child in sorted(base.iterdir()) if base.is_dir() else []:
        if not child.is_dir():
            continue
        marker = child / _TEMPORARY_MARKER
        if not marker.is_file():
            continue
        try:
            payload = read_json(marker)
        except Exception:
            continue
        if payload.get("producer") != "static-analysis-runner":
            continue
        if _pid_alive(int(payload.get("pid") or 0)):
            continue
        shutil.rmtree(child)
        removed.append(child.name)
    return removed


def prepare_repository_acquisition_run(
    work_dir: str | Path,
    *,
    namespace: str,
    run_id: str,
) -> tuple[Path, list[str]]:
    """Create a Runner-owned temporary root and clean stale owned runs.

    This root is intentionally outside persistent output. Repository checkouts must
    live below it and are expected to be removed immediately after each repository.
    """
    safe_namespace = re.sub(r"[^a-zA-Z0-9_.-]", "-", str(namespace or "")).strip("-.")
    if not safe_namespace:
        raise ValueError("temporary repository acquisition namespace must not be empty")
    base = Path(work_dir).expanduser().resolve() / safe_namespace
    if base == Path(base.anchor) or base == Path.home().resolve():
        raise ValueError(f"unsafe repository acquisition work directory: {base}")
    base.mkdir(parents=True, exist_ok=True)
    removed = _cleanup_stale_temporary_runs(base)
    run_root = base / run_id
    if run_root.exists():
        marker = run_root / _TEMPORARY_MARKER
        if not marker.is_file():
            raise ValueError(f"refuse to replace unowned temporary directory: {run_root}")
        shutil.rmtree(run_root)
    run_root.mkdir(parents=True)
    write_json(
        run_root / _TEMPORARY_MARKER,
        {
            "schema_version": _TEMPORARY_MARKER_SCHEMA,
            "producer": "static-analysis-runner",
            "namespace": safe_namespace,
            "pid": os.getpid(),
            "created_at": now_utc(),
        },
    )
    return run_root, removed

def _write_askpass_script(run_root: Path) -> Path:
    target = run_root / "git-askpass.sh"
    target.write_text(
        "#!/bin/sh\n"
        "case \"$1\" in\n"
        "  *Username*) printf '%s\\n' \"$PORTFOLIO_GIT_USERNAME\" ;;\n"
        "  *) printf '%s\\n' \"$PORTFOLIO_GIT_PASSWORD\" ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    target.chmod(0o700)
    return target

def _git_environment(
    *,
    auth_mode: str,
    token_env: str,
    username_env: str,
    password_env: str,
    askpass_script: Path,
) -> dict[str, str]:
    mode = str(auth_mode or "auto").strip().lower()
    token = os.environ.get(token_env, "")
    username = os.environ.get(username_env, "")
    password = os.environ.get(password_env, "")
    env: dict[str, str] = {
        "GIT_LFS_SKIP_SMUDGE": "1",
        "GIT_TERMINAL_PROMPT": "0",
    }
    effective = mode
    if mode == "auto":
        effective = "token" if token else "basic" if username and password else "credential-helper"
    if effective == "token":
        if not token:
            raise ValueError(f"authentication token environment variable is empty: {token_env}")
        if username:
            env.update(
                {
                    "GIT_ASKPASS": str(askpass_script),
                    "PORTFOLIO_GIT_USERNAME": username,
                    "PORTFOLIO_GIT_PASSWORD": token,
                }
            )
        else:
            env.update(
                {
                    "GIT_CONFIG_COUNT": "1",
                    "GIT_CONFIG_KEY_0": "http.extraHeader",
                    "GIT_CONFIG_VALUE_0": f"Authorization: Bearer {token}",
                }
            )
    elif effective == "basic":
        if not username or not password:
            raise ValueError(
                "basic authentication requires both environment variables: "
                f"{username_env}, {password_env}"
            )
        env.update(
            {
                "GIT_ASKPASS": str(askpass_script),
                "PORTFOLIO_GIT_USERNAME": username,
                "PORTFOLIO_GIT_PASSWORD": password,
            }
        )
    elif effective == "ssh":
        env["GIT_SSH_COMMAND"] = "ssh -o BatchMode=yes"
    elif effective not in {"credential-helper", "none"}:
        raise ValueError(f"unsupported auth_mode: {auth_mode!r}")
    return env

def _transient_clone_failure(log_text: str) -> bool:
    normalized = log_text.casefold()
    permanent = (
        "authentication failed",
        "access denied",
        "repository not found",
        "not found",
        "couldn't find remote ref",
        "remote branch",
        "does not appear to be a git repository",
    )
    if any(value in normalized for value in permanent):
        return False
    transient = (
        "timed out",
        "timeout",
        "connection reset",
        "connection refused",
        "temporary failure",
        "remote end hung up",
        "http 500",
        "http 502",
        "http 503",
        "http 504",
        "the requested url returned error: 5",
    )
    return any(value in normalized for value in transient)

def _clone_repository(
    *,
    source: PortfolioRepositorySource,
    target: Path,
    logs: Path,
    auth_mode: str,
    token_env: str,
    username_env: str,
    password_env: str,
    askpass_script: Path,
    retries: int,
    timeout_seconds: float,
) -> tuple[str, list[dict[str, Any]]]:
    if retries < 0:
        raise ValueError("clone retries must be non-negative")
    clone_url = _sanitize_repository_url(source.clone_url)
    env = _git_environment(
        auth_mode=auth_mode,
        token_env=token_env,
        username_env=username_env,
        password_env=password_env,
        askpass_script=askpass_script,
    )
    attempts: list[dict[str, Any]] = []
    commit_ref = bool(source.ref and re.fullmatch(r"[0-9a-fA-F]{7,64}", source.ref))
    for attempt in range(1, retries + 2):
        if target.exists():
            shutil.rmtree(target)
        if commit_ref:
            target.mkdir(parents=True)
            commands = [
                ["git", "init", "--quiet", str(target)],
                ["git", "-C", str(target), "remote", "add", "origin", clone_url],
                ["git", "-C", str(target), "fetch", "--depth", "1", "--no-tags", "origin", str(source.ref)],
                ["git", "-C", str(target), "checkout", "--detach", "--quiet", "FETCH_HEAD"],
            ]
        else:
            command = [
                "git", "clone", "--depth", "1", "--single-branch", "--no-tags",
            ]
            if source.ref:
                command += ["--branch", source.ref]
            command += [clone_url, str(target)]
            commands = [command]
        succeeded = True
        combined_log = ""
        started_at = now_utc()
        for index, command in enumerate(commands, start=1):
            log_path = logs / source.repo_id / f"attempt-{attempt}-command-{index}.log"
            result = run_process(
                command,
                log_path=log_path,
                env=env,
                timeout_seconds=timeout_seconds,
            )
            text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.is_file() else ""
            combined_log += text
            if result.returncode != 0 or result.timed_out:
                succeeded = False
                break
        attempts.append(
            {
                "attempt": attempt,
                "started_at": started_at,
                "finished_at": now_utc(),
                "status": "completed" if succeeded else "failed",
                "transient": False if succeeded else _transient_clone_failure(combined_log),
            }
        )
        if succeeded:
            commit = subprocess.run(
                ["git", "-C", str(target), "rev-parse", "HEAD"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                env={**os.environ, **env},
            ).stdout.strip()
            return commit, attempts
        if attempt > retries or not attempts[-1]["transient"]:
            raise RuntimeError(
                f"git clone failed for {source.repo_id} after {attempt} attempt(s); "
                f"see {logs / source.repo_id}"
            )
        time.sleep(min(2.0, 0.25 * (2 ** (attempt - 1))))
    raise AssertionError("unreachable")

def _failure_message(exc: BaseException, *, secret_values: Iterable[str]) -> str:
    value = str(exc)
    for secret in secret_values:
        if secret:
            value = value.replace(secret, "***")
    return value
