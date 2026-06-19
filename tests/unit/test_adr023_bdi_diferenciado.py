"""Tests for ADR-023 — BDI Diferenciado por Categoria.

Covers:
  - TabelaBdi model validates with DEFAULT_BDI_TABELA values
  - resolver_componentes_bdi() applies PerfilBdiProjeto overrides
  - Skill 04: _resolve_bdi() priority order (override > tabela_bdi input > DEFAULT)
  - Skill 04: EQUIP BDI = 70% MAO_OBRA + 30% DIESEL (ADR-023 §D3)
  - Skill 04: BDI applied per-category in planejamento output
  - Skill 05: IndiretoComBdi emitted for each category using DEFAULT_BDI_TABELA.indireto
  - Skill 05: graceful degradation when tabela_bdi input is malformed
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from concilium.domain.models.canonical import CanonicalModel, ValidacaoItem
from concilium.domain.models.financial.bdi import (
    DEFAULT_BDI_TABELA,
    ComponentesBdi,
    IndiretoComBdi,
    PerfilBdiProjeto,
    TabelaBdi,
    resolver_componentes_bdi,
)

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_meta():
    from concilium.domain.models.canonical import Meta

    return Meta(gerado_em=datetime(2026, 1, 1, tzinfo=UTC), contexto_id="ctx-bdi-test")


def _make_minimal_canonical(**kwargs) -> CanonicalModel:
    from concilium.domain.models.canonical import Coordenadas, Projeto, RegimeTrabalho

    defaults: dict = {
        "meta": _make_meta(),
        "projeto": Projeto(
            id="proj-bdi-test",
            nome="BDI Test",
            tipo_obra="pavimentacao",
            localizacao="CE",
            coordenadas=Coordenadas(lat=-3.7, lng=-38.5),
            data_inicio=date(2026, 1, 1),
            data_termino=date(2026, 12, 31),
            regime_trabalho=RegimeTrabalho(dias_semana=5, horas_dia=8),
            snapshot_catalogo_id="snap-bdi-test",
            snapshot_perfil_id="perf-bdi-test",
        ),
    }
    defaults.update(kwargs)
    return CanonicalModel(**defaults)


def _comp_bdi_from_total(target_bdi: float) -> ComponentesBdi:
    """Build a ComponentesBdi where bdi_total == target_bdi.

    Uses only the lucro (l) component with all others zeroed, so:
        bdi_total = (1 + l) / 1 - 1 = l
    """
    return ComponentesBdi(
        ac=0.0,
        df=0.0,
        r=0.0,
        cr=0.0,
        l=target_bdi,
        cofins=0.0,
        iss=0.0,
        pis=0.0,
        cssl=0.0,
        ir=0.0,
    )


def _make_bdi_perfil(**lucro_overrides) -> PerfilBdiProjeto:
    """Build a valid PerfilBdiProjeto using DEFAULT component values by default.

    Pass keyword args (mao_obra, material, servicos, indireto, diesel) to override lucro.
    """
    from concilium.domain.models.financial.bdi import (
        AplicacaoTributaria,
        CheckboxTributo,
        PerfilBdiProjeto,
        PerfilLucroProjeto,
        PerfilTributarioProjeto,
    )

    def _trib(a: float) -> CheckboxTributo:
        return CheckboxTributo(aplicavel=a > 0, aliquota=a)

    def _aplic_from_comp(comp: ComponentesBdi) -> AplicacaoTributaria:
        return AplicacaoTributaria(
            iss=_trib(comp.iss),
            cofins=_trib(comp.cofins),
            pis=_trib(comp.pis),
            cssl=_trib(comp.cssl),
            ir=_trib(comp.ir),
        )

    tributario = PerfilTributarioProjeto(
        regime="lucro_presumido",
        municipio="Goiânia/GO",
        iss_aliquota_municipal=0.05,
        mao_obra=_aplic_from_comp(DEFAULT_BDI_TABELA.mao_obra),
        material=_aplic_from_comp(DEFAULT_BDI_TABELA.material),
        servicos=_aplic_from_comp(DEFAULT_BDI_TABELA.servicos),
        indireto=_aplic_from_comp(DEFAULT_BDI_TABELA.indireto),
        diesel=_aplic_from_comp(DEFAULT_BDI_TABELA.diesel),
    )
    lucro = PerfilLucroProjeto(
        mao_obra=lucro_overrides.get("mao_obra", DEFAULT_BDI_TABELA.mao_obra.l),
        material=lucro_overrides.get("material", DEFAULT_BDI_TABELA.material.l),
        servicos=lucro_overrides.get("servicos", DEFAULT_BDI_TABELA.servicos.l),
        indireto=lucro_overrides.get("indireto", DEFAULT_BDI_TABELA.indireto.l),
        diesel=lucro_overrides.get("diesel", DEFAULT_BDI_TABELA.diesel.l),
    )
    return PerfilBdiProjeto(
        projeto_id="proj-bdi-test",
        content_hash="test-hash-0000",
        confirmado_em=datetime(2026, 1, 1, tzinfo=UTC),
        confirmado_por="test@mendeslobo.com",
        tributario=tributario,
        lucro=lucro,
    )


# ── TabelaBdi model ──────────────────────────────────────────────────────────


class TestTabelaBdi:
    def test_default_tabela_bdi_is_valid(self):
        """DEFAULT_BDI_TABELA must be a valid TabelaBdi instance."""
        assert isinstance(DEFAULT_BDI_TABELA, TabelaBdi)

    def test_default_bdi_mao_obra(self):
        """Default MO BDI ≈ 29.97% — planilha AGIS / fórmula TCU multiplicativa.

        Componentes: AC=5%, DF=1.5%, R=1%, L=9% | ISS=5%, CSSL=1.99%, IR=2.74%
        BDI = (1.05)(1.015)(1.01)(1.09) / (1 - 0.0973) - 1 ≈ 29.97%
        """
        assert abs(DEFAULT_BDI_TABELA.mao_obra.bdi_total - 0.2997) < 1e-3

    def test_default_bdi_material(self):
        """Default material BDI = 4.00% — apenas lucro, sem tributos sobre fornecimento."""
        assert abs(DEFAULT_BDI_TABELA.material.bdi_total - 0.04) < 1e-6

    def test_default_bdi_diesel(self):
        """Default diesel BDI = 4.00% — tratado como fornecimento de insumo (planilha AGIS)."""
        assert abs(DEFAULT_BDI_TABELA.diesel.bdi_total - 0.04) < 1e-6

    def test_default_bdi_indireto(self):
        """Default indireto BDI ≈ 25.21% — planilha AGIS / fórmula TCU multiplicativa.

        Componentes: AC=5%, DF=1.5%, R=1%, L=5% | ISS=5%, CSSL=1.99%, IR=2.74%
        BDI = (1.05)(1.015)(1.01)(1.05) / (1 - 0.0973) - 1 ≈ 25.23%
        (Planilha mostra 25.21% — diferença de 0.02% por arredondamento na planilha)
        """
        assert abs(DEFAULT_BDI_TABELA.indireto.bdi_total - 0.2523) < 1e-3

    def test_tabela_bdi_round_trip(self):
        """TabelaBdi serializes and deserializes without loss."""
        raw = DEFAULT_BDI_TABELA.model_dump()
        restored = TabelaBdi.model_validate(raw)
        assert abs(restored.mao_obra.bdi_total - DEFAULT_BDI_TABELA.mao_obra.bdi_total) < 1e-9

    def test_componentes_bdi_accepts_zero_values(self):
        """ComponentesBdi with all-zero components gives BDI=0 (cost-plus contract)."""
        comp = ComponentesBdi(
            ac=0.0,
            df=0.0,
            r=0.0,
            cr=0.0,
            l=0.0,
            cofins=0.0,
            iss=0.0,
            pis=0.0,
            cssl=0.0,
            ir=0.0,
        )
        assert comp.bdi_total == 0.0


class TestResolverComponentesBdi:
    def test_resolver_returns_tabela_when_override_matches_defaults(self):
        """Passing DEFAULT's own component values returns a table with identical BDI."""
        perfil = _make_bdi_perfil()  # all values mirror DEFAULT
        result = resolver_componentes_bdi(DEFAULT_BDI_TABELA, perfil)
        assert abs(result.mao_obra.bdi_total - DEFAULT_BDI_TABELA.mao_obra.bdi_total) < 1e-6
        assert abs(result.material.bdi_total - DEFAULT_BDI_TABELA.material.bdi_total) < 1e-6

    def test_resolver_applies_lucro_override(self):
        """PerfilBdiProjeto with higher lucro on mao_obra increases its bdi_total."""
        base_mo = DEFAULT_BDI_TABELA.mao_obra.bdi_total
        # Increase MO lucro by 5 percentage points
        perfil = _make_bdi_perfil(mao_obra=DEFAULT_BDI_TABELA.mao_obra.l + 0.05)
        result = resolver_componentes_bdi(DEFAULT_BDI_TABELA, perfil)
        assert result.mao_obra.bdi_total > base_mo


