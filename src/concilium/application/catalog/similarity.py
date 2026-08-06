"""Similaridade determinística de insumos de catálogo (ADR-179).

Motivação: `_pc_mo_duplicatas` (`_plausibility_checks.py`) e `_build_dup_map`
(`cure_plausibility.py`) só detectam duplicata por igualdade EXATA de
(descrição normalizada, preço) — perdem o caso real onde o mesmo cargo é
importado duas vezes com tratamentos de encargos diferentes (ex.: `P0058`
"Sala Técnica" R$24.720/mês com encargos embutidos vs. `MO-SALA-TEC`,
R$12.000/mês, salário-base ADR-009-normalizado — mesma pessoa/função, preços
diferentes por um fator ≈ α de encargos, nunca capturado pelo match exato).

Este módulo generaliza para um score determinístico (sem ML/embeddings, sem
aleatoriedade) combinando:
- similaridade de descrição: Dice ponderado por IDF sobre tokens de conteúdo
  (stopwords removidas). O peso IDF é o que torna isso viável em mão de obra:
  validado contra o catálogo `mendeslobo` real, Dice sem peso classificava
  "Encarregado de Frente" (R$7.500) e "Encarregado de Obras" (R$3.737) como
  similares só por compartilharem a palavra genérica "Encarregado" — IDF pesa
  essa palavra quase a zero (aparece em ~10 descrições) e a palavra específica
  ("Frente"/"Obras", cada uma única) domina o score.
- similaridade de preço: tolerância direta OU compatível com a faixa de α de
  encargos — a segunda hipótese só entra se a descrição já é um bom match
  (`SIMILARIDADE_DESC_MIN_HIPOTESE_ENCARGOS`), senão qualquer par de salários
  cuja razão caia nos [1.0, 2.5] típicos (a maioria dos pares em uma folha de
  pagamento real) gera ruído sem relação com duplicata de cadastro.
- concordância de categoria.

Cada score carrega o breakdown completo para auditoria manual.

Nível 2 (produção) e Nível 3 (CPU) — ver `producao_similarity`/`cpu_similarity`
mais abaixo — comparam composições agregadas (Jaccard de recursos canônicos +
cosseno de quantidade + proximidade de valor_horario), tanto dentro de um
catálogo (dedup — "enxugar") quanto entre dois catálogos (achar equivalentes
reais para herdar dado, ex.: `grafo_sinergia` do rfi-r02 pra CPUs sem dado do
mendeslobo — nunca inventar número, só copiar de um par confirmado).
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field

from concilium.domain.constants import ALPHA_CLT_TIPICO, ALPHA_MAX_ENCARGOS, ALPHA_MIN_ENCARGOS
from concilium.domain.constants import SIMILARIDADE_CPU_DUPLICATA_MIN as _CPU_DUPLICATA_MIN
from concilium.domain.constants import SIMILARIDADE_CPU_REVISAR_MIN as _CPU_REVISAR_MIN
from concilium.domain.constants import SIMILARIDADE_DESC_MIN_HIPOTESE_ENCARGOS as _DESC_MIN_ENCARGOS
from concilium.domain.constants import SIMILARIDADE_DUPLICATA_MIN as _DUPLICATA_MIN
from concilium.domain.constants import SIMILARIDADE_PESO_CATEGORIA as _PESO_CATEGORIA
from concilium.domain.constants import SIMILARIDADE_PESO_DESC_CPU as _PESO_DESC_CPU
from concilium.domain.constants import SIMILARIDADE_PESO_DESCRICAO as _PESO_DESCRICAO
from concilium.domain.constants import SIMILARIDADE_PESO_PRECO as _PESO_PRECO
from concilium.domain.constants import SIMILARIDADE_PESO_QUANTIDADE_RECURSOS as _PESO_QTY
from concilium.domain.constants import SIMILARIDADE_PESO_RECEITA_RECURSOS as _PESO_RECIPE
from concilium.domain.constants import SIMILARIDADE_PESO_VALOR_HORARIO as _PESO_VH
from concilium.domain.constants import SIMILARIDADE_REVISAR_MIN as _REVISAR_MIN
from concilium.domain.constants import SIMILARIDADE_TOL_PRECO_DIRETO as _TOL_PRECO_DIRETO
from concilium.domain.constants import SIMILARIDADE_TOL_VALOR_HORARIO as _TOL_VH

Idf = dict[str, float]

# Stopwords de descrição de cargo/insumo em pt-BR — preposições/artigos que inflam
# a similaridade de tokens sem carregar significado (ex.: "Operador DE Trator DE
# Esteiras" vs "Operador DE Trator DE Pneus" — "de" não deve contar como overlap).
# "diurno"/"noturno" entram pelo mesmo motivo: são metadado de turno (convenção
# SV-P00xx-D/N, "(Diurno, 12×36)"), não descrevem a função/equipamento — achado
# real ao validar: sem isso, "Operador de Motoniveladora (Diurno, 12×36)" e
# "Operador de Escavadeira (Diurno, 12×36)" (equipamentos DIFERENTES) pontuavam
# desc_sim=0,8 só por compartilharem "diurno"+os dígitos do turno.
_STOPWORDS = frozenset(
    {"de", "da", "do", "das", "dos", "e", "a", "o", "as", "os", "em", "com", "para", "no", "na", "diurno", "noturno"}
)

# Padrão de turno "12×36" (dígito, SINAL DE MULTIPLICAÇÃO UNICODE ×, dígito) — só
# esse caractere específico, nunca a letra ASCII "X" usada em dimensão de CPU
# ("2,00 X 2,00 M"). Removido como unidade ANTES da tokenização geral — achado
# real ao validar Nível 2/3 (produção/CPU): descartar todo token puramente
# numérico (fix anterior, pensado só pra turno de MAO_OBRA) também zerava as
# dimensões de CPUs de drenagem ("2,00 X 2,00" e "3,00 X 2,00" ficavam
# idênticas), quase fundindo CPUs de tamanho físico diferente.
_TURNO_PATTERN = re.compile(r"\d+\s*×\s*\d+")


@dataclass
class SimilarityScore:
    codigo_a: str
    codigo_b: str
    score: float
    desc_sim: float
    price_sim: float
    categoria_sim: float
    classificacao: str | None  # "duplicata_provavel" | "revisar" | None
    detalhe: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "codigo_a": self.codigo_a,
            "codigo_b": self.codigo_b,
            "score": round(self.score, 4),
            "desc_sim": round(self.desc_sim, 4),
            "price_sim": round(self.price_sim, 4),
            "categoria_sim": round(self.categoria_sim, 4),
            "classificacao": self.classificacao,
            "detalhe": self.detalhe,
        }


def _tokens_de_conteudo(descricao: str) -> frozenset[str]:
    """Normaliza (remove acento, minúsculo) e tokeniza, descartando stopwords e
    o padrão de turno "12×36" (removido como unidade via `_TURNO_PATTERN`, não
    por descartar todo dígito — dígitos isolados podem ser dimensão real de CPU,
    ex. "2,00" em "CORPO BSCC 2,00 X 2,00 M"). Números genéricos que sobrarem
    (ex. "00" repetido em toda descrição decimal) são naturalmente descontados
    pelo IDF do corpus (mesma lógica que já desconta "operador"/"encarregado"),
    não precisam de stopword explícita."""
    t = unicodedata.normalize("NFD", str(descricao or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = _TURNO_PATTERN.sub(" ", t)
    tokens = t.replace("(", " ").replace(")", " ").replace(",", " ").replace("×", " ").split()
    return frozenset(tok for tok in tokens if tok not in _STOPWORDS)


def build_idf(descricoes: list[str]) -> Idf:
    """IDF suavizado (mesma fórmula de `TfidfVectorizer(smooth_idf=True)`):
    `idf(t) = ln((1+N)/(1+df(t))) + 1`. Sempre > 0, decresce com a frequência do
    token no corpus — palavra em toda descrição (ex.: "operador") vale pouco,
    palavra rara (ex.: "valetadeira") vale muito. Determinístico, só estatística
    de corpus, sem aleatoriedade nem aprendizado."""
    n = len(descricoes)
    if n == 0:
        return {}
    df: dict[str, int] = {}
    for desc in descricoes:
        for tok in _tokens_de_conteudo(desc):
            df[tok] = df.get(tok, 0) + 1
    return {tok: math.log((1 + n) / (1 + freq)) + 1.0 for tok, freq in df.items()}


def _weighted_dice(a: frozenset[str], b: frozenset[str], idf: Idf | None) -> float:
    """Dice ponderado: `2·Σ_{t∈A∩B} w(t) / (Σ_{t∈A} w(t) + Σ_{t∈B} w(t))`. Sem `idf`
    (ou token ausente do corpus usado para construí-lo), peso cai para 1.0 —
    equivalente ao Dice não-ponderado."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    w = (lambda tok: idf.get(tok, 1.0)) if idf else (lambda _tok: 1.0)
    inter_w = sum(w(t) for t in a & b)
    total_w = sum(w(t) for t in a) + sum(w(t) for t in b)
    return 2 * inter_w / total_w if total_w > 0 else 0.0


