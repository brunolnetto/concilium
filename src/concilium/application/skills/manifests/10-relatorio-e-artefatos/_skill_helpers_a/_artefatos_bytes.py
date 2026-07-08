"""Skill 07 — Adapter de Saída (gera JSON + Excel .xlsm) — geração de bytes Excel/live-model/memorial."""


from concilium.domain.models.canonical import CanonicalModel, ValidacaoItem
from concilium.infrastructure.adapters.excel_adapter import ExcelRenderer


def _gerar_excel_bytes(canonical_in: CanonicalModel, validacoes: list, gerar_excel: bool) -> bytes | None:
    if not gerar_excel:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-ADAPTER-EXCEL",
                status="AVISO",
                mensagem="Geração de Excel relatório desabilitada por input 'gerar_excel=false'",
            )
        )
        return None
    try:
        excel_bytes = ExcelRenderer(canonical_in).to_bytes()
        validacoes.append(
            ValidacaoItem(codigo="VAL-ADAPTER-EXCEL", status="OK", mensagem="Excel relatório gerado com sucesso")
        )
        return excel_bytes
    except Exception as e:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-ADAPTER-EXCEL", status="AVISO", mensagem=f"Erro ao gerar Excel relatório: {str(e)}"
            )
        )
        return None


def _gerar_live_model(canonical_in: CanonicalModel, validacoes: list, gerar_modelo_vivo: bool) -> bytes | None:
    """Formulação referencial migrada para MEMORIAL.CATALOGO + REFERÊNCIA no ExcelRenderer.

    O modelo vivo separado (live_model.py) foi descontinuado. As abas MEMORIAL.CATALOGO
    e REFERÊNCIA do adapter principal já expõem os parâmetros de catálogo e a auditoria
    de cálculo que o live_model fornecia.
    """
    validacoes.append(
        ValidacaoItem(
            codigo="VAL-ADAPTER-EXCEL-LIVE",
            status="AVISO",
            mensagem=(
                "Modelo vivo descontinuado. Formulação referencial disponível nas abas "
                "MEMORIAL.CATALOGO e REFERÊNCIA do relatório Excel principal."
            ),
        )
    )
    return None


def _gerar_memorial_json_bytes(canonical_in: CanonicalModel) -> bytes | None:
    if canonical_in.memorial_calculo_bdi is None:
        return None
    try:
        import json as _json

        return _json.dumps(
            canonical_in.memorial_calculo_bdi.to_dict(), indent=2, ensure_ascii=False, default=str
        ).encode("utf-8")
    except Exception as _mem_exc:
        import logging as _logging

        _logging.getLogger(__name__).warning("memorial_bdi.json falhou: %s", _mem_exc)
        return None