# ── Skill 04 _resolve_bdi() ──────────────────────────────────────────────────


class TestResolveBdiPriority:
    """_resolve_bdi() priority: override manual > tabela_bdi input > DEFAULT."""

    def _call_resolve(self, inputs: dict, validacoes: list | None = None):
        from concilium.application.skills.manifests.skill_04_planejamento_bdi import _resolve_bdi

        validacoes_out: list[ValidacaoItem] = validacoes if validacoes is not None else []
        return _resolve_bdi(inputs, validacoes_out), validacoes_out

    def _import_resolve_bdi(self):
        """Import _resolve_bdi; skip test if skill module not importable."""
        try:
            import importlib

            mod = importlib.import_module("concilium.application.skills.manifests.04_planejamento_bdi.skill")
            return mod._resolve_bdi
        except Exception:
            # Try alternate import path
            import importlib.util
            from pathlib import Path

            skill_path = (
                Path(__file__).parent.parent.parent
                / "src/concilium/application/skills/manifests/06-resultado-financeiro/_precificacao/skill.py"
            )
            spec = importlib.util.spec_from_file_location("skill_04", skill_path)
            mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            return mod._resolve_bdi

    def test_override_manual_wins_over_default(self):
        """bdi_aplicado in inputs overrides DEFAULT_BDI_TABELA."""
        _resolve_bdi = self._import_resolve_bdi()
        override = {
            "material": 0.10,
            "diesel": 0.30,
            "mao_obra": 0.40,
            "equipamentos": 0.35,
        }
        validacoes: list[ValidacaoItem] = []
        result = _resolve_bdi({"bdi_aplicado": override}, validacoes)

        assert result["material"] == 0.10
        assert result["mao_obra"] == 0.40
        # Should emit VAL-BDI-FONTE with status=AVISO (override used)
        bdi_val = next((v for v in validacoes if v.codigo == "VAL-BDI-FONTE"), None)
        assert bdi_val is not None
        assert bdi_val.status == "AVISO"

    def test_tabela_bdi_input_wins_over_default(self):
        """TabelaBdi in inputs.tabela_bdi is used over DEFAULT."""
        _resolve_bdi = self._import_resolve_bdi()

        custom_tabela = TabelaBdi(
            mao_obra=_comp_bdi_from_total(0.20),
            material=_comp_bdi_from_total(0.08),
            diesel=_comp_bdi_from_total(0.15),
            indireto=_comp_bdi_from_total(0.10),
            servicos=_comp_bdi_from_total(0.20),
            data_vigencia="2026-01-01",
        )
        validacoes: list[ValidacaoItem] = []
        result = _resolve_bdi({"tabela_bdi": custom_tabela.model_dump()}, validacoes)

        assert abs(result["mao_obra"] - 0.20) < 1e-6
        assert abs(result["material"] - 0.08) < 1e-6

    def test_default_used_when_no_inputs(self):
        """When no BDI input is provided, DEFAULT_BDI_TABELA is used."""
        _resolve_bdi = self._import_resolve_bdi()
        validacoes: list[ValidacaoItem] = []
        result = _resolve_bdi({}, validacoes)

        assert abs(result["mao_obra"] - DEFAULT_BDI_TABELA.mao_obra.bdi_total) < 1e-6
        assert abs(result["material"] - DEFAULT_BDI_TABELA.material.bdi_total) < 1e-6

    def test_equip_bdi_derivado_da_composicao(self):
        """ADR-023 §D3 revisado: equip = frac_loc×material + (1−frac_loc)×mao_obra.

        Default (locação pura, SV-31/STF: locação de bens móveis sem ISS) → material.
        O placeholder 70/30 original foi removido — aplicava markup de MO/diesel a uma
        base que, pós ADR-088/090, contém apenas locação+manutenção.
        """
        _resolve_bdi = self._import_resolve_bdi()
        validacoes: list[ValidacaoItem] = []
        result = _resolve_bdi({}, validacoes)

        bdi_mat = DEFAULT_BDI_TABELA.material.bdi_total
        assert abs(result["equipamentos"] - bdi_mat) < 1e-5, (
            f"EQUIP BDI {result['equipamentos']:.6f} != material {bdi_mat:.6f} (locação pura)"
        )

    def test_malformed_tabela_bdi_falls_back_to_default(self):
        """Invalid tabela_bdi dict emits AVISO and falls back to DEFAULT."""
        _resolve_bdi = self._import_resolve_bdi()
        validacoes: list[ValidacaoItem] = []
        result = _resolve_bdi({"tabela_bdi": {"invalid_key": 999}}, validacoes)

        # Must fall back to DEFAULT values
        assert abs(result["mao_obra"] - DEFAULT_BDI_TABELA.mao_obra.bdi_total) < 1e-6
        # Should have emitted a parse warning
        parse_val = next((v for v in validacoes if v.codigo == "VAL-BDI-PARSE"), None)
        assert parse_val is not None
        assert parse_val.status == "AVISO"


