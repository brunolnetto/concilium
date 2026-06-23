"""Targeted tiny-gap coverage batch 15.

Covers explicit missing lines in:
- domain/models/analytics/cubo_analitico.py
- domain/models/analytics/cubo_pool.py
- domain/models/analytics/diagnostico_pe.py
- domain/models/analytics/optimization.py
- domain/models/artifact.py
- domain/models/campaign/campaign.py
- domain/models/catalog/snapshot.py
- domain/models/catalog/versioned.py
- domain/models/financial/memorial_bdi.py
- domain/repositories/blob_storage_port.py
"""

from __future__ import annotations

from datetime import date, datetime

import pytest
from pydantic import BaseModel, ValidationError

from concilium.domain.models.analytics.cubo_analitico import CelulaAnalitica, CuboAnalitico
from concilium.domain.models.analytics.cubo_pool import (
    CelulaPoolInstancial,
    CuboPoolInstancial,
    _measure_value,
    bucket_periodo,
)
from concilium.domain.models.analytics.diagnostico_pe import DiagnosticoPEItem, FatorPE
from concilium.domain.models.analytics.optimization import RampProfile
from concilium.domain.models.artifact import ArtifactEnvelope, ArtifactKind, ConciliumArtifactRegistry
from concilium.domain.models.campaign.campaign import GoResearchCampaignBundle, ParametroSweep
from concilium.domain.models.catalog.snapshot import _cs_append_batch_summary
from concilium.domain.models.catalog.versioned import CPUVersionada, DateRange, VersaoCPU
from concilium.domain.models.financial.memorial_bdi import MemorialDecomposicao
from concilium.domain.repositories.blob_storage_port import BlobStoragePort


class _Payload(BaseModel):
    value: str


def _cell(**overrides) -> CelulaAnalitica:
    base = dict(
        natureza="direto",
        atividade_id="A1",
        categoria_insumo="material",
        propriedade="consumivel",
        semana_iso="2026-W10",
        componente_bdi="custo_direto",
        valor_rs=100.0,
        valor_fisico=0.0,
        unidade_fisica="",
    )
    base.update(overrides)
    return CelulaAnalitica(**base)


def test_cubo_analitico_predicate_skip_and_scalar_bucket():
    cubo = CuboAnalitico(
        projeto_id="p1",
        gerado_em="2026-01-01T00:00:00Z",
        regime_bdi="pre_reforma",
        total_preco_venda=300.0,
        celulas=(
            _cell(atividade_id="A1", semana_iso="2026-W10", valor_rs=100.0),
            _cell(atividade_id="A2", semana_iso="2026-W11", valor_rs=200.0),
        ),
    )

    filtered = cubo._aggregate_temporal("semana", predicate=lambda c: c.atividade_id == "A1")
    assert set(filtered.keys()) == {"2026-W10"}

    scalar = cubo._aggregate_temporal_scalar("mes", predicate=lambda c: True)
    assert scalar
    assert list(scalar.values())[0] == 300.0


def test_cubo_analitico_consumo_diesel_paths():
    diesel = _cell(
        categoria_insumo="material",
        propriedade="combustivel",
        unidade_fisica="L",
        valor_fisico=42.5,
        componente_bdi="custo_direto",
        atividade_id="ATV-D",
        semana_iso="2026-W12",
    )
    non_diesel = _cell(atividade_id="ATV-X", valor_rs=50.0)
    cubo = CuboAnalitico(
        projeto_id="p2",
        gerado_em="2026-01-01T00:00:00Z",
        regime_bdi="pre_reforma",
        total_preco_venda=150.0,
        celulas=(diesel, non_diesel),
    )

    assert cubo.consumo_diesel_temporal("semana") == {"2026-W12": 42.5}
    assert cubo.consumo_diesel_por_atividade() == {"ATV-D": 42.5}


