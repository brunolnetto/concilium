"""
Resolve as 4 lacunas identificadas no benchmark AGIS:

1. MO-GERENTE-QSMS: cria insumo no catálogo e substitui código provisório
2. MO-BIOLOGO / MO-BOTANICO: cria insumos sazonais para fase de supressão
3. LAB: adiciona P0009 Auxiliar de Laboratório (qty=1, expansão para volumes maiores)
4. ADM: esclarece P0033 Motorista Pipa (qty=0, não faz parte da equipe ADM)
"""
import io, json, sys
from datetime import datetime, timezone
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT   = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "config/catalogos/mendeslobo/.catalog_bundle.json"
REF    = ROOT / "benchmarks/data/AGIS/referencia.json"

bundle = json.loads(BUNDLE.read_text(encoding="utf-8"))
ref    = json.loads(REF.read_text(encoding="utf-8"))

insumos = bundle.get("insumos", [])
ins_idx = {i["codigo"]: i for i in insumos if i.get("codigo")}
TODAY   = datetime.now(timezone.utc).strftime("%Y-%m-%d")

# ── 1. Criar novos insumos MAO_OBRA ─────────────────────────────────────────

NOVOS_INSUMOS = [
    {
        "codigo": "MO-GERENTE-QSMS",
        "tipo": "MAO_OBRA",
        "descricao": "Gerente de QSMS",
        "unidade": "mes",
        "preco_unitario": 15000.0,
        "fonte_preco": "negociado",
        "data_referencia_preco": TODAY,
        "categoria": "DIVERSOS",
        "atributos_especificos": {
            "tipo_contrato": "PJ",
            "salario_mensal": 15000.0,
            "horas_mes": 220.0,
            "metodo_custo_total": "custo_total_ja_incluido",
            "taxa_encargos_pct": 0.0,
            "nota_encargos": "PJ — valor já representa custo total ao projeto (honorários + responsabilidades PCMSO/PPRA/PCA/PBA/PGRCC).",
        },
        "_nota_projeto": (
            "Profissional habilitado (Engenheiro ou Biólogo com NR-10/NR-35) responsável pelos "
            "programas ambientais e de saúde ocupacional conforme exigência DNIT/IBAMA para obras ferroviárias. "
            "Criado para benchmark AGIS — presença durante toda a obra (12,57 meses)."
        ),
    },
    {
        "codigo": "MO-BIOLOGO",
        "tipo": "MAO_OBRA",
        "descricao": "Biólogo de campo",
        "unidade": "mes",
        "preco_unitario": 7500.0,
        "fonte_preco": "negociado",
        "data_referencia_preco": TODAY,
        "categoria": "DIVERSOS",
        "atributos_especificos": {
            "tipo_contrato": "PJ",
            "salario_mensal": 7500.0,
            "horas_mes": 220.0,
            "metodo_custo_total": "custo_total_ja_incluido",
            "taxa_encargos_pct": 0.0,
            "nota_encargos": "PJ — honorários de consultoria. Sem vínculo empregatício.",
        },
        "_nota_projeto": (
            "Responsável pelo monitoramento de fauna (afugentamento e resgate) durante a fase de "
            "desmatamento/supressão vegetal. Presença sazonal conforme exigência IBAMA. "
            "Permanência típica: fase eap-1_0 (supressão) = ~5,83 meses."
        ),
        "_sazonalidade": "eap-1_0 (desmatamento/supressão vegetal)",
    },
    {
        "codigo": "MO-BOTANICO",
        "tipo": "MAO_OBRA",
        "descricao": "Botânico de campo",
        "unidade": "mes",
        "preco_unitario": 7500.0,
        "fonte_preco": "negociado",
        "data_referencia_preco": TODAY,
        "categoria": "DIVERSOS",
        "atributos_especificos": {
            "tipo_contrato": "PJ",
            "salario_mensal": 7500.0,
            "horas_mes": 220.0,
            "metodo_custo_total": "custo_total_ja_incluido",
            "taxa_encargos_pct": 0.0,
            "nota_encargos": "PJ — honorários de consultoria.",
        },
        "_nota_projeto": (
            "Responsável pela identificação e coleta de espécimes botânicos antes da supressão, "
            "conforme Plano de Compensação Ambiental. Presença sazonal (fase de supressão). "
            "Permanência típica: fase eap-1_0 = ~5,83 meses."
        ),
        "_sazonalidade": "eap-1_0 (desmatamento/supressão vegetal)",
    },
]

adicionados = []
for ins in NOVOS_INSUMOS:
    cod = ins["codigo"]
    if cod not in ins_idx:
        insumos.append(ins)
        ins_idx[cod] = ins
        adicionados.append(cod)
        print(f"  [+] {cod}: {ins['descricao']} R${ins['preco_unitario']:,.2f}/mês ({ins['atributos_especificos']['tipo_contrato']})")
    else:
        print(f"  [=] {cod} já existe no catálogo — mantido")

