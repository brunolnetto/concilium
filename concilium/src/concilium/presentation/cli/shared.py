"""CLI shared utilities for Typer subcommands."""

import json
import os
from pathlib import Path

import typer
from rich import print as rprint

from concilium.infrastructure.storage.store_factory import build_project_repository


def _looks_like_workspace_root(path: Path) -> bool:
    return (
        path.exists()
        and path.is_dir()
        and (path / "pyproject.toml").exists()
        and (path / "config").is_dir()
        and (path / "benchmarks").is_dir()
    )


def _tools_root() -> Path:
    """Resolve raiz do workspace, mesmo com pacote instalado no venv."""
    env_root = os.environ.get("CONCILIUM_ROOT")
    if env_root:
        candidate = Path(env_root).expanduser()
        if _looks_like_workspace_root(candidate):
            return candidate.resolve()

    cwd = Path.cwd().resolve()
    for candidate in (cwd, *cwd.parents):
        if _looks_like_workspace_root(candidate):
            return candidate

    return Path(__file__).resolve().parents[4]


def _resolve_env_path(*, primary: str, default: Path) -> Path:
    """Resolve path de configuraÃ§Ã£o com compatibilidade retroativa."""
    if os.environ.get(primary):
        return Path(os.environ[primary])
    return default


def _require_existing_dir(path: Path, *, label: str, env_keys: tuple[str, str]) -> Path:
    """Valida diretÃ³rio obrigatÃ³rio e retorna erro amigÃ¡vel quando invÃ¡lido."""
    if not path.exists():
        keys = " ou ".join(env_keys)
        raise RuntimeError(f"{label} nÃ£o encontrado: {path}. Defina {keys} para apontar para um diretÃ³rio vÃ¡lido.")
    if not path.is_dir():
        raise RuntimeError(f"{label} invÃ¡lido: {path} nÃ£o Ã© um diretÃ³rio.")
    return path


def _config_root() -> Path:
    """Returns config root path (without validation)."""
    return _resolve_env_path(
        primary="CONCILIUM_CONFIG_ROOT",
        default=_tools_root() / "config",
    )


def _projetos_root() -> Path:
    """Returns projects root path (without validation)."""
    return _resolve_env_path(
        primary="CONCILIUM_PROJECTS_ROOT",
        default=_tools_root() / "projetos",
    )


def _benchmark_projects_root() -> Path:
    """Returns benchmark projects root path (without validation).

    Benchmarks devem persistir projetos em diretório dedicado para não poluir
    os projetos reais operados via CLI/MCP.
    """
    return Path(
        os.environ.get(
            "CONCILIUM_BENCHMARK_PROJECTS_ROOT",
            str(_tools_root() / "benchmarks" / "projetos"),
        )
    )


def config_root() -> Path:
    """Retorna diretÃ³rio de configuraÃ§Ã£o com validaÃ§Ã£o."""
    return _require_existing_dir(
        _config_root(),
        label="DiretÃ³rio de configuraÃ§Ã£o",
        env_keys=("CONCILIUM_CONFIG_ROOT", "CONCILIUM_CONFIG"),
    )


def projetos_root() -> Path:
    """Retorna diretÃ³rio de projetos."""
    return _projetos_root()


def benchmark_projects_root() -> Path:
    """Retorna diretório de projetos dedicado a benchmarks."""
    root = _benchmark_projects_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def project_repository(*, benchmark: bool = False):
    """Build project repository using StoreFactory backend selection."""
    root = benchmark_projects_root() if benchmark else projetos_root()
    root.mkdir(parents=True, exist_ok=True)
    return build_project_repository(root)


def _find_projects_by_name(base, name_or_id: str) -> list:

    matches = []
    for p in base.iterdir():
        if not p.is_dir():
            continue
        meta_path = p / "meta.json"
        if not meta_path.exists():
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("nome") == name_or_id:
            matches.append(p)
    return matches


def resolve_project(name_or_id: str):
    """Resolve nome ou UUID para um ProjectStore."""
    base = _projetos_root()
    if not base.exists():
        rprint(
            "[red]DiretÃ³rio de projetos nÃ£o existe: "
            f"{base}. Defina CONCILIUM_PROJECTS_ROOT ou CONCILIUM_PROJETOS.[/red]"
        )
        raise typer.Exit(1)

    # Tentativa direta por UUID/diretÃ³rio
    direct = base / name_or_id
    if direct.is_dir() and (direct / "meta.json").exists():
        return project_repository().get_project(name_or_id)

    # Busca por nome
    matches = _find_projects_by_name(base, name_or_id)

    if len(matches) == 0:
        rprint(f"[red]Projeto nÃ£o encontrado: {name_or_id}[/red]")
        raise typer.Exit(1)
    if len(matches) > 1:
        rprint(f"[red]MÃºltiplos projetos com nome '{name_or_id}'. Use o UUID:[/red]")
        for m in matches:
            rprint(f"  â€¢ {m.name}")
        raise typer.Exit(1)
    return project_repository().get_project(matches[0].name)


def parse_project_version(arg: str) -> tuple[str, str | None]:
    """Aceita 'projeto' ou 'projeto@v3'. Retorna (nome, versao_ou_None)."""
    if "@" in arg:
        nome, ver = arg.split("@", 1)
        return nome, ver
    return arg, None
