#!/usr/bin/env python3
"""
Curação do catálogo Concilium — alinha dados aos schemas normalizados.

Uso:
    python scripts/cure_catalog.py --contexto mendeslobo          # dry-run (relatório)
    python scripts/cure_catalog.py --contexto mendeslobo --apply  # aplica mudanças

Ações automáticas:
    - Producao: migra campo legado `equipe` → `composicao_padrao_equipe`
    - Producao: migra `producao_horaria` -> `valor_horario` e remove legado
    - Producao: estrutura `historico_observacoes` (adiciona campos obrigatórios ausentes)
    - Producao: deduplica equipe/composição padrão (funções/equipamentos)
    - Producao: remove `cpu_ids` (redundante com CPU.producao_id_ref)
    - CPU: tenta preencher composicao_itens vazia quando existe insumo candidato inequívoco
    - CPU: remove `fonte_preco` / `data_referencia_preco` (deprecated)
    - Insumo MAO_OBRA: remove `custo_com_encargos` se presente
    - Insumo EQUIPAMENTO: remove `custo_manutencao_hora` / `custo_produtivo_hora` se presentes
    - Qualquer entidade: remove `custo_hora_total` de decomposicao_equip
    - Insumo: preenche `fonte_preco` ausente com "catalogo_proprio"
    - Producao: preenche `valor_horario` faltante a partir de produção equivalente (PROD-*) quando possível
    - Insumo: normaliza códigos inválidos (ASCII / regex / comprimento) e reescreve referências

Validação final:
    Ao terminar, roda os 4 schemas JSON contra todos os dados e reporta erros residuais.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import unicodedata
import warnings
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

# RefResolver emite deprecation warning no import em jsonschema>=4.18.
warnings.filterwarnings("ignore", category=DeprecationWarning, message=".*RefResolver is deprecated.*")

# Forca UTF-8 no stdout para evitar UnicodeEncodeError no Windows (cp1252)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

try:
    from jsonschema import Draft202012Validator, RefResolver
except ImportError:
    print("Instale jsonschema: uv add jsonschema", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_ROOT = ROOT / "config" / "schemas" / "catalog"


# ── Helpers ──────────────────────────────────────────────────────────────────

def _load_schema(name: str) -> dict:
    return json.loads((SCHEMA_ROOT / name).read_text(encoding="utf-8"))


_SCHEMA_STORE: dict[str, dict] | None = None

def _schema_store() -> dict[str, dict]:
    global _SCHEMA_STORE
    if _SCHEMA_STORE is None:
        _SCHEMA_STORE = {}
        for f in SCHEMA_ROOT.glob("*.schema.json"):
            s = json.loads(f.read_text(encoding="utf-8"))
            if "$id" in s:
                _SCHEMA_STORE[s["$id"]] = s
    return _SCHEMA_STORE

def _make_validator(schema: dict) -> Draft202012Validator:
    base_uri = SCHEMA_ROOT.as_uri() + "/"
    return Draft202012Validator(
        schema,
        resolver=RefResolver(base_uri=base_uri, referrer=schema, store=_schema_store()),
    )


def _validate_all(entities: list[dict], validator: Draft202012Validator, label: str) -> list[str]:
    erros = []
    for ent in entities:
        eid = ent.get("codigo") or ent.get("id") or "<sem-id>"
        for err in validator.iter_errors(ent):
            path = ".".join(str(x) for x in err.absolute_path)
            erros.append(f"{label} {eid}: {path or '<root>'} → {err.message}")
    return erros


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_code(code: str) -> str:
    ascii_code = unicodedata.normalize("NFKD", code).encode("ascii", "ignore").decode("ascii")
    clean = re.sub(r"[^A-Z0-9-]", "-", ascii_code.upper())
    clean = re.sub(r"-+", "-", clean).strip("-")
    if not clean:
        clean = "INSUMO"
    if len(clean) <= 40:
        return clean
    digest = hashlib.sha1(clean.encode("utf-8")).hexdigest()[:6].upper()
    return f"{clean[:33]}-{digest}"[:40]


def _is_valid_insumo_code(code: str) -> bool:
    return bool(re.match(r"^[A-Z0-9-]{3,40}$", code))


def _categoria_custo_from_tipo(tipo: str | None) -> str:
    if tipo == "MAO_OBRA":
        return "MAO_OBRA"
    if tipo == "EQUIPAMENTO":
        return "EQUIPAMENTO"
    if tipo == "TERCEIRIZADO":
        return "MATERIAL"
    return "MATERIAL"


def _team_is_empty(equipe: dict | None) -> bool:
    if not isinstance(equipe, dict):
        return True
    funcoes = equipe.get("funcoes") if isinstance(equipe.get("funcoes"), list) else []
    equipamentos = equipe.get("equipamentos") if isinstance(equipe.get("equipamentos"), list) else []
    return len(funcoes) == 0 and len(equipamentos) == 0


def _infer_tipo_contrato(insumo: dict) -> str:
    codigo = str(insumo.get("codigo") or "").upper()
    descricao = str(insumo.get("descricao") or "").upper()
    if "-PJ" in codigo or " PJ" in descricao:
        return "PJ"
    return "CLT"


def _q(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    pos = (len(ordered) - 1) * p
    low = int(pos)
    high = min(low + 1, len(ordered) - 1)
    frac = pos - low
    return ordered[low] * (1 - frac) + ordered[high] * frac


def _iqr_bounds(values: list[float], *, non_negative: bool = False) -> tuple[float, float] | None:
    if len(values) < 8:
        return None
    q1 = _q(values, 0.25)
    q3 = _q(values, 0.75)
    iqr = q3 - q1
    if iqr <= 0:
        return None
    low = q1 - 1.5 * iqr
    high = q3 + 1.5 * iqr
    if non_negative:
        low = max(0.0, low)
        high = max(0.0, high)
    return low, high


def _robust_bounds(values: list[float], *, non_negative: bool = False) -> tuple[float, float] | None:
    if len(values) < 8:
        return None
    ordered = sorted(values)
    q10 = _q(ordered, 0.10)
    q90 = _q(ordered, 0.90)
    iqr = _iqr_bounds(ordered, non_negative=non_negative)
    if iqr is None:
        low, high = q10, q90
    else:
        low, high = iqr
        low = min(low, q10)
        high = max(high, q90)
    if non_negative:
        low = max(0.0, low)
        high = max(0.0, high)
    return low, high


# ── Ações de curação ─────────────────────────────────────────────────────────

class CurationReport:
    def __init__(self) -> None:
        self.fixed: list[str] = []
        self.manual: list[str] = []
        self.skipped: list[str] = []

    def add_fixed(self, msg: str) -> None:
        self.fixed.append(msg)

    def add_manual(self, msg: str) -> None:
        self.manual.append(msg)

    def add_skipped(self, msg: str) -> None:
        self.skipped.append(msg)


def _dedupe_team_items(items: list[dict], id_key: str, qty_key: str) -> list[dict]:
    by_id: dict[str, dict] = {}
    for raw in items:
        if not isinstance(raw, dict):
            continue
        item_id = raw.get(id_key)
        if not isinstance(item_id, str) or not item_id:
            continue
        qty = raw.get(qty_key)
        try:
            qty_i = int(qty)
        except Exception:
            qty_i = 0
        if qty_i <= 0:
            continue
        if item_id in by_id:
            by_id[item_id][qty_key] = int(by_id[item_id].get(qty_key) or 0) + qty_i
        else:
            clean = dict(raw)
            clean[qty_key] = qty_i
            by_id[item_id] = clean
    return list(by_id.values())


def _normalize_team(equipe: dict) -> dict:
    normalized = dict(equipe)
    funcoes = equipe.get("funcoes") if isinstance(equipe.get("funcoes"), list) else []
    equipamentos = equipe.get("equipamentos") if isinstance(equipe.get("equipamentos"), list) else []
    normalized["funcoes"] = _dedupe_team_items(funcoes, "funcao_id", "num_pessoas")
    normalized["equipamentos"] = _dedupe_team_items(equipamentos, "equip_id", "num_unidades")
    return normalized


def cure_producao(prod: dict, report: CurationReport, apply: bool) -> dict:
    pid = prod.get("id", "<sem-id>")
    changed = dict(prod)

    # Remove campos exclusivos de CPU que contaminaram Producao
    prod_cpu_fields = {"atributos_categoria", "cpu_ids"}
    contaminados = [k for k in prod_cpu_fields if k in changed]
    if contaminados:
        if apply:
            for k in contaminados:
                del changed[k]
        for k in contaminados:
            report.add_fixed(f"PRODUCAO {pid}: removido campo exclusivo de CPU '{k}'")

    # Migra producao_horaria legado -> valor_horario canônico
    if "producao_horaria" in changed:
        if apply:
            if "valor_horario" not in changed and changed.get("producao_horaria") is not None:
                changed["valor_horario"] = changed.get("producao_horaria")
            del changed["producao_horaria"]
        report.add_fixed(f"PRODUCAO {pid}: migrado/removido campo legado producao_horaria")

    # Migra equipe -> composicao_padrao_equipe
    if "equipe" in changed and "composicao_padrao_equipe" not in changed:
        if apply:
            changed["composicao_padrao_equipe"] = changed.pop("equipe")
        report.add_fixed(f"PRODUCAO {pid}: migrado equipe -> composicao_padrao_equipe")

    elif "equipe" in changed and "composicao_padrao_equipe" in changed:
        if apply:
            del changed["equipe"]
        report.add_fixed(f"PRODUCAO {pid}: removido campo legado equipe (composicao_padrao_equipe ja existe)")

    # Normaliza composição padrão para remover duplicidade de funções/equipamentos
    equipe_padrao = changed.get("composicao_padrao_equipe")
    if isinstance(equipe_padrao, dict):
        normalized = _normalize_team(equipe_padrao)
        if normalized != equipe_padrao:
            if apply:
                changed["composicao_padrao_equipe"] = normalized
            report.add_fixed(f"PRODUCAO {pid}: deduplicada composicao_padrao_equipe")

    # Remove cpu_ids (redundante)
    if "cpu_ids" in changed:
        if apply:
            del changed["cpu_ids"]
        report.add_fixed(f"PRODUCAO {pid}: removido cpu_ids (derivável via CPU.producao_id_ref)")

    # Estrutura historico_observacoes
    obs = changed.get("historico_observacoes", [])
    if isinstance(obs, list):
        new_obs = []
        for i, item in enumerate(obs):
            if not isinstance(item, dict):
                report.add_skipped(f"PRODUCAO {pid}: historico_observacoes[{i}] não é objeto — ignorado")
                continue
            missing = [f for f in ("data", "autor", "descricao") if not item.get(f)]
            if missing:
                if apply:
                    fixed_item = dict(item)
                    if not fixed_item.get("data"):
                        fixed_item["data"] = _now_iso()
                    if not fixed_item.get("autor"):
                        fixed_item["autor"] = "cure_catalog"
                    if not fixed_item.get("descricao"):
                        fixed_item["descricao"] = "(migrado sem descrição original)"
                    if not fixed_item.get("tipo"):
                        fixed_item["tipo"] = "migracao"
                    new_obs.append(fixed_item)
                report.add_fixed(f"PRODUCAO {pid}: historico_observacoes[{i}] completado com campos ausentes: {missing}")
            else:
                new_obs.append(item)
        if apply:
            changed["historico_observacoes"] = new_obs

    # Normaliza equipes dentro de variantes (quando existirem)
    variantes = changed.get("variantes")
    if isinstance(variantes, list):
        novas_variantes = []
        touched = False
        for item in variantes:
            if not isinstance(item, dict):
                novas_variantes.append(item)
                continue
            var = dict(item)
            equipe_var = var.get("equipe")
            if isinstance(equipe_var, dict):
                normalized_var = _normalize_team(equipe_var)
                if normalized_var != equipe_var:
                    var["equipe"] = normalized_var
                    touched = True
            novas_variantes.append(var)
        if apply and touched:
            changed["variantes"] = novas_variantes
        if touched:
            report.add_fixed(f"PRODUCAO {pid}: deduplicadas equipes nas variantes")

    return changed if apply else prod


def cure_cpu(cpu: dict, report: CurationReport, apply: bool) -> dict:
    codigo = cpu.get("codigo", "<sem-codigo>")
    changed = dict(cpu)

    # Move dmt_referencia_m do root para atributos_categoria (campo mal posicionado)
    dmt_root_fields = {k: v for k, v in changed.items() if k in ("dmt_referencia_m", "dmt_min_metros", "dmt_max_metros")}
    if dmt_root_fields:
        if apply:
            attrs_cat = dict(changed.get("atributos_categoria") or {})
            for k, v in dmt_root_fields.items():
                attrs_cat[k] = v
                del changed[k]
            changed["atributos_categoria"] = attrs_cat
        for k in dmt_root_fields:
            report.add_fixed(f"CPU {codigo}: movido '{k}' do root para atributos_categoria")

    # Remove campos deprecated do root de CPU
    for campo in ("fonte_preco", "data_referencia_preco"):
        if campo in changed:
            if apply:
                del changed[campo]
            report.add_fixed(f"CPU {codigo}: removido campo deprecated '{campo}'")

    return changed if apply else cpu


_CPU_ONLY_FIELDS = {"atributos_categoria", "cpu_referencia_id", "producao_id_ref", "composicao_itens",
                    "custo_direto_unitario_planilha", "precos_unitarios_sbdi"}


def cure_insumo(ins: dict, report: CurationReport, apply: bool) -> dict:
    codigo = ins.get("codigo", "<sem-codigo>")
    tipo = ins.get("tipo", "")
    changed = dict(ins)

    if not changed.get("fonte_preco"):
        if apply:
            changed["fonte_preco"] = "catalogo_proprio"
        report.add_fixed(f"INSUMO {codigo}: preenchido fonte_preco='catalogo_proprio'")

    # Remove campos exclusivos de CPU que foram copiados para Insumo por engano
    cpu_contaminados = [k for k in _CPU_ONLY_FIELDS if k in changed]
    if cpu_contaminados:
        if apply:
            for k in cpu_contaminados:
                del changed[k]
        for k in cpu_contaminados:
            report.add_fixed(f"INSUMO {codigo}: removido campo exclusivo de CPU '{k}'")

    # Remove campos derivados de MAO_OBRA
    if tipo == "MAO_OBRA":
        attrs = changed.get("atributos_especificos", {})
        if not isinstance(attrs, dict):
            attrs = {}
        # Padroniza regime de contratação para permitir cálculo consistente de encargos.
        regime = attrs.get("tipo_contrato")
        if regime not in {"CLT", "PJ"}:
            inferred = _infer_tipo_contrato(changed)
            if apply:
                attrs["tipo_contrato"] = inferred
            report.add_fixed(f"INSUMO {codigo}: preenchido tipo_contrato='{inferred}'")
        if isinstance(attrs, dict):
            derivados = [k for k in ("custo_com_encargos",) if k in attrs]
            if derivados and apply:
                for k in derivados:
                    del attrs[k]
                changed["atributos_especificos"] = attrs
            for k in derivados:
                report.add_fixed(f"INSUMO {codigo}: removido campo derivado atributos_especificos.{k}")
        if apply:
            changed["atributos_especificos"] = attrs

    # Remove campos derivados de EQUIPAMENTO
    if tipo == "EQUIPAMENTO":
        attrs = changed.get("atributos_especificos", {})
        if isinstance(attrs, dict):
            derivados = [k for k in ("custo_manutencao_hora", "custo_produtivo_hora") if k in attrs]
            if derivados and apply:
                for k in derivados:
                    del attrs[k]
                changed["atributos_especificos"] = attrs
            for k in derivados:
                report.add_fixed(f"INSUMO {codigo}: removido campo derivado atributos_especificos.{k}")
            # Remove custo_hora_total de decomposicao_equip se presente
            decomp = attrs.get("decomposicao_equip")
            if isinstance(decomp, dict) and "custo_hora_total" in decomp:
                if apply:
                    del decomp["custo_hora_total"]
                report.add_fixed(f"INSUMO {codigo}: removido decomposicao_equip.custo_hora_total (derivado da soma)")

    return changed if apply else ins


def _apply_insumo_code_remap(cpus: list[dict], prods: list[dict], remap: dict[str, str]) -> None:
    if not remap:
        return

    def _map_code(value: object) -> object:
        if isinstance(value, str) and value in remap:
            return remap[value]
        return value

    for cpu in cpus:
        itens = cpu.get("composicao_itens")
        if isinstance(itens, list):
            for item in itens:
                if isinstance(item, dict):
                    item["insumo_id"] = _map_code(item.get("insumo_id"))

    for prod in prods:
        equipe = prod.get("composicao_padrao_equipe")
        if isinstance(equipe, dict):
            funcoes = equipe.get("funcoes")
            if isinstance(funcoes, list):
                for f in funcoes:
                    if isinstance(f, dict):
                        f["funcao_id"] = _map_code(f.get("funcao_id"))
            equipamentos = equipe.get("equipamentos")
            if isinstance(equipamentos, list):
                for e in equipamentos:
                    if isinstance(e, dict):
                        e["equip_id"] = _map_code(e.get("equip_id"))

        variantes = prod.get("variantes")
        if isinstance(variantes, list):
            for var in variantes:
                if not isinstance(var, dict):
                    continue
                v_eq = var.get("equipe")
                if not isinstance(v_eq, dict):
                    continue
                v_funcoes = v_eq.get("funcoes")
                if isinstance(v_funcoes, list):
                    for f in v_funcoes:
                        if isinstance(f, dict):
                            f["funcao_id"] = _map_code(f.get("funcao_id"))
                v_equip = v_eq.get("equipamentos")
                if isinstance(v_equip, list):
                    for e in v_equip:
                        if isinstance(e, dict):
                            e["equip_id"] = _map_code(e.get("equip_id"))


def cure_contextual(cpus: list[dict], prods: list[dict], insumos: list[dict], report: CurationReport, apply: bool) -> None:
    # 0) Corrigir equipes vazias em produções CAP por mapeamento explícito de template
    prod_by_id = {p.get("id"): p for p in prods if isinstance(p, dict) and isinstance(p.get("id"), str)}
    cap_team_template_map = {
        "CPU-DREN-BOCA-BDCAP-100-PROD-001": "CPU-DREN-BOCA-BDTC-100-PROD-001",
        "CPU-DREN-BOCA-BSCAP-100-PROD-001": "CPU-DREN-BOCA-BSTC-100-PROD-001",
        "CPU-DREN-BOCA-BTCAP-100-PROD-001": "CPU-DREN-BOCA-BTCC-300X300-PROD-001",
        "CPU-DREN-CORPO-BDCAP-100-PROD-001": "CPU-DREN-CORPO-BDTC-100-PA1-PROD-001",
        "CPU-DREN-CORPO-BSCAP-100-PROD-001": "CPU-DREN-CORPO-BSTC-100-PA1-PROD-001",
        "CPU-DREN-CORPO-BTCAP-100-PROD-001": "CPU-DREN-CORPO-BTCC-100-PROD-001",
    }
    for target_id, source_id in cap_team_template_map.items():
        target = prod_by_id.get(target_id)
        source = prod_by_id.get(source_id)
        if not isinstance(target, dict) or not isinstance(source, dict):
            continue
        target_team = target.get("composicao_padrao_equipe")
        source_team = source.get("composicao_padrao_equipe")
        if not _team_is_empty(target_team) or _team_is_empty(source_team):
            continue
        if apply:
            target["composicao_padrao_equipe"] = json.loads(json.dumps(source_team))
        report.add_fixed(f"PRODUCAO {target_id}: equipe herdada de template {source_id}")

    # 1) Preencher valor_horario faltante via produção equivalente PROD-*
    for prod in prods:
        if not isinstance(prod, dict):
            continue
        pid = prod.get("id")
        if not isinstance(pid, str):
            continue
        if prod.get("valor_horario") is not None:
            continue
        m = re.match(r"^CPU-([A-Z0-9]+)-(.+)-PROD-([0-9]+)$", pid)
        if not m:
            continue
        candidate_id = f"PROD-{m.group(2)}-{m.group(3)}"
        candidate = prod_by_id.get(candidate_id)
        candidate_val = (candidate or {}).get("valor_horario") if isinstance(candidate, dict) else None
        if candidate_val is None:
            continue
        if apply:
            prod["valor_horario"] = candidate_val
        report.add_fixed(f"PRODUCAO {pid}: valor_horario herdado de {candidate_id}")

    # 2) Normalizar códigos de insumo inválidos e propagar remapeamento
    remap: dict[str, str] = {}
    used_codes: set[str] = set()
    for ins in insumos:
        if isinstance(ins, dict) and isinstance(ins.get("codigo"), str):
            used_codes.add(ins["codigo"])

    for ins in insumos:
        if not isinstance(ins, dict):
            continue
        old_code = ins.get("codigo")
        if not isinstance(old_code, str) or _is_valid_insumo_code(old_code):
            continue
        new_code = _normalize_code(old_code)
        if new_code in used_codes and new_code != old_code:
            salt = 1
            base = new_code
            while new_code in used_codes and new_code != old_code:
                suffix = f"-{salt}"
                new_code = (base[: 40 - len(suffix)] + suffix)[:40]
                salt += 1
        remap[old_code] = new_code
        used_codes.add(new_code)
        if apply:
            ins["codigo"] = new_code
        report.add_fixed(f"INSUMO {old_code}: codigo normalizado para {new_code}")

    _apply_insumo_code_remap(cpus, prods, remap)

    # 3) Auto-preencher composicao_itens vazia quando houver insumo candidato inequívoco
    insumo_by_code = {i.get("codigo"): i for i in insumos if isinstance(i, dict) and isinstance(i.get("codigo"), str)}
    prod_by_id = {p.get("id"): p for p in prods if isinstance(p, dict) and isinstance(p.get("id"), str)}
    for cpu in cpus:
        if not isinstance(cpu, dict):
            continue
        codigo = cpu.get("codigo")
        itens = cpu.get("composicao_itens")
        if not isinstance(codigo, str) or not isinstance(itens, list) or itens:
            continue
        candidates = [f"MA-AGIS-{codigo}", f"MA-{codigo}"]
        found = [c for c in candidates if c in insumo_by_code]
        if len(found) != 1:
            # fallback de negócio: sintetiza composição a partir da equipe da produção referenciada
            prod_ref = cpu.get("producao_id_ref")
            prod = prod_by_id.get(prod_ref) if isinstance(prod_ref, str) else None
            equipe = (prod or {}).get("composicao_padrao_equipe") if isinstance(prod, dict) else None
            synthesized: list[dict] = []
            if isinstance(equipe, dict):
                for f in equipe.get("funcoes") if isinstance(equipe.get("funcoes"), list) else []:
                    if not isinstance(f, dict):
                        continue
                    insumo_id = f.get("funcao_id")
                    if not isinstance(insumo_id, str) or insumo_id not in insumo_by_code:
                        continue
                    qtd = f.get("num_pessoas")
                    try:
                        coef = float(qtd)
                    except Exception:
                        coef = 0.0
                    if coef <= 0:
                        continue
                    tipo = (insumo_by_code.get(insumo_id) or {}).get("tipo")
                    synthesized.append(
                        {
                            "insumo_id": insumo_id,
                            "coeficiente": coef,
                            "categoria_custo": _categoria_custo_from_tipo(tipo if isinstance(tipo, str) else None),
                        }
                    )
                for e in equipe.get("equipamentos") if isinstance(equipe.get("equipamentos"), list) else []:
                    if not isinstance(e, dict):
                        continue
                    insumo_id = e.get("equip_id")
                    if not isinstance(insumo_id, str) or insumo_id not in insumo_by_code:
                        continue
                    qtd = e.get("num_unidades")
                    try:
                        coef = float(qtd)
                    except Exception:
                        coef = 0.0
                    if coef <= 0:
                        continue
                    tipo = (insumo_by_code.get(insumo_id) or {}).get("tipo")
                    synthesized.append(
                        {
                            "insumo_id": insumo_id,
                            "coeficiente": coef,
                            "categoria_custo": _categoria_custo_from_tipo(tipo if isinstance(tipo, str) else None),
                        }
                    )
            if synthesized:
                if apply:
                    cpu["composicao_itens"] = synthesized
                report.add_fixed(
                    f"CPU {codigo}: composicao_itens sintetizada a partir da equipe da produção {prod_ref}"
                )
            else:
                report.add_manual(f"CPU {codigo}: composicao_itens vazia sem candidato único de insumo")
                report.add_skipped(
                    f"CPU {codigo}: composicao_itens vazia (permitido no schema; revisar economicamente depois)"
                )
            continue

        insumo_id = found[0]
        tipo = (insumo_by_code.get(insumo_id) or {}).get("tipo")
        novo_item = {
            "insumo_id": insumo_id,
            "coeficiente": 1.0,
            "categoria_custo": _categoria_custo_from_tipo(tipo if isinstance(tipo, str) else None),
        }
        if apply:
            cpu["composicao_itens"] = [novo_item]
        report.add_fixed(f"CPU {codigo}: composicao_itens preenchida automaticamente com {insumo_id}")

    # 4) Corrigir outliers de produtividade para mediana do grupo (categoria/unidade)
    prod_by_id = {p.get("id"): p for p in prods if isinstance(p, dict) and isinstance(p.get("id"), str)}
    rows: list[dict] = []
    for cpu in cpus:
        if not isinstance(cpu, dict):
            continue
        codigo = cpu.get("codigo")
        if not isinstance(codigo, str):
            continue
        categoria = cpu.get("categoria")
        unidade = cpu.get("unidade")
        prod_ref = cpu.get("producao_id_ref")
        if not isinstance(prod_ref, str) or not prod_ref:
            continue
        prod = prod_by_id.get(prod_ref)
        if not isinstance(prod, dict):
            continue
        try:
            valor_horario = float(prod.get("valor_horario"))
        except (TypeError, ValueError):
            continue
        if valor_horario <= 0:
            continue
        rows.append(
            {
                "cpu_codigo": codigo,
                "categoria": str(categoria or "SEM_CATEGORIA"),
                "unidade": str(unidade or "SEM_UNIDADE"),
                "producao_id_ref": prod_ref,
                "valor_horario": valor_horario,
            }
        )

    grouped: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        key = (row["categoria"], row["unidade"])
        grouped.setdefault(key, []).append(row)

    for key, items in grouped.items():
        values = [float(r["valor_horario"]) for r in items if float(r["valor_horario"]) > 0]
        bounds = _robust_bounds(values, non_negative=True)
        if bounds is None:
            continue
        med = float(median(values))
        low, high = bounds

        for item in items:
            current = float(item["valor_horario"])
            if low <= current <= high:
                continue
            if abs(current - med) <= 1e-12:
                continue

            # Evita sobrecorreção: atua apenas em desvios realmente extremos.
            # - baixo extremo: abaixo de 50% do limite inferior
            # - alto extremo: acima de 200% do limite superior
            if low > 0 and current < low:
                if current >= low * 0.5:
                    continue
            elif current > high:
                if current <= high * 2.0:
                    continue
            else:
                continue

            prod_ref = item["producao_id_ref"]
            cpu_codigo = item["cpu_codigo"]
            if apply:
                prod = prod_by_id.get(prod_ref)
                if isinstance(prod, dict):
                    prod["valor_horario"] = med
            report.add_fixed(
                "PRODUCAO "
                f"{prod_ref}: valor_horario {current:.6f} -> {med:.6f} "
                f"(CPU {cpu_codigo}, grupo {key[0]}/{key[1]}, IQR {low:.6f}..{high:.6f})"
            )


# ── Carregamento e persistência ───────────────────────────────────────────────

def _context_base(contexto_id: str) -> Path:
    base = ROOT / "config" / "catalogos" / contexto_id
    if not base.exists():
        print(f"Contexto não encontrado: {contexto_id}", file=sys.stderr)
        sys.exit(1)
    return base


def _load_entity_files(base: Path, subdirs: tuple[str, ...]) -> list[tuple[Path, dict]]:
    rows: list[tuple[Path, dict]] = []
    for subdir in subdirs:
        directory = base / subdir
        if not directory.exists():
            continue
        for file_path in sorted(directory.rglob("*.json")):
            if file_path.name.startswith("."):
                continue
            try:
                payload = json.loads(file_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(payload, dict):
                rows.append((file_path, payload))
    return rows


def _persist_entity_files(entries: list[tuple[Path, dict]], apply: bool) -> int:
    if not apply:
        return 0
    written = 0
    for file_path, payload in entries:
        should_write = True
        try:
            current = json.loads(file_path.read_text(encoding="utf-8"))
            should_write = current != payload
        except Exception:
            should_write = True
        if should_write:
            file_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            written += 1
    return written


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Curação do catálogo Concilium")
    parser.add_argument("--contexto", required=True, help="ID do contexto (ex: mendeslobo)")
    parser.add_argument("--apply", action="store_true", help="Aplica mudanças (padrão: dry-run)")
    args = parser.parse_args()

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"\n{'='*60}")
    print(f"  Curação do catálogo [{mode}] — contexto: {args.contexto}")
    print(f"{'='*60}\n")

    base = _context_base(args.contexto)
    bundle_path = base / ".catalog_bundle.json"
    cpu_entries = _load_entity_files(base, ("cpus",))
    insumo_entries = _load_entity_files(base, ("insumos",))
    prod_entries = _load_entity_files(base, ("producoes", "produtividades"))

    cpus: list[dict] = [item for _, item in cpu_entries]
    insumos: list[dict] = [item for _, item in insumo_entries]
    prods: list[dict] = [item for _, item in prod_entries]

    report = CurationReport()

    cured_prods = [cure_producao(p, report, args.apply) for p in prods]
    cured_cpus = [cure_cpu(c, report, args.apply) for c in cpus]
    cured_insumos = [cure_insumo(i, report, args.apply) for i in insumos]
    cure_contextual(cured_cpus, cured_prods, cured_insumos, report, args.apply)

    # Relatório de ações
    if report.fixed:
        print(f"[AUTO] {len(report.fixed)} correção(ões) automática(s):")
        for m in report.fixed:
            prefix = "  ✓" if args.apply else "  → (dry-run)"
            print(f"{prefix} {m}")

    if report.manual:
        print(f"\n[MANUAL] {len(report.manual)} item(ns) requerem intervenção manual:")
        for m in report.manual:
            print(f"  ⚠ {m}")

    if report.skipped:
        print(f"\n[INFO] {len(report.skipped)} aviso(s):")
        for m in report.skipped:
            print(f"  · {m}")

    # Persiste se --apply
    if args.apply:
        n_cpus = _persist_entity_files([(p, obj) for (p, _), obj in zip(cpu_entries, cured_cpus, strict=False)], True)
        n_prods = _persist_entity_files([(p, obj) for (p, _), obj in zip(prod_entries, cured_prods, strict=False)], True)
        n_ins = _persist_entity_files([(p, obj) for (p, _), obj in zip(insumo_entries, cured_insumos, strict=False)], True)
        print(f"  Arquivos atualizados: CPUs={n_cpus}, PRODUCOES={n_prods}, INSUMOS={n_ins}")
        if bundle_path.exists():
            bundle_path.unlink()
            print(f"  Bundle invalidado: {bundle_path}")

    # Validação final contra schemas
    print(f"\n{'─'*60}")
    print("  Validação residual contra schemas normalizados")
    print(f"{'─'*60}")

    cpu_v = _make_validator(_load_schema("cpu.schema.json"))
    prod_v = _make_validator(_load_schema("producao.schema.json"))
    ins_v = _make_validator(_load_schema("insumo.schema.json"))

    data_to_validate = cured_cpus if args.apply else cpus
    erros = (
        _validate_all(data_to_validate, cpu_v, "CPU")
        + _validate_all(cured_prods if args.apply else prods, prod_v, "PRODUCAO")
        + _validate_all(cured_insumos if args.apply else insumos, ins_v, "INSUMO")
    )

    if erros:
        print(f"\n[ERRO] {len(erros)} erro(s) residual(is) após curação:")
        for e in erros[:50]:
            print(f"  ✗ {e}")
        if len(erros) > 50:
            print(f"  ... mais {len(erros) - 50} erros")
        if not args.apply:
            print("\n[INFO] Execução em DRY-RUN: para persistir correções, execute novamente com --apply.")
        print()
        sys.exit(1)
    else:
        print("\n  ✓ Nenhum erro residual — catálogo em conformidade com os schemas.\n")


if __name__ == "__main__":
    main()