def _desc_sim(a: dict, b: dict, idf: Idf | None = None) -> float:
    return _weighted_dice(_tokens_de_conteudo(a.get("descricao", "")), _tokens_de_conteudo(b.get("descricao", "")), idf)


def _price_sim_direto(pa: float, pb: float) -> float:
    """Preços "diretamente" equivalentes (mesma base, diferença pequena — ruído de
    import/arredondamento). Tolerância SIMILARIDADE_TOL_PRECO_DIRETO (15%)."""
    if pa <= 0 or pb <= 0:
        return 0.0
    rel_diff = abs(pa - pb) / max(pa, pb)
    return max(0.0, 1.0 - rel_diff / _TOL_PRECO_DIRETO)


def _price_sim_encargos(pa: float, pb: float) -> float:
    """Preços compatíveis com o MESMO cargo em bases diferentes: um lado já inclui
    encargos (α), o outro é salário-base — a razão entre os dois deve cair na faixa
    plausível de α (ALPHA_MIN_ENCARGOS..ALPHA_MAX_ENCARGOS). Score decai conforme a
    razão se afasta do α "típico" CLT (ALPHA_CLT_TIPICO), dentro da faixa."""
    if pa <= 0 or pb <= 0:
        return 0.0
    ratio = max(pa, pb) / min(pa, pb)
    if not (ALPHA_MIN_ENCARGOS <= ratio <= ALPHA_MAX_ENCARGOS):
        return 0.0
    largura_faixa = ALPHA_MAX_ENCARGOS - ALPHA_MIN_ENCARGOS
    return max(0.0, 1.0 - abs(ratio - ALPHA_CLT_TIPICO) / largura_faixa)


