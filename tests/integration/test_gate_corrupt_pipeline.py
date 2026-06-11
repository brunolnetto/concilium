"""Integration test — ADR-022 §D5: corrupt pipeline gate propagation.

Scenario: skill 03-equipes-diretas has been marked as a GATE failure
(pipeline_blocked_from=["05-equipes-e-alocacao"]).

Expected behaviour:
  1. Skill 07-custos-indiretos must NOT produce a MOB=R$0 silently.
     Instead, MOB is omitted entirely from canonical.indiretos,
     and a VAL-INDIR-MOB-BLOQUEADO validation item (AVISO) is emitted.
  2. Skill 06-consolidar receives the result of skill 05 (no MOB).
     It uses MOB=0.0 in the cost aggregation (partial cost — acknowledged absence).
  3. pipeline_integridade stays "CORROMPIDO" through both skills.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from concilium.domain.models.canonical import (
    CanonicalModel,
    Coordenadas,
    Meta,
    Projeto,
    RegimeTrabalho,
)

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_minimal_canonical(
    *,
    pipeline_blocked_from: list[str],
    pipeline_integridade: str | None = "CORROMPIDO",
) -> CanonicalModel:
    """Minimal canonical with a blocked GATE skill set."""
    return CanonicalModel(
        meta=Meta(
            gerado_em=datetime(2026, 1, 1, tzinfo=UTC),
            contexto_id="ctx-test-022-integration",
        ),
        projeto=Projeto(
            id="proj-gate-022",
            nome="Teste Corrompido ADR-022",
            tipo_obra="terraplenagem",
            localizacao="GO",
            coordenadas=Coordenadas(lat=-16.0, lng=-49.0),
            data_inicio=date(2026, 1, 1),
            data_termino=date(2026, 12, 31),
            regime_trabalho=RegimeTrabalho(dias_semana=5, horas_dia=8),
            snapshot_catalogo_id="snap-test-022",
            snapshot_perfil_id="perf-test-022",
        ),
        pipeline_blocked_from=pipeline_blocked_from,
        pipeline_integridade=pipeline_integridade,  # type: ignore[arg-type]
    )


def _perfil_com_mob() -> dict[str, Any]:
    """Minimal perfil with all 5 indirect categories including MOB."""
    return {
        "limiar_ponto_equilibrio": 0.0,
        "faixa_margem_alvo": {"min": 0.05, "max": 0.15},
        "faixa_margem_aceitavel": {"min": 0.02, "max": 0.20},
        "categorias_indireto": [
            {"codigo": "ADM", "descricao": "Administração de obra"},
            {"codigo": "TOP", "descricao": "Topografia"},
            {"codigo": "LAB", "descricao": "Laboratório"},
            {"codigo": "QSMS", "descricao": "Qualidade, SMS"},
            {"codigo": "MOB", "descricao": "Mobilização e desmobilização"},
        ],
        "razao_indireto_direto_alvo": None,
    }


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestGateCorruptPipeline:
    """ADR-022 §D5: skill 03 GATE failure → MOB omitted → CORROMPIDO preserved."""

    def test_skill05_omits_mob_when_03_blocked(self):
        """Skill 05 must skip MOB when 03-equipes-diretas is in pipeline_blocked_from."""
        mod = _import_05_indiretos()

        canonical = _make_minimal_canonical(pipeline_blocked_from=["05-equipes-e-alocacao"])
        perfil = _perfil_com_mob()

        result = mod.run_custos_indiretos(canonical, inputs={}, perfil=perfil)

        # MOB must be absent from indiretos
        mob_entries = [ind for ind in result.canonical.indiretos if ind.categoria == "MOB"]
        assert mob_entries == [], (
            f"MOB should be omitted (not R$0) when 03-equipes-diretas is blocked. Got: {mob_entries}"
        )

        # Explicit validation item must be present
        val_codigos = [v.codigo for v in result.validacoes]
        assert "VAL-INDIR-MOB-BLOQUEADO" in val_codigos, (
            f"Expected VAL-INDIR-MOB-BLOQUEADO in validacoes. Got: {val_codigos}"
        )

        # Validation item must be AVISO (not ERRO — does not block pipeline by itself)
        mob_val = next(v for v in result.validacoes if v.codigo == "VAL-INDIR-MOB-BLOQUEADO")
        assert mob_val.status == "AVISO", f"VAL-INDIR-MOB-BLOQUEADO should be AVISO, got {mob_val.status}"

        # pipeline_integridade must stay CORROMPIDO (not reset by skill 05)
        assert result.canonical.pipeline_integridade == "CORROMPIDO", (
            "pipeline_integridade should remain CORROMPIDO after skill 05. "
            f"Got: {result.canonical.pipeline_integridade}"
        )

    def test_skill05_includes_mob_when_03_not_blocked(self):
        """Control: MOB IS included when 03-equipes-diretas is not blocked."""
        mod = _import_05_indiretos()

        canonical = _make_minimal_canonical(
            pipeline_blocked_from=[],
            pipeline_integridade=None,
        )
        perfil = _perfil_com_mob()

        result = mod.run_custos_indiretos(canonical, inputs={}, perfil=perfil)

        mob_entries = [ind for ind in result.canonical.indiretos if ind.categoria == "MOB"]
        assert mob_entries, "MOB should be present when pipeline is not blocked"

        val_codigos = [v.codigo for v in result.validacoes]
        assert "VAL-INDIR-MOB-BLOQUEADO" not in val_codigos

    def test_skill06_uses_zero_for_missing_mob(self):
        """Skill 06 uses MOB=0.0 (partial cost) when MOB was omitted by skill 05."""
        from concilium.domain.models.canonical import (
            EquipeDireta,
            Indireto,
            Planejamento,
            PrecoUnitarioCategoria,
            SubtotalCategorias,
            SubtotalSemBdiComBdi,
        )

        mod_06 = _import_06_consolidar()

        # Build a canonical that has gone through skill 05 with blocked MOB:
        # - indiretos: ADM + TOP present, MOB absent
        # - equipes_diretas: a minimal entry (required by skill 06 pre-condition)
        # - planejamento: a minimal entry
        canonical = _make_minimal_canonical(pipeline_blocked_from=["05-equipes-e-alocacao"])
        adm = Indireto(categoria="ADM", descricao="Administração", custo_total=50_000.0)
        top = Indireto(categoria="TOP", descricao="Topografia", custo_total=20_000.0)

        equipe = EquipeDireta(
            equipe_id="eq-01",
            item_id="eap-01",
            cpu_id="ESCO-CARGA-1CAT-DMT2000",
            nome="Escavação",
            custo_total=200_000.0,
        )
        plan = Planejamento(
            item_id="eap-01",
            cpu_id="ESCO-CARGA-1CAT-DMT2000",
            quantitativo=1000.0,
            preco_unitario=PrecoUnitarioCategoria(total=200.0),
            subtotal=SubtotalSemBdiComBdi(
                sem_bdi=SubtotalCategorias(total=200_000.0),
                com_bdi=SubtotalCategorias(total=220_000.0),
            ),
        )

        canonical_after_05 = canonical.model_copy(
            update={
                "indiretos": [adm, top],
                "equipes_diretas": [equipe],
                "planejamento": [plan],
            }
        )

        perfil = _perfil_com_mob()
        result = mod_06.run_consolidacao_financeira(canonical_after_05, inputs={}, perfil=perfil)

        # MOB component in resultado should be 0.0
        assert result.canonical.resultado is not None
        assert result.canonical.resultado.custo.indireto_mob == 0.0, (
            "indireto_mob should be 0.0 (partial) when MOB was omitted. "
            f"Got: {result.canonical.resultado.custo.indireto_mob}"
        )

        # pipeline_integridade must still be CORROMPIDO
        assert result.canonical.pipeline_integridade == "CORROMPIDO", (
            "pipeline_integridade should still be CORROMPIDO after skill 06. "
            f"Got: {result.canonical.pipeline_integridade}"
        )

    def test_pipeline_integridade_corrompido_preserved_end_to_end(self):
        """End-to-end: pipeline_blocked_from is preserved across skill executions."""
        mod_05 = _import_05_indiretos()

        canonical = _make_minimal_canonical(pipeline_blocked_from=["05-equipes-e-alocacao"])

        # After skill 05, the canonical should still carry the blocked skill
        result_05 = mod_05.run_custos_indiretos(canonical, inputs={}, perfil=_perfil_com_mob())

        assert "05-equipes-e-alocacao" in (result_05.canonical.pipeline_blocked_from or []), (
            "pipeline_blocked_from should still contain '03-equipes-diretas' after skill 05"
        )
        assert result_05.canonical.pipeline_integridade == "CORROMPIDO"


# ── Import helpers (skills have dashes in their directory names) ──────────────


def _import_05_indiretos():
    """Import run_custos_indiretos from the skill module, working around dashes in path."""
    import importlib.util
    from pathlib import Path

    skill_path = (
        Path(__file__).parent.parent.parent
        / "src"
        / "concilium"
        / "application"
        / "skills"
        / "manifests"
        / "06-resultado-financeiro"
        / "_indiretos"
        / "skill.py"
    )
    spec = importlib.util.spec_from_file_location("skill_05_indiretos", skill_path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _import_06_consolidar():
    """Import run_consolidacao_financeira from the skill module, working around dashes in path."""
    import importlib.util
    from pathlib import Path

    skill_path = (
        Path(__file__).parent.parent.parent
        / "src"
        / "concilium"
        / "application"
        / "skills"
        / "manifests"
        / "06-resultado-financeiro"
        / "_consolidacao"
        / "skill.py"
    )
    spec = importlib.util.spec_from_file_location("skill_06_consolidar", skill_path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod
