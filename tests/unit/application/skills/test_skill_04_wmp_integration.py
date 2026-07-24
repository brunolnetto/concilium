"""Integration tests — Skill 04 (cronograma) with Workforce Mobilization Policies (ADR-054).

These tests exercise the full _expand_mobilizacao_policies path inside run_cronograma,
verifying that policies flow correctly from inputs through to the canonical output.

Covers:
- Normal WMP expansion → MANUAL_ALLOCATION mode, VAL-WMP-OK, curvas_forca populated
- Embedded Atividade.mobilizacao_policy (§7.2) — higher priority than file override
- Explicit num_equipes_por_item priority over WMP (explicit wins)
- VAL-WMP-POOL — n_max exceeds resource pool
- VAL-WMP-DESMOB — demobilization forces incompleteness
- VAL-WMP-01 — item not in EAP
- VAL-WMP-03 — invalid policy schema
- VAL-WMP-04 — zero quantitativo
- use_mobilizacao_policy=False bypass (pipeline layer, tested here via inputs absent)
- Week allocation curve shape: n_inicial at t=0, n_maximo after ramp
"""

from __future__ import annotations

from datetime import date, timedelta

from concilium.application.skills import run_catalogo_de_recursos, run_cronograma, run_escopo_e_eap
from concilium.domain.models.canonical import (
    Atividade,
    CanonicalModel,
)
from concilium.domain.models.planning.mobilizacao import MobilizacaoPolicy

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_DEADLINE_DAYS = 365  # 1 year — generous enough for all test scenarios


def _make_catalogo(cpu_specs: list[dict]) -> dict:
    """Build a minimal catalogo dict accepted by run_cronograma."""
    cpus = []
    produtividades = []
    for spec in cpu_specs:
        prod_id = f"PROD-{spec['codigo']}"
        cpus.append(
            {
                "codigo": spec["codigo"],
                "descricao": spec.get("descricao", spec["codigo"]),
                "unidade": spec.get("unidade", "m3"),
                "producao_id_ref": prod_id,
                "categoria": "TERRAPLENAGEM",
                "composicao_itens": [],
                "equipe": {
                    "funcoes": [],
                    "equipamentos": spec.get("equipamentos", []),
                },
            }
        )
        produtividades.append(
            {
                "id": prod_id,
                "descricao": f"Produção {spec['codigo']}",
                "valor_horario": float(spec.get("producao_horaria", 500.0)),
                "cpu_ids": [spec["codigo"]],
            }
        )
    return {"cpus": cpus, "produtividades": produtividades}


def _make_canonical_with_eap(
    items: list[dict],
    pool: dict[str, int] | None = None,
    deadline_days: int = _DEADLINE_DAYS,
) -> CanonicalModel:
    """Create a minimal CanonicalModel with EAP items."""
    inputs = {
        "nome": "WMP Integration Test",
        "tipo_obra": "terraplenagem",
        "localizacao": "Test, BR",
        "coordenadas": {"lat": -10.0, "lng": -40.0},
        # ADR-148: horas_improdutivas_dia=0.0 isola os testes de WMP do fator eta_jornada
        # (mecânica de mobilização/desmobilização é o que estes testes exercitam).
        "regime_trabalho": {"dias_semana": 6, "horas_dia": 8, "horas_improdutivas_dia": 0.0},
        "data_inicio": "2026-06-01",
        "data_termino": (date(2026, 6, 1) + timedelta(days=deadline_days)).isoformat(),
        "eap": items,
        "contexto_id": "test",
        "snapshot_catalogo_id": "snap-cat",
        "snapshot_perfil_id": "snap-perfil",
    }
    canonical = run_escopo_e_eap(None, inputs, catalogo=None).canonical

    if pool:
        tipos = [{"tipo_id": tid, "nome": tid, "categoria": "EQUIPAMENTO", "custo_unitario_dia": 0} for tid in pool]
        pool_items = [{"tipo_id": tid, "quantidade_total": qty} for tid, qty in pool.items()]
        canonical = run_catalogo_de_recursos(canonical, {"tipos_recurso": tipos, "pool_inicial": pool_items}).canonical

    return canonical


def _eap_item(idx: int, quantitativo: float = 50_000.0) -> dict:
    return {
        "item_id": f"eap-{idx:02d}",
        "ordem": idx,
        "cpu_id": f"CPU-{idx:02d}",
        "descricao": f"Serviço {idx}",
        "unidade": "m3",
        "quantitativo": quantitativo,
    }


