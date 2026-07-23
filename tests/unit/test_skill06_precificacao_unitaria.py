"""Coverage batch B — targets runtime.py, 04-cronograma, 05-equipes-e-alocacao,
06-resultado-financeiro/_precificacao, 07-diagnostico-criticidade, and semantic/normalizer edge cases.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from concilium.domain.models.canonical import (
    CanonicalModel,
    Coordenadas,
    EapItem,
    Meta,
    Projeto,
    RegimeTrabalho,
)


def _make_meta():
    return Meta(gerado_em=datetime.now(UTC), contexto_id="test")

def _make_proj(data_inicio="2026-06-01", data_termino="2026-07-31"):
    return Projeto(
        id="p1",
        nome="proj",
        tipo_obra="terraplenagem",
        localizacao="x",
        coordenadas=Coordenadas(lat=-3.0, lng=-38.0),
        regime_trabalho=RegimeTrabalho(dias_semana=5, horas_dia=8),
        data_inicio=date(2026, 6, 1),
        data_termino=date(2026, 7, 31),
        snapshot_catalogo_id="s",
        snapshot_perfil_id="s",
    )

def _minimal_canonical(**kw):
    return CanonicalModel(meta=_make_meta(), projeto=_make_proj(), **kw)

def _load_skill_module(skill_id: str) -> object:
    import concilium.application.skills as _skills_pkg

    return _skills_pkg._load_skill_module(skill_id)


# ══ 06-resultado-financeiro/_precificacao/skill.py ══════════════════════════════════════════════


class TestPlanejamentoBdiEdgeCases:
    def _make_canonical_with_eap(self, cpu_id="CPU-BDI-01"):
        eap = [EapItem(item_id="i1", ordem=1, cpu_id=cpu_id, descricao="Test", unidade="m3", quantitativo=100.0)]
        return _minimal_canonical(eap=eap)

    def _base_perfil(self):
        return {
            "formula_bdi": {
                "faixas_por_categoria": {
                    "material": {"min": 0.05, "max": 0.15},
                    "diesel": {"min": 0.05, "max": 0.15},
                    "mao_obra": {"min": 0.1, "max": 0.25},
                    "equipamentos": {"min": 0.05, "max": 0.20},
                }
            },
            "limites_bdi": {},
        }

    def _base_cpu(self, cpu_id="CPU-BDI-01"):
        return {
            "codigo": cpu_id,
            "descricao": "CPU BDI Test",
            "producao_horaria": 50.0,
            "composicao_padrao_equipe": {"funcoes": [], "equipamentos": []},
            "composicao_itens": [
                {"insumo_id": "INS-MAT-01", "coeficiente": 1.0, "categoria_custo": "material"},
            ],
        }

    def _base_insumo(self):
        return {
            "codigo": "INS-MAT-01",
            "tipo": "MATERIAL",
            "descricao": "Material",
            "preco_unitario": 100.0,
            "unidade": "m3",
            "atributos_especificos": {},
        }

    def test_cpu_not_in_lookup_erros_eap(self):
        """cpu_id not in catalogo → VAL-EAP-01 ERRO ou VAL-CPU-SINTETICO AVISO (ADR-108 fallback)."""
        from concilium.application.skills import load_skill_stage

        run_precificacao_unitaria = load_skill_stage(
            "06-resultado-financeiro", "_precificacao", "run_precificacao_unitaria"
        )

        canonical = self._make_canonical_with_eap("CPU-MISSING-BDI")
        catalogo = {"cpus": [], "insumos": []}  # cpu not present
        result = run_precificacao_unitaria(canonical, {}, catalogo, self._base_perfil())
        val_errors = [v for v in result.validacoes if v.codigo in ("VAL-EAP-01", "VAL-CPU-SINTETICO")]
        assert len(val_errors) >= 1

    def test_categoria_not_in_preco_cat_skipped(self):
        """composicao_item with categoria_custo not in preco_cat → continue (line 126)."""
        from concilium.application.skills import load_skill_stage

        run_precificacao_unitaria = load_skill_stage(
            "06-resultado-financeiro", "_precificacao", "run_precificacao_unitaria"
        )

        cpu_id = "CPU-BDI-02"
        canonical = self._make_canonical_with_eap(cpu_id)
        cpu = dict(self._base_cpu(cpu_id))
        # Use unknown categoria_custo
        cpu["composicao_itens"] = [
            {"insumo_id": "INS-MAT-01", "coeficiente": 1.0, "categoria_custo": "TERCEIRIZADO"},
        ]
        catalogo = {"cpus": [cpu], "insumos": [self._base_insumo()]}
        result = run_precificacao_unitaria(canonical, {}, catalogo, self._base_perfil())
        # Should succeed; TERCEIRIZADO is not in preco_cat → skipped
        assert result.canonical is not None
        plan = result.canonical.planejamento
        if plan:
            assert plan[0].preco_unitario.total == 0.0  # nothing was added to preco_cat







# _precificacao/skill.py line 71: _extract_overrides returns dict when dict
# ---------------------------------------------------------------------------


class TestExtractOverrides:
    def _load(self):
        from concilium.application.skills import load_skill_stage

        return load_skill_stage("06-resultado-financeiro", "_precificacao", "_extract_overrides")

    def test_returns_dict_when_dict_value(self):
        """Line 71: val is a dict → return val."""
        fn = self._load()
        result = fn({"insumos_override": {"key": 42}})
        assert result == {"key": 42}

    def test_returns_none_when_not_dict(self):
        fn = self._load()
        assert fn({"insumos_override": "string"}) is None
        assert fn({}) is None


# ---------------------------------------------------------------------------


# _precificacao/skill.py lines 192-198: _as_bool string branches
# ---------------------------------------------------------------------------


class TestAsBool:
    def _load(self):
        from concilium.application.skills import load_skill_stage

        return load_skill_stage("06-resultado-financeiro", "_precificacao", "_as_bool")

    def test_true_string_returns_true(self):
        """Lines 192, 194-195: string in truthy set → True."""
        fn = self._load()
        assert fn("true") is True
        assert fn("yes") is True
        assert fn("1") is True

    def test_false_string_returns_false(self):
        """Lines 192, 196-197: string in falsy set → False."""
        fn = self._load()
        assert fn("false") is False
        assert fn("no") is False
        assert fn("0") is False

    def test_unrecognized_string_returns_false(self):
        """Line 198: string not in either set → falls through to return False."""
        fn = self._load()
        assert fn("maybe") is False

    def test_numeric_nonzero_returns_true(self):
        """Line 204-205: int/float branch — nonzero numeric → True."""
        fn = self._load()
        assert fn(1) is True
        assert fn(2.5) is True

    def test_numeric_zero_returns_false(self):
        """Line 204-205: int/float branch — zero numeric → False."""
        fn = self._load()
        assert fn(0) is False
        assert fn(0.0) is False


# ---------------------------------------------------------------------------


# _precificacao/skill.py lines 290, 294: run_precificacao_unitaria
# erros_eap and erros_insumo blocks triggered
# ---------------------------------------------------------------------------


class TestRunPrecificacaoErros:
    def _load_run(self):
        from concilium.application.skills import load_skill_stage

        return load_skill_stage("06-resultado-financeiro", "_precificacao", "run_precificacao_unitaria")

    def _make_canonical(self, cpu_id: str = "ACT-NOPREFIX"):
        from datetime import UTC, date, datetime

        from concilium.domain.models.canonical import (
            CanonicalModel,
            Coordenadas,
            EapItem,
            Meta,
            Projeto,
            RegimeTrabalho,
        )

        return CanonicalModel(
            meta=Meta(gerado_em=datetime.now(UTC), contexto_id="ctx-test"),
            projeto=Projeto(
                id="proj-test",
                nome="Test",
                tipo_obra="pavimentacao",
                localizacao="CE",
                coordenadas=Coordenadas(lat=-3.7, lng=-38.5),
                data_inicio=date(2026, 1, 1),
                data_termino=date(2026, 6, 30),
                regime_trabalho=RegimeTrabalho(dias_semana=5, horas_dia=8),
                snapshot_catalogo_id="snap-test",
                snapshot_perfil_id="perf-test",
            ),
            eap=[
                EapItem(
                    item_id="EAP-001",
                    ordem=1,
                    cpu_id=cpu_id,
                    descricao="Item teste",
                    unidade="m3",
                    quantitativo=100.0,
                )
            ],
        )

    def test_unknown_cpu_populates_erros_eap(self):
        """Lines 290: erros_eap non-empty → VAL-EAP-01 validacao appended."""
        run = self._load_run()
        # cpu_id not starting with "CPU-" → erros_eap.append directly
        canonical = self._make_canonical(cpu_id="ACT-UNKNOWN-XYZ")
        # Empty catalog so cpu_lookup is empty
        catalogo: dict = {"cpus": [], "insumos": [], "produtividades": [], "producoes": []}

        result = run(canonical, inputs={}, catalogo=catalogo, perfil={})

        codes = [v.codigo for v in result.validacoes]
        assert "VAL-EAP-01" in codes

    def test_erros_insumo_triggers_val_plan_insumo(self):
        """Line 294: erros_insumo non-empty → VAL-PLAN-INSUMO appended."""
        import sys

        from concilium.application.skills import load_skill_stage

        # Load the skill module via o loader real de estágios para poder
        # monkeypatch _process_eap_item.
        fn = load_skill_stage("06-resultado-financeiro", "_precificacao", "run_precificacao_unitaria")
        mod = sys.modules[fn.__module__]

        # Replace _process_eap_item to inject erros_insumo
        def _fake_process(
            item,
            cpu_lookup,
            insumo_lookup,
            prod_lookup,
            equipe_lookup,
            planejamento_item_overrides,
            bdi_aplicado,
            repo,
            jurisdicao_id,
            overrides,
            data_base,
            plan_out,
            erros_eap,
            erros_insumo,
            equip_sem_decomp,
            validacoes,
            benchmark_mode,
            **kwargs,
        ):
            erros_insumo.add("INS-FAKE-01")

        mod._process_eap_item = _fake_process

        canonical = self._make_canonical(cpu_id="CPU-TEST")
        catalogo: dict = {"cpus": [], "insumos": [], "produtividades": [], "producoes": []}

        result = mod.run_precificacao_unitaria(canonical, {}, catalogo, {})
        codes = [v.codigo for v in result.validacoes]
        assert "VAL-PLAN-INSUMO" in codes


# ---------------------------------------------------------------------------