def _price_sim(a: dict, b: dict, desc_sim: float) -> float:
    pa = float(a.get("preco_unitario") or 0)
    pb = float(b.get("preco_unitario") or 0)
    direto = _price_sim_direto(pa, pb)
    tipo = a.get("tipo") or b.get("tipo")
    unidade_a = (a.get("unidade") or "mes").strip().lower()
    unidade_b = (b.get("unidade") or "mes").strip().lower()
    ambos_mensais = unidade_a not in ("h", "hr") and unidade_b not in ("h", "hr")
    if tipo != "MAO_OBRA" or desc_sim < _DESC_MIN_ENCARGOS or not ambos_mensais:
        # Hipótese de encargos só faz sentido para mão de obra MENSAL (salário-base
        # vs. taxa com encargos embutidos), e só quando a descrição já corrobora —
        # senão qualquer par de salários "normais" cai na faixa de α por coincidência
        # (a faixa cobre boa parte de uma folha real). unidade="h" já é taxa
        # all-in por convenção (AGIS/SV) — não existe "hora sem encargos" no
        # catálogo para essa hipótese resgatar; achado real: AGIS-FN-MOTOR-BASC
        # (R$38,1/h) x SV-P0032-D (R$18,48/h) caía na faixa só por coincidência de
        # razão, mas são duas fontes de preço distintas (terceirizado AGIS x tabela
        # interna Serra Verde por turno), não a mesma pessoa em duas bases.
        return direto
    return max(direto, _price_sim_encargos(pa, pb))


