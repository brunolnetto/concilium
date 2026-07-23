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