# ---------------------------------------------------------------------------
# Normal WMP expansion
# ---------------------------------------------------------------------------


class TestWMPExpansion:
    def test_wmp_produces_manual_allocation_mode(self):
        """WMP-derived allocation triggers MANUAL_ALLOCATION mode in Skill 04."""
        canonical = _make_canonical_with_eap([_eap_item(1)])
        catalogo = _make_catalogo([{"codigo": "CPU-01", "producao_horaria": 500.0}])

        result = run_cronograma(
            canonical,
            {
                "mobilizacao_policies": {
                    "eap-01": {"n_inicial": 2, "n_maximo": 5, "taxa_mobilizacao": 1.0},
                }
            },
            catalogo=catalogo,
        )

        assert not result.has_errors
        val_codes = [v.codigo for v in result.validacoes]
        assert "VAL-CRON-MODE" in val_codes
        mode_val = next(v for v in result.validacoes if v.codigo == "VAL-CRON-MODE")
        assert "MANUAL" in mode_val.mensagem
        assert "VAL-WMP-OK" in val_codes

    def test_curvas_forca_populated_in_canonical(self):
        """run_cronograma persists WMP curves in canonical.curvas_forca."""
        canonical = _make_canonical_with_eap([_eap_item(1), _eap_item(2)])
        catalogo = _make_catalogo(
            [
                {"codigo": "CPU-01", "producao_horaria": 300.0},
                {"codigo": "CPU-02", "producao_horaria": 400.0},
            ]
        )

        result = run_cronograma(
            canonical,
            {
                "mobilizacao_policies": {
                    "eap-01": {"n_inicial": 1, "n_maximo": 4, "taxa_mobilizacao": 1.0},
                    "eap-02": {"n_inicial": 2, "n_maximo": 6, "taxa_mobilizacao": 2.0},
                }
            },
            catalogo=catalogo,
        )

        assert not result.has_errors
        assert len(result.canonical.curvas_forca) == 2
        ids = {c.atividade_id for c in result.canonical.curvas_forca}
        assert "eap-01" in ids
        assert "eap-02" in ids

    def test_ramp_shape_n_inicial_at_week0(self):
        """Week 0 allocation equals n_inicial; n_maximo reached after ramp."""
        canonical = _make_canonical_with_eap([_eap_item(1, quantitativo=500_000.0)])
        catalogo = _make_catalogo([{"codigo": "CPU-01", "producao_horaria": 100.0}])

        result = run_cronograma(
            canonical,
            {
                "mobilizacao_policies": {
                    "eap-01": {"n_inicial": 2, "n_maximo": 5, "taxa_mobilizacao": 1.0},
                }
            },
            catalogo=catalogo,
        )

        assert not result.has_errors
        curva = next(c for c in result.canonical.curvas_forca if c.atividade_id == "eap-01")

        assert curva.semanas[0].num_equipes == 2  # week 0 = n_inicial
        # After 3 more weeks (t=3: 2+3=5=n_maximo), should plateau at 5
        late_weeks = [s for s in curva.semanas if s.semana_offset >= 4]
        assert all(s.num_equipes == 5 for s in late_weeks), "Should plateau at n_maximo"

    def test_complete_delivery_of_quantitativo(self):
        """WMP curve must fully deliver quantitativo."""
        Q = 30_000.0
        canonical = _make_canonical_with_eap([_eap_item(1, quantitativo=Q)])
        catalogo = _make_catalogo([{"codigo": "CPU-01", "producao_horaria": 500.0}])

        result = run_cronograma(
            canonical,
            {
                "mobilizacao_policies": {
                    "eap-01": {"n_inicial": 1, "n_maximo": 3, "taxa_mobilizacao": 1.0},
                }
            },
            catalogo=catalogo,
        )

        assert not result.has_errors
        curva = next(c for c in result.canonical.curvas_forca if c.atividade_id == "eap-01")
        assert curva.is_complete
        assert curva.delivered >= Q - 1.0

    def test_scheduled_activity_generated(self):
        """Canonical cronograma must have a scheduled_activity for the WMP item."""
        canonical = _make_canonical_with_eap([_eap_item(1)])
        catalogo = _make_catalogo([{"codigo": "CPU-01", "producao_horaria": 600.0}])

        result = run_cronograma(
            canonical,
            {
                "mobilizacao_policies": {
                    "eap-01": {"n_inicial": 3, "n_maximo": 3, "taxa_mobilizacao": 3.0},
                }
            },
            catalogo=catalogo,
        )

        assert not result.has_errors
        cronograma = result.canonical.cronograma
        assert cronograma is not None
        ids = [sa.activity_id for sa in cronograma.scheduled_activities]
        assert "eap-01" in ids

    def test_multiple_items_expand_independently(self):
        """Each item gets its own WMP curve and allocation."""
        canonical = _make_canonical_with_eap([_eap_item(1), _eap_item(2), _eap_item(3)])
        catalogo = _make_catalogo(
            [
                {"codigo": "CPU-01", "producao_horaria": 400.0},
                {"codigo": "CPU-02", "producao_horaria": 600.0},
                {"codigo": "CPU-03", "producao_horaria": 300.0},
            ]
        )

        result = run_cronograma(
            canonical,
            {
                "mobilizacao_policies": {
                    "eap-01": {"n_inicial": 1, "n_maximo": 4, "taxa_mobilizacao": 1.0},
                    "eap-02": {"n_inicial": 2, "n_maximo": 6, "taxa_mobilizacao": 2.0},
                    "eap-03": {"n_inicial": 1, "n_maximo": 2, "taxa_mobilizacao": 0.5},
                }
            },
            catalogo=catalogo,
        )

        assert not result.has_errors
        assert len(result.canonical.curvas_forca) == 3
        wmp_ok = [v for v in result.validacoes if v.codigo == "VAL-WMP-OK"]
        assert len(wmp_ok) == 3


