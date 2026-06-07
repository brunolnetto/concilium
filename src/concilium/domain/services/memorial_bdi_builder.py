"""MemorialBDIBuilder — serviço puro que constrói o memorial de cálculo BDI (ADR-057).

Totalmente determinístico: mesmos inputs → mesmo memorial.
Sem I/O, sem estado mutável.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from concilium.domain.models.bdi import (
    DEFAULT_BDI_TABELA,
    ComponentesBdi,
    TabelaBdi,
)
from concilium.domain.models.memorial_bdi import (
    MemorialBDICategoria,
    MemorialCalculoBDI,
    MemorialDecomposicao,
    MemorialEncargos,
    MemorialItemAplicacao,
    MemorialMeta,
)

_VIGENCIA_ENCARGOS = "2026-04-01"
_VIGENCIA_BDI = "2026-04-01"
_FONTE_ENCARGOS = "domain/constants.py + domain/models/bdi.py DEFAULT_ENCARGOS (rfi_catalog.xlsm)"

_CATEGORIAS = ["mao_obra", "material", "servicos", "indireto", "diesel"]


def _ba_get_eap_fields(eap: object, item_id: str) -> tuple:
    """Returns (descricao, cpu_id, unidade) from EAP entry or defaults."""
    descricao = eap.descricao if eap and hasattr(eap, "descricao") else item_id
    cpu_id = eap.cpu_id if eap else ""
    unidade = eap.unidade if eap else "un"
    return descricao, cpu_id, unidade


def _ba_get_pu_values(pu: object, pu_bdi: object) -> tuple:
    """Returns (pu_sem, pu_com, bdi_ef) from price unit objects."""
    pu_sem = float(pu.total) if pu and hasattr(pu, "total") else 0.0
    pu_com = float(pu_bdi.total) if pu_bdi and hasattr(pu_bdi, "total") else 0.0
    bdi_ef = round((pu_com / pu_sem - 1) if pu_sem > 0 else 0.0, 6)
    return pu_sem, pu_com, bdi_ef


def _ba_get_sub_floats(sub: object) -> tuple:
    """Returns (subtotal_sem_bdi, subtotal_com_bdi) rounded to 2 decimals."""
    sem = float(sub.sem_bdi.total) if sub and sub.sem_bdi else 0.0
    com = float(sub.com_bdi.total) if sub and sub.com_bdi else 0.0
    return round(sem, 2), round(com, 2)


def _ba_get_pu_components(pu: object) -> tuple:
    """Returns (mo, equip, mat, diesel) cost components from a PU object."""
    mo = float(pu.mao_obra) if pu and hasattr(pu, "mao_obra") else 0.0
    equip = float(pu.equipamentos) if pu and hasattr(pu, "equipamentos") else 0.0
    mat = float(pu.material) if pu and hasattr(pu, "material") else 0.0
    diesel = float(pu.diesel) if pu and hasattr(pu, "diesel") else 0.0
    return mo, equip, mat, diesel


def _mb_resolve_custo_direto(resultado: Any) -> float:
    """Retorna custo direto operacional instancial (única fonte de verdade)."""
    if not resultado or not getattr(resultado, "custo", None):
        return 0.0
    custo = resultado.custo
    return float(getattr(custo, "direto_equipes", 0.0) or 0.0)


class MemorialBDIBuilder:
    """Constrói MemorialCalculoBDI a partir de um canonical e dos inputs de BDI usados."""

    def build(
        self,
        canonical_in: Any,  # CanonicalModel — Any para evitar import circular
        bdi_fonte: str,  # de onde veio o BDI (fonte_bdi)
        regime_version: str,  # "pre_reforma" | "transicao" | "pleno_cbs_ibs"
        tabela_usada: TabelaBdi | None = None,
        override_aplicado: bool = False,
    ) -> MemorialCalculoBDI:
        """Constrói o memorial completo.

        Args:
            canonical_in: CanonicalModel com resultado, planejamento, equipes_diretas
            bdi_fonte: string identificando a origem do BDI (ADR-057 §D4)
            regime_version: regime tributário em vigor para este run
            tabela_usada: TabelaBdi efetiva (se None, usa DEFAULT_BDI_TABELA)
            override_aplicado: True se qualquer campo foi sobrescrito por input
        """
        tabela = tabela_usada or DEFAULT_BDI_TABELA
        projeto_id = canonical_in.projeto.nome if canonical_in.projeto else "desconhecido"

        meta = MemorialMeta(
            projeto_id=projeto_id,
            version=str(getattr(canonical_in, "_version_", "?")),
            gerado_em=datetime.now(UTC).isoformat(),
            skill_versao="08-consolidacao-financeira",
            vigencia_encargos=_VIGENCIA_ENCARGOS,
            vigencia_bdi=_VIGENCIA_BDI,
            regime_tributario=regime_version,
        )

        enc_horista = self._build_encargos("horista_clt")
        enc_mensalista = self._build_encargos("mensalista_clt")

        bdi_por_cat: dict[str, MemorialBDICategoria] = {}
        decomp_por_cat: dict[str, MemorialDecomposicao] = {}

        for cat in _CATEGORIAS:
            comp: ComponentesBdi = getattr(tabela, cat)
            bdi_por_cat[cat] = self._build_bdi_categoria(cat, comp, bdi_fonte, regime_version, override_aplicado)
            decomp_por_cat[cat] = self._build_decomposicao(cat, comp)

        aplicacao = self._build_aplicacao(canonical_in)

        resultado = canonical_in.resultado
        venda = float(resultado.venda.total_com_bdi) if resultado and resultado.venda else 0.0
        custo_direto = _mb_resolve_custo_direto(resultado)
        margem = float(resultado.resultado_financeiro) if resultado else 0.0
        margem_pct = float(resultado.margem_pct) if resultado else 0.0

        # Aproximação conservadora de tributos totais na receita.
        # Mantemos a taxa histórica até concluir distribuição por categoria no consolidado.
        tributos_total = venda * 0.1338
        # Overhead sintético = parcela restante da receita após custo direto, margem e tributos.
        overhead_total = venda - custo_direto - margem - tributos_total

        return MemorialCalculoBDI(
            meta=meta,
            encargos_horista=enc_horista,
            encargos_mensalista=enc_mensalista,
            bdi_por_categoria=bdi_por_cat,
            decomposicao_por_categoria=decomp_por_cat,
            aplicacao_por_item=aplicacao,
            venda_total_com_bdi=round(venda, 2),
            custo_direto_total=round(custo_direto, 2),
            overhead_total=round(overhead_total, 2),
            margem_total=round(margem, 2),
            tributos_total=round(tributos_total, 2),
            margem_pct=round(margem_pct, 6),
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _build_encargos(regime: str) -> MemorialEncargos:
        from concilium.domain.constants import (
            _ENC_A_TOTAL,
            _ENC_B_HORISTA,
            _ENC_B_MENSALISTA,
            _ENC_C_HORISTA,
            _ENC_C_MENSALISTA,
            _ENC_D_HORISTA,
            _ENC_D_MENSALISTA,
            _ENC_E_HORISTA,
            _ENC_E_MENSALISTA,
            _ENC_F_HORISTA,
            _ENC_F_MENSALISTA,
            _ENC_JUDICIAL,
        )
        from concilium.domain.models.bdi import DEFAULT_ENCARGOS

        if regime == "horista_clt":
            enc = DEFAULT_ENCARGOS.horistas
            return MemorialEncargos(
                regime=regime,
                grupo_a=_ENC_A_TOTAL,
                grupo_b=_ENC_B_HORISTA,
                grupo_c=_ENC_C_HORISTA,
                grupo_d=_ENC_D_HORISTA,
                grupo_e=_ENC_E_HORISTA,
                grupo_f=_ENC_F_HORISTA,
                judicial=_ENC_JUDICIAL,
                total=enc.total,
                vigencia=_VIGENCIA_ENCARGOS,
                fonte=_FONTE_ENCARGOS,
            )
        # mensalista_clt
        enc = DEFAULT_ENCARGOS.mensalistas
        return MemorialEncargos(
            regime=regime,
            grupo_a=_ENC_A_TOTAL,
            grupo_b=_ENC_B_MENSALISTA,
            grupo_c=_ENC_C_MENSALISTA,
            grupo_d=_ENC_D_MENSALISTA,
            grupo_e=_ENC_E_MENSALISTA,
            grupo_f=_ENC_F_MENSALISTA,
            judicial=_ENC_JUDICIAL,
            total=enc.total,
            vigencia=_VIGENCIA_ENCARGOS,
            fonte=_FONTE_ENCARGOS,
        )

    @staticmethod
    def _build_bdi_categoria(
        cat: str,
        comp: ComponentesBdi,
        fonte_bdi: str,
        regime_version: str,
        override: bool,
    ) -> MemorialBDICategoria:
        return MemorialBDICategoria(
            categoria=cat,
            ac=comp.ac,
            df=comp.df,
            r=comp.r,
            cr=comp.cr,
            l=comp.l,
            overhead_total=comp.overhead,
            cofins=comp.cofins,
            iss=comp.iss,
            pis=comp.pis,
            cssl=comp.cssl,
            ir=comp.ir,
            tributos_total=comp.tributos,
            bdi_total=comp.bdi_total,
            fonte_bdi=fonte_bdi,
            regime_version=regime_version,
            override_aplicado=override,
        )

    @staticmethod
    def _build_decomposicao(cat: str, comp: ComponentesBdi) -> MemorialDecomposicao:
        d = comp.decomposicao_no_preco()
        soma = round(sum(d.values()), 4)
        return MemorialDecomposicao(
            categoria=cat,
            custo_direto_pct=d["custo_direto"],
            overhead_ac_pct=d["overhead_ac"],
            overhead_df_pct=d["overhead_df"],
            overhead_r_pct=d["overhead_r"],
            overhead_cr_pct=d["overhead_cr"],
            margem_l_pct=d["margem_l"],
            tributo_cofins_pct=d["tributo_cofins"],
            tributo_iss_pct=d["tributo_iss"],
            tributo_pis_pct=d["tributo_pis"],
            tributo_cssl_pct=d["tributo_cssl"],
            tributo_ir_pct=d["tributo_ir"],
            soma=soma,
        )

    @staticmethod
    def _build_aplicacao(canonical_in: Any) -> list[MemorialItemAplicacao]:
        items = []
        plan_lookup = {p.item_id: p for p in (canonical_in.planejamento or [])}
        eap_lookup = {e.item_id: e for e in (canonical_in.eap or [])}

        for item_id, plan in plan_lookup.items():
            eap = eap_lookup.get(item_id)
            descricao, cpu_id, unidade = _ba_get_eap_fields(eap, item_id)
            qtd = float(getattr(plan, "quantitativo", 0))
            pu = plan.preco_unitario
            pu_bdi = plan.preco_unitario_com_bdi
            sub = plan.subtotal
            pu_sem, pu_com, bdi_ef = _ba_get_pu_values(pu, pu_bdi)
            sub_sem, sub_com = _ba_get_sub_floats(sub)
            mo, equip, mat, diesel = _ba_get_pu_components(pu)
            items.append(
                MemorialItemAplicacao(
                    item_id=item_id,
                    descricao=str(descricao)[:80],
                    cpu_id=str(cpu_id),
                    quantitativo=qtd,
                    unidade=str(unidade),
                    preco_unit_sem_bdi=round(pu_sem, 4),
                    bdi_aplicado=bdi_ef,
                    preco_unit_com_bdi=round(pu_com, 4),
                    subtotal_sem_bdi=sub_sem,
                    subtotal_com_bdi=sub_com,
                    custo_mao_obra=round(mo, 4),
                    custo_equipamentos=round(equip, 4),
                    custo_material=round(mat, 4),
                    custo_diesel=round(diesel, 4),
                )
            )
        return items