def _categoria_sim(a: dict, b: dict) -> float:
    ca, cb = a.get("categoria"), b.get("categoria")
    if not ca or not cb:
        return 0.5  # sem informação suficiente — neutro, não penaliza nem bonifica
    return 1.0 if ca == cb else 0.0


def _classificar(score: float) -> str | None:
    if score >= _DUPLICATA_MIN:
        return "duplicata_provavel"
    if score >= _REVISAR_MIN:
        return "revisar"
    return None


def insumo_similarity(a: dict, b: dict, idf: Idf | None = None) -> SimilarityScore:
    """Score determinístico de similaridade entre dois insumos do mesmo `tipo`.

    `idf`: pesos de palavra construídos por `build_idf` sobre o corpus de
    descrições relevante (ex.: todos os insumos MAO_OBRA sendo comparados).
    Omitir cai para Dice não-ponderado — aceitável para comparar só um par
    isolado, mas gera mais falso-positivo em varredura de catálogo real (por
    isso `find_candidate_duplicates` sempre constrói e propaga o IDF).

    Curto-circuito: se `codigo_referencia_externa` de um já lista o código do
    outro, a duplicata já foi declarada em algum momento (import RFI, `cure_
    duplicatas`) — score=1.0 direto, sem precisar recomputar desc/preço.
    """
    cod_a, cod_b = a.get("codigo", ""), b.get("codigo", "")
    ref_a = str(a.get("codigo_referencia_externa") or "")
    ref_b = str(b.get("codigo_referencia_externa") or "")
    if cod_b and cod_b in [x.strip() for x in ref_a.split(",")]:
        return SimilarityScore(
            cod_a,
            cod_b,
            1.0,
            1.0,
            1.0,
            1.0,
            "duplicata_provavel",
            {"motivo": "referencia_externa_declarada"},
        )
    if cod_a and cod_a in [x.strip() for x in ref_b.split(",")]:
        return SimilarityScore(
            cod_a,
            cod_b,
            1.0,
            1.0,
            1.0,
            1.0,
            "duplicata_provavel",
            {"motivo": "referencia_externa_declarada"},
        )

    desc_sim = _desc_sim(a, b, idf)
    price_sim = _price_sim(a, b, desc_sim)
    categoria_sim = _categoria_sim(a, b)
    score = _PESO_DESCRICAO * desc_sim + _PESO_PRECO * price_sim + _PESO_CATEGORIA * categoria_sim
    return SimilarityScore(cod_a, cod_b, score, desc_sim, price_sim, categoria_sim, _classificar(score))


def find_candidate_duplicates(insumos: list[dict]) -> list[SimilarityScore]:
    """Varredura par-a-par com *blocking* por `tipo` (MAO_OBRA/EQUIPAMENTO/MATERIAL
    não são comparados entre si — não faz sentido). Dentro do bloco, O(n²/2) —
    trivial na escala real do catálogo (centenas de itens por tipo). O IDF é
    construído por bloco, sobre as descrições daquele bloco especificamente.

    Retorna só pares com `classificacao` não-nula, ordenados por score decrescente.
    """
    blocos: dict[str, list[dict]] = {}
    for ins in insumos:
        blocos.setdefault(ins.get("tipo", ""), []).append(ins)

    resultado: list[SimilarityScore] = []
    for grupo in blocos.values():
        idf = build_idf([ins.get("descricao", "") for ins in grupo])
        for j in range(1, len(grupo)):
            for i in range(j):
                sc = insumo_similarity(grupo[i], grupo[j], idf)
                if sc.classificacao is not None:
                    resultado.append(sc)
    resultado.sort(key=lambda s: s.score, reverse=True)
    return resultado