# ---------------------------------------------------------------------------
# Policy source priority
# ---------------------------------------------------------------------------


class TestPolicyPriority:
    def test_explicit_num_equipes_wins_over_wmp(self):
        """When num_equipes_por_item is explicit for an item, WMP is skipped for it."""
        canonical = _make_canonical_with_eap([_eap_item(1)])
        catalogo = _make_catalogo([{"codigo": "CPU-01", "producao_horaria": 500.0}])
        semanas_obra = [f"2026-W{w:02d}" for w in range(24, 50)]

        result = run_cronograma(
            canonical,
            {
                "num_equipes_por_item": {"eap-01": {s: 7 for s in semanas_obra}},
                "mobilizacao_policies": {
                    "eap-01": {"n_inicial": 1, "n_maximo": 3, "taxa_mobilizacao": 1.0},
                },
            },
            catalogo=catalogo,
        )

        assert not result.has_errors
        # No WMP-OK means WMP was skipped for eap-01 (explicit wins)
        wmp_ok = [v for v in result.validacoes if v.codigo == "VAL-WMP-OK"]
        assert len(wmp_ok) == 0

    def test_embedded_atividade_policy_higher_priority_than_file(self):
        """Atividade.mobilizacao_policy embedded in canonical overrides file-level policy."""
        policy_embedded = MobilizacaoPolicy(n_inicial=4, n_maximo=4, taxa_mobilizacao=4.0)
        canonical = _make_canonical_with_eap([_eap_item(1, quantitativo=10_000.0)])
        catalogo = _make_catalogo([{"codigo": "CPU-01", "producao_horaria": 500.0}])

        # Inject Atividade with embedded policy via model_copy
        atividade = Atividade(
            atividade_id="act-01",
            eap_item_id="eap-01",
            descricao="Test",
            fracao_quantitativo=1.0,
            quantitativo_atividade=10_000.0,
            cpu_id="CPU-01",
            mobilizacao_policy=policy_embedded,
        )
        canonical = canonical.model_copy(update={"atividades": [atividade]})

        # File policy says n_inicial=1 — embedded says n_inicial=4
        result = run_cronograma(
            canonical,
            {
                "mobilizacao_policies": {
                    "eap-01": {"n_inicial": 1, "n_maximo": 2, "taxa_mobilizacao": 1.0},
                }
            },
            catalogo=catalogo,
        )

        assert not result.has_errors
        curva = next(c for c in result.canonical.curvas_forca if c.atividade_id == "eap-01")
        # Embedded policy (n_inicial=4, n_maximo=4) should override file (n_inicial=1)
        assert curva.semanas[0].num_equipes == 4