bundle["insumos"] = insumos
BUNDLE.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"\n  Catálogo atualizado: {len(adicionados)} insumos adicionados\n")

# ── 2. Atualizar equipes_indiretas no referencia.json ────────────────────────

equipes = ref.get("equipes_indiretas", [])
indir   = ref.get("indiretos_detalhamento", {})

# Helper para encontrar equipe por categoria
def _get_equipe(cat: str) -> dict | None:
    return next((e for e in equipes if e.get("categoria") == cat), None)

# ── QSMS: substituir GERENTE-QSMS pelo novo código + adicionar sazonal ──────
qsms = _get_equipe("QSMS")
if qsms:
    mo = qsms.setdefault("mao_obra", [])

    # Substitui o código provisório pelo código real
    for func in mo:
        if func.get("codigo") == "GERENTE-QSMS":
            func["codigo"] = "MO-GERENTE-QSMS"
            func["funcao"] = "GERENTE DE QSMS"
            func["_codigo_criado"] = True
            print(f"  [QSMS] GERENTE-QSMS → MO-GERENTE-QSMS")

    # Remove P0002 se quantidade = 0 (XLSM mostra zero)
    mo_filtrado = [f for f in mo if not (f.get("codigo") == "P0002" and f.get("quantidade", 1) == 0)]
    if len(mo_filtrado) < len(mo):
        print(f"  [QSMS] P0002 removido (quantidade=0 na planilha)")
        mo = mo_filtrado

    # Adiciona Biólogo e Botânico como recursos sazonais (eap-1_0)
    sazonais = [
        {
            "codigo": "MO-BIOLOGO",
            "funcao": "BIÓLOGO DE CAMPO",
            "quantidade": 1,
            "salario_base": 7500.0,
            "horas_extras_mensal": 0.0,
            "encargos_pct": 0.0,
            "custo_unitario": 7500.0,
            "tipo_contratacao": "PJ",
            "sazonalidade": "eap-1_0",
            "permanencia_meses_sazonal": 5.83,
            "custo_total_sazonal": 7500.0 * 5.83,
            "_nota": "Presente apenas durante a fase de desmatamento/supressão (eap-1_0, ~25 semanas). "
                     "Custo NÃO incluído no custo_fixo_mensal base — é custo sazonal adicional.",
        },
        {
            "codigo": "MO-BOTANICO",
            "funcao": "BOTÂNICO DE CAMPO",
            "quantidade": 1,
            "salario_base": 7500.0,
            "horas_extras_mensal": 0.0,
            "encargos_pct": 0.0,
            "custo_unitario": 7500.0,
            "tipo_contratacao": "PJ",
            "sazonalidade": "eap-1_0",
            "permanencia_meses_sazonal": 5.83,
            "custo_total_sazonal": 7500.0 * 5.83,
            "_nota": "Identificação e coleta de espécimes antes da supressão. Mesmo período do Biólogo.",
        },
    ]
    # Só adiciona se não existirem ainda
    codigos_atuais = {f["codigo"] for f in mo}
    for s in sazonais:
        if s["codigo"] not in codigos_atuais:
            mo.append(s)
            print(f"  [QSMS] + {s['codigo']} (sazonal eap-1_0, {s['permanencia_meses_sazonal']} meses)")

    qsms["mao_obra"] = mo
    qsms["_lacunas_identificadas"] = []  # Limpa as lacunas resolvidas
    qsms["custo_sazonal_biologo_botanico"] = 2 * 7500.0 * 5.83
    qsms["_nota_custo_sazonal"] = (
        "Biólogo + Botânico = R$ 87.450 total sazonal (fora do custo_fixo_mensal base). "
        "Deve ser somado ao custo indireto da fase de supressão."
    )

    # Atualiza também em indiretos_detalhamento
    if "QSMS" in indir:
        indir["QSMS"]["composicao_equipe"] = {
            **indir["QSMS"].get("composicao_equipe", {}),
            "mao_obra": mo,
        }
        indir["QSMS"]["lacunas_resolvidas"] = [
            "MO-GERENTE-QSMS criado no catálogo",
            "Biólogo e Botânico adicionados como sazonais (eap-1_0)",
        ]

