#!/usr/bin/env python3
"""
Curação do catálogo Concilium — alinha dados aos schemas normalizados.

Uso:
    python tools/cure_catalog.py --contexto mendeslobo          # dry-run (relatório)
    python tools/cure_catalog.py --contexto mendeslobo --apply  # aplica mudanças

Ações automáticas:
    - Producao: migra campo legado `equipe` → `composicao_padrao_equipe`
    - Producao: estrutura `historico_observacoes` (adiciona campos obrigatórios ausentes)
    - Producao: remove `cpu_ids` (redundante com CPU.producao_id_ref)
    - CPU: reporta composicao_itens vazia (requer intervenção manual)
    - CPU: reporta e sinaliza fonte_preco / data_referencia_preco (deprecated)
    - Insumo MAO_OBRA: remove `custo_com_encargos` se presente
    - Insumo EQUIPAMENTO: remove `custo_manutencao_hora` / `custo_produtivo_hora` se presentes
    - Qualquer entidade: remove `custo_hora_total` de decomposicao_equip

Validação final:
    Ao terminar, roda os 4 schemas JSON contra todos os dados e reporta erros residuais.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

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


def cure_producao(prod: dict, report: CurationReport, apply: bool) -> dict:
    pid = prod.get("id", "<sem-id>")
    changed = dict(prod)

    # Remove campos exclusivos de CPU que contaminaram Producao
    prod_cpu_fields = {"atributos_categoria", "cpu_ids", "producao_horaria"}
    contaminados = [k for k in prod_cpu_fields if k in changed]
    if contaminados:
        if apply:
            for k in contaminados:
                del changed[k]
        for k in contaminados:
            report.add_fixed(f"PRODUCAO {pid}: removido campo exclusivo de CPU '{k}'")

    # Migra equipe → composicao_padrao_equipe
    if "equipe" in changed and "composicao_padrao_equipe" not in changed:
        if apply:
            changed["composicao_padrao_equipe"] = changed.pop("equipe")
        report.add_fixed(f"PRODUCAO {pid}: migrado equipe → composicao_padrao_equipe")

    elif "equipe" in changed and "composicao_padrao_equipe" in changed:
        if apply:
            del changed["equipe"]
        report.add_fixed(f"PRODUCAO {pid}: removido campo legado equipe (composicao_padrao_equipe já existe)")

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

    return changed if apply else prod


def cure_cpu(cpu: dict, report: CurationReport, apply: bool) -> dict:
    codigo = cpu.get("codigo", "<sem-codigo>")

    # Composicao vazia — requer intervenção manual
    if isinstance(cpu.get("composicao_itens"), list) and len(cpu["composicao_itens"]) == 0:
        report.add_manual(f"CPU {codigo}: composicao_itens vazia — requer preenchimento manual")

    # Move dmt_referencia_m do root para atributos_categoria (campo mal posicionado)
    dmt_root_fields = {k: v for k, v in cpu.items() if k in ("dmt_referencia_m", "dmt_min_metros", "dmt_max_metros")}
    if dmt_root_fields:
        if apply:
            changed = dict(cpu)
            attrs_cat = dict(changed.get("atributos_categoria") or {})
            for k, v in dmt_root_fields.items():
                attrs_cat[k] = v
                del changed[k]
            changed["atributos_categoria"] = attrs_cat
            return changed
        for k in dmt_root_fields:
            report.add_fixed(f"CPU {codigo}: movido '{k}' do root para atributos_categoria")

    # Sinaliza campos deprecated
    for campo in ("fonte_preco", "data_referencia_preco"):
        if campo in cpu:
            report.add_skipped(f"CPU {codigo}: campo deprecated '{campo}' presente — remova após curação dos Insumos")

    return cpu  # CPUs não são alteradas automaticamente aqui


_CPU_ONLY_FIELDS = {"atributos_categoria", "cpu_referencia_id", "producao_id_ref", "composicao_itens",
                    "custo_direto_unitario_planilha", "precos_unitarios_sbdi"}


def cure_insumo(ins: dict, report: CurationReport, apply: bool) -> dict:
    codigo = ins.get("codigo", "<sem-codigo>")
    tipo = ins.get("tipo", "")
    changed = dict(ins)

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
        if isinstance(attrs, dict):
            derivados = [k for k in ("custo_com_encargos",) if k in attrs]
            if derivados and apply:
                for k in derivados:
                    del attrs[k]
                changed["atributos_especificos"] = attrs
            for k in derivados:
                report.add_fixed(f"INSUMO {codigo}: removido campo derivado atributos_especificos.{k}")

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


# ── Carregamento e persistência ───────────────────────────────────────────────

def _load_catalog(contexto_id: str) -> tuple[Path, dict]:
    """Lê o bundle compilado ou reconstrói dos arquivos individuais."""
    bundle_path = ROOT / "config" / "catalogos" / contexto_id / ".catalog_bundle.json"
    if bundle_path.exists():
        data = json.loads(bundle_path.read_text(encoding="utf-8"))
        return bundle_path, data

    # Fallback: lê arquivos individuais
    base = ROOT / "config" / "catalogos" / contexto_id
    if not base.exists():
        print(f"Contexto não encontrado: {contexto_id}", file=sys.stderr)
        sys.exit(1)

    def _load_dir(subdir: str) -> list[dict]:
        d = base / subdir
        if not d.exists():
            return []
        return [json.loads(f.read_text(encoding="utf-8")) for f in sorted(d.rglob("*.json")) if not f.name.startswith(".")]

    data = {
        "cpus": _load_dir("cpus"),
        "insumos": _load_dir("insumos"),
        "producoes": _load_dir("producoes"),
    }
    return bundle_path, data


def _persist_bundle(path: Path, data: dict, apply: bool) -> None:
    if not apply:
        return
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  Bundle atualizado: {path}")


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

    bundle_path, catalog = _load_catalog(args.contexto)
    cpus: list[dict] = catalog.get("cpus", [])
    insumos: list[dict] = catalog.get("insumos", [])
    prods: list[dict] = catalog.get("producoes", []) or catalog.get("produtividades", [])

    report = CurationReport()

    cured_prods = [cure_producao(p, report, args.apply) for p in prods]
    cured_cpus = [cure_cpu(c, report, args.apply) for c in cpus]
    cured_insumos = [cure_insumo(i, report, args.apply) for i in insumos]

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
        catalog["producoes"] = cured_prods
        catalog["cpus"] = cured_cpus
        catalog["insumos"] = cured_insumos
        _persist_bundle(bundle_path, catalog, apply=True)

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
        print()
        sys.exit(1)
    else:
        print("\n  ✓ Nenhum erro residual — catálogo em conformidade com os schemas.\n")


if __name__ == "__main__":
    main()