# ---------------------------------------------------------------------------
# Validation codes
# ---------------------------------------------------------------------------


class TestWMPValidationCodes:
    def test_val_wmp_01_item_not_in_eap(self):
        """VAL-WMP-01 emitted when policy references unknown item_id."""
        canonical = _make_canonical_with_eap([_eap_item(1)])
        catalogo = _make_catalogo([{"codigo": "CPU-01", "producao_horaria": 500.0}])

        result = run_cronograma(
            canonical,
            {
                "mobilizacao_policies": {
                    "eap-99": {"n_inicial": 1, "n_maximo": 3, "taxa_mobilizacao": 1.0},
                }
            },
            catalogo=catalogo,
        )

        val_codes = [v.codigo for v in result.validacoes]
        assert "VAL-WMP-01" in val_codes

    def test_val_wmp_03_invalid_policy_schema(self):
        """VAL-WMP-03 emitted when policy dict fails MobilizacaoPolicy validation."""
        canonical = _make_canonical_with_eap([_eap_item(1)])
        catalogo = _make_catalogo([{"codigo": "CPU-01", "producao_horaria": 500.0}])

        result = run_cronograma(
            canonical,
            {
                "mobilizacao_policies": {
                    "eap-01": {"n_inicial": 5, "n_maximo": 2, "taxa_mobilizacao": 1.0},  # n_max < n_ini
                }
            },
            catalogo=catalogo,
        )

        val_codes = [v.codigo for v in result.validacoes]
        assert "VAL-WMP-03" in val_codes

    def test_val_wmp_pool_n_max_exceeds_pool(self):
        """VAL-WMP-POOL emitted when n_max × equipment_units > pool capacity."""
        canonical = _make_canonical_with_eap(
            [_eap_item(1)],
            pool={"TRATOR-01": 2},  # pool allows only 2 tractors
        )
        catalogo = _make_catalogo(
            [
                {
                    "codigo": "CPU-01",
                    "producao_horaria": 500.0,
                    "equipamentos": [{"equip_id": "TRATOR-01", "num_unidades": 1}],
                }
            ]
        )

        result = run_cronograma(
            canonical,
            {
                "mobilizacao_policies": {
                    "eap-01": {"n_inicial": 1, "n_maximo": 5, "taxa_mobilizacao": 1.0},
                    # 5 teams × 1 tractor = 5 > pool(2)
                }
            },
            catalogo=catalogo,
        )

        val_codes = [v.codigo for v in result.validacoes]
        assert "VAL-WMP-POOL" in val_codes

    def test_val_wmp_desmob_forced_before_delivery(self):
        """VAL-WMP-DESMOB emitted when plateau+desmob prevents full delivery.

        Setup: n_maximo=3, plateau=1, desmob=3/week → n drops to 0 at week 2.
        Max deliverable = week0(3) + week1(3) = 6 × 400 = 2,400 units.
        Q = 50,000 >> 2,400 → incompleta → VAL-WMP-DESMOB.
        guard = MAX_MULTIPLIER × ceil(50,000 / (400×6×8×3)) ≈ 10 × 4 = 40 iterations (fast).
        """
        P = 400.0
        n_max = 3
        m, h = 6, 8
        max_deliverable = P * m * h * n_max * 2  # only 2 active weeks (plateau=1, then desmob kills)
        Q = max_deliverable * 10  # comfortably impossible

        canonical = _make_canonical_with_eap([_eap_item(1, quantitativo=Q)])
        catalogo = _make_catalogo([{"codigo": "CPU-01", "producao_horaria": P}])

        result = run_cronograma(
            canonical,
            {
                "mobilizacao_policies": {
                    "eap-01": {
                        "n_inicial": n_max,
                        "n_maximo": n_max,
                        "taxa_mobilizacao": float(n_max),  # instant ramp
                        "taxa_desmobilizacao": float(n_max),  # full desmob in 1 week
                        "semanas_plateau": 1,  # only 1 week at plateau, then immediate desmob
                    },
                }
            },
            catalogo=catalogo,
        )

        val_codes = [v.codigo for v in result.validacoes]
        assert "VAL-WMP-DESMOB" in val_codes

    def test_no_wmp_validation_without_policies(self):
        """Skill 04 runs cleanly with no WMP codes when mobilizacao_policies absent."""
        canonical = _make_canonical_with_eap([_eap_item(1)])
        catalogo = _make_catalogo([{"codigo": "CPU-01", "producao_horaria": 500.0}])
        semanas = [f"2026-W{w:02d}" for w in range(24, 40)]

        result = run_cronograma(
            canonical,
            {
                "num_equipes_por_item": {"eap-01": {s: 3 for s in semanas}},
            },
            catalogo=catalogo,
        )

        wmp_codes = [v.codigo for v in result.validacoes if v.codigo.startswith("VAL-WMP")]
        assert len(wmp_codes) == 0