# ── Nível 2 (produção) / Nível 3 (CPU) ────────────────────────────────────────


@dataclass
class CompositeSimilarityScore:
    """Score de produção OU CPU — composição agregada, não insumo isolado."""

    codigo_a: str
    codigo_b: str
    score: float
    desc_sim: float
    recipe_sim: float
    qty_sim: float
    vh_sim: float
    classificacao: str | None  # "duplicata_provavel" | "revisar" | None
    detalhe: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "codigo_a": self.codigo_a,
            "codigo_b": self.codigo_b,
            "score": round(self.score, 4),
            "desc_sim": round(self.desc_sim, 4),
            "recipe_sim": round(self.recipe_sim, 4),
            "qty_sim": round(self.qty_sim, 4),
            "vh_sim": round(self.vh_sim, 4),
            "classificacao": self.classificacao,
            "detalhe": self.detalhe,
        }


def _rc_process_spec_items(
    items: list | None,
    id_chave: str,
    qtd_chave: str,
    canon_map: dict[str, str],
) -> dict[str, float]:
    """Processa items de uma spec categoria (funcoes/equipamentos/materiais),
    resolvendo IDs canônicos e acumulando quantidades. Retorna dict parcial
    {recurso_id_canônico: quantidade} para merge posterior."""
    result: dict[str, float] = {}
    for item in items or []:
        rid = item.get(id_chave, "")
        rid = canon_map.get(rid, rid)
        if rid:
            result[rid] = result.get(rid, 0.0) + float(
                item.get(qtd_chave) or (1 if qtd_chave != "consumo_por_hora" else 0)
            )
    return result


def _recursos_canonicos(producao: dict | None, canon_map: dict[str, str] | None) -> dict[str, float]:
    """Multiset {recurso_id_canônico: quantidade} da composição de uma produção
    (funcoes + equipamentos + materiais). `canon_map` resolve códigos duplicados
    pro mesmo recurso ANTES de comparar — sem isso, duas produções com o mesmo
    recurso referenciado por códigos-P diferentes pareceriam usar recursos
    diferentes."""
    if not producao:
        return {}
    canon_map = canon_map or {}
    equipe = producao.get("composicao_padrao_equipe") or producao.get("equipe") or {}
    recursos: dict[str, float] = {}
    specs = [
        ("funcoes", "funcao_id", "num_pessoas"),
        ("equipamentos", "equip_id", "num_unidades"),
        ("materiais", "insumo_id", "consumo_por_hora"),
    ]
    for categoria_chave, id_chave, qtd_chave in specs:
        items = equipe.get(categoria_chave) or []
        categoria_recursos = _rc_process_spec_items(items, id_chave, qtd_chave, canon_map)
        recursos.update(categoria_recursos)
    return recursos


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _cosseno(a: dict[str, float], b: dict[str, float]) -> float:
    chaves = set(a) | set(b)
    if not chaves:
        return 1.0
    va = [a.get(k, 0.0) for k in chaves]
    vb = [b.get(k, 0.0) for k in chaves]
    norma = math.sqrt(sum(x * x for x in va))
    normb = math.sqrt(sum(x * x for x in vb))
    if norma == 0 or normb == 0:
        return 0.0
    return sum(x * y for x, y in zip(va, vb, strict=True)) / (norma * normb)


