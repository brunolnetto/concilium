"""Memorial de Cálculo BDI — artefato de auditoria ponta a ponta (ADR-057).

Documenta a cadeia completa:
    Salário_base × (1 + Encargos) → Custo_MO
    Custo_MO × (1 + BDI) → Preço_Venda
    Preço_Venda = Custo_direto% + Overhead% + Margem% + Tributos%

Todos os tipos são frozen — o memorial é imutável após construção.
Invariante: MemorialDecomposicao.soma == 1.0 (100% do preço de venda).
"""

from __future__ import annotations

from dataclasses import dataclass

# ── Nível 1: Encargos Sociais ─────────────────────────────────────────────────


@dataclass(frozen=True)
class MemorialEncargos:
    """Breakdown auditável dos encargos sociais aplicados (Grupos A–F + Judicial).

    Valores derivados de domain/constants.py → DEFAULT_ENCARGOS (bdi.py).
    Fonte: rfi_catalog.xlsm (MendesLobo, vigência abril/2026).
    """

    regime: str  # "horista_clt" | "mensalista_clt" | "pj"
    grupo_a: float  # Básicos: INSS emp., RAT, Sal.Educ., FGTS, terceiros
    grupo_b: float  # Com incidência de A: férias, 13º, DSR
    grupo_c: float  # Sem incidência de A: aviso prévio, multas, indenizações
    grupo_d: float  # Reincidências de B sobre C
    grupo_e: float  # Seguros e benefícios: saúde, vida, EPI
    grupo_f: float  # Vale-transporte + vale-refeição (horistas); 0 para mensalistas
    judicial: float  # Provisão para passivo trabalhista
    total: float  # = A + B + C + D + E + F + Judicial
    vigencia: str  # "AAAA-MM-DD"
    fonte: str  # referência ao arquivo/planilha de origem


# ── Nível 2: BDI por Categoria ────────────────────────────────────────────────


@dataclass(frozen=True)
class MemorialBDICategoria:
    """BDI auditável para uma categoria de custo — componentes + resultado.

    Fórmula TCU Acórdão 2622/2013:
        BDI = (1 + AC + DF + R + CR + L) / (1 - T) - 1
    onde T = cofins + iss + pis + cssl + ir.
    """

    categoria: str  # "mao_obra" | "material" | "servicos" | "indireto" | "diesel"

    # Overhead (numerador): cada componente como fração (0.050 = 5%)
    ac: float  # Administração Central
    df: float  # Despesas Financeiras / custo de capital
    r: float  # Garantia, Risco, Seguro
    cr: float  # Contingência de Risco
    l: float  # Lucro / Margem  # noqa: E741
    overhead_total: float  # = AC + DF + R + CR + L

    # Tributos (denominador): taxas efetivas sobre receita bruta
    cofins: float
    iss: float
    pis: float
    cssl: float
    ir: float
    tributos_total: float  # = COFINS + ISS + PIS + CSSL + IR

    # Resultado
    bdi_total: float  # = (1 + OH) / (1 - T) - 1

    # Rastreabilidade
    fonte_bdi: str  # de onde vieram os valores (ver ADR-057 §D4)
    regime_version: str  # "pre_reforma" | "transicao" | "pleno_cbs_ibs"
    override_aplicado: bool  # True se qualquer componente foi sobrescrito


# ── Nível 3: Decomposição no Preço de Venda ───────────────────────────────────


@dataclass(frozen=True)
class MemorialDecomposicao:
    """Para cada R$1,00 cobrado ao cliente — quanto vai a cada destino.

    Derivado de MemorialBDICategoria via ComponentesBdi.decomposicao_no_preco().

    Invariante: soma de todos os campos == 1.0 (±0.001 por arredondamento).
    """

    categoria: str

    # Custo direto
    custo_direto_pct: float  # C/PV = (1-T)/(1+OH)

    # Overhead por componente: OHx/PV = OHx × C/PV
    overhead_ac_pct: float
    overhead_df_pct: float
    overhead_r_pct: float
    overhead_cr_pct: float
    margem_l_pct: float  # Margem líquida sobre o preço de venda

    # Tributos: fração direta do preço de venda
    tributo_cofins_pct: float
    tributo_iss_pct: float
    tributo_pis_pct: float
    tributo_cssl_pct: float
    tributo_ir_pct: float

    soma: float  # = custo + Σoverhead + margem + Σtributos → deve ser 1.0

    @property
    def overhead_total_pct(self) -> float:
        return round(
            self.overhead_ac_pct + self.overhead_df_pct + self.overhead_r_pct + self.overhead_cr_pct,
            6,
        )

    @property
    def tributos_total_pct(self) -> float:
        return round(
            self.tributo_cofins_pct
            + self.tributo_iss_pct
            + self.tributo_pis_pct
            + self.tributo_cssl_pct
            + self.tributo_ir_pct,
            6,
        )


# ── Nível 4: Aplicação por Item da EAP ───────────────────────────────────────


@dataclass(frozen=True)
class MemorialItemAplicacao:
    """Como o BDI foi aplicado a um item específico da EAP."""

    item_id: str
    descricao: str
    cpu_id: str
    quantitativo: float
    unidade: str

    # Custos unitários
    preco_unit_sem_bdi: float  # R$/unidade antes do BDI
    bdi_aplicado: float  # fração BDI efetiva usada (MO, MAT ou composição)
    preco_unit_com_bdi: float  # R$/unidade após BDI

    # Subtotais
    subtotal_sem_bdi: float
    subtotal_com_bdi: float

    # Composição de categorias (sem BDI)
    custo_mao_obra: float
    custo_equipamentos: float
    custo_material: float
    custo_diesel: float


# ── Memorial Completo ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class MemorialMeta:
    """Metadados de rastreabilidade do memorial."""

    projeto_id: str
    version: str  # versão do canonical que o gerou
    gerado_em: str  # ISO timestamp
    skill_versao: str  # "06-resultado-financeiro"
    vigencia_encargos: str  # "2026-04-01"
    vigencia_bdi: str  # "2026-04-01"
    regime_tributario: str  # "pre_reforma" | "transicao" | "pleno_cbs_ibs"


@dataclass(frozen=True)
class MemorialCalculoBDI:
    """Memorial de cálculo BDI completo — artefato de auditoria (ADR-057).

    Captura a cadeia:
        Encargos → Custo MO → BDI por categoria → Preço Venda → Decomposição
        + Aplicação a cada item da EAP + Resultado financeiro

    Gerado por MemorialBDIBuilder.build() — determinístico dado o canonical.
    Exportado como JSON (memorial_bdi.json) e Excel (aba MEMORIAL.BDI).
    """

    meta: MemorialMeta
    encargos_horista: MemorialEncargos
    encargos_mensalista: MemorialEncargos
    bdi_por_categoria: dict[str, MemorialBDICategoria]  # keyed by categoria
    decomposicao_por_categoria: dict[str, MemorialDecomposicao]
    aplicacao_por_item: list[MemorialItemAplicacao]

    # Resultado sintético
    venda_total_com_bdi: float
    custo_direto_total: float
    overhead_total: float
    margem_total: float
    tributos_total: float
    margem_pct: float  # = margem_total / venda_total_com_bdi

    def to_dict(self) -> dict:
        """Serialização recursiva para JSON export."""
        import dataclasses

        def _conv(obj):
            if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
                return {k: _conv(v) for k, v in dataclasses.asdict(obj).items()}
            if isinstance(obj, dict):
                return {k: _conv(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_conv(v) for v in obj]
            return obj

        return _conv(self)