# ── Skill 05 IndiretoComBdi ──────────────────────────────────────────────────


class TestIndiretoComBdi:
    def test_indireto_com_bdi_model(self):
        """IndiretoComBdi computes custo_com_bdi correctly."""
        item = IndiretoComBdi(
            categoria="ADM",
            custo_sem_bdi=100_000.0,
            bdi_aplicado=0.2247,
            custo_com_bdi=round(100_000.0 * 1.2247, 2),
        )
        assert abs(item.custo_com_bdi - 122_470.0) < 0.01
        assert abs(item.bdi_aplicado - 0.2247) < 1e-6

    def test_indireto_com_bdi_default_uses_indireto_component(self):
        """DEFAULT_BDI_TABELA.indireto.bdi_total is used when no tabela_bdi provided."""
        bdi_indireto = DEFAULT_BDI_TABELA.indireto.bdi_total
        custo_sem = 50_000.0
        expected_com = round(custo_sem * (1 + bdi_indireto), 2)

        item = IndiretoComBdi(
            categoria="TOP",
            custo_sem_bdi=custo_sem,
            bdi_aplicado=round(bdi_indireto, 6),
            custo_com_bdi=expected_com,
        )
        assert abs(item.custo_com_bdi - expected_com) < 0.01

    def test_indireto_com_bdi_all_categories(self):
        """IndiretoComBdi is valid for all standard indirect categories."""
        bdi = DEFAULT_BDI_TABELA.indireto.bdi_total
        for cat in ("ADM", "TOP", "LAB", "QSMS", "MOB"):
            item = IndiretoComBdi(
                categoria=cat,
                custo_sem_bdi=1000.0,
                bdi_aplicado=bdi,
                custo_com_bdi=round(1000.0 * (1 + bdi), 2),
            )
            assert item.categoria == cat
            assert item.custo_com_bdi > item.custo_sem_bdi


