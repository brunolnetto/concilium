"""Motor de comparação e merge entre duas fontes de entidades de catálogo (issue #134).

Extraído de `scripts/benchmark/merge_rfi.py`, onde a lógica vivia acoplada à leitura da
planilha `PLANILHA PADRÃO RFI.xlsm`. A lógica de matching/scoring sempre foi agnóstica de
origem — opera sobre `list[dict]` quaisquer, sem saber se vieram de uma planilha ou de
outro catálogo. Este módulo isola essa lógica genérica; `merge_rfi.py` continua sendo o
adaptador que sabe ler o formato específico da planilha RFI e agora importa o motor daqui.

Terminologia (como um JOIN entre duas listas `base` e `origem`, por `id_key`):
    LEFT_ONLY   : só na `base`     → mantém sem alteração
    RIGHT_ONLY  : só na `origem`   → candidato a inclusão na base
    INNER_HIGH  : match confiante (score >= THRESHOLD_HIGH) → atualiza dados na base
    INNER_LOW   : match incerto  (THRESHOLD_LOW <= score < THRESHOLD_HIGH) → revisão manual

Heurística de matching (`_match_score`):
    1. Código direto              → score 1.0
    2. Overlap de tokens          → score 0.0-1.0 (após normalização ASCII)
    3. Boost +0.10 se mesma unidade E preço dentro de ±30%
    Limiar HIGH >= 0.85 / LOW 0.50-0.85 / NO_MATCH < 0.50
"""

from __future__ import annotations

import re
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# ── Tipos de entidade suportados por `catalog compare` / `catalog merge` ──────
TIPOS_VALIDOS = ("insumos", "producoes", "cpus")
ID_KEYS = {"insumos": "codigo", "producoes": "id", "cpus": "codigo"}

# ── Constantes de matching ────────────────────────────────────────────────────
THRESHOLD_HIGH = 0.85
THRESHOLD_LOW = 0.50
PRICE_TOLERANCE = 0.30  # ±30%
CODE_COLLISION_DESC_MIN = 0.28  # código igual mas desc muito divergente → INNER_LOW

# ── Normalização de unidades ──────────────────────────────────────────────────
# Mapeia variantes gráficas para forma canônica ASCII
_UNIT_CANON: dict[str, str] = {
    "m²": "m2", "m³": "m3",
    "M²": "m2", "M³": "m3",
    "M2": "m2", "M3": "m3",
    "m2": "m2", "m3": "m3",
    "UND": "un", "und": "un", "UN": "un", "Und": "un",
    "KG": "kg", "Kg": "kg",
    "TON": "t", "Ton": "t",
    "H": "h", "Hr": "h",
    "L": "l", "Lt": "l",
}


def _norm_unit(u: str | None) -> str:
    if not u:
        return ""
    s = u.strip()
    # Substitui caracteres superscript unicode → ASCII equivalente
    s = s.replace("²", "2").replace("³", "3")  # ² → 2, ³ → 3
    return _UNIT_CANON.get(s, s.lower())


# ── Normalização de texto ─────────────────────────────────────────────────────
_STOP = {"de", "do", "da", "dos", "das", "e", "a", "o", "em", "com", "para", "por"}

# Abreviações técnicas de construção → forma expandida
# Permite que "Esc/carg/transp" bata com "Escavação, carga e transporte"
_ABBREV = {
    "esc": "escavacao",
    "carg": "carga",
    "transp": "transporte",
    "compac": "compactacao",
    "compact": "compactacao",
    "regul": "regularizacao",
    "subl": "subleito",
    "sublet": "subleito",
    "sub": "subleito",
    "reg": "regularizacao",
    "bgtc": "brita graduada tratada cimento",
    "bgsc": "brita graduada sem cimento",
    "cbuq": "concreto betuminoso usinado quente",
    "pn": "proctor normal",
    "pi": "proctor intermediario",
    "dmt": "distancia media transporte",
    "dn": "diametro nominal",
    "pba": "pba",
    "cat": "categoria",
}


def _expand_abbrev_token(tok: str) -> set[str]:
    """Expande um token que pode ser abreviação para seu conjunto de palavras."""
    expansion = _ABBREV.get(tok, tok)
    if expansion == tok:
        return {tok}
    # Expansão multi-palavra: divide e filtra cada palavra individualmente
    result = set()
    for word in expansion.split():
        if word not in _STOP and len(word) > 1:
            result.add(word)
    return result


