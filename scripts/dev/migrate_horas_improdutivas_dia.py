"""ADR-148 Fase F0: grava `horas_improdutivas_dia: 0.0` explicitamente em specs de
projeto já materializados, ANTES do default do modelo (`RegimeTrabalho`) mudar
para `0.5`.

Contexto: sem esta migração, qualquer projeto existente que seja re-lido depois
do deploy do ADR-148 herdaria silenciosamente o novo default (0.5h), reduzindo
~6,25% da produção planejada (regime 8h) sem nenhuma edição visível — exatamente
o "default silencioso" que a ADR-148 D5 decide evitar (mesmo padrão da ADR-124 D5).

Backend-agnóstico por construção: usa `build_project_repository()` — o mesmo
factory que a aplicação usa em runtime, resolvido a partir de
`CONCILIUM__STORE_BACKEND` (filesystem, sharepoint, s3, azure, gdrive). Não há
hardcode de backend; rodar este script com as env vars de um ambiente SharePoint
apontadas migra o SharePoint, sem alterações de código.

Escopo desta migração:
  1. `<versao>/canonical.json` — campo `projeto.regime_trabalho.horas_improdutivas_dia`
     (fonte real consumida pelo motor de cronograma/custo). Coberto em todos os
     backends via `ProjectHandle.list_versions()` + `read_json`/`write_json`.
  2. `escopos/<id>/meta.json` — campo `regime_trabalho.horas_improdutivas_dia`
     (metadado descritivo, não consumido pelo motor de cálculo). Coberto apenas
     quando `list_escopos()` retorna resultados reais — hoje, só o backend
     filesystem (`FileProjectHandle`). Ver limitação abaixo.

LIMITAÇÃO CONHECIDA — versões aprovadas em backends remotos (pré-existente,
não introduzida por esta ADR): o backend filesystem grava `approved_versions`
no `meta.json` do projeto (`ProjectStore.approve()`), que este script usa para
pular versões aprovadas sem tentar escrevê-las. `StorageProjectHandle`
(SharePoint/S3/Azure/GDrive) delega `approve()` inteiramente a
`BlobStoragePort.aprovar_versao()` (ex.: checkin de versão major no SharePoint)
e NÃO espelha isso em `approved_versions` — não há hoje um sinal genérico e
consultável de "esta versão está aprovada" para esses backends. Para eles, este
script tenta a escrita e reporta como bloqueada qualquer versão cuja escrita o
backend rejeitar — mas nada garante que todo backend rejeite escrita em uma
versão aprovada. **Antes de rodar `--apply` contra um backend remoto em
produção, confirme manualmente a proteção de escrita de versões aprovadas no
backend configurado, ou rode em uma janela sem aprovações concorrentes.**

LIMITAÇÃO CONHECIDA — meta de escopo em backends remotos (idem, pré-existente):
`StorageProjectHandle.list_escopos()`/`escopo()` retornam stub vazio (`[]`/`None`)
— não implementados para o caminho blob-backed. Este script reporta
explicitamente quantos escopos foram migrados por projeto; `0` em um backend
remoto significa "não suportado hoje", não "nenhum escopo existe".

Idempotente: specs que já têm o campo (qualquer valor) são ignorados.

Uso (lê `CONCILIUM__STORE_BACKEND` e demais env vars do backend, como a app):
    # Ver o que seria alterado, sem tocar em nada (padrão):
    python scripts/dev/migrate_horas_improdutivas_dia.py --dry-run

    # Aplicar de fato (não força escrita além do que o backend permitir):
    python scripts/dev/migrate_horas_improdutivas_dia.py --apply
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

_FIELD = "horas_improdutivas_dia"
_LEGACY_VALUE = 0.0


def _patch_regime(regime: Any) -> bool:
    """Muta `regime` in-place se elegível. Retorna True se mudou."""
    if not isinstance(regime, dict) or _FIELD in regime:
        return False
    regime[_FIELD] = _LEGACY_VALUE
    return True


def _migrate_canonical(handle: Any, version: str, apply: bool) -> tuple[str | None, bool]:
    """Retorna (descrição_ou_None, bloqueado)."""
    rel_path = f"{version}/canonical.json"
    canonical = handle.read_json(rel_path, None)
    if not isinstance(canonical, dict):
        return None, False
    projeto = canonical.get("projeto")
    if not isinstance(projeto, dict):
        return None, False
    regime = projeto.get("regime_trabalho")
    if not _patch_regime(regime):
        return None, False
    projeto["regime_trabalho"] = regime
    canonical["projeto"] = projeto

    approved = set(handle.meta.get("approved_versions") or [])
    if version in approved:
        return f"[BLOQUEADO — versão aprovada, requer ação manual] {handle.meta.get('id')}/{rel_path}", True

    if not apply:
        return f"canonical: {handle.meta.get('id')}/{rel_path}", False

    try:
        handle.write_json(rel_path, canonical)
    except Exception as exc:  # backend pode rejeitar escrita (ex.: checked-in no SharePoint)
        return f"[BLOQUEADO pelo backend — {exc}] {handle.meta.get('id')}/{rel_path}", True
    return f"canonical: {handle.meta.get('id')}/{rel_path}", False


def _migrate_escopos(handle: Any, apply: bool) -> list[str]:
    changed: list[str] = []
    for escopo_id in handle.list_escopos():
        escopo = handle.escopo(escopo_id)
        if escopo is None:
            continue
        meta = escopo.read_json("meta.json", None) if hasattr(escopo, "read_json") else None
        if not isinstance(meta, dict):
            continue
        regime = meta.get("regime_trabalho")
        if not _patch_regime(regime):
            continue
        meta["regime_trabalho"] = regime
        if apply:
            escopo.write_json("meta.json", meta)
        changed.append(f"escopo meta: {handle.meta.get('id')}/escopos/{escopo_id}/meta.json")
    return changed


def migrate(repo: Any, apply: bool) -> dict[str, list[str]]:
    changed: list[str] = []
    blocked: list[str] = []

    for handle in repo.list_projects():
        changed.extend(_migrate_escopos(handle, apply))
        for version in handle.list_versions():
            desc, is_blocked = _migrate_canonical(handle, version, apply)
            if desc and is_blocked:
                blocked.append(desc)
            elif desc:
                changed.append(desc)

    return {"changed": changed, "blocked": blocked}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="Lista o que seria alterado, sem escrever")
    group.add_argument("--apply", action="store_true", help="Aplica as mudanças permitidas pelo backend")
    args = parser.parse_args()

    from concilium.infrastructure.settings import get_storage
    from concilium.infrastructure.storage.store_factory import build_project_repository, resolve_store_backend

    backend = resolve_store_backend()
    repo = build_project_repository(get_storage().projects_root)

    print(f"Backend: {backend}\n")
    result = migrate(repo, apply=args.apply)

    verbo = "Alterado" if args.apply else "Seria alterado"
    for desc in result["changed"]:
        print(f"{verbo}: {desc}")
    for desc in result["blocked"]:
        print(desc)

    print(
        f"\nResumo: {len(result['changed'])} arquivo(s) "
        f"{'migrado(s)' if args.apply else 'a migrar'}, "
        f"{len(result['blocked'])} bloqueado(s)."
    )
    if backend != "filesystem":
        print(
            "Backend remoto: metadados de escopo (escopos/*/meta.json) não são "
            "cobertos hoje (StorageProjectHandle.list_escopos() é um stub vazio — "
            "limitação pré-existente). Apenas canonical.json foi migrado."
        )
    if not args.apply:
        print("Rode com --apply para gravar as mudanças.")


if __name__ == "__main__":
    main()
