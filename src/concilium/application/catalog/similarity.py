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

Escopo desta primeira fase: Nível 1 (insumo-a-insumo). Níveis 2 (produção) e
3 (CPU) — comparar composições/recursos agregados — ficam propostos na ADR-179
para uma fase seguinte, não implementados aqui.
"""

from __future__ import annotations

import math
import unicodedata
from dataclasses import dataclass, field

from concilium.domain.constants import ALPHA_CLT_TIPICO, ALPHA_MAX_ENCARGOS, ALPHA_MIN_ENCARGOS
from concilium.domain.constants import SIMILARIDADE_DESC_MIN_HIPOTESE_ENCARGOS as _DESC_MIN_ENCARGOS
from concilium.domain.constants import SIMILARIDADE_DUPLICATA_MIN as _DUPLICATA_MIN
from concilium.domain.constants import SIMILARIDADE_PESO_CATEGORIA as _PESO_CATEGORIA
from concilium.domain.constants import SIMILARIDADE_PESO_DESCRICAO as _PESO_DESCRICAO
from concilium.domain.constants import SIMILARIDADE_PESO_PRECO as _PESO_PRECO
from concilium.domain.constants import SIMILARIDADE_REVISAR_MIN as _REVISAR_MIN
from concilium.domain.constants import SIMILARIDADE_TOL_PRECO_DIRETO as _TOL_PRECO_DIRETO

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
    tokens puramente numéricos (padrão de turno "12×36" — dígito isolado não
    descreve função/equipamento neste domínio; se algum dia houver token
    alfanumérico com significado real, ex. "180TH", ele não é puramente
    numérico e não é afetado)."""
    t = unicodedata.normalize("NFD", str(descricao or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    tokens = t.replace("(", " ").replace(")", " ").replace(",", " ").replace("×", " ").split()
    return frozenset(tok for tok in tokens if tok not in _STOPWORDS and not tok.isdigit())


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
        return SimilarityScore(cod_a, cod_b, 1.0, 1.0, 1.0, 1.0, "duplicata_provavel", {"motivo": "referencia_externa_declarada"})
    if cod_a and cod_a in [x.strip() for x in ref_b.split(",")]:
        return SimilarityScore(cod_a, cod_b, 1.0, 1.0, 1.0, 1.0, "duplicata_provavel", {"motivo": "referencia_externa_declarada"})

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
