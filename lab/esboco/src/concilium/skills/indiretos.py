"""Skill 05 — Indiretos.

Dimensiona indiretos da obra por categoria ativa no perfil. Para AGIS:
ADM, TOP, LAB, QSMS, MOB.

Cada categoria tem composição própria (funções + equipamentos + verbas) e custo
proporcional ao prazo total. MOB tem estrutura especial (mobilizações + baixadas).

Para Fase 1A, implementação simplificada:
- ADM/TOP/LAB/QSMS: composição vem de inputs ou usa heurística baseada no porte
- MOB: vem totalmente de inputs (mobilizacoes, baixadas, alimentacao)

Inputs (no dict 'inputs'):
    composicoes_indireto: dict[categoria, dict] — opcional, override por categoria
    dados_mobilizacao: dict — para categoria MOB
    perc_encargos: float — default 0.92
"""

from typing import Any

from concilium.models.canonical import (
    CanonicalModel,
    Indireto,
    Mobilizacao,
    ValidacaoItem,
)
from concilium.skills.escopo import SkillResult


def _meses_entre(inicio, fim) -> int:
    """Conta meses inteiros entre datas (inclusivo)."""
    return (fim.year - inicio.year) * 12 + (fim.month - inicio.month) + 1


def _composicao_default_por_categoria(categoria: str, prazo_meses: int, num_pessoas_direta: int) -> dict:
    """Composição-default por categoria. Heurística pragmática para Fase 1A.

    Estes valores são placeholders razoáveis; o esperado é que o usuário forneça
    composicoes_indireto via inputs com base no histórico real da AGIS.
    """
    if categoria == "ADM":
        return {
            "funcoes": [
                {"funcao_id": "ADM-COORD", "descricao": "Coordenador", "num_pessoas": 1, "custo_mensal_unitario": 12500},
            ],
            "verbas_mensais": [
                {"descricao": "Alojamento", "valor_unitario": 3500, "quantidade": 1, "total_mensal": 3500},
            ],
            "verbas_fixas": [
                {"descricao": "Instalação canteiro", "valor_total": 25000},
            ],
        }
    if categoria == "TOP":
        return {
            "funcoes": [
                {"funcao_id": "TOPO", "descricao": "Topógrafo", "num_pessoas": 1, "custo_mensal_unitario": 9216},
            ],
        }
    if categoria == "LAB":
        return {
            "verbas_mensais": [
                {"descricao": "Ensaios laboratoriais", "valor_unitario": 4000, "quantidade": 1, "total_mensal": 4000},
            ],
        }
    if categoria == "QSMS":
        return {
            "verbas_mensais": [
                {"descricao": "EPIs e treinamentos", "valor_unitario": 3000, "quantidade": 1, "total_mensal": 3000},
            ],
        }
    return {}


def _custo_categoria_padrao(comp: dict, prazo_meses: int) -> float:
    """Calcula custo total = (funcoes + verbas_mensais) × prazo + verbas_fixas."""
    custo_mensal = 0.0
    for f in comp.get("funcoes", []):
        custo_mensal += f["custo_mensal_unitario"] * f.get("num_pessoas", 1)
    for v in comp.get("verbas_mensais", []):
        custo_mensal += v.get("total_mensal", 0)

    custo_total = custo_mensal * prazo_meses
    for vf in comp.get("verbas_fixas", []):
        custo_total += vf.get("valor_total", 0)
    return round(custo_total, 2)


