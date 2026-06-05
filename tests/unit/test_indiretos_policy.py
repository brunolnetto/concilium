from datetime import UTC, date, datetime

from concilium.application.skills import run_custos_indiretos
from concilium.domain.models.canonical import (
    CanonicalModel,
    Coordenadas,
    EquipeDireta,
    FuncaoEquipeDireta,
    Meta,
    Praticabilidade,
    Projeto,
    RegimeTrabalho,
)


def _minimal_canonical_with_equipes():
    meta = Meta(gerado_em=datetime.now(UTC), contexto_id="test")
    proj = Projeto(
        id="p1",
        nome="proj",
        tipo_obra="terraplenagem",
        localizacao="x",
        coordenadas=Coordenadas(lat=0.0, lng=0.0),
        regime_trabalho=RegimeTrabalho(dias_semana=5, horas_dia=8),
        data_inicio=date(2026, 6, 1),
        data_termino=date(2026, 12, 31),
        snapshot_catalogo_id="s",
        snapshot_perfil_id="s",
    )
    prat = Praticabilidade(
        fonte="t",
        limiar_inviabilidade_mm=0,
        calculada_em=datetime.now(UTC),
        percentual_produtivo_mensal={str(m).zfill(2): 1.0 for m in range(1, 13)},
    )
    func = FuncaoEquipeDireta(
        funcao_id="f1",
        descricao="x",
        num_pessoas=2,
        salario_base=1000,
        percentual_encargos=0.92,
        horas_extras_pct=0.0,
        custo_mensal_unitario=2000,
    )
    equipe = EquipeDireta(
        equipe_id="eq1",
        item_id="i1",
        cpu_id="CPU-X",
        nome="t",
        funcoes=[func],
        equipamentos=[],
        num_equipes_base=1,
        custo_mao_obra_mensal=4000,
        custo_equipamentos_mensal=0,
        custo_fixo_mensal=4000,
        permanencia_meses=2.0,
        custo_total=8000,
    )
    return CanonicalModel(meta=meta, projeto=proj, praticabilidade=prat, equipes_diretas=[equipe])


def test_indiretos_policy_scaling_applies():
    can = _minimal_canonical_with_equipes()
    perfil = {"categorias_indireto": [{"codigo": "ADM", "descricao": "Adm"}, {"codigo": "MOB", "descricao": "Mob"}]}
    inputs = {"dados_mobilizacao": {"mobilizacoes": []}, "composicoes_indireto": {}}

    # baseline standard
    res_std = run_custos_indiretos(can, inputs, perfil=perfil)
    total_std = sum(i.custo_total for i in res_std.canonical.indiretos)

    # robust policy (should increase indirects)
    dv = {"dv4_indirect_policy": "robust"}
    res_rob = run_custos_indiretos(can, {**inputs, "decision_variables": dv}, perfil=perfil)
    total_rob = sum(i.custo_total for i in res_rob.canonical.indiretos)

    assert total_rob > total_std
    assert any(v.codigo == "VAL-IND-POL-01" and v.status == "OK" for v in res_rob.validacoes)

    # unknown policy -> error validation and no scaling applied to baseline values
    dv_bad = {"dv4_indirect_policy": "unknown_policy"}
    res_bad = run_custos_indiretos(can, {**inputs, "decision_variables": dv_bad}, perfil=perfil)
    assert any(v.codigo == "VAL-IND-POL-01" and v.status == "ERRO" for v in res_bad.validacoes)
