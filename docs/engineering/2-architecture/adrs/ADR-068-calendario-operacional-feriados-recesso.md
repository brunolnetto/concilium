# ADR-068: Calendario Operacional de Producao (Feriados e Recesso)

**Status:** Implementado
**Data:** 2026-05-22
**Autor:** Engenheiro Senior
**Relacionado:** ADR-007, ADR-038, ADR-046, ADR-058, ADR-060, ADR-061

---

## 1. Contexto

O planejamento atual usa:
- Regime de trabalho (`dias_semana`, `horas_dia`) no nivel de projeto
- Praticabilidade semanal derivada de clima (chuva)
- Distribuicao semanal por semana ISO no cronograma

Esse desenho funciona para produtividade climatica, mas ainda nao representa de forma explicita:
- Feriados globais/corporativos
- Feriados por jurisdicao (nacional/estadual/municipal)
- Semanas de recesso operacional

Na pratica, isso mistura indisponibilidade civil com indisponibilidade climatica e reduz a explicabilidade do cronograma, do PE e das sugestoes de backtracking.

---

## 2. Problema

### P1 - Ausencia de calendario operacional formal
Nao existe entidade de calendario com governanca/versionamento para dias nao uteis e recessos.

### P2 - Ineficiencia de PE sem separacao de causa civil
Diagnostico PE separa fatores estruturais e evitaveis, mas nao explicita um fator proprio para indisponibilidade por feriado/recesso.

### P3 - Simulacao limitada para decisao temporal
Backtracking sugere deslocamento de janela (timing), porem sem um componente civil explicito para responder "quanto ganho movendo para fora de semanas com feriados/recesso".

### P4 - Lacuna de produto
Exportacoes Excel carregam a maior parte da analise temporal, mas a API/UI ainda nao oferece visao analitica nativa do efeito de calendario sobre custo e margem.

---

## 3. Decisao

### D1 - Introduzir CalendarioOperacional como entidade de primeira classe
Criar uma camada de calendario com composicao de regras em tres niveis:
1. Global (corporativo)
2. Jurisdicao
3. Projeto/Escopo

Precedencia: Projeto/Escopo > Jurisdicao > Global.

### D2 - Separar fatores de capacidade semanal
Capacidade efetiva semanal passa a ser calculada como:

`capacidade_semana = capacidade_regime * fator_clima * fator_calendario`

Onde:
- `fator_clima` continua vindo da skill de produtividade climatica
- `fator_calendario` vem do novo calendario operacional

### D3 - Representar recesso por intervalo de datas
Semanas de recesso devem ser definidas por janelas de datas (`inicio`, `fim`) e convertidas para impacto semanal ISO por intersecao de dias uteis.

### D4 - Explicabilidade no diagnostico e no backtracking
Adicionar fator causal de calendario no diagnostico de PE e habilitar alavanca de ajuste de janela com base no calendario efetivo.

### D5 - Governanca e auditabilidade
Versionar as configuracoes de calendario no mesmo padrao das entidades de configuracao, com diff e trilha de auditoria.

---

## 4. Modelo de dados (proposto)

```python
@dataclass(frozen=True)
class EventoCalendario:
    id: str
    nome: str
    tipo: Literal["feriado", "ponto_facultativo", "recesso"]
    escopo: Literal["global", "jurisdicao", "projeto"]
    jurisdicao_id: str | None
    inicio: date
    fim: date
    recorrencia: Literal["anual", "unica"]
    fator_operacao: float  # 0.0 = parada total, 0.5 = operacao parcial


@dataclass(frozen=True)
class CalendarioOperacionalSemanal:
    semana_iso: str
    dias_uteis_base: float
    dias_uteis_efetivos: float
    fator_calendario: float
    eventos_aplicados: tuple[str, ...]
```

No canonico, incluir:
- `calendario_operacional` (artefato consolidado por semana)
- `fator_calendario_semanal` por semana ISO

---

## 5. Mapeamento: oportunidades e fraquezas dos pontos 1 e 2

### 5.1 Ponto 1 - Cubo analitico