def _custo_mob(dados_mob: dict, num_pessoas_direta: int, prazo_meses: int) -> tuple[float, list[Mobilizacao]]:
    """Calcula custo total de MOB e retorna lista de mobilizações modeladas."""
    custo_total = 0.0
    mobilizacoes: list[Mobilizacao] = []

    for m in dados_mob.get("mobilizacoes", []):
        mob = Mobilizacao(
            descricao=m["descricao"],
            num_unidades=m["num_unidades"],
            origem=m["origem"],
            destino=m["destino"],
            distancia_km=m["distancia_km"],
            custo_km=m["custo_km"],
            custo_total=m["num_unidades"] * m["distancia_km"] * m["custo_km"],
        )
        mobilizacoes.append(mob)
        custo_total += mob.custo_total

    # Alimentação/equipe direta mensal
    custo_pessoa_mes = dados_mob.get("custo_pessoa_mes", 1850)
    custo_total += num_pessoas_direta * custo_pessoa_mes * prazo_meses

    # Baixadas (passagens periódicas)
    for b in dados_mob.get("baixadas", []):
        n_ocorrencias = len(b.get("meses_ocorrencia", []))
        custo_total += b.get("num_pessoas", 0) * b.get("valor_por_pessoa", 0) * n_ocorrencias

    return round(custo_total, 2), mobilizacoes


def run_indiretos(
    canonical_in: CanonicalModel,
    inputs: dict[str, Any],
    perfil: dict[str, Any],
) -> SkillResult:
    """Popula seção 'indiretos' do canônico.

    Pré-condições:
        - equipes_diretas populado (para num_pessoas_direta)
        - projeto.data_inicio/termino para prazo
    """
    validacoes: list[ValidacaoItem] = []

    if not canonical_in.equipes_diretas:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-IND-PRECONDICAO",
                status="AVISO",
                mensagem="equipes_diretas vazia — usando 0 pessoas para cálculo de MOB",
            )
        )

    prazo_meses = _meses_entre(canonical_in.projeto.data_inicio, canonical_in.projeto.data_termino)
    num_pessoas_direta = sum(
        sum(f.num_pessoas for f in eq.funcoes)
        for eq in canonical_in.equipes_diretas
    )

    composicoes_input = inputs.get("composicoes_indireto", {})
    dados_mob = inputs.get("dados_mobilizacao", {})

    indiretos_out: list[Indireto] = []

    for cat in perfil["categorias_indireto"]:
        codigo = cat["codigo"]
        descricao = cat["descricao"]

        if codigo == "MOB":
            custo, mobs = _custo_mob(dados_mob, num_pessoas_direta, prazo_meses)
            indiretos_out.append(
                Indireto(
                    categoria="MOB",
                    descricao=descricao,
                    mobilizacoes=mobs,
                    permanencia_meses=float(prazo_meses),
                    custo_total=custo,
                )
            )
        else:
            comp = composicoes_input.get(codigo) or _composicao_default_por_categoria(
                codigo, prazo_meses, num_pessoas_direta
            )
            custo = _custo_categoria_padrao(comp, prazo_meses)
            indiretos_out.append(
                Indireto(
                    categoria=codigo,  # type: ignore[arg-type]
                    descricao=descricao,
                    funcoes=comp.get("funcoes", []),
                    equipamentos=comp.get("equipamentos", []),
                    verbas_mensais=comp.get("verbas_mensais", []),
                    verbas_fixas=comp.get("verbas_fixas", []),
                    permanencia_meses=float(prazo_meses),
                    custo_total=custo,
                )
            )

    # Validação razão indireto/direto (se faixa estiver definida no perfil)
    razao_alvo = perfil.get("razao_indireto_direto_alvo")
    if razao_alvo and canonical_in.equipes_diretas:
        custo_direto = sum(eq.custo_total for eq in canonical_in.equipes_diretas)
        custo_indireto = sum(i.custo_total for i in indiretos_out)
        if custo_direto > 0:
            razao = custo_indireto / custo_direto
            if not (razao_alvo["min"] <= razao <= razao_alvo["max"]):
                validacoes.append(
                    ValidacaoItem(
                        codigo="VAL-POL-INDIRETO",
                        status="AVISO",
                        mensagem=(
                            f"Razão indireto/direto {razao*100:.1f}% fora da faixa "
                            f"[{razao_alvo['min']*100:.1f}%, {razao_alvo['max']*100:.1f}%]"
                        ),
                    )
                )
            else:
                validacoes.append(ValidacaoItem(codigo="VAL-POL-INDIRETO", status="OK"))

    novo = canonical_in.model_copy(update={"indiretos": indiretos_out})
    return SkillResult(novo, validacoes)
