"""Skills do pipeline Concilium — auto-descobertas dos manifests.

Cada skill reside em manifests/{id}/skill.py com manifesto em skill.toml.
Os módulos são carregados apenas quando a skill é efetivamente executada (lazy).
"""

import importlib.util
import sys
import threading
import tomllib
import types
from pathlib import Path
from typing import Any

# Defer heavy imports to avoid Pydantic cascade
# from concilium.application.skills.base import SkillResult  # noqa: F401 — re-exported
from concilium.application.skills.registry import SkillRegistry  # noqa: F401 — re-exported

_MANIFESTS = Path(__file__).parent / "manifests"
_IMPORT_LOCK = threading.Lock()


def _skill_pkg_name(skill_id: str) -> str:
    return f"_concilium_skillpkg_{skill_id.replace('-', '_')}"


def _skill_mod_name(skill_id: str) -> str:
    return f"{_skill_pkg_name(skill_id)}.skill"


def _ensure_skill_package(skill_id: str, skill_dir: Path) -> str:
    pkg_name = _skill_pkg_name(skill_id)
    if pkg_name in sys.modules:
        return pkg_name

    pkg = types.ModuleType(pkg_name)
    pkg.__path__ = [str(skill_dir)]  # type: ignore[attr-defined]
    pkg.__package__ = pkg_name
    sys.modules[pkg_name] = pkg
    return pkg_name