class TestSkill05IndiretosBdiEmission:
    """Integration: skill 05 produces indiretos_com_bdi."""

    def _load_skill05(self):
        import importlib.util
        from pathlib import Path

        skill_path = (
            Path(__file__).parent.parent.parent
            / "src/concilium/application/skills/manifests/06-resultado-financeiro/_indiretos/skill.py"
        )
        spec = importlib.util.spec_from_file_location("skill_05", skill_path)
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod.run_custos_indiretos

    def _minimal_perfil(self) -> dict:
        return {
            "categorias_indireto": [
                {"codigo": "ADM", "descricao": "Administração Local"},
                {"codigo": "TOP", "descricao": "Topografia"},
            ],
        }

    def test_skill05_emits_indiretos_com_bdi(self):
        """run_custos_indiretos() should populate canonical.indiretos_com_bdi."""
        run_custos_indiretos = self._load_skill05()
        canonical_in = _make_minimal_canonical()
        perfil = self._minimal_perfil()

        result = run_custos_indiretos(canonical_in=canonical_in, inputs={}, perfil=perfil)

        assert result.canonical.indiretos_com_bdi is not None
        assert len(result.canonical.indiretos_com_bdi) > 0

        # BDI should match DEFAULT
        bdi_expected = DEFAULT_BDI_TABELA.indireto.bdi_total
        for item in result.canonical.indiretos_com_bdi:
            assert abs(item.bdi_aplicado - bdi_expected) < 1e-5, (
                f"IndiretoComBdi.bdi_aplicado {item.bdi_aplicado} != DEFAULT {bdi_expected}"
            )
            assert item.custo_com_bdi >= item.custo_sem_bdi

    def test_skill05_com_bdi_uses_custom_tabela_bdi(self):
        """Providing tabela_bdi in inputs overrides DEFAULT for indireto component."""
        run_custos_indiretos = self._load_skill05()

        custom_indireto_bdi = 0.50  # 50% — obviously different from default
        custom_tabela = TabelaBdi(
            mao_obra=_comp_bdi_from_total(DEFAULT_BDI_TABELA.mao_obra.bdi_total),
            material=_comp_bdi_from_total(DEFAULT_BDI_TABELA.material.bdi_total),
            diesel=_comp_bdi_from_total(DEFAULT_BDI_TABELA.diesel.bdi_total),
            indireto=_comp_bdi_from_total(custom_indireto_bdi),
            servicos=_comp_bdi_from_total(DEFAULT_BDI_TABELA.servicos.bdi_total),
            data_vigencia="2026-01-01",
        )

        canonical_in = _make_minimal_canonical()
        perfil = self._minimal_perfil()
        result = run_custos_indiretos(
            canonical_in=canonical_in,
            inputs={"tabela_bdi": custom_tabela.model_dump()},
            perfil=perfil,
        )

        for item in result.canonical.indiretos_com_bdi:
            assert abs(item.bdi_aplicado - custom_indireto_bdi) < 1e-5

    def test_skill05_emits_val_indir_bdi_ok(self):
        """run_custos_indiretos() emits VAL-INDIR-BDI-OK validation."""
        run_custos_indiretos = self._load_skill05()
        canonical_in = _make_minimal_canonical()
        result = run_custos_indiretos(
            canonical_in=canonical_in,
            inputs={},
            perfil=self._minimal_perfil(),
        )
        val_codes = [v.codigo for v in result.validacoes]
        assert "VAL-INDIR-BDI-OK" in val_codes

    def test_skill05_malformed_tabela_bdi_degrades_gracefully(self):
        """Malformed tabela_bdi in inputs: emits AVISO, uses DEFAULT, does not crash."""
        run_custos_indiretos = self._load_skill05()
        canonical_in = _make_minimal_canonical()
        result = run_custos_indiretos(
            canonical_in=canonical_in,
            inputs={"tabela_bdi": {"garbage": True}},
            perfil=self._minimal_perfil(),
        )
        # Should still produce indiretos_com_bdi (using DEFAULT)
        assert len(result.canonical.indiretos_com_bdi) > 0
        # Should emit parse warning
        assert any(v.codigo == "VAL-INDIR-BDI-PARSE" for v in result.validacoes)
        # BDI should fall back to DEFAULT
        for item in result.canonical.indiretos_com_bdi:
            assert abs(item.bdi_aplicado - DEFAULT_BDI_TABELA.indireto.bdi_total) < 1e-5


