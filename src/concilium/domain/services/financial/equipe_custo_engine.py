"""ADR-106 F1 — LifecycleEngine: engine unificado de custo de equipe.

Centraliza o cálculo de custo instancial composicional (ADR-085 D3) para
equipes diretas e indiretas, eliminando a duplicação entre skill-05 e skill-07.

Invariantes (NEP-028 IC-1 a IC-6):
  IC-3: CustoEquipeDecomposicao.total == soma de todos os componentes
  IC-5: Engine é stateless — mesmo input → mesmo output (idempotente)
  IC-6: DirectTeamCostStrategy e IndirectTeamCostStrategy operam em
        partições disjuntas do canônico

Arquitetura:
  LifecycleEngine
    ├── calcular(prod_weeks, idle_weeks, c_mo, c_eq, ...) → CustoEquipeDecomposicao
    └── (F2) DirectTeamCostStrategy   ← para equipes_diretas
    └── (F4) IndirectTeamCostStrategy ← para indiretos
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CustoEquipeDecomposicao:
    """Decomposição de custo de equipe por componente e fase de lifecycle (ADR-106 §F1).

    Produzida por LifecycleEngine para ambas as estratégias (direta e indireta).
    Invariante IC-3: total == soma de todos os campos de custo.
    """

    # Custo ativo (semanas produtivas — todos os componentes à taxa plena)
    ativo_mo: float
    ativo_eq: float
    ativo_comb: float  # Diesel/combustível (apenas diretas; zero para indiretas)
    ativo_mat: float  # Material (apenas diretas; zero para indiretas)

    # Custo ocioso (semanas idle — mobilizado sem produzir)
    idle_mo: float  # MO integral (CLT não permite taxa reduzida)
    idle_eq: float  # EQ à taxa de locação reduzida ρ

    # Mob / demob
    mob: float  # Custo de entrada no pool/projeto (evento)
    demob: float  # Custo de saída (early dismissal ou fim normal)

    # Janelas de mob (ADR-106 F5 — default=0 até catálogo ter leadtime_mob_semanas)
    mob_window: float = 0.0  # (c_mo + c_eq_locacao) × leadtime_mob_semanas
    demob_window: float = 0.0  # (c_mo + c_eq_locacao) × lag_demob_semanas

    # Semanas off (custo zero — antes do mob ou após demob)
    semanas_off: int = 0

    # Total (IC-3: soma de todos os componentes acima)
    total: float = field(default=0.0)

    def __post_init__(self) -> None:
        computed = (
            self.ativo_mo
            + self.ativo_eq
            + self.ativo_comb
            + self.ativo_mat
            + self.idle_mo
            + self.idle_eq
            + self.mob
            + self.demob
            + self.mob_window
            + self.demob_window
        )
        if self.total == 0.0 and computed > 0:
            self.total = round(computed, 2)


def _fill_custo_inst_sem_pool(equipes: list) -> None:
    """ADR-106 F3 — Preenche custo_inst_* para equipes sem pool contract (in-place).

    Para cada equipe com custo_inst_mo is None (não coberta por pool), usa
    DirectTeamCostStrategy para computar a decomposição instancial a partir
    dos campos mensais da equipe e da permanência efetiva.

    Equipes já com custo_inst_mo (cobertas por ADR-085 pool path) são preservadas.

    Invariante IC-3 garantido: soma(custo_inst_*) ≈ custo_total.
    """
    from concilium.domain.constants import SEMANAS_POR_MES

    strategy = DirectTeamCostStrategy()

    for eq in equipes:
        if getattr(eq, "custo_inst_mo", None) is not None:
            continue  # pool path já preencheu — preservar

        perm_efetiva = float(getattr(eq, "permanencia_efetiva_meses", 0.0) or 0.0)
        if perm_efetiva <= 0:
            # Equipe sem permanência: decomposição zero, alinhada com custo_total
            eq.custo_inst_mo = 0.0
            eq.custo_inst_eq = 0.0
            eq.custo_inst_comb = 0.0
            eq.custo_inst_mat = 0.0
            eq.custo_inst_mob_demob = 0.0
            continue

        semanas = round(perm_efetiva * SEMANAS_POR_MES)
        decomp = strategy.calcular_para_equipe(eq, semanas_ativas=semanas, semanas_idle=0)

        # Reescalar a decomposição para alinhar com custo_total real da equipe
        # (pode divergir se permanencia_efetiva difere da permanencia contratual)
        custo_total = float(getattr(eq, "custo_total", 0.0) or 0.0)
        if decomp.total > 0 and custo_total > 0:
            fator = custo_total / decomp.total
        else:
            fator = 1.0

        eq.custo_inst_mo = round(decomp.ativo_mo * fator + decomp.idle_mo * fator, 2)
        eq.custo_inst_eq = round((decomp.ativo_eq + decomp.idle_eq) * fator, 2)
        eq.custo_inst_comb = round(decomp.ativo_comb * fator, 2)
        eq.custo_inst_mat = round(decomp.ativo_mat * fator, 2)
        eq.custo_inst_mob_demob = round((decomp.mob + decomp.demob) * fator, 2)

        # Garantia de fechamento IC-3: ajustar mob_demob pelo resíduo de arredondamento
        soma = eq.custo_inst_mo + eq.custo_inst_eq + eq.custo_inst_comb + eq.custo_inst_mat + eq.custo_inst_mob_demob
        residuo = round(custo_total - soma, 2)
        eq.custo_inst_mob_demob = round(eq.custo_inst_mob_demob + residuo, 2)


class DirectTeamCostStrategy:
    """ADR-106 F2 — Estratégia de custo para equipes diretas (skill-05).

    Converte os campos mensais de EquipeDireta em taxas semanais e delega
    para LifecycleEngine. A taxa de MO já inclui encargos (custo_mao_obra_mensal
    + custo_encargos_mensal = custo real de MO para o empregador).

    IC-6: opera exclusivamente sobre equipes_diretas, nunca sobre indiretos.
    """

    def calcular_para_equipe(
        self,
        equipe: object,
        semanas_ativas: int,
        semanas_idle: int = 0,
        c_mob: float = 0.0,
        c_demob: float = 0.0,
        rho_idle_eq: float = 1.0,
    ) -> CustoEquipeDecomposicao:
        """Calcula decomposição de custo para uma equipe direta.

        Args:
            equipe: EquipeDireta com campos custo_*_mensal preenchidos.
            semanas_ativas: semanas produtivas do item no cronograma.
            semanas_idle: semanas ociosas dentro do ciclo de vida.
            c_mob: custo de mobilização (evento — default=0 até ADR-106 F5).
            c_demob: custo de desmobilização (evento — default=0 até F5).
            rho_idle_eq: fração de c_eq aplicada durante idle (default=1 = taxa plena).
        """
        from concilium.domain.constants import SEMANAS_POR_MES

        def _semanal(custo_mensal: float) -> float:
            return custo_mensal / SEMANAS_POR_MES

        # MO = base + encargos (custo real do empregador)
        c_mo = _semanal(
            float(getattr(equipe, "custo_mao_obra_mensal", 0.0) or 0.0)
            + float(getattr(equipe, "custo_encargos_mensal", 0.0) or 0.0)
        )
        c_eq = _semanal(float(getattr(equipe, "custo_equipamentos_mensal", 0.0) or 0.0))
        c_comb = _semanal(float(getattr(equipe, "custo_combustivel_total_mensal", 0.0) or 0.0))
        c_mat = _semanal(float(getattr(equipe, "custo_material_mensal", 0.0) or 0.0))
        c_idle_eq = c_eq * rho_idle_eq

        engine = LifecycleEngine()
        return engine.calcular(
            prod_weeks=semanas_ativas,
            idle_weeks=semanas_idle,
            c_mo=c_mo,
            c_eq=c_eq,
            c_comb=c_comb,
            c_mat=c_mat,
            c_idle_eq=c_idle_eq,
            c_mob=c_mob,
            c_demob=c_demob,
        )


class IndirectTeamCostStrategy:
    """ADR-106 F4 — Estratégia de custo para equipes indiretas (skill-07).

    Parameterização:
      c_mo = custo_total / SEMANAS_POR_MES (custo fixo mensal dividido em semanas)
      c_eq = custo_equipamentos / SEMANAS_POR_MES
      Combustível e material = zero (indiretos não têm estas categorias)

    Escopo: project-scoped (permanência = duração do projeto).
    MOB: driver "one_time" — custo_mob_desmob distribuído entre mob e demob.
    IC-6: opera exclusivamente sobre Indireto, nunca sobre EquipeDireta.
    """

    def calcular_para_indireto(
        self,
        indireto: object,
        semanas_projeto: int,
    ) -> CustoEquipeDecomposicao:
        """Calcula decomposição de custo para uma equipe indireta.

        Args:
            indireto: Indireto com custo_mao_obra, custo_equipamentos, custo_mob_desmob.
            semanas_projeto: duração total do projeto em semanas (para semanas produtivas).
        """
        from concilium.domain.constants import SEMANAS_POR_MES

        def _semanal(custo_mensal: float) -> float:
            return custo_mensal / SEMANAS_POR_MES

        c_mo = _semanal(
            float(getattr(indireto, "custo_mao_obra", 0.0) or 0.0)
            + float(getattr(indireto, "custo_encargos", 0.0) or 0.0)
        )
        c_eq = _semanal(float(getattr(indireto, "custo_equipamentos", 0.0) or 0.0))

        mob_total = float(getattr(indireto, "custo_mobilizacao", 0.0) or 0.0)
        c_mob = round(mob_total / 2.0, 2)
        c_demob = round(mob_total - c_mob, 2)  # garante que mob + demob == custo_mobilizacao

        engine = LifecycleEngine()
        return engine.calcular(
            prod_weeks=semanas_projeto,
            idle_weeks=0,  # indiretos não têm idle (project-scoped)
            c_mo=c_mo,
            c_eq=c_eq,
            c_comb=0.0,  # IC-6: sem combustível para indiretos
            c_mat=0.0,  # IC-6: sem material para indiretos
            c_idle_eq=c_eq,
            c_mob=c_mob,
            c_demob=c_demob,
        )


class LifecycleEngine:
    """Engine stateless de custo instancial composicional (ADR-106 F1).

    Implementa a mesma lógica de ``calcular_custo_instancia_composicional``
    (ADR-085 D3, atualmente em ``_05_equipes_custo_helpers.py``) mas retorna
    ``CustoEquipeDecomposicao`` em vez de dict, e aceita mob/demob explícitos.

    Stateless (IC-5): nenhum estado interno — mesmo input → mesmo output.
    """

    def calcular(
        self,
        prod_weeks: int,
        idle_weeks: int,
        c_mo: float,
        c_eq: float,
        c_comb: float,
        c_mat: float,
        c_idle_eq: float,
        c_mob: float = 0.0,
        c_demob: float = 0.0,
        c_demob_efetivo: float = 0.0,
        mob_window: float = 0.0,
        demob_window: float = 0.0,
        semanas_off: int = 0,
        leadtime_mob_semanas: int = 0,
        lag_demob_semanas: int = 0,
        trailing_weeks_eq: int = 0,
    ) -> CustoEquipeDecomposicao:
        """Calcula decomposição de custo para um ciclo de vida de equipe.

        Args:
            prod_weeks: semanas produtivas (ativas).
            idle_weeks: semanas ociosas (mobilizado, sem produção).
            c_mo: custo semanal de MO (base + encargos por semana).
            c_eq: custo semanal de equipamentos (taxa plena).
            c_comb: custo semanal de combustível (apenas diretas).
            c_mat: custo semanal de material (apenas diretas).
            c_idle_eq: custo semanal de EQ em idle (taxa de locação reduzida ρ).
            c_mob: custo de mobilização (evento de entrada).
            c_demob: custo de desmobilização normal (evento de saída).
            c_demob_efetivo: custo de desmob antecipada (early dismissal EQ).
            mob_window: custo pré-calculado da janela de mobilização (ADR-106 F5).
                Se leadtime_mob_semanas > 0, este valor é ignorado e recalculado.
            demob_window: custo pré-calculado da janela de desmob (ADR-106 F5).
                Se lag_demob_semanas > 0, este valor é ignorado e recalculado.
            semanas_off: semanas fora do ciclo (custo zero — informativo).
            leadtime_mob_semanas: semanas de pré-ativação (ADR-106 F5).
                Custo da janela: (c_mo + c_eq) × leadtime_mob_semanas.
                0 = sem janela (backward compat).
            lag_demob_semanas: semanas pós-atividade (ADR-106 F5).
                Custo da janela: (c_mo + c_eq) × lag_demob_semanas.
                0 = sem janela (backward compat).
            trailing_weeks_eq: semanas de EQ trailing (ADR-106 F6 — early dismissal EQ).
                Se economia_eq = c_idle_eq × trailing_weeks_eq - c_demob > 0, EQ é
                devolvida antecipadamente. MO não é afetada (CLT).

        Returns:
            CustoEquipeDecomposicao com decomposição completa e total auditável.
        """
        ativo_mo = round(c_mo * prod_weeks, 2)
        ativo_eq = round(c_eq * prod_weeks, 2)
        ativo_comb = round(c_comb * prod_weeks, 2)
        ativo_mat = round(c_mat * prod_weeks, 2)

        idle_mo = round(c_mo * idle_weeks, 2)  # MO integral durante ociosidade (CLT)
        idle_eq = round(c_idle_eq * idle_weeks, 2)  # EQ à taxa de locação reduzida

        # ADR-106 F5 — Mob window: custo (c_mo + c_eq) × leadtime/lag semanas.
        # Sem combustível nem material (recursos transitando, sem produção).
        if leadtime_mob_semanas > 0:
            mob_window = round((c_mo + c_eq) * leadtime_mob_semanas, 2)
        if lag_demob_semanas > 0:
            demob_window = round((c_mo + c_eq) * lag_demob_semanas, 2)

        # ADR-106 F6 — Early dismissal para EQ (CLT protege MO).
        # Se devolução antecipada economiza mais que o custo de c_demob_eq,
        # substitui c_demob_efetivo pelo custo de devolução antecipada (c_demob).
        # MO continua sendo paga (aviso prévio — não modelado aqui).
        if trailing_weeks_eq > 0 and c_idle_eq > 0:
            economia_eq = round(c_idle_eq * trailing_weeks_eq - c_demob, 2)
            if economia_eq > 0:
                # Devolver EQ antecipadamente: custo = c_demob (evento de saída EQ)
                # c_demob_efetivo recebe o custo de desmob efetivo da EQ
                c_demob_efetivo = c_demob if c_demob_efetivo == 0.0 else c_demob_efetivo

        mob = round(c_mob, 2)
        demob = round(c_demob + c_demob_efetivo, 2)

        total = round(
            ativo_mo + ativo_eq + ativo_comb + ativo_mat + idle_mo + idle_eq + mob + demob + mob_window + demob_window,
            2,
        )

        return CustoEquipeDecomposicao(
            ativo_mo=ativo_mo,
            ativo_eq=ativo_eq,
            ativo_comb=ativo_comb,
            ativo_mat=ativo_mat,
            idle_mo=idle_mo,
            idle_eq=idle_eq,
            mob=mob,
            demob=demob,
            mob_window=round(mob_window, 2),
            demob_window=round(demob_window, 2),
            semanas_off=semanas_off,
            total=total,
        )