def test_cubo_pool_bucket_fallbacks_and_measure_default():
    # ISO parse ok but unsupported granularity should fall back to raw week.
    assert bucket_periodo("2026-W10", "quinzena") == "2026-W10"
    # Non-ISO/non-sequential key should be returned as-is.
    assert bucket_periodo("custom-key", "mes") == "custom-key"

    c = CelulaPoolInstancial(
        contrato_id="C1",
        tipo_id="ESC",
        instancia_numero=1,
        semana_iso="2026-W10",
        estado="off",
        atividade_id=None,
        custo_mo=10.0,
        custo_eq=2.0,
        custo_comb=3.0,
        custo_mat=5.0,
    )
    assert _measure_value(c, "custo_total") == c.custo_total
    assert _measure_value(c, "unknown_measure") == c.custo_total


def test_cubo_pool_ciclo_vida_branch_edges():
    c1 = CelulaPoolInstancial(
        contrato_id="C1",
        tipo_id="ESC",
        instancia_numero=1,
        semana_iso="2026-W10",
        estado="prod",
        atividade_id="A1",
        custo_mo=1.0,
    )
    c2 = CelulaPoolInstancial(
        contrato_id="C1",
        tipo_id="ESC",
        instancia_numero=1,
        semana_iso="2026-W09",
        estado="prod",
        atividade_id="A1",
        custo_mo=1.0,
    )
    c3 = CelulaPoolInstancial(
        contrato_id="C1",
        tipo_id="ESC",
        instancia_numero=1,
        semana_iso="2026-W11",
        estado="off",
        atividade_id=None,
    )
    cubo = CuboPoolInstancial(projeto_id="p", gerado_em="g", celulas=(c1, c2, c3))

    vida = cubo.ciclo_vida_instancias()["ESC-01"]
    assert vida["prod_w"] == 2
    assert vida["off_w"] == 1
    assert vida["semana_mob"] == "2026-W09"
    assert vida["semana_demob"] == "2026-W10"


def test_diagnostico_pe_aproveitamento_necessario_branches():
    fatores = (FatorPE(codigo="F_RESIDUAL", gap_rs=1.0, pct_gap=1.0),)
    ok_item = DiagnosticoPEItem(
        atividade_id="a",
        cpu_id="cpu",
        descricao="d",
        preco_venda=100.0,
        custo_realizado=90.0,
        gap_rs=10.0,
        pct_gap_sobre_venda=0.1,
        eta_real=0.8,
        p_medio_uniforme=0.8,
        cov_n_p=0.0,
        eps_cross=0.0,
        validez_aproximacao=True,
        n_total=1.0,
        fatores=fatores,
        l_aplicado=0.1,
        l_requerido=0.1,
        delta_l=0.0,
    )
    assert ok_item.aproveitamento_necessario_pct == ok_item.aproveitamento_pct

    deficit_item = ok_item.__class__(**{**ok_item.__dict__, "gap_rs": -20.0, "custo_realizado": 120.0})
    assert deficit_item.aproveitamento_necessario_pct > deficit_item.aproveitamento_pct


def test_ramp_profile_model_validator_lines():
    with pytest.raises(ValidationError):
        RampProfile(
            activity_id="A",
            K_max=1,
            n_0=2,
            r=0,
            d=0,
            n_i=1,
            resources_per_team={},
            m=(1,),
            boundary_supply={},
            boundary_demand={},
        )

    with pytest.raises(ValidationError):
        RampProfile(
            activity_id="A",
            K_max=3,
            n_0=1,
            r=3,
            d=2,
            n_i=4,
            resources_per_team={},
            m=(1, 2, 3, 3),
            boundary_supply={},
            boundary_demand={},
        )


def test_artifact_ref_and_registry_helpers():
    payload = _Payload(value="x")
    env = ArtifactEnvelope.create(
        payload=payload,
        kind=ArtifactKind.RESULTADO,
        schema_name="_Payload",
        schema_version="1",
        created_by="test",
    )
    ref = env.ref()
    assert ref.artifact_id == env.meta.artifact_id
    assert ref.content_hash == env.meta.content_hash

    with pytest.raises(ValueError, match="Schema desconhecido"):
        ConciliumArtifactRegistry.validate("SchemaInexistente", {"x": 1})

    known = ConciliumArtifactRegistry.known_schemas()
    assert "Producao" in known