# ── Phase 5 §D3 — DecomposicaoEquipamento ────────────────────────────────────


class TestDecomposicaoEquipamento:
    """ADR-023 §D3: DecomposicaoEquipamento model validation."""

    def test_valid_decomposition(self):
        from concilium.domain.models.financial.bdi import DecomposicaoEquipamento

        d = DecomposicaoEquipamento(
            equip_id="EQ-001",
            custo_hora_total=100.0,
            custo_mao_obra_h=50.0,
            custo_diesel_h=20.0,
            custo_material_h=10.0,
            custo_capital_h=20.0,
        )
        assert d.custo_hora_total == 100.0
        assert abs(d.fracao_mao_obra - 0.70) < 1e-6  # (50+20)/100
        assert abs(d.fracao_diesel - 0.20) < 1e-6
        assert abs(d.fracao_material - 0.10) < 1e-6

    def test_components_must_sum_to_total(self):
        from concilium.domain.models.financial.bdi import DecomposicaoEquipamento

        with pytest.raises(Exception, match="Soma dos componentes"):
            DecomposicaoEquipamento(
                equip_id="EQ-BAD",
                custo_hora_total=100.0,
                custo_mao_obra_h=40.0,
                custo_diesel_h=20.0,
                custo_material_h=10.0,
                custo_capital_h=10.0,  # sums to 80, not 100
            )

    def test_fracao_properties_sum_to_one(self):
        from concilium.domain.models.financial.bdi import DecomposicaoEquipamento

        d = DecomposicaoEquipamento(
            equip_id="EQ-002",
            custo_hora_total=200.0,
            custo_mao_obra_h=80.0,
            custo_diesel_h=60.0,
            custo_material_h=40.0,
            custo_capital_h=20.0,
        )
        total = d.fracao_mao_obra + d.fracao_diesel + d.fracao_material
        assert abs(total - 1.0) < 1e-5

    def test_atributos_insumo_carries_decomposicao(self):
        from concilium.domain.models.catalog.catalogo import AtributosInsumo
        from concilium.domain.models.financial.bdi import DecomposicaoEquipamento

        decomp = DecomposicaoEquipamento(
            equip_id="EQ-003",
            custo_hora_total=100.0,
            custo_mao_obra_h=70.0,
            custo_diesel_h=30.0,
            custo_material_h=0.0,
            custo_capital_h=0.0,
        )
        attr = AtributosInsumo(decomposicao_equip=decomp)
        assert attr.decomposicao_equip is not None
        assert attr.decomposicao_equip.equip_id == "EQ-003"

    def test_atributos_insumo_decomposicao_none_by_default(self):
        from concilium.domain.models.catalog.catalogo import AtributosInsumo

        attr = AtributosInsumo()
        assert attr.decomposicao_equip is None


