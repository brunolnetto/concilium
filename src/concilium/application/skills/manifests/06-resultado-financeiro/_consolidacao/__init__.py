# Hyphenated manifest dir: only loaded at runtime via a synthetic package (see
# concilium/application/skills/__init__.py); ty cannot resolve this statically.
from .skill import run_consolidacao_financeira  # ty: ignore[unresolved-import]
