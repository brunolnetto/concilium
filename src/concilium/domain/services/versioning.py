"""Domain service for project version lifecycle rules."""

from __future__ import annotations


def validate_delete_version(tipo_projeto: str, versions: list[str], version: str) -> None:
    """Raise RuntimeError if deleting `version` is not allowed.

    Rules:
    - tipo_projeto == 'project': cannot delete the last remaining version
      (protects production projects from accidental full erasure).
    - Other types (e.g., 'hot_project'): deletion always allowed, even of the
      last version, to support rapid iteration and cleanup workflows.
    """
    if tipo_projeto == "project" and len(versions) == 1:
        raise RuntimeError(
            "Não é possível excluir a última versão de um projeto do tipo 'project'. "
            "Exclua o projeto inteiro se desejar remover todos os dados."
        )
