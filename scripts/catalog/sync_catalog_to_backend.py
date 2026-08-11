"""Sincroniza um catálogo local (config/catalogos/<id>/) para o backend de storage
remoto configurado no ambiente (CONCILIUM__STORE_BACKEND) — em produção, SEMPRE
SharePoint (cd/production/README.md §"Variáveis de ambiente", D-ACA: `sharepoint`
não é opcional lá).

Por que este script existe: a produção lê o catálogo via `BlobStoragePort`/SharePoint
(ADR-047 §D5/§D6; `_catalog_prefix` em `application/runtime/mixins/_catalog_storage.py`),
NÃO do filesystem deste repositório git — o `git` é só a cópia de trabalho/staging.
Qualquer edição de catálogo feita localmente (novo insumo, correção de schema, merge de
producoes/→produtividades/, enriquecimento de descricao, etc.) só chega à produção
depois de rodar este script com as credenciais SharePoint corretas no ambiente
(CONCILIUM__STORE_BACKEND=sharepoint + CONCILIUM__SP_*) — hoje esse passo não é
automatizado por nenhum deploy/CI existente (verificado: nem deploy.sh, nem
provision.sh, nem os workflows do GitHub tocam dados de catálogo, só infraestrutura
e a imagem da aplicação).

Comportamento (replicação por CONTEÚDO — não é upload cego de tudo a cada rodada):
  - Para cada arquivo local em config/catalogos/<id>/**/*.json (ignora .catalog_bundle.json,
    *.duckdb* e outros artefatos de cache — não fazem parte do dado fonte): sobe via
    `gravar_blob` se o blob remoto está ausente ou o conteúdo remoto é diferente
    (comparação byte a byte via leitura do remoto — não por timestamp).
  - Para cada blob remoto SEM correspondente local no mesmo prefixo: reporta como
    órfão (ex.: arquivos deixados por uma migração de pasta como producoes/→
    produtividades/); só remove de fato (`deletar_blob`) se --delete-orphans for
    passado explicitamente — é destrutivo e não tem desfazer.
  - --dry-run (padrão): só relata o que mudaria, não grava nem apaga nada.
  - --apply: grava/apaga de fato.

Uso (com CONCILIUM__STORE_BACKEND=sharepoint + CONCILIUM__SP_* já exportados no ambiente
que tem acesso real ao SharePoint de produção):
    python scripts/catalog/sync_catalog_to_backend.py mendeslobo --dry-run
    python scripts/catalog/sync_catalog_to_backend.py mendeslobo --apply
    python scripts/catalog/sync_catalog_to_backend.py mendeslobo --apply --delete-orphans
    python scripts/catalog/sync_catalog_to_backend.py rfi-r02 --apply --delete-orphans
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT))

# Arquivos/padrões que são artefato de cache local, não dado fonte do catálogo —
# nunca devem ser espelhados para o backend remoto.
_IGNORAR_NOMES = {".catalog_bundle.json"}
_IGNORAR_SUFIXOS = (".duckdb", ".duckdb.timestamp")


def _deve_ignorar(path: Path) -> bool:
    if path.name in _IGNORAR_NOMES:
        return True
    return any(path.name.endswith(suf) for suf in _IGNORAR_SUFIXOS)


def _listar_arquivos_locais(cat_dir: Path) -> list[Path]:
    return sorted(p for p in cat_dir.rglob("*") if p.is_file() and not _deve_ignorar(p))


def run_sync(
    catalog_id: str,
    local_dir: Path | None = None,
    apply: bool = False,
    delete_orphans: bool = False,
) -> dict[str, Any]:
    from concilium.infrastructure.storage.store_factory import build_blob_storage, resolve_store_backend

    backend = resolve_store_backend()
    if backend == "filesystem":
        raise SystemExit(
            "CONCILIUM__STORE_BACKEND resolve para 'filesystem' neste ambiente — "
            "não há backend remoto para sincronizar (script é um no-op nesse caso; "
            "exporte CONCILIUM__STORE_BACKEND=sharepoint + CONCILIUM__SP_* do ambiente "
            "de produção antes de rodar)."
        )

    cat_dir = local_dir or (REPO_ROOT / "config" / "catalogos" / catalog_id)
    if not cat_dir.is_dir():
        raise SystemExit(f"Catálogo local não encontrado: {cat_dir}")

    storage = build_blob_storage()
    base = f"config/catalogos/{catalog_id}"

    stats: dict[str, Any] = {
        "backend": backend,
        "enviados": 0,
        "inalterados": 0,
        "orfaos_remotos": [],
        "orfaos_removidos": 0,
    }

    locais = _listar_arquivos_locais(cat_dir)
    caminhos_remotos_esperados: set[str] = set()

    for path in locais:
        rel = path.relative_to(cat_dir).as_posix()
        remoto = f"{base}/{rel}"
        caminhos_remotos_esperados.add(remoto)
        conteudo_local = path.read_bytes()

        try:
            conteudo_remoto = storage.ler_blob(remoto)
        except FileNotFoundError:
            conteudo_remoto = None

        if conteudo_remoto == conteudo_local:
            stats["inalterados"] += 1
            continue

        stats["enviados"] += 1
        print(f"  [{'ENVIAR' if apply else 'ENVIARIA'}] {remoto}")
        if apply:
            storage.gravar_blob(remoto, conteudo_local)

    remotos_existentes = set(storage.listar_blobs(base))
    orfaos = sorted(remotos_existentes - caminhos_remotos_esperados)
    stats["orfaos_remotos"] = orfaos
    for remoto in orfaos:
        acao = "REMOVER" if (apply and delete_orphans) else "ÓRFÃO"
        print(f"  [{acao}] {remoto}")
        if apply and delete_orphans:
            storage.deletar_blob(remoto)
            stats["orfaos_removidos"] += 1

    return stats


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sincroniza um catálogo local para o backend remoto configurado (produção: SharePoint)"
    )
    parser.add_argument("catalog_id", help="ID do catálogo (ex: mendeslobo, rfi-r02)")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", help="apenas relata (padrão)")
    group.add_argument("--apply", action="store_true", help="grava/apaga de fato")
    parser.add_argument(
        "--delete-orphans",
        action="store_true",
        help="remove blobs remotos sem correspondente local (destrutivo, sem desfazer)",
    )
    args = parser.parse_args()

    stats = run_sync(args.catalog_id, apply=args.apply, delete_orphans=args.delete_orphans)
    modo = "APLICADO" if args.apply else "DRY-RUN (use --apply para gravar)"
    print(
        f"\n[{modo}] backend={stats['backend']} — {stats['enviados']} enviado(s), "
        f"{stats['inalterados']} inalterado(s), {len(stats['orfaos_remotos'])} órfão(s) remoto(s)"
        + (f", {stats['orfaos_removidos']} removido(s)" if args.delete_orphans else "")
    )
    if stats["orfaos_remotos"] and not args.delete_orphans:
        print("Use --delete-orphans para remover os órfãos listados acima (ex.: producoes/ antigo).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