# ---------------------------------------------------------------------------
# Curve mechanics
# ---------------------------------------------------------------------------


class TestWMPCurveMechanics:
    def test_imediato_policy_single_week_small_q(self):
        """Immediate max-capacity policy completes in 1 week when Q fits."""
        P, m, h, n = 500.0, 6, 8, 4
        Q = P * m * h * n * 0.5  # exactly half a week of production
        canonical = _make_canonical_with_eap([_eap_item(1, quantitativo=Q)])
        catalogo = _make_catalogo([{"codigo": "CPU-01", "producao_horaria": P}])

        result = run_cronograma(
            canonical,
            {
                "mobilizacao_policies": {
                    "eap-01": {"n_inicial": n, "n_maximo": n, "taxa_mobilizacao": float(n)},
                }
            },
            catalogo=catalogo,
        )

        assert not result.has_errors
        curva = next(c for c in result.canonical.curvas_forca if c.atividade_id == "eap-01")
        assert curva.duration_weeks == 1
        assert curva.is_complete

    def test_praticabilidade_reduces_weekly_production(self):
        """p(t) < 1 reduces weekly production but WMP compensates via more weeks."""
        P, m, h, n = 1_000.0, 6, 8, 5
        Q = P * m * h * n * 10  # exactly 10 weeks at p=1.0

        canonical = _make_canonical_with_eap([_eap_item(1, quantitativo=Q)])

        # Inject praticabilidade — 50% efficiency all year
        from datetime import datetime

        from concilium.domain.models.canonical import Praticabilidade

        prat = Praticabilidade(
            fonte="test",
            limiar_inviabilidade_mm=10.0,
            calculada_em=datetime(2026, 1, 1),
            percentual_produtivo_semanal={f"2026-W{w:02d}": 0.5 for w in range(1, 53)},
        )
        canonical = canonical.model_copy(update={"praticabilidade": prat})
        catalogo = _make_catalogo([{"codigo": "CPU-01", "producao_horaria": P}])

        result = run_cronograma(
            canonical,
            {
                "mobilizacao_policies": {
                    "eap-01": {"n_inicial": n, "n_maximo": n, "taxa_mobilizacao": float(n)},
                }
            },
            catalogo=catalogo,
        )

        assert not result.has_errors
        curva = next(c for c in result.canonical.curvas_forca if c.atividade_id == "eap-01")
        # With p=0.5, needs 20 weeks (double) to deliver same Q
        assert curva.duration_weeks == 20
        assert curva.is_complete

    def test_curva_forca_matches_distribuicao_semanal(self):
        """num_equipes in curva_forca must match distribuicao_semanal for each week."""
        canonical = _make_canonical_with_eap([_eap_item(1, quantitativo=200_000.0)])
        catalogo = _make_catalogo([{"codigo": "CPU-01", "producao_horaria": 400.0}])

        result = run_cronograma(
            canonical,
            {
                "mobilizacao_policies": {
                    "eap-01": {"n_inicial": 1, "n_maximo": 4, "taxa_mobilizacao": 1.0},
                }
            },
            catalogo=catalogo,
        )

        assert not result.has_errors
        curva = next(c for c in result.canonical.curvas_forca if c.atividade_id == "eap-01")
        cronograma = result.canonical.cronograma
        sa = next(a for a in cronograma.scheduled_activities if a.activity_id == "eap-01")

        # Every ISO week in the curve that maps to an ISO key should match distribuicao_semanal
        for s in curva.semanas:
            if s.semana_iso and s.semana_iso in sa.distribuicao_semanal:
                expected_n = s.num_equipes
                actual_n = sa.distribuicao_semanal[s.semana_iso].num_equipes
                assert actual_n == expected_n, (
                    f"Week {s.semana_iso}: curve says {expected_n}, distribuicao says {actual_n}"
                )