def _load_skill_module(skill_id: str) -> types.ModuleType:
    """Load manifests/{skill_id}/skill.py preserving relative imports.

    The module is loaded as `<synthetic_pkg>.skill` and `<synthetic_pkg>` is a
    synthetic package pointing to the manifest directory. This lets
    `from ._skill_helpers_x import ...` work when skills are loaded from files.
    """
    skill_path = _MANIFESTS / skill_id / "skill.py"
    if not skill_path.exists():
        raise ImportError(f"Arquivo skill.py não encontrado: {skill_path}")

    mod_name = _skill_mod_name(skill_id)
    if mod_name in sys.modules:
        return sys.modules[mod_name]

    _ensure_skill_package(skill_id, skill_path.parent)
    spec = importlib.util.spec_from_file_location(mod_name, skill_path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    # Register before execution so nested imports during module init can resolve.
    sys.modules[mod_name] = mod
    try:
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
    except Exception:
        # Avoid leaking partially initialized modules into future lazy loads.
        sys.modules.pop(mod_name, None)
        raise
    return mod


def _get_compat_alias(skill_id: str) -> str:
    _, name = skill_id.split("-", 1)
    return f"concilium.application.skills.{name.replace('-', '_')}"


class _SkillProxy(types.ModuleType):
    """Lazy-loading module proxy registered in sys.modules at package init time.

    Allows ``from concilium.application.skills import run_cronograma`` (and all
    other skill submodule-style imports) to work without generated files on disk.
    The proxy is transparently replaced in sys.modules with the real module
    the first time any attribute is accessed.
    """

    def __init__(self, skill_id: str) -> None:
        super().__init__(_get_compat_alias(skill_id))
        self._concilium_skill_id = skill_id

    def __getattr__(self, name: str):  # noqa: ANN204
        skill_id: str = self.__dict__["_concilium_skill_id"]
        alias: str = self.__name__
        mod_name = _skill_mod_name(skill_id)
        if mod_name not in sys.modules:
            with _IMPORT_LOCK:
                if mod_name not in sys.modules:
                    _load_skill_module(skill_id)
        mod = sys.modules[mod_name]
        # Replace proxy with real module so future imports bypass this object
        sys.modules[alias] = mod
        return getattr(mod, name)


def _load(skill_id: str, func_name: str) -> Any:
    """Carrega função de skill do arquivo manifests/{skill_id}/skill.py.

    Idempotente: se o módulo já está em sys.modules (e.g., carregado pelo proxy),
    reutiliza-o sem re-executar o arquivo.
    """
    mod_name = _skill_mod_name(skill_id)
    if mod_name not in sys.modules:
        with _IMPORT_LOCK:
            if mod_name not in sys.modules:
                _load_skill_module(skill_id)
    mod = sys.modules[mod_name]
    if not hasattr(mod, func_name):
        # Recover from stale/partial module object kept from previous failures.
        with _IMPORT_LOCK:
            sys.modules.pop(mod_name, None)
            _load_skill_module(skill_id)
            mod = sys.modules[mod_name]
    alias = _get_compat_alias(skill_id)
    sys.modules[alias] = mod  # always update (replaces proxy if present)
    return getattr(mod, func_name)


def _discover_manifest_index() -> dict[str, str]:
    """Descobre skills lendo apenas os TOMLs (não carrega módulos Python).

    Retorna {skill_id: func_name}.  Custo: apenas I/O de arquivos .toml.
    """
    index: dict[str, str] = {}
    if not _MANIFESTS.exists():
        return index
    for manifest_dir in sorted(_MANIFESTS.iterdir()):
        if not manifest_dir.is_dir():
            continue
        toml_path = manifest_dir / "skill.toml"
        if not toml_path.exists():
            continue
        try:
            with open(toml_path, "rb") as f:
                config = tomllib.load(f)
            skill_id = config.get("skill", {}).get("id") or manifest_dir.name
            _, name = skill_id.split("-", 1)
            if not (manifest_dir / "skill.py").exists():
                raise RuntimeError(f"skill.py ausente em {manifest_dir}")
            index[skill_id] = f"run_{name.replace('-', '_')}"
        except Exception as e:
            raise RuntimeError(f"Erro lendo manifesto em {manifest_dir}: {e}") from e
    return index


def _discover_manifest_meta() -> dict[str, dict]:
    """Descobre skills lendo TOMLs e retorna metadados completos.

    Retorna {skill_id: {func_name, phase, gate}}.
    """
    meta: dict[str, dict] = {}
    if not _MANIFESTS.exists():
        return meta
    for manifest_dir in sorted(_MANIFESTS.iterdir()):
        if not manifest_dir.is_dir():
            continue
        toml_path = manifest_dir / "skill.toml"
        if not toml_path.exists():
            continue
        try:
            with open(toml_path, "rb") as f:
                config = tomllib.load(f)
            skill_cfg = config.get("skill", {})
            skill_id = skill_cfg.get("id") or manifest_dir.name
            _, name = skill_id.split("-", 1)
            meta[skill_id] = {
                "func_name": f"run_{name.replace('-', '_')}",
                "phase": skill_cfg.get("phase", "Sem Classificação"),
                "gate": bool(skill_cfg.get("gate", False)),
                "depends_on": config.get("depends_on", {}),
            }
        except Exception as e:
            raise RuntimeError(f"Erro lendo manifesto em {manifest_dir}: {e}") from e
    return meta


# backward-compat alias (test_coverage_batch_a calls _discover_skills())
_discover_skills = _discover_manifest_index


def list_compat_aliases() -> dict[str, str]:
    """Retorna mapeamento alias -> módulo real lazy."""
    return {_get_compat_alias(skill_id): _skill_mod_name(skill_id) for skill_id in _MANIFEST_INDEX}


class _LazySkillsDict:
    """Dict de skills com carregamento lazy dos módulos Python.

    Iterar / testar membership usa apenas o índice de TOMLs (rápido).
    Acessar SKILLS[skill_id] carrega o módulo sob demanda.
    """

    def __init__(self, index: dict[str, str]) -> None:
        self._index = index  # {skill_id: func_name}
        self._loaded: dict[str, Any] = {}  # {skill_id: run_fn}

    def __contains__(self, skill_id: object) -> bool:
        return skill_id in self._index

    def __iter__(self):
        return iter(self._index)

    def __len__(self) -> int:
        return len(self._index)

    def __getitem__(self, skill_id: str) -> Any:
        if skill_id not in self._index:
            raise KeyError(skill_id)
        if skill_id not in self._loaded:
            func_name = self._index[skill_id]
            self._loaded[skill_id] = _load(skill_id, func_name)
        return self._loaded[skill_id]

    def keys(self):
        return self._index.keys()

    def values(self):
        # Força carregamento de todos — usar apenas quando necessário
        for skill_id in self._index:
            if skill_id not in self._loaded:
                self[skill_id]
        return self._loaded.values()

    def items(self):
        for skill_id in self._index:
            yield skill_id, self[skill_id]

    def get(self, skill_id: str, default: Any = None) -> Any:
        if skill_id not in self._index:
            return default
        return self[skill_id]


# ── Índice descoberto na inicialização (barato: só lê TOMLs) ──────────────────
_MANIFEST_INDEX: dict[str, str] = _discover_manifest_index()

# ── Metadados completos: phase, gate, func_name ───────────────────────────────
MANIFEST_META: dict[str, dict] = _discover_manifest_meta()

# ── Dict lazy: módulos carregados apenas quando a skill é executada ───────────
SKILLS: _LazySkillsDict = _LazySkillsDict(_MANIFEST_INDEX)

# ── Auto-registra proxies preguiçosos para todos os manifests descobertos ─────
# Permite `from concilium.application.skills import run_cronograma` (e similares)
# sem arquivos extras no disco. Custo: só iteração do índice já em memória.
for _sid in _MANIFEST_INDEX:
    _alias = _get_compat_alias(_sid)
    if _alias not in sys.modules:
        sys.modules[_alias] = _SkillProxy(_sid)


# ── Re-exporta funções individuais via __getattr__ (não carrega nada agora) ───
def __getattr__(name: str) -> Any:
    """Suporta lazy load de skills e classes sem eager import."""
    # Lazy load SkillResult
    if name == "SkillResult":
        from concilium.application.skills.base import SkillResult

        return SkillResult

    # Lazy load skill functions
    if name.startswith("run_"):
        name[4:]  # remove "run_"
        # Encontra skill_id pelo func_name
        for skill_id, func_name in _MANIFEST_INDEX.items():
            if func_name == name:
                return _load(skill_id, func_name)
    raise AttributeError(f"module 'concilium.application.skills' has no attribute {name!r}")


__all__ = [f"run_{k.split('-', 1)[1].replace('-', '_')}" for k in _MANIFEST_INDEX.keys()] + [
    "SKILLS",
    "MANIFEST_META",
    "SHIM_ID",
    "SHIM_TARGET",
    "SHIM_SCOPE",
    "list_compat_aliases",
    "SkillResult",
    "SkillRegistry",
]