def _vh_sim(vh_a: float, vh_b: float) -> float:
    """Proximidade de valor_horario — tolerância mais larga que preço de MO
    (SIMILARIDADE_TOL_VALOR_HORARIO, 30%): frotas/fontes/calibração diferentes
    entre catálogos geram mais ruído natural do que uma tabela de salário."""
    if vh_a <= 0 or vh_b <= 0:
        return 0.0
    rel_diff = abs(vh_a - vh_b) / max(vh_a, vh_b)
    return max(0.0, 1.0 - rel_diff / _TOL_VH)


def _classificar_cpu(score: float) -> str | None:
    if score >= _CPU_DUPLICATA_MIN:
        return "duplicata_provavel"
    if score >= _CPU_REVISAR_MIN:
        return "revisar"
    return None


def producao_similarity(
    a: dict, b: dict, canon_map: dict[str, str] | None = None, idf: Idf | None = None
) -> CompositeSimilarityScore:
    """Nível 2 — similaridade entre duas produções pela composição agregada:
    Jaccard do conjunto de recursos canônicos usados + cosseno do vetor de
    quantidade + proximidade de valor_horario + Dice/IDF da descrição."""
    ra = _recursos_canonicos(a, canon_map)
    rb = _recursos_canonicos(b, canon_map)
    recipe_sim = _jaccard(set(ra), set(rb))
    qty_sim = _cosseno(ra, rb)
    vh_sim = _vh_sim(float(a.get("valor_horario") or 0), float(b.get("valor_horario") or 0))
    desc_sim = _desc_sim(a, b, idf)
    score = _PESO_DESC_CPU * desc_sim + _PESO_RECIPE * recipe_sim + _PESO_QTY * qty_sim + _PESO_VH * vh_sim
    cod_a = a.get("id") or a.get("codigo", "")
    cod_b = b.get("id") or b.get("codigo", "")
    return CompositeSimilarityScore(cod_a, cod_b, score, desc_sim, recipe_sim, qty_sim, vh_sim, _classificar_cpu(score))


def cpu_similarity(
    cpu_a: dict,
    cpu_b: dict,
    prod_a: dict | None,
    prod_b: dict | None,
    canon_map: dict[str, str] | None = None,
    idf: Idf | None = None,
) -> CompositeSimilarityScore:
    """Nível 3 — CPU→produção é 1:1 no schema real (producao_id_ref), então
    similaridade de CPU é a de suas produções vinculadas, com a descrição
    vindo do CPU (mais estável entre catálogos que a da produção — costuma
    seguir convenção DNIT/SICRO padronizada) e `unidade` como GATE: m³ vs m²
    não pode ser a mesma atividade, curto-circuita score=0 sem classificar."""
    ua, ub = cpu_a.get("unidade"), cpu_b.get("unidade")
    if ua and ub and ua != ub:
        cod_a, cod_b = cpu_a.get("codigo", ""), cpu_b.get("codigo", "")
        return CompositeSimilarityScore(
            codigo_a=cod_a,
            codigo_b=cod_b,
            score=0.0,
            desc_sim=0.0,
            recipe_sim=0.0,
            qty_sim=0.0,
            vh_sim=0.0,
            classificacao=None,
            detalhe={"motivo": "unidade_incompativel"},
        )

    ra = _recursos_canonicos(prod_a, canon_map)
    rb = _recursos_canonicos(prod_b, canon_map)
    recipe_sim = _jaccard(set(ra), set(rb))
    qty_sim = _cosseno(ra, rb)
    vh_sim = _vh_sim(float((prod_a or {}).get("valor_horario") or 0), float((prod_b or {}).get("valor_horario") or 0))
    desc_sim = _desc_sim(cpu_a, cpu_b, idf)
    score = _PESO_DESC_CPU * desc_sim + _PESO_RECIPE * recipe_sim + _PESO_QTY * qty_sim + _PESO_VH * vh_sim
    cod_a, cod_b = cpu_a.get("codigo", ""), cpu_b.get("codigo", "")
    return CompositeSimilarityScore(cod_a, cod_b, score, desc_sim, recipe_sim, qty_sim, vh_sim, _classificar_cpu(score))