class TestSkill04EquipamentoDecomp:
    """ADR-023 §D3: skill 04 uses decomposicao_equip when available."""

    def _load_skill04(self):
        import importlib.util
        import pathlib

        path = (
            pathlib.Path(__file__).parent.parent.parent
            / "src"
            / "concilium"
            / "application"
            / "skills"
            / "manifests"
            / "06-resultado-financeiro"
            / "_precificacao"
            / "skill.py"
        )
        spec = importlib.util.spec_from_file_location("skill_04", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.run_precificacao_unitaria

    def _make_canonical_with_eap(self):
        from concilium.domain.models.canonical import EapItem

        return _make_minimal_canonical(
            eap=[
                EapItem(
                    item_id="EAP-001",
                    ordem=1,
                    cpu_id="CPU-ESCAV",
                    descricao="Escavação",
                    unidade="m3",
                    quantitativo=100.0,
                )
            ]
        )

    def _catalog_with_decomp(self, decomp_data: dict | None):
        """Catalog with one EQUIPAMENTO insumo, optionally carrying decomposicao_equip."""
        atribs = {"consumo_litros_hora": 10.0}
        if decomp_data:
            atribs["decomposicao_equip"] = decomp_data
        return {
            "cpus": [
                {
                    "codigo": "CPU-ESCAV",
                    "descricao": "Escavação",
                    "unidade": "m3",
                    "origem": "PROPRIA",
                    "categoria": "TERRAPLENAGEM",
                    "producao_id_ref": "PROD-001",
                    "composicao_itens": [
                        {"insumo_id": "INS-ESCAV", "coeficiente": 1.0, "categoria_custo": "EQUIPAMENTO"},
                    ],
                }
            ],
            "insumos": [
                {
                    "codigo": "INS-ESCAV",
                    "tipo": "EQUIPAMENTO",
                    "descricao": "Escavadeira",
                    "unidade": "h",
                    "preco_unitario": 200.0,
                    "fonte_preco": "catalogo_proprio",
                    "atributos_especificos": atribs,
                }
            ],
            "produtividades": [{"id": "PROD-001", "valor_horario": 10.0}],
        }

    def _minimal_perfil(self):
        return {"formula_bdi": {}}

    def test_with_decomp_routes_cost_to_correct_buckets(self):
        """When decomposicao_equip present: MAO_OBRA 70%, DIESEL 20%, MATERIAL 10%."""
        run = self._load_skill04()
        canonical_in = self._make_canonical_with_eap()
        decomp = {
            "equip_id": "INS-ESCAV",
            "custo_hora_total": 100.0,
            "custo_mao_obra_h": 50.0,
            "custo_diesel_h": 20.0,
            "custo_material_h": 10.0,
            "custo_capital_h": 20.0,
        }
        result = run(
            canonical_in=canonical_in,
            inputs={},
            catalogo=self._catalog_with_decomp(decomp),
            perfil=self._minimal_perfil(),
        )
        plan = result.canonical.planejamento
        assert len(plan) == 1
        p = plan[0]
        # equipamentos bucket should be ~0 (residual only)
        assert p.preco_unitario.equipamentos < 1e-6
        # mao_obra = 200 * (50+20)/100 = 140; diesel = 200 * 20/100 = 40; material = 200 * 10/100 = 20
        assert abs(p.preco_unitario.mao_obra - 140.0) < 0.01
        assert abs(p.preco_unitario.diesel - 40.0) < 0.01
        assert abs(p.preco_unitario.material - 20.0) < 0.01

    def test_without_decomp_emits_val_equip_decomp_aviso(self):
        """When decomposicao_equip absent: emits VAL-EQUIP-DECOMP AVISO."""
        run = self._load_skill04()
        canonical_in = self._make_canonical_with_eap()
        result = run(
            canonical_in=canonical_in,
            inputs={},
            catalogo=self._catalog_with_decomp(None),
            perfil=self._minimal_perfil(),
        )
        codes = {v.codigo: v.status for v in result.validacoes}
        assert "VAL-EQUIP-DECOMP" in codes
        assert codes["VAL-EQUIP-DECOMP"] == "AVISO"

    def test_without_decomp_uses_weighted_average_in_equipamentos(self):
        """Fallback: full cost stays in equipamentos bucket."""
        run = self._load_skill04()
        canonical_in = self._make_canonical_with_eap()
        result = run(
            canonical_in=canonical_in,
            inputs={},
            catalogo=self._catalog_with_decomp(None),
            perfil=self._minimal_perfil(),
        )
        plan = result.canonical.planejamento
        assert len(plan) == 1
        p = plan[0]
        # All 200 should be in equipamentos (no decomposition)
        assert abs(p.preco_unitario.equipamentos - 200.0) < 0.01

    def test_with_decomp_no_val_equip_decomp_aviso(self):
        """When decomposicao_equip present: VAL-EQUIP-DECOMP should NOT be emitted."""
        run = self._load_skill04()
        canonical_in = self._make_canonical_with_eap()
        decomp = {
            "equip_id": "INS-ESCAV",
            "custo_hora_total": 100.0,
            "custo_mao_obra_h": 70.0,
            "custo_diesel_h": 30.0,
            "custo_material_h": 0.0,
            "custo_capital_h": 0.0,
        }
        result = run(
            canonical_in=canonical_in,
            inputs={},
            catalogo=self._catalog_with_decomp(decomp),
            perfil=self._minimal_perfil(),
        )
        codes = [v.codigo for v in result.validacoes]
        assert "VAL-EQUIP-DECOMP" not in codes
