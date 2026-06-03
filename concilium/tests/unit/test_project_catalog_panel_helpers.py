from __future__ import annotations

from concilium.presentation.ui.templates import _project_page_helpers_b as h


def test_override_badge_sem_parcial_total() -> None:
    base = {
        "producao_horaria": 10.0,
        "equipe": {"funcoes": [{"funcao_id": "MO1", "num_pessoas": 1}], "equipamentos": []},
        "composicao_itens": [{"insumo_id": "I1", "coeficiente": 2, "categoria_custo": "MATERIAL"}],
    }

    assert h._pcat_override_badge(base, {}) == "Sem override"

    parcial = {"producao_horaria": 12.0}
    assert h._pcat_override_badge(base, parcial) == "Override parcial"

    total = {
        "producao_horaria": 12.0,
        "equipe": {"funcoes": [{"funcao_id": "MO1", "num_pessoas": 2}], "equipamentos": []},
        "composicao_itens": [{"insumo_id": "I1", "coeficiente": 3, "categoria_custo": "MATERIAL"}],
    }
    assert h._pcat_override_badge(base, total) == "Override total"


def test_health_checks_detect_inconsistencies() -> None:
    cpu = {
        "data_referencia_preco": "2020-01",
        "equipe": {"funcoes": [{"funcao_id": "MO_X", "descricao": "", "num_pessoas": 1}], "equipamentos": []},
        "composicao_itens": [
            {"insumo_id": "MISSING", "coeficiente": 1, "categoria_custo": "FOO"},
        ],
    }
    insumos_idx = {"OK": {"codigo": "OK", "preco_unitario": 100.0}}

    alerts = h._pcat_health_checks(cpu, insumos_idx)
    joined = " | ".join(alerts)
    assert "função sem descrição" in joined
    assert "insumo inexistente" in joined
    assert "categoria_custo inválida" in joined
    assert "referência de preço defasada" in joined


def test_apply_operational_filters() -> None:
    rows = [
        {
            "search_text": "cpu_a escavadeira",
            "categoria": "TERRAPLENAGEM",
            "used_in_eap": True,
            "composicao_incompleta": False,
            "preco_defasado": False,
        },
        {
            "search_text": "cpu_b moto",
            "categoria": "PAV",
            "used_in_eap": False,
            "composicao_incompleta": True,
            "preco_defasado": True,
        },
    ]

    out = h._pcat_apply_filters(
        rows,
        q="cpu_b",
        cat_filters=["PAV"],
        only_used=False,
        only_incomplete=True,
        only_stale_price=True,
    )
    assert len(out) == 1
    assert out[0]["categoria"] == "PAV"
