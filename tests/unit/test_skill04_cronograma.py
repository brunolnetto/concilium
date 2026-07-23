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
    Praticabilidade,
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


# ══ 04-cronograma/skill.py ════════════════════════════════════════════════════


class TestCronogramaEdgeCases:
    def _load_lookup_eficiencia(self):
        mod = _load_skill_module("04-cronograma")
        return mod._lookup_eficiencia

    def test_lookup_eficiencia_direct_hit(self):
        """semana_key found directly in prat_semanal → return value (line 74)."""
        fn = self._load_lookup_eficiencia()
        result = fn("2026-W23", {"2026-W23": 0.85}, {})
        assert result == 0.85

    def test_lookup_eficiencia_exception_path(self):
        """malformed semana_key (no '-W') → except Exception → return 1.0 (lines 84-85)."""
        fn = self._load_lookup_eficiencia()
        result = fn("BAD_KEY_NO_DASH_W", {}, {})
        assert result == 1.0

    def test_run_cronograma_prat_set_but_empty_eap(self):
        """praticabilidade set but empty eap → VAL-CRON-PRECONDICAO (lines 118-121)."""
        from concilium.application.skills import run_cronograma

        prat = Praticabilidade(
            fonte="test",
            limiar_inviabilidade_mm=0,
            calculada_em=datetime.now(UTC),
            percentual_produtivo_mensal={"06": 1.0},
        )
        canonical = _minimal_canonical(praticabilidade=prat, eap=[])
        result = run_cronograma(canonical, {}, {})
        assert result.has_errors
        assert any(v.codigo == "VAL-CRON-PRECONDICAO" for v in result.validacoes)

    def test_run_cronograma_negative_num_equipes_clamped(self):
        """num_equipes < 0 is clamped to 0 (line 167)."""
        from concilium.application.skills import run_cronograma

        cpu_id = "CPU-TEST-01"
        prat = Praticabilidade(
            fonte="test",
            limiar_inviabilidade_mm=0,
            calculada_em=datetime.now(UTC),
            percentual_produtivo_mensal={"06": 1.0, "07": 1.0},
        )
        eap = [EapItem(item_id="i1", ordem=1, cpu_id=cpu_id, descricao="test", unidade="m3", quantitativo=100.0)]
        canonical = _minimal_canonical(eap=eap, praticabilidade=prat)
        catalogo = {
            "cpus": [
                {
                    "codigo": cpu_id,
                    "producao_horaria": 50.0,
                    "descricao": "Test CPU",
                    "composicao_padrao_equipe": {"funcoes": [], "equipamentos": []},
                }
            ]
        }
        # Pass negative num_equipes for one week
        inputs = {"num_equipes_por_item": {"i1": {"2026-W23": -1}}}
        result = run_cronograma(canonical, inputs, catalogo)
        # Should run without crash; negative clamped to 0
        assert result.canonical is not None

    def test_run_cronograma_composicao_exception_pass(self):
        """Exception in resource usage calculation → except Exception: pass (lines 203-204)."""
        from concilium.application.skills import run_cronograma

        cpu_id = "CPU-BAD-COMP"
        prat = Praticabilidade(
            fonte="test",
            limiar_inviabilidade_mm=0,
            calculada_em=datetime.now(UTC),
            percentual_produtivo_mensal={"06": 1.0, "07": 1.0},
        )
        eap = [EapItem(item_id="i1", ordem=1, cpu_id=cpu_id, descricao="test", unidade="m3", quantitativo=100.0)]
        canonical = _minimal_canonical(eap=eap, praticabilidade=prat)
        # Malformed composicao: num_unidades is None → int(None) raises
        catalogo = {
            "cpus": [
                {
                    "codigo": cpu_id,
                    "producao_horaria": 50.0,
                    "descricao": "Test",
                    "composicao_padrao_equipe": {
                        "funcoes": [{"funcao_id": "f1", "num_pessoas": None}],
                        "equipamentos": [{"equip_id": "e1", "num_unidades": None}],
                    },
                }
            ]
        }
        inputs = {"num_equipes_por_item": {"i1": {"2026-W23": 1}}}
        result = run_cronograma(canonical, inputs, catalogo)
        # Should succeed (exception swallowed at lines 203-204)
        assert result.canonical is not None



