from datetime import date

import pytest

from concilium.domain.models.canonical import Projeto, transition_status_projeto


def _projeto(status: str = "RASCUNHO") -> Projeto:
    return Projeto(
        id="proj-1",
        nome="Projeto teste",
        tipo_obra="terraplenagem",
        localizacao="Aracoiaba, CE",
        coordenadas={"lat": -4.37, "lng": -38.81},
        regime_trabalho={"dias_semana": 6, "horas_dia": 8},
        data_inicio=date(2026, 1, 1),
        data_termino=date(2026, 12, 31),
        status=status,
        snapshot_catalogo_id="cat-1",
        snapshot_perfil_id="perfil-1",
    )


def test_transicao_valida_rascunho_para_aprovado() -> None:
    assert transition_status_projeto("RASCUNHO", "APROVADO") == "APROVADO"


def test_transicao_valida_em_validacao_para_rascunho() -> None:
    assert transition_status_projeto("EM_VALIDACAO", "RASCUNHO") == "RASCUNHO"


def test_transicao_valida_fluxo_execucao() -> None:
    assert transition_status_projeto("APROVADO", "EM_EXECUCAO") == "EM_EXECUCAO"
    assert transition_status_projeto("EM_EXECUCAO", "CONCLUIDO") == "CONCLUIDO"


def test_transicao_invalida_levanta_erro() -> None:
    with pytest.raises(ValueError, match="Transição de status inválida"):
        transition_status_projeto("RASCUNHO", "CONCLUIDO")


def test_projeto_with_status_aplica_transicao_valida() -> None:
    projeto = _projeto("EM_VALIDACAO")
    atualizado = projeto.with_status("APROVADO")
    assert atualizado.status == "APROVADO"


def test_projeto_with_status_bloqueia_transicao_invalida() -> None:
    projeto = _projeto("CONCLUIDO")
    with pytest.raises(ValueError, match="Transição de status inválida"):
        projeto.with_status("APROVADO")


def test_can_transition_to_responde_corretamente() -> None:
    projeto = _projeto("EM_VALIDACAO")
    assert projeto.can_transition_to("APROVADO") is True
    assert projeto.can_transition_to("CONCLUIDO") is False