def _normalize(text: str) -> set[str]:
    """Converte texto em conjunto de tokens ASCII normalizados com expansão de abreviações."""
    t = unicodedata.normalize("NFD", str(text).lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")  # remove acentos
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    tokens = {w for w in t.split() if w not in _STOP and len(w) > 1}
    # Expande abreviações: substitui token abreviado pelos tokens expandidos (multi-palavra)
    expanded: set[str] = set()
    for tok in tokens:
        expanded.update(_expand_abbrev_token(tok))
    return expanded


def _similarity(a: str, b: str) -> float:
    """Jaccard similarity entre tokens normalizados."""
    ta, tb = _normalize(a), _normalize(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _check_tipo_mismatch(origem: dict, destino: dict) -> bool:
    """Retorna True se tipos são incompatíveis (void match)."""
    tipo_origem = origem.get("tipo")
    tipo_destino = destino.get("tipo")
    return bool(tipo_origem and tipo_destino and tipo_origem != tipo_destino)


def _boost_price_match(score: float, origem: dict, destino: dict) -> float:
    """Aplica boost +0.10 se unidade e preço compatíveis (dentro de ±30%)."""
    u_origem = _norm_unit(origem.get("unidade"))
    u_destino = _norm_unit(destino.get("unidade"))
    if not u_origem or u_origem != u_destino:
        return score

    p_origem = origem.get("preco_unitario") or 0
    p_destino = destino.get("preco_unitario") or 0
    if p_destino > 0 and abs(p_origem - p_destino) / p_destino <= PRICE_TOLERANCE:
        return min(1.0, score + 0.10)
    return score


def _match_score(origem: dict, destino: dict) -> float:
    """Score de matching entre uma entidade de origem e uma de destino (base)."""
    # 0. Tipos incompatíveis → sem match (evita cross-type MATERIAL vs TERCEIRIZADO, etc.)
    if _check_tipo_mismatch(origem, destino):
        return 0.0

    desc_sim = _similarity(origem.get("descricao", ""), destino.get("descricao", ""))

    # 1. Código direto (usa codigo com fallback para id — producoes podem ter só id)
    origem_code = origem.get("codigo") or origem.get("id", "")
    destino_code = destino.get("codigo") or destino.get("id", "")
    if origem_code and origem_code == destino_code:
        # Protege contra code collision: código igual mas conteúdo divergente
        if desc_sim < CODE_COLLISION_DESC_MIN:
            return 0.70  # força INNER_LOW para revisão manual
        return 1.0

    # 2. Similaridade de descrição
    score = desc_sim

    # 3. Boost por unidade + preço (usa unidades normalizadas)
    score = _boost_price_match(score, origem, destino)

    return round(score, 4)


def _categorize(score: float, origem: dict, destino: dict | None) -> str:
    if destino is None:
        return "RIGHT_ONLY"
    if score >= THRESHOLD_HIGH:
        return "INNER_HIGH"
    if score >= THRESHOLD_LOW:
        return "INNER_LOW"
    return "NO_MATCH"  # tratar como RIGHT_ONLY


def _dpf_check_unidade(v_base: Any, v_origem: Any) -> bool:
    """Retorna True se unidades são iguais após normalização (false positive)."""
    return _norm_unit(str(v_base or "")) == _norm_unit(str(v_origem or ""))


def _dpf_check_descricao(v_base: Any, v_origem: Any) -> bool:
    """Retorna True se descrições são iguais/subset após normalização (false positive)."""
    t_base = _normalize(str(v_base or ""))
    t_origem = _normalize(str(v_origem or ""))
    if t_base == t_origem:
        return True  # idênticas após normalização
    # origem é subconjunto da base: base é mais completa → manter base
    if t_origem and t_origem.issubset(t_base):
        return True
    return False


def _dpf_build_entry(v_base: Any, v_origem: Any, field: str) -> dict[str, Any]:
    """Constrói delta_entry com delta_pct opcional para preco_unitario."""
    delta_entry: dict[str, Any] = {"catalog": v_base, "rfi": v_origem}
    if field == "preco_unitario" and v_base and v_origem:
        try:
            pct = (float(v_origem) - float(v_base)) / float(v_base) * 100
            delta_entry["delta_pct"] = round(pct, 2)
        except (TypeError, ZeroDivisionError):
            pass
    return delta_entry


def _delta_process_field(field: str, v_base: Any, v_origem: Any) -> dict[str, Any] | None:
    """Processa um campo para detectar diferenças relevantes. Retorna delta_entry ou None se igual."""
    if v_origem is None:
        return None

    # Normaliza unidades antes de comparar (m³ == m3, etc.)
    if field == "unidade":
        if _dpf_check_unidade(v_base, v_origem):
            return None  # mesma unidade, variação gráfica apenas

    # Normaliza descrições
    if field == "descricao":
        if _dpf_check_descricao(v_base, v_origem):
            return None  # idênticas ou subset após normalização

    if v_base != v_origem:
        return _dpf_build_entry(v_base, v_origem, field)
    return None


def _delta(base: dict, origem: dict) -> dict:
    """Computa diferenças relevantes entre a entidade da base e a de origem (ignora variações gráficas)."""
    d: dict = {}
    for field in ("preco_unitario", "descricao", "unidade", "fonte_preco"):
        v_base = base.get(field)
        v_origem = origem.get(field)
        delta_entry = _delta_process_field(field, v_base, v_origem)
        if delta_entry:
            d[field] = delta_entry
    return d


class RelatorioComparacao:
    """Relatório de comparação entre duas listas de entidades (`base` e `origem`), tipo JOIN.

    LEFT_ONLY  : entidades presentes só na `base`   (destino) — mantidas sem alteração.
    RIGHT_ONLY : entidades presentes só na `origem` (comparação) — candidatas a inclusão.
    INNER_HIGH : match confiante entre uma entidade da base e uma da origem (score alto).
    INNER_LOW  : match incerto entre uma entidade da base e uma da origem (score médio).
    """

    def __init__(self) -> None:
        self.inner_high: list[dict] = []
        self.inner_low: list[dict] = []
        self.right_only: list[dict] = []
        self.left_only: list[dict] = []


def _find_best_match(item_origem: dict, base: list[dict]) -> tuple[float, dict | None]:
    """Encontra o melhor match de item_origem na base, retornando (best_score, best_base)."""
    best_score = 0.0
    best_base: dict | None = None
    for item_base in base:
        s = _match_score(item_origem, item_base)
        if s > best_score:
            best_score = s
            best_base = item_base
    return best_score, best_base


def _ce_add_categorized_item(
    report: RelatorioComparacao,
    category: str,
    best_score: float,
    item_origem: dict,
    best_base: dict | None,
) -> None:
    """Adiciona item ao relatório na categoria apropriada."""
    if category == "RIGHT_ONLY" or category == "NO_MATCH":
        report.right_only.append({"rfi": item_origem, "score": best_score})
    elif category == "INNER_HIGH":
        assert best_base is not None
        delta = _delta(best_base, item_origem)
        report.inner_high.append({
            "catalog": best_base, "rfi": item_origem,
            "score": best_score, "delta": delta,
        })
    elif category == "INNER_LOW":
        report.inner_low.append({
            "catalog": best_base, "rfi": item_origem,
            "score": best_score,
        })


def _ce_add_left_only(report: RelatorioComparacao, base: list[dict], id_key: str) -> None:
    """Adiciona ao relatório entidades da base que não matcharam com nada na origem (LEFT_ONLY)."""
    matched_base_codes = {e["catalog"].get(id_key, "") for e in report.inner_high}
    matched_base_codes |= {e["catalog"].get(id_key, "") for e in report.inner_low}
    for item_base in base:
        if item_base.get(id_key, "") not in matched_base_codes:
            report.left_only.append({"catalog": item_base})


def comparar_entidades(
    base: list[dict],
    origem: list[dict],
    id_key: str = "codigo",
) -> tuple[RelatorioComparacao, list[dict]]:
    """Compara duas listas de entidades e retorna relatório + lista base inalterada.

    Estratégia INNER_HIGH: entidade da base é candidata a ter seus dados atualizados
    com os da origem se diferentes (ver `aplicar_merge`).
    """
    report = RelatorioComparacao()
    result = list(base)  # começa com tudo da base

    for item_origem in origem:
        best_score, best_base = _find_best_match(item_origem, base)
        category = _categorize(best_score, item_origem, best_base)
        _ce_add_categorized_item(report, category, best_score, item_origem, best_base)

    # LEFT_ONLY: na base mas não matchou com nada na origem
    _ce_add_left_only(report, base, id_key)

    return report, result


def _apply_inner_high_updates(
    result: dict[str, dict],
    relatorio: RelatorioComparacao,
    id_key: str,
) -> None:
    """Atualiza INNER_HIGH: aplica deltas na base onde match foi confiante."""
    for item in relatorio.inner_high:
        base_code = item["catalog"].get(id_key, "")
        if base_code in result and item["delta"]:
            for field, chg in item["delta"].items():
                result[base_code][field] = chg["rfi"]
            result[base_code]["_rfi_updated_at"] = datetime.now(UTC).strftime("%Y-%m-%d")


def _apply_right_only_additions(
    result: dict[str, dict],
    relatorio: RelatorioComparacao,
    id_key: str,
) -> None:
    """Adiciona RIGHT_ONLY: inclui novas entidades da origem na base."""
    for item in relatorio.right_only:
        item_origem = item["rfi"]
        cod = item_origem.get(id_key, "")
        if not cod:
            continue
        # Se o código já existe na base (colisão verdadeira), importa com prefixo RFI-
        if cod in result:
            cod = f"RFI-{cod}"
        clean = {k: v for k, v in item_origem.items() if not k.startswith("_")}
        clean[id_key] = cod
        clean["_rfi_imported_at"] = datetime.now(UTC).strftime("%Y-%m-%d")
        result[cod] = clean


def _apply_inner_low_collisions(
    result: dict[str, dict],
    relatorio: RelatorioComparacao,
    id_key: str,
) -> None:
    """Processa INNER_LOW colisões: código igual mas conteúdo diverge → importa com prefixo RFI-."""
    for item in relatorio.inner_low:
        origem_e = item["rfi"]
        base_e = item["catalog"]
        origem_cod = origem_e.get(id_key, "")
        base_cod = base_e.get(id_key, "")
        if origem_cod == base_cod and origem_cod:
            # True collision: importa origem com novo código prefixado
            new_cod = f"RFI-{origem_cod}"
            if new_cod not in result:
                clean = {k: v for k, v in origem_e.items() if not k.startswith("_")}
                clean[id_key] = new_cod
                clean["_rfi_collision_original_code"] = origem_cod
                clean["_rfi_imported_at"] = datetime.now(UTC).strftime("%Y-%m-%d")
                result[new_cod] = clean


def aplicar_merge(
    base: list[dict],
    origem: list[dict],
    relatorio: RelatorioComparacao,
    id_key: str = "codigo",
    incluir_novos: bool = True,
) -> list[dict]:
    """Aplica o merge: atualiza INNER_HIGH, adiciona RIGHT_ONLY à base.

    `origem` não é lido diretamente aqui — o relatório já carrega as entidades
    de origem relevantes (delta, colisões); o parâmetro existe por simetria com
    `comparar_entidades` e para uso futuro.
    """
    result = {e.get(id_key, ""): dict(e) for e in base}

    # Atualiza INNER_HIGH
    _apply_inner_high_updates(result, relatorio, id_key)

    # Adiciona RIGHT_ONLY
    if incluir_novos:
        _apply_right_only_additions(result, relatorio, id_key)

    # Processa INNER_LOW colisões reais
    _apply_inner_low_collisions(result, relatorio, id_key)

    return list(result.values())


def resolver_catalogo_id(rt: Any, id_ou_contexto: str) -> str:
    """Resolve um contexto_id para o catalogo_id real, quando divergem (ex.: contexto
    "mendeslobo-rfi" -> catálogo "rfi-r02").

    `id_ou_contexto` pode ser diretamente um catalogo_id (a maioria dos casos, onde
    contexto_id == catalogo_id) ou um contexto_id que aponta para outro catálogo — só
    `rt.load_contexto` sabe essa relação. Fallback para `id_ou_contexto` como está quando
    não existe contexto com esse id (ex.: já é um catalogo_id puro, sem contexto próprio).
    """
    try:
        return str(rt.load_contexto(id_ou_contexto).catalogo_id)
    except Exception:
        return id_ou_contexto


def carregar_entidades_catalogo(rt: Any, catalogo_id: str) -> dict[str, list[dict]]:
    """Adaptador de fonte "catálogo": carrega insumos/producoes/cpus via `rt.load_catalogo`.

    Usa a via canônica de carregamento (`rt.load_catalogo`), que já lida com staleness
    e regeneração do `.catalog_bundle.json` — nunca lê esse cache diretamente.
    `catalogo_id` já deve estar resolvido (ver `resolver_catalogo_id`) antes de chegar aqui.
    """
    catalogo = rt.load_catalogo(catalogo_id)
    producoes = catalogo.get("producoes") or catalogo.get("produtividades") or []
    return {
        "insumos": catalogo.get("insumos", []) or [],
        "producoes": producoes,
        "cpus": catalogo.get("cpus", []) or [],
    }


# ── Resolução de fonte (compartilhada entre CLI e MCP — issue #134) ───────────
# `merge_rfi.py` sabe ler o formato específico da planilha; aqui só decidimos QUAL
# adaptador usar para uma string de origem, e propagamos erros de forma agnóstica
# de apresentação (RuntimeError com mensagem clara) para cada camada traduzir no
# seu próprio idioma (typer.Exit+rprint na CLI, dict {"erro": ...} no MCP).


def eh_planilha(origem: str) -> bool:
    """True se `origem` for um caminho de arquivo .xlsm/.xlsx existente no disco."""
    path = Path(origem)
    return path.suffix.lower() in (".xlsm", ".xlsx") and path.exists()


def carregar_entidades_planilha(xlsm_path: Path, repo_root: Path) -> dict[str, list[dict]]:
    """Adaptador de fonte "planilha RFI": lê o .xlsm via scripts/benchmark/merge_rfi.py.

    `merge_rfi.py` não é um módulo estaticamente importável (vive fora de `src/`), então
    é carregado via importlib — mesmo mecanismo usado anteriormente pelo antigo merge-rfi.
    """
    import importlib.util

    try:
        import openpyxl
    except ImportError as exc:
        raise RuntimeError("openpyxl não encontrado. Execute: uv add openpyxl") from exc

    merge_script = repo_root / "scripts" / "benchmark" / "merge_rfi.py"
    if not merge_script.exists():
        raise RuntimeError(f"Script não encontrado: {merge_script}")

    spec = importlib.util.spec_from_file_location("merge_rfi", merge_script)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Não foi possível carregar {merge_script}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    wb = openpyxl.load_workbook(xlsm_path, data_only=True, keep_vba=False)
    try:
        extraido = mod.extract_rfi(wb)
    finally:
        wb.close()
    extraido.setdefault("cpus", [])  # planilha RFI nunca modela CPUs
    return extraido


def resolver_fonte_entidades(origem: str, rt: Any, repo_root: Path) -> dict[str, list[dict]]:
    """Resolve `origem` para {"insumos": [...], "producoes": [...], "cpus": [...]}.

    - Planilha (.xlsm/.xlsx existente no disco) -> `carregar_entidades_planilha`.
    - Caso contrário -> catálogo (contexto_id ou catalogo_id, resolvidos via
      `resolver_catalogo_id`) -> `carregar_entidades_catalogo`.
    """
    if eh_planilha(origem):
        return carregar_entidades_planilha(Path(origem), repo_root)
    return carregar_entidades_catalogo(rt, resolver_catalogo_id(rt, origem))


def resolver_tipos(tipo: str) -> list[str]:
    """Expande `tipo` (insumos|producoes|cpus|todos) para a lista de tipos a processar.

    Levanta ValueError com mensagem clara se `tipo` não for reconhecido.
    """
    if tipo == "todos":
        return list(TIPOS_VALIDOS)
    if tipo not in TIPOS_VALIDOS:
        raise ValueError(f"Tipo inválido: '{tipo}'. Use: insumos | producoes | cpus | todos")
    return [tipo]


def gerar_relatorios(
    base: dict[str, list[dict]], origem: dict[str, list[dict]], tipos: list[str]
) -> dict[str, RelatorioComparacao]:
    """Gera um `RelatorioComparacao` por tipo, usando o `id_key` correto de cada um."""
    return {t: comparar_entidades(base.get(t, []), origem.get(t, []), id_key=ID_KEYS[t])[0] for t in tipos}
