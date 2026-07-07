"""Formulário QQP/EAP — ADR-092.

Interface Streamlit em três seções para criação de projetos por humanos
semi-instruídos:
  Seção 1 — Identificação do Projeto
  Seção 2 — QQP: lista de serviços com sugestão automática de CPU
  Seção 3 — Revisão e criação
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import streamlit as st

try:
    from ..config import DEFAULT_ACTOR, DEFAULT_BASE_URL
    from ..infra.api import api_call
except ImportError:
    src_root = Path(__file__).resolve().parents[4]
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))
    from concilium.presentation.ui.config import DEFAULT_ACTOR, DEFAULT_BASE_URL
    from concilium.presentation.ui.infra.api import api_call


# ── Helpers ───────────────────────────────────────────────────────────────────


def _load_contextos() -> list[str]:
    try:
        resp = api_call("GET", "/api/contextos", base_url=DEFAULT_BASE_URL, actor=DEFAULT_ACTOR)
        return [c["id"] for c in (resp.get("items") or []) if c.get("id")]
    except Exception:
        return []


def _suggest_cpus(servicos: list[dict]) -> dict:
    try:
        return api_call(
            "POST",
            "/api/formulario/sugerir-cpus",
            base_url=DEFAULT_BASE_URL,
            actor=DEFAULT_ACTOR,
            payload={"servicos": servicos},
        )
    except Exception as exc:
        return {"erro": str(exc), "mapeados": [], "nao_mapeados": [], "total": 0}


def _criar_projeto(payload: dict) -> dict:
    try:
        return api_call(
            "POST",
            "/api/formulario/projeto",
            base_url=DEFAULT_BASE_URL,
            actor=DEFAULT_ACTOR,
            payload=payload,
        )
    except Exception as exc:
        return {"status": "erro", "erro": str(exc)}


def _buscar_cpus(termo: str) -> list[dict]:
    try:
        resp = api_call(
            "GET",
            "/api/catalogs/cpus",
            base_url=DEFAULT_BASE_URL,
            actor=DEFAULT_ACTOR,
            params={"q": termo, "limit": "10"},
        )
        return resp.get("items") or []
    except Exception:
        return []


# ── State helpers ─────────────────────────────────────────────────────────────


def _init_state() -> None:
    if "qqp_servicos" not in st.session_state:
        st.session_state.qqp_servicos = [
            {"descricao": "", "quantidade": 1.0, "unidade": "m³", "cpu_id": "", "predecessores": []}
        ]
    if "qqp_sugestoes" not in st.session_state:
        st.session_state.qqp_sugestoes = {}
    if "qqp_resultado" not in st.session_state:
        st.session_state.qqp_resultado = None


# ── Render ────────────────────────────────────────────────────────────────────


def _render_secao_identificacao() -> tuple[str, str, Any, Any, int, int, str]:
    """Seção 1: Identificação do Projeto.

    Retorna (contexto_id, tipo_obra, data_inicio, data_termino, dias_semana, horas_dia, objetivo_pool).
    """
    with st.expander("1️⃣  Identificação do Projeto", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            st.text_input("Nome do projeto *", key="qqp_nome", placeholder="Ex: Lote 09/10 CE")
            tipo_obra = st.selectbox(
                "Tipo de obra *",
                ["terraplenagem", "pavimentacao", "saneamento"],
                key="qqp_tipo_obra",
            )
            st.text_input("Localização *", key="qqp_localizacao", placeholder="Cidade, UF")
        with col2:
            contextos = _load_contextos()
            contexto_id = st.selectbox(
                "Contexto de cálculo *",
                contextos or ["test"],
                key="qqp_contexto_id",
                help="Define catálogo, perfil BDI e jurisdição fiscal.",
            )
            data_inicio = st.date_input("Data de início *", key="qqp_data_inicio")
            data_termino = st.date_input("Data de término (opcional)", key="qqp_data_termino", value=None)

        col3, col4, col5 = st.columns(3)
        with col3:
            dias_semana = st.number_input("Dias/semana", min_value=1, max_value=7, value=6, key="qqp_dias_semana")
        with col4:
            horas_dia = st.number_input("Horas/dia", min_value=4, max_value=12, value=8, key="qqp_horas_dia")
        with col5:
            objetivo_pool = st.selectbox(
                "Objetivo de pool",
                ["balanceado", "minimizar_prazo", "minimizar_custo"],
                key="qqp_objetivo_pool",
            )
    return contexto_id, tipo_obra, data_inicio, data_termino, dias_semana, horas_dia, objetivo_pool


def _badge_for_confianca(confianca: str) -> str:
    return {"alta": "🟢", "media": "🟡", "nenhuma": "🔴"}.get(confianca, "")


def _render_servico_row(idx: int, svc: dict, sugestoes: dict) -> bool:
    """Renderiza uma linha da tabela de serviços. Retorna True se o botão de excluir foi clicado."""
    key_prefix = f"svc_{idx}"
    is_first = idx == 0
    label_vis = "visible" if is_first else "collapsed"
    col_d, col_q, col_u, col_cpu, col_del = st.columns([4, 1.5, 1, 2.5, 0.5])

    with col_d:
        svc["descricao"] = st.text_input(
            "Descrição" if is_first else "",
            value=svc.get("descricao", ""),
            key=f"{key_prefix}_desc",
            placeholder="Ex: Escavação de material de 3ª categoria",
            label_visibility=label_vis,
        )
    with col_q:
        svc["quantidade"] = st.number_input(
            "Qtd" if is_first else "",
            value=float(svc.get("quantidade", 1.0)),
            min_value=0.0,
            key=f"{key_prefix}_qtd",
            label_visibility=label_vis,
        )
    with col_u:
        svc["unidade"] = st.text_input(
            "Un." if is_first else "",
            value=svc.get("unidade", "m³"),
            key=f"{key_prefix}_und",
            label_visibility=label_vis,
        )
    with col_cpu:
        sugestao = sugestoes.get(idx, {})
        cpu_sugerido = sugestao.get("cpu_id", "")
        confianca = sugestao.get("confianca", "")
        badge = _badge_for_confianca(confianca)

        svc["cpu_id"] = st.text_input(
            f"CPU {badge}" if is_first else badge or "",
            value=svc.get("cpu_id") or cpu_sugerido,
            key=f"{key_prefix}_cpu",
            placeholder="CPU-TERRA-...",
            label_visibility="visible" if is_first else "visible",
        )
    with col_del:
        return bool(st.button("✕", key=f"{key_prefix}_del", use_container_width=True))


def _handle_suggest_cpus(servicos: list[dict], sugestoes: dict) -> None:
    """Chama a API de sugestão de CPUs e aplica os resultados aos serviços sem CPU."""
    with st.spinner("Buscando CPUs no catálogo..."):
        svc_payload = [
            {"descricao": s["descricao"], "quantidade": s["quantidade"], "unidade": s["unidade"]}
            for s in servicos
            if s.get("descricao")
        ]
        resultado = _suggest_cpus(svc_payload)
        # Aplica sugestões
        for i, item in enumerate(resultado.get("mapeados", [])):
            if i < len(servicos) and not servicos[i].get("cpu_id"):
                servicos[i]["cpu_id"] = item.get("cpu_id", "")
                sugestoes[i] = {"cpu_id": item["cpu_id"], "confianca": item.get("confianca", "media")}
        st.session_state.qqp_sugestoes = sugestoes
        n_mapeados = len(resultado.get("mapeados", []))
        n_nao = len(resultado.get("nao_mapeados", []))
        if n_nao == 0:
            st.success(f"✅ Todos os {n_mapeados} serviços mapeados com sucesso.")
        else:
            st.warning(f"⚠️  {n_mapeados} mapeados, {n_nao} sem CPU — preencha manualmente.")
        st.rerun()


def _render_secao_qqp(servicos: list[dict], sugestoes: dict) -> None:
    """Seção 2: QQP — Serviços e Quantitativos."""
    with st.expander("2️⃣  QQP — Serviços e Quantitativos", expanded=True):
        st.caption("Liste os serviços do projeto. O sistema sugere o CPU correspondente automaticamente.")

        # Tabela de serviços
        for idx, svc in enumerate(servicos):
            if _render_servico_row(idx, svc, sugestoes):
                servicos.pop(idx)
                st.rerun()

        col_add, col_suggest = st.columns([1, 1])
        with col_add:
            if st.button("➕ Adicionar serviço", use_container_width=True):
                servicos.append(
                    {"descricao": "", "quantidade": 1.0, "unidade": "m³", "cpu_id": "", "predecessores": []}
                )
                st.rerun()
        with col_suggest:
            if st.button("🔍 Sugerir CPUs automaticamente", use_container_width=True, type="primary"):
                _handle_suggest_cpus(servicos, sugestoes)


def _compute_campos_ok(data_inicio: Any, servicos_validos: list) -> bool:
    return bool(
        st.session_state.get("qqp_nome")
        and st.session_state.get("qqp_localizacao")
        and data_inicio
        and servicos_validos
    )


def _render_servicos_sem_cpu_warning(servicos_sem_cpu: list[dict]) -> None:
    if not servicos_sem_cpu:
        return
    st.warning("Os itens abaixo ainda não têm CPU. Preencha manualmente ou use 'Sugerir CPUs' na seção anterior.")
    for s in servicos_sem_cpu:
        st.markdown(f"- **{s['descricao']}** ({s['quantidade']} {s['unidade']})")


def _build_projeto_payload(
    servicos_validos: list[dict],
    contexto_id: str,
    tipo_obra: str,
    data_inicio: Any,
    data_termino: Any,
    dias_semana: int,
    horas_dia: int,
    objetivo_pool: str,
) -> dict[str, Any]:
    return {
        "nome": st.session_state.qqp_nome,
        "contexto_id": contexto_id,
        "tipo_obra": tipo_obra,
        "localizacao": st.session_state.qqp_localizacao,
        "data_inicio": str(data_inicio),
        "data_termino": str(data_termino) if data_termino else None,
        "dias_semana": int(dias_semana),
        "horas_dia": int(horas_dia),
        "objetivo_pool": objetivo_pool,
        "servicos": [
            {
                "descricao": s["descricao"],
                "quantidade": float(s["quantidade"]),
                "unidade": s["unidade"],
                "cpu_id": s["cpu_id"],
                "predecessores": s.get("predecessores", []),
            }
            for s in servicos_validos
        ],
    }


def _render_resultado_criacao(resultado: dict | None) -> None:
    if not resultado:
        return
    st_status = resultado.get("status")
    if st_status == "criado":
        st.success(f"✅ Projeto criado: **{resultado['project_id']}** (versão {resultado['version']})")
        st.markdown(f"> {resultado.get('nota', '')}")
        if st.button("Ir para o projeto"):
            # Navigate to project page
            st.session_state.selected_project = {"id": resultado["project_id"]}
            st.rerun()
    elif st_status == "pendente_mapeamento":
        st.warning("Ainda há serviços sem CPU — não foi possível criar o projeto.")
    elif st_status in ("erro", "erro_escopo"):
        erros = resultado.get("erros") or [resultado.get("erro", "Erro desconhecido")]
        st.error("❌ Erro ao criar projeto:\n" + "\n".join(f"- {e}" for e in erros))


def _split_servicos(servicos: list[dict]) -> tuple[list[dict], list[dict]]:
    servicos_validos = [s for s in servicos if s.get("descricao") and s.get("cpu_id")]
    servicos_sem_cpu = [s for s in servicos if s.get("descricao") and not s.get("cpu_id")]
    return servicos_validos, servicos_sem_cpu


def _render_secao_revisao_metrics(
    servicos: list[dict], servicos_validos: list[dict], servicos_sem_cpu: list[dict]
) -> None:
    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Total de serviços", len([s for s in servicos if s.get("descricao")]))
    col_b.metric("Com CPU ✅", len(servicos_validos))
    col_c.metric("Sem CPU ⚠️", len(servicos_sem_cpu))


def _render_secao_revisao(
    servicos: list[dict],
    contexto_id: str,
    tipo_obra: str,
    data_inicio: Any,
    data_termino: Any,
    dias_semana: int,
    horas_dia: int,
    objetivo_pool: str,
) -> None:
    """Seção 3: Revisão e Criação."""
    with st.expander("3️⃣  Revisão e Criação", expanded=True):
        servicos_validos, servicos_sem_cpu = _split_servicos(servicos)
        _render_secao_revisao_metrics(servicos, servicos_validos, servicos_sem_cpu)
        _render_servicos_sem_cpu_warning(servicos_sem_cpu)

        campos_ok = _compute_campos_ok(data_inicio, servicos_validos)
        criar_disabled = not campos_ok or bool(servicos_sem_cpu)

        if criar_disabled and not campos_ok:
            st.info("Preencha nome, localização, data de início e pelo menos um serviço com CPU.")

        if st.button(
            "🚀 Criar Projeto",
            disabled=criar_disabled,
            type="primary",
            use_container_width=True,
        ):
            payload = _build_projeto_payload(
                servicos_validos,
                contexto_id,
                tipo_obra,
                data_inicio,
                data_termino,
                dias_semana,
                horas_dia,
                objetivo_pool,
            )
            with st.spinner("Criando projeto e executando skill de escopo..."):
                resultado = _criar_projeto(payload)
            st.session_state.qqp_resultado = resultado

        _render_resultado_criacao(st.session_state.qqp_resultado)


def render_formulario_qqp_page() -> None:
    """Página principal do formulário QQP/EAP."""
    _init_state()

    st.header("📋 Novo Projeto — Formulário QQP")
    st.caption("Crie um projeto a partir de uma lista de serviços. O sistema mapeia automaticamente os CPUs.")

    contexto_id, tipo_obra, data_inicio, data_termino, dias_semana, horas_dia, objetivo_pool = (
        _render_secao_identificacao()
    )

    servicos: list[dict] = st.session_state.qqp_servicos
    sugestoes: dict = st.session_state.qqp_sugestoes
    _render_secao_qqp(servicos, sugestoes)

    _render_secao_revisao(
        servicos, contexto_id, tipo_obra, data_inicio, data_termino, dias_semana, horas_dia, objetivo_pool
    )
