"""ADR-130 F5 — Ligação de `atualizar_capacidade_gargalo` ao fluxo real de write-back.

`CatalogUpdater._update_producao` (ADR-017 §D5) é o mecanismo real de calibração —
não ADR-076 (`_ponte_equilibrio.py`), que é apenas diagnóstico e nunca escreve no
catálogo. Este arquivo cobre o caso especial `proposta.campo == "capacidade_horaria"`:

- (a) Producao COM grafo_sinergia: `capacidade_horaria` atualiza a capacidade do
  elemento gargalo (via `atualizar_capacidade_gargalo`), preserva `relacoes`, nunca
  toca `valor_horario`, e mantém o mesmo versionamento/auditoria do caminho genérico.
- (b) Producao SEM grafo_sinergia: `ValueError` propaga (não corrompe o catálogo).
- (c) Outros `campo` (ex. `valor_horario`): comportamento genérico inalterado (regressão).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from concilium.domain.models.catalog.catalogo import (
    ComposicaoPadraoEquipe,
    EquipamentoEquipe,
    FuncaoEquipe,
)
from concilium.domain.models.catalog.producao import (
    AuditoriaProducao,
    CapacidadeElemento,
    CondicoesCalibração,
    GrafoSinergiaEquipe,
    OrigemProducao,
    Producao,
    QualidadeProducao,
    RelacaoSinergia,
)
from concilium.domain.models.project.observacao import PropostaAtualizacao
from concilium.infrastructure.catalog.updater import CatalogUpdater
from concilium.infrastructure.repositories.producao import RepositorioProducao

_NOW = datetime(2026, 7, 1, 12, 0, 0)


def _composicao() -> ComposicaoPadraoEquipe:
    return ComposicaoPadraoEquipe(
        funcoes=[FuncaoEquipe(funcao_id="OPER-ESCAV", num_pessoas=1)],
        equipamentos=[
            EquipamentoEquipe(equip_id="ESCAV-38T", num_unidades=1),
            EquipamentoEquipe(equip_id="CAMINHAO-BASC", num_unidades=4),
        ],
    )


def _grafo() -> GrafoSinergiaEquipe:
    return GrafoSinergiaEquipe(
        relacoes=[
            RelacaoSinergia(tipo="acoplamento", origem="OPER-ESCAV", destino="ESCAV-38T"),
            RelacaoSinergia(tipo="dimensionamento", origem="ESCAV-38T", destino="CAMINHAO-BASC", razao=4.0),
        ],
        capacidades=[
            CapacidadeElemento(elemento_id="ESCAV-38T", capacidade_horaria=100.0, unidade="m3/h"),
            CapacidadeElemento(elemento_id="CAMINHAO-BASC", capacidade_horaria=30.0, unidade="m3/h"),
        ],
        gargalo_declarado="ESCAV-38T",
    )


def _producao(*, com_grafo: bool = True, prod_id: str = "PROD-ESCO-1-PROD-001") -> Producao:
    return Producao(
        id=prod_id,
        codigo="ESCO-CARGA-1CAT",
        descricao="Escavação carga 1a categoria",
        valor_horario=100.0,
        unidade="m3",
        origem=OrigemProducao(
            tipo="tabela_referencia",
            fonte_id="SICRO",
            data_calibracao=_NOW,
            referencia="ref",
        ),
        condicoes_calibracao=CondicoesCalibração(),
        qualidade=QualidadeProducao(
            confianca_pct=70, intervalo_confianca=(90.0, 110.0), quantidade_amostras=3, desvio_padrao=5.0
        ),
        composicao_padrao_equipe=_composicao(),
        auditoria=AuditoriaProducao(
            criado_por="eng@co.com",
            data_criacao=_NOW,
            ultima_modificacao=_NOW,
            modificado_por="eng@co.com",
            versao="1.0",
        ),
        grafo_sinergia=_grafo() if com_grafo else None,
    )


def _proposta(**kwargs) -> PropostaAtualizacao:
    defaults = dict(
        proposta_id="PROP-CAP-001",
        tipo_artefato="producao",
        artefato_id="PROD-ESCO-1-PROD-001",
        observacoes=["OBS-CAP-001"],
        n_obras_suporte=2,
        delta_medio_pct=20.0,
        confianca_estimada=0.85,
        campo="capacidade_horaria",
        valor_atual=100.0,
        valor_proposto=120.0,
        justificativa="Medição de campo — obra XPTO, maio/2026.",
        fonte="observacao_obra",
        status="APROVADA",
        criado_em=_NOW,
        criado_por="engenheiro@co.com",
    )
    defaults.update(kwargs)
    return PropostaAtualizacao(**defaults)


def _make_updater(tmp_path: Path) -> CatalogUpdater:
    prods_dir = tmp_path / "producoes"
    prods_dir.mkdir(exist_ok=True)
    insumos_dir = tmp_path / "insumos"
    insumos_dir.mkdir(exist_ok=True)
    return CatalogUpdater(prods_dir, insumos_dir)


class TestUpdateProducaoCapacidadeHorariaComGrafo:
    def test_atualiza_capacidade_do_gargalo_e_versiona(self, tmp_path: Path) -> None:
        prods_dir = tmp_path / "producoes"
        prods_dir.mkdir()
        repo = RepositorioProducao(prods_dir)
        repo.salvar(_producao(com_grafo=True))

        updater = _make_updater(tmp_path)
        proposta = _proposta(valor_proposto=120.0)
        result = updater.apply_update(proposta, "aprovador@co.com")

        assert result.sucesso is True
        assert result.novo_artefato_id == "PROD-ESCO-1-PROD-002"
        assert result.versao_anterior == "PROD-ESCO-1-PROD-001"

        nova = repo.obter_ou_erro("PROD-ESCO-1-PROD-002")
        # Gargalo (ESCAV-38T) recebe a nova capacidade proposta.
        cap_by_id = {c.elemento_id: c for c in nova.grafo_sinergia.capacidades}
        assert cap_by_id["ESCAV-38T"].capacidade_horaria == 120.0
        assert cap_by_id["ESCAV-38T"].fonte == "medicao_obra"
        # Elemento não-gargalo permanece intocado.
        assert cap_by_id["CAMINHAO-BASC"].capacidade_horaria == 30.0
        # relacoes preservadas.
        assert len(nova.grafo_sinergia.relacoes) == 2
        # valor_horario NUNCA é sobrescrito por esta via (D3/A3).
        assert nova.valor_horario == 100.0

    def test_versionamento_e_auditoria_iguais_ao_caminho_generico(self, tmp_path: Path) -> None:
        prods_dir = tmp_path / "producoes"
        prods_dir.mkdir()
        repo = RepositorioProducao(prods_dir)
        repo.salvar(_producao(com_grafo=True))

        updater = _make_updater(tmp_path)
        proposta = _proposta(valor_proposto=120.0, confianca_estimada=0.85, n_obras_suporte=2)
        updater.apply_update(proposta, "aprovador@co.com")

        nova = repo.obter_ou_erro("PROD-ESCO-1-PROD-002")
        assert nova.auditoria.versao == "2.0"
        assert nova.auditoria.modificado_por == "aprovador@co.com"
        assert nova.qualidade.confianca_pct == 85
        assert nova.qualidade.quantidade_amostras == 2
        assert nova.origem.tipo == "calibrado_contra_obra_real"


class TestUpdateProducaoCapacidadeHorariaSemGrafo:
    def test_raises_value_error_sem_grafo_sinergia(self, tmp_path: Path) -> None:
        prods_dir = tmp_path / "producoes"
        prods_dir.mkdir()
        repo = RepositorioProducao(prods_dir)
        repo.salvar(_producao(com_grafo=False))

        updater = _make_updater(tmp_path)
        proposta = _proposta(valor_proposto=120.0)

        with pytest.raises(ValueError, match="gargalo"):
            updater.apply_update(proposta, "aprovador@co.com")

        # Nada persistido: só o arquivo original (PROD-001) deve existir.
        assert repo.listar_ids() == ["PROD-ESCO-1-PROD-001"]


class TestUpdateProducaoOutroCampoRegressao:
    def test_valor_horario_via_campo_generico_inalterado(self, tmp_path: Path) -> None:
        """Regressão: `campo != "capacidade_horaria"` segue o caminho genérico de
        sempre (blind dict-merge via model_copy), mesmo em Producao com grafo."""
        prods_dir = tmp_path / "producoes"
        prods_dir.mkdir()
        repo = RepositorioProducao(prods_dir)
        repo.salvar(_producao(com_grafo=True))

        updater = _make_updater(tmp_path)
        proposta = _proposta(campo="valor_horario", valor_atual=100.0, valor_proposto=135.0)
        result = updater.apply_update(proposta, "aprovador@co.com")

        assert result.sucesso is True
        nova = repo.obter_ou_erro("PROD-ESCO-1-PROD-002")
        assert nova.valor_horario == 135.0
        # grafo_sinergia inalterado pelo caminho genérico.
        cap_by_id = {c.elemento_id: c for c in nova.grafo_sinergia.capacidades}
        assert cap_by_id["ESCAV-38T"].capacidade_horaria == 100.0
        assert cap_by_id["ESCAV-38T"].fonte == "catalogo"