def test_artifact_registry_validate_success_and_create_fallback_json_branch():
    class _TmpModel(BaseModel):
        x: int

    ConciliumArtifactRegistry.register("TmpModelBatch15", _TmpModel)
    validated = ConciliumArtifactRegistry.validate("TmpModelBatch15", {"x": 7})
    assert isinstance(validated, _TmpModel)
    assert validated.x == 7

    # Fallback path for payloads without model_dump_json (line 126-128).
    env = ArtifactEnvelope.create(
        payload={"k": "v"},
        kind=ArtifactKind.RESULTADO,
        schema_name="dict_payload",
        schema_version="1",
        created_by="test",
    )
    assert env.meta.content_hash


def test_campaign_bundle_cardinality_breakdown_and_post_init():
    sweep = [
        ParametroSweep(campo="a", valores=[1, 2]),
        ParametroSweep(campo="b", valores=["x", "y"], scope="per_item", item_ids=["i1", "i2"]),
    ]
    bundle = GoResearchCampaignBundle(base_spec={"x": 1}, sweep=sweep)
    rows = bundle.cardinality_breakdown()

    assert rows[0]["scope"] == "global"
    assert rows[0]["acumulado"] == 2
    assert rows[1]["scope"] == "per_item"
    assert rows[1]["n_items"] == 2
    assert rows[1]["contrib"] == 4
    assert rows[1]["acumulado"] == 8

    explicit = GoResearchCampaignBundle(base_spec={"x": 1}, sweep=[], campaign_id="campaign-fixed")
    assert explicit.campaign_id == "campaign-fixed"


def test_snapshot_append_batch_summary_line():
    parts: list[str] = []
    _cs_append_batch_summary(parts, added=["a"], removed=["b"], modified=["c", "d"], label="insumo(s)")
    assert parts == ["1 insumo(s) +, 1 -, 2 mod."]


def test_cpu_versionada_custo_unitario_none_branch():
    cpu = CPUVersionada(
        id="CPU-X",
        descricao="CPU X",
        unidade="m3",
        categoria="TERRAPLENAGEM",
        versoes=[
            VersaoCPU(
                versao="2026-04",
                validade=DateRange(inicio=date(2026, 4, 1), fim=date(2026, 5, 1)),
                producao_horaria=10.0,
                custo_unitario_sem_encargos=20.0,
                encargos_aplicados_pct=0.5,
                jurisdicao_id_atu="BR-CE@2026-04",
                auditado_por="qa",
                auditado_em=datetime(2026, 4, 2),
            )
        ],
    )
    assert cpu.custo_unitario_em(date(2025, 1, 1)) is None


def test_memorial_decomposicao_properties():
    mem = MemorialDecomposicao(
        categoria="mao_obra",
        custo_direto_pct=0.7,
        overhead_ac_pct=0.03,
        overhead_df_pct=0.02,
        overhead_r_pct=0.01,
        overhead_cr_pct=0.04,
        margem_l_pct=0.05,
        tributo_cofins_pct=0.01,
        tributo_iss_pct=0.02,
        tributo_pis_pct=0.0,
        tributo_cssl_pct=0.03,
        tributo_ir_pct=0.04,
        soma=0.95,
    )
    assert mem.overhead_total_pct == 0.10
    assert mem.tributos_total_pct == 0.10


class _DummyBlobStorage(BlobStoragePort):
    def ler_blob(self, path: str) -> bytes:
        return b""

    def gravar_blob(self, path: str, content: bytes) -> None:
        return None

    def listar_blobs(self, prefix: str) -> list[str]:
        return []

    def blob_existe(self, path: str) -> bool:
        return False


def test_blob_storage_port_default_methods():
    storage = _DummyBlobStorage()
    assert storage.aprovar_versao("x") is None
    assert storage.gerar_url_temporaria("x") is None