def _prod_por_id(producoes: list[dict]) -> dict[str, dict]:
    return {p.get("id") or p.get("codigo", ""): p for p in producoes}


def find_candidate_cpu_duplicates(
    cpus: list[dict], producoes: list[dict], canon_map: dict[str, str] | None = None
) -> list[CompositeSimilarityScore]:
    """Dedup DENTRO de um catálogo — blocking por `categoria` (TERRAPLENAGEM não
    é comparado com DRENAGEM etc.). `unidade` incompatível é filtrado dentro de
    `cpu_similarity` (gate), não no blocking, porque duas CPUs de mesma
    categoria/unidade-diferente ainda podem valer registrar como "revisar" no
    relatório de auditoria mais amplo — aqui, coerente com find_candidate_
    duplicates, só devolve pares classificados."""
    prod_by_id = _prod_por_id(producoes)
    blocos: dict[str, list[dict]] = {}
    for cpu in cpus:
        blocos.setdefault(cpu.get("categoria", ""), []).append(cpu)

    resultado: list[CompositeSimilarityScore] = []
    for grupo in blocos.values():
        idf = build_idf([c.get("descricao", "") for c in grupo])
        for j in range(1, len(grupo)):
            for i in range(j):
                a, b = grupo[i], grupo[j]
                pa, pb = prod_by_id.get(a.get("producao_id_ref", "")), prod_by_id.get(b.get("producao_id_ref", ""))
                sc = cpu_similarity(a, b, pa, pb, canon_map, idf)
                if sc.classificacao is not None:
                    resultado.append(sc)
    resultado.sort(key=lambda s: s.score, reverse=True)
    return resultado


def find_cross_catalog_cpu_matches(
    cpus_a: list[dict],
    producoes_a: list[dict],
    cpus_b: list[dict],
    producoes_b: list[dict],
    canon_map: dict[str, str] | None = None,
) -> list[CompositeSimilarityScore]:
    """Compara CPUs de DOIS catálogos diferentes (produto cruzado dentro de cada
    bloco de `categoria` compartilhada) — não remove/funde nada, só identifica
    equivalentes reais candidatos a herdar dado (ex.: `grafo_sinergia`) de um
    catálogo pro outro. `canon_map` aqui tende a contribuir pouco pro recipe_sim/
    qty_sim (códigos de insumo raramente coincidem entre catálogos sem uma
    dedup de insumo cross-catálogo dedicada, fora de escopo) — desc_sim domina
    por design (peso 0,50), coerente com CPUs seguirem nomenclatura DNIT/SICRO
    padronizada entre fontes."""
    prod_by_id_a, prod_by_id_b = _prod_por_id(producoes_a), _prod_por_id(producoes_b)
    blocos_a: dict[str, list[dict]] = {}
    for cpu in cpus_a:
        blocos_a.setdefault(cpu.get("categoria", ""), []).append(cpu)
    blocos_b: dict[str, list[dict]] = {}
    for cpu in cpus_b:
        blocos_b.setdefault(cpu.get("categoria", ""), []).append(cpu)

    resultado: list[CompositeSimilarityScore] = []
    for categoria, grupo_a in blocos_a.items():
        grupo_b = blocos_b.get(categoria)
        if not grupo_b:
            continue
        idf = build_idf([c.get("descricao", "") for c in grupo_a] + [c.get("descricao", "") for c in grupo_b])
        for a in grupo_a:
            for b in grupo_b:
                pa = prod_by_id_a.get(a.get("producao_id_ref", ""))
                pb = prod_by_id_b.get(b.get("producao_id_ref", ""))
                sc = cpu_similarity(a, b, pa, pb, canon_map, idf)
                if sc.classificacao is not None:
                    resultado.append(sc)
    resultado.sort(key=lambda s: s.score, reverse=True)
    return resultado