| Tipo | Item | Impacto |
|---|---|---|
| Oportunidade | O cubo ja e temporal (semana ISO), permitindo anexar fator de calendario por semana sem quebrar a granularidade 4D atual | Baixo custo de integracao |
| Oportunidade | Metodos de agregacao (`composicao_preco_temporal`, `group_by`) facilitam analise "antes/depois" de calendario | Alta explicabilidade |
| Oportunidade | Exportacao Excel ja possui secoes analiticas prontas para absorver nova metrica de calendario | Entrega incremental rapida |
| Fraqueza | Modelo atual nao tem dimensao explicita para causa civil (feriado/recesso) no cubo | Risco de leitura ambigua com clima |
| Fraqueza | UI nao expoe visual nativo do cubo; dependencia alta de Excel | Friccao de produto |
| Fraqueza | Granularidade semanal mascara efeito intrassemana (ex.: feriado no meio da semana) | Precisao limitada |

### 5.2 Ponto 2 - PE e backtracking

| Tipo | Item | Impacto |
|---|---|---|
| Oportunidade | Diagnostico ja trabalha com fatores causais; adicionar `F_CALENDARIO` e evolucao natural da estrutura | Baixo retrabalho de arquitetura |
| Oportunidade | Backtracking ja possui alavanca de timing (`T0_RAMP`) e pode usar calendario para recomendar janela melhor | Melhora decisao automatica |
| Oportunidade | API/UI de diagnostico/backtracking ja existe e permite entrega incremental sem novo canal | Time-to-value curto |
| Fraqueza | Endpoint atual e best-effort; falhas podem ocultar diagnostico de calendario | Confiabilidade de produto |
| Fraqueza | Sem separacao formal clima x calendario, risco de dupla contagem/atribuicao incorreta | Risco matematico |
| Fraqueza | Ausencia de simulador dedicado para comparar cenarios de calendario na UI/API | Baixa capacidade exploratoria |

---

## 6. Consequencias

### Positivas
| ID | Consequencia |
|---|---|
| C1 | Cronograma mais realista para janelas com feriados e recesso |
| C2 | Diagnostico de PE mais explicavel, separando causa climatica e causa civil |
| C3 | Backtracking com recomendacoes temporais mais robustas |
| C4 | Maior auditabilidade em decisoes de prazo, custo e margem |

### Riscos e custos
| ID | Risco | Mitigacao |
|---|---|---|
| R1 | Complexidade de configuracao por jurisdicao | Padrao default + heranca global |
| R2 | Regressao em cronograma existente | Feature flag e testes de paridade |
| R3 | Dupla contagem clima/calendario | Formula unica com fatores separados e validacao dedicada |
| R4 | Dados de feriados incompletos | Fallback para calendario global + validacoes de cobertura |

---

## 7. Plano de implementacao

| Fase | Entregas | Status |
|---|---|---|
| F1 | Modelo `CalendarioOperacional` + loader de configuracao | Concluido |
| F2 | Calculo `fator_calendario_semanal` e artefato no canonico | Concluido |
| F3 | Integracao no cronograma (`fator_total = clima * calendario`) | Concluido |
| F4 | Novo fator no Diagnostico PE (`F_CALENDARIO`) | Concluido |
| F5 | Backtracking com recomendacao temporal orientada por calendario | Concluido |
| F6 | Endpoints/API/UI de simulacao e visualizacao | Concluido |
| F7 | Atualizacao Excel + documentacao + testes regressivos | Concluido |

---

## 8. Definition of Done

### Fase 1-3
- [x] Calendario operacional versionado e carregado com precedencia correta
- [x] Cronograma refletindo feriados/recessos em `dias_uteis_efetivos`
- [x] Testes de paridade com calendario neutro (`fator_calendario = 1.0`)

### Fase 4-5
- [x] Diagnostico PE com `F_CALENDARIO` e sem dupla contagem com clima
- [x] Backtracking sugerindo ajuste temporal com impacto estimado em custo/prazo
- [x] Validacao roundtrip mantendo tolerancias de ADR-061

### Fase 6-7
- [x] API para consultar/simular calendario efetivo por semana
- [x] UI com visao semanal de clima x calendario x fator total
- [x] Excel com secao de calendario operacional e contribuicao no PE
