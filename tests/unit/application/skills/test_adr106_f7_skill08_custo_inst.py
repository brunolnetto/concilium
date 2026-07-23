"""ADR-106 F7 — Skill-08 usa custo_inst_* diretamente, sem heurística proporcional.

TDD: testes escritos antes da implementação.

Estado atual: itens sem pool contracts usam heurística proporcional em skill-08
  (ct * custo_mo / base, ct * custo_eq / base, ...).

F7 objetivo: quando eq.custo_inst_mo is not None (preenchido por F3), skill-08
  deve usar esses valores diretamente em vez da heurística.

Verificação: a decomposição categorial de um item sem pool deve refletir
  os custo_inst_* da equipe, não a proporção das custos mensais.
"""

from __future__ import annotations


def _build_cat_bottom_up_direct():
    """Importa a função de decomposição categorial de skill-08."""
    import importlib.util
    import sys
    from pathlib import Path

    path = (
        Path(__file__).resolve().parents[4]
        / "src/concilium/application/skills/manifests"
        / "06-resultado-financeiro/_consolidacao/_skill_helpers/__init__.py"
    )
    spec = importlib.util.spec_from_file_location("sk08_helpers", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sk08_helpers"] = mod
    spec.loader.exec_module(mod)
    return mod._build_custo_categorial_bottom_up


def _make_canonical_com_custo_inst(
    custo_inst_mo: float,
    custo_inst_eq: float,
    custo_inst_comb: float,
    custo_inst_mat: float,
    custo_total: float,
):
    """Cria CanonicalModel mínimo com equipe sem pool e custo_inst_* preenchido."""
    from datetime import UTC, datetime

    from concilium.domain.models.canonical import (
        CanonicalModel,
        Coordenadas,
        EapItem,
        EquipeDireta,
        FuncaoEquipeDireta,
        Meta,
        Projeto,
        RegimeTrabalho,
    )

    meta = Meta(gerado_em=datetime.now(UTC), contexto_id="test")
    projeto = Projeto(
        id="p1",
        nome="T",
        tipo_obra="terraplenagem",
        localizacao="BR",
        coordenadas=Coordenadas(lat=0, lng=0),
        regime_trabalho=RegimeTrabalho(dias_semana=6, horas_dia=8),
        data_inicio="2026-01-01",
        data_termino="2026-12-31",
        snapshot_catalogo_id="c",
        snapshot_perfil_id="p",
    )
    eap = [EapItem(item_id="i1", ordem=1, cpu_id="CPU-1", descricao="T", unidade="m3", quantitativo=100.0)]
    eq = EquipeDireta(
        equipe_id="eq1",
        item_id="i1",
        cpu_id="CPU-1",
        nome="E1",
        num_equipes_base=1,
        funcoes=[FuncaoEquipeDireta(funcao_id="F1", num_pessoas=2)],
        custo_mao_obra_mensal=20_000.0,
        custo_encargos_mensal=35_540.0,
        custo_equipamentos_mensal=15_000.0,
        custo_combustivel_total_mensal=5_000.0,
        custo_material_mensal=1_000.0,
        permanencia_meses=6.0,
        permanencia_efetiva_meses=6.0,
        custo_total=custo_total,
        custo_inst_mo=custo_inst_mo,
        custo_inst_eq=custo_inst_eq,
        custo_inst_comb=custo_inst_comb,
        custo_inst_mat=custo_inst_mat,
        custo_inst_mob_demob=custo_total - custo_inst_mo - custo_inst_eq - custo_inst_comb - custo_inst_mat,
    )
    return CanonicalModel(meta=meta, projeto=projeto, eap=eap, equipes_diretas=[eq])


class TestSkill08UsaCustoInstDireto:
    """F7: quando custo_inst_* estão preenchidos, skill-08 usa sem heurística."""

    def test_decomposicao_usa_custo_inst_mo(self):
        """mao_obra no breakdown deve refletir custo_inst_mo, não proporção mensal."""
        fn = _build_cat_bottom_up_direct()

        # Cenário: custo_inst_mo é exatamente 50% do custo_total
        custo_total = 100_000.0
        custo_inst_mo = 50_000.0
        custo_inst_eq = 30_000.0
        custo_inst_comb = 15_000.0
        custo_inst_mat = 5_000.0

        can = _make_canonical_com_custo_inst(custo_inst_mo, custo_inst_eq, custo_inst_comb, custo_inst_mat, custo_total)
        cat = fn(can)

        # mao_obra deve ser ≈ custo_inst_mo (não proporção mensal)
        # tolerância de 0.50 para arredondamentos
        assert abs(cat["mao_obra"] - custo_inst_mo) < 0.50, (
            f"mao_obra={cat['mao_obra']:.2f} deveria ser ≈ {custo_inst_mo:.2f} (custo_inst_mo)"
        )

    def test_total_categoria_fecha(self):
        """mao_obra + eq_aluguel + material ≈ custo_total."""
        fn = _build_cat_bottom_up_direct()
        custo_total = 100_000.0
        can = _make_canonical_com_custo_inst(50_000, 30_000, 15_000, 5_000, custo_total)
        cat = fn(can)
        total_cat = cat["mao_obra"] + cat["eq_aluguel"] + cat["material"]
        assert abs(total_cat - custo_total) < 1.0