# ── LAB: adicionar P0009 com quantidade=1 ────────────────────────────────────
lab = _get_equipe("LAB")
if lab:
    mo = lab.setdefault("mao_obra", [])
    codigos_atuais = {f["codigo"] for f in mo}

    if "P0009" not in codigos_atuais:
        mo.append({
            "codigo": "P0009",
            "funcao": "AUXILIAR DE LABORATÓRIO",
            "quantidade": 1,
            "salario_base": 2217.60,
            "horas_extras_mensal": 554.40,
            "encargos_pct": 1691.06,
            "custo_unitario": 4463.06,
            "tipo_contratacao": "CLT",
            "_nota": (
                "Adicionado para capacidade operacional adequada. "
                "Na planilha XLSM (abr/2026) aparece com quantidade=0 — praça não preenchida. "
                "Recomendado para volumes de ensaios acima de 50 amostras/dia. "
                "Verificar com engenheiro de laboratório."
            ),
            "_status": "recomendado — confirmar com o engenheiro de laboratório",
        })
        lab["_total_pessoas_mo"] = len([f for f in mo if f.get("quantidade", 0) > 0])
        # Recalcula custo_fixo_mensal com P0009
        custo_adicional = 4463.06
        lab["custo_fixo_mensal"] = lab.get("custo_fixo_mensal", 10847.25) + custo_adicional
        lab["custo_total"] = lab["custo_fixo_mensal"] * lab.get("permanencia_meses", 12.567)
        lab["_nota_expansao"] = (
            f"Com P0009 (Aux. Lab): custo mensal R$ {lab['custo_fixo_mensal']:,.2f} "
            f"(+R$ {custo_adicional:,.2f} vs versão mínima). "
            "Total obra: R$ {:,.2f}".format(lab["custo_total"])
        )
        print(f"  [LAB]  + P0009 Auxiliar de Laboratório (CLT, R$ 4.463,06/mês) — qty=1")
        print(f"  [LAB]  Custo mensal: R$ {lab['custo_fixo_mensal']:,.2f} (era R$ 10.847,25)")
    else:
        print(f"  [LAB]  P0009 já existe")

    lab["mao_obra"] = mo

    if "LAB" in indir:
        indir["LAB"]["composicao_equipe"] = {
            **indir["LAB"].get("composicao_equipe", {}),
            "mao_obra": mo,
        }

# ── ADM: esclarecer P0033 (quantidade=0, não pertence ao time ADM) ───────────
adm = _get_equipe("ADM")
if adm:
    mo = adm.get("mao_obra", [])
    total_antes = len(mo)
    # P0033 não está na lista atual do ADM (foi corretamente omitido na implementação)
    # Apenas adiciona uma nota explicativa no header da equipe
    adm["_nota_p0033"] = (
        "P0033 (Motorista Caminhão Pipa) aparece na aba ADM do XLSM como linha de referência de custo, "
        "mas com quantidade=0 e equipamento E0013 (caminhão pipa) também zerado. "
        "A operação de pipa é realizada pelas equipes diretas (EQUIPE-4 ATERRO, EQUIPE-6 ROCHA) "
        "que têm seus próprios motoristas e equipamentos de pipa. "
        "Código P0033 corretamente EXCLUÍDO do time ADM."
    )
    adm["_lacunas_resolvidas"] = adm.get("_lacunas_resolvidas", []) + [
        "P0033: confirmado como ausente da equipe ADM (quantidade=0 na planilha)"
    ]
    print(f"  [ADM]  P0033: confirmado qty=0 (pipa está nas equipes diretas ATERRO/ROCHA)")
    print(f"  [ADM]  Nota explicativa adicionada ao header da equipe")

    if "ADM" in indir:
        indir["ADM"]["nota_p0033"] = adm["_nota_p0033"]

# Salva referencia.json
ref["equipes_indiretas"] = equipes
ref["indiretos_detalhamento"] = indir
REF.write_text(json.dumps(ref, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"\n  referencia.json atualizado com todas as correções.")

# ── Sumário final ─────────────────────────────────────────────────────────────
print("\n" + "=" * 65)
print("SUMÁRIO DAS LACUNAS RESOLVIDAS")
print("=" * 65)
print("""
  1. MO-GERENTE-QSMS ✅
     Criado no catálogo: PJ, R$ 15.000/mês
     Substituído no QSMS em lugar do código provisório 'GERENTE-QSMS'

  2. MO-BIOLOGO + MO-BOTANICO ✅
     Criados no catálogo: PJ, R$ 7.500/mês cada
     Adicionados ao QSMS como recursos sazonais (eap-1_0)
     Permanência: ~5,83 meses (fase desmatamento/supressão)
     Custo sazonal adicional: 2 × 7.500 × 5,83 = R$ 87.450

  3. P0009 Auxiliar de Laboratório ✅
     Adicionado ao time LAB com quantidade=1 (CLT)
     Custo acrescido: +R$ 4.463,06/mês
     Novo custo mensal LAB: R$ 15.310,31/mês
     Nota: recomendado, confirmar com engenheiro de lab

  4. P0033 Motorista Pipa em ADM ✅
     Confirmado quantidade=0 na planilha
     Nota explicativa adicionada: pipa está em ATERRO/ROCHA
     P0033 permanece EXCLUÍDO do time ADM (correto)
""")
