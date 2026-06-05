# ADR-039 — Compensação de Ineficiências Estruturais no Confronto de Benchmarks

**Status:** Implementado  
**Data:** 2026-05-08  
**Atualizado:** 2026-05-15  
**Contexto:** MendesLobo Construtora — Concilium

---

## Estado de Implementação (2026-05-15)

| Fase | Item | Status |
|---|---|---|
| F1 — BridgeAnalyzer | Classe de domínio com 4 níveis | ✅ `domain/services/bridge_analyzer.py` |
| F1 | BridgeAnalysis dataclass imutável + propriedades derivadas | ✅ |
| F1 | **26 testes unitários** cobrindo: F_i<1, P=0.83, delta real isolado, VERDE/AMARELO/VERMELHO, validações | ✅ `tests/unit/test_bridge_analyzer.py` |
| F2 — Skill 08 | Integração BridgeAnalyzer na Consolidação Financeira | ✅ `skills/08-consolidacao-financeira/skill.py` |
| F2 | Injeção em `canonical.bridge_analysis` | ✅ |
| F2 | Validações VAL-BRIDGE-OK / VAL-BRIDGE-WARN | ✅ |
| F3 — Skill 15 | **Seção waterfall no Relatório Executivo** | ✅ `skills/15-relatorio-executivo/skill.py` |
| F3 | Nota metodológica embutida no artefato | ✅ |
| F3 | Validação VAL-REX-BRIDGE com status VERDE/AMARELO/VERMELHO | ✅ |

### Nota sobre F2 — Extração automática de necessidades_fracionadas

A lista `necessidades_fracionadas` é recebida via `inputs.get("necessidades_fracionadas", [])` na Skill 08. A extração automática a partir das atividades do cronograma requer integração com a Skill 04 (Cronograma) — implementada como passagem de parâmetro manual por ora. A lógica `calcular_necessidade_fracionada(Q, P, T)` está disponível em `BridgeAnalyzer` para uso direto.

---

## Contexto

### Problema

A auditoria sistemática de projetos de infraestrutura revelou divergências superiores a 100% entre o **Custo Direto de Catálogo (Metodologia B)** e o **Custo Operacional de Equipes (Metodologia A)**. Esse delta bruto tornava os relatórios de confronto alarmistas e comercialmente indefensáveis:

- **P1 — Quantização de Escala (Arredondamento Inteiro de Equipes):** Obras de prazo engessado forçam a mobilização de números *inteiros* de equipes. Se a matemática indica 3,34 frentes, a construtora paga por 4,00. O catálogo cobre apenas a fração ideal (3,34 × CPU); o operacional cobre 4 × custos fixos mensais. A diferença é estrutural, não ineficiência operacional.
- **P2 — Impacto Climático (Janela de Praticabilidade):** A CPU assume aproveitamento teórico de 100% do tempo disponível. A operação remunera disponibilidade (salários mensais, aluguel de equipamentos), mas produz apenas dentro da janela útil (ex: 83% no Espírito Santo em período chuvoso). O catálogo não penaliza esse percentual; o caixa sim.
- **P3 — Delta Real Mascarado:** Ao somar os dois fatores acima, um desvio genuinamente baixo de gestão (ex: 10%) aparece no relatório bruto como 124%. A diretoria reage a um alarmismo que não corresponde à realidade de campo.
- **P4 — Ausência de Hierarquia de Responsabilidade:** Sem a separação dos fatores, não é possível responder "quem é responsável por este desvio?": Catálogo/Orçamentista (erro de calibração), Diretoria/Contrato (decisão de escala de prazo) ou Natureza (chuva).

---

## Decisão

### D1 — Arquitetura de Compensação em Cascata ("The Bridge")

O confronto entre Catálogo e Operacional passará por estágios sequenciais de compensação, cada um isolando e quantificando um tipo de ineficiência:

#### Nível 1 — Catálogo Base (Puro)
Ponto de partida linear tradicional, sem qualquer compensação.

$$C_{cat} = \sum_{i} \left( Q_i \times PU_i \right)$$

#### Nível 2 — Catálogo Escalado (Fator Quantização)
Majora o catálogo pela razão de arredondamento das equipes técnicas por atividade.

$$C_{escala} = \sum_{i} \left[ (Q_i \times PU_i) \times \frac{\lceil F_i \rceil}{F_i} \right]$$

Onde $F_i$ é a necessidade técnica fracionada de equipes para a atividade $i$: $F_i = \frac{Q_i}{P_i \times T}$.

*Impacto isolado:* Absorve o custo morto da ociosidade forçada por escala de prazo.

#### Nível 3 — Catálogo Normalizado (Fator Clima)
Aplica o redutor de praticabilidade geográfico $P \in (0, 1]$ do regime pluviométrico da obra.

$$C_{clima} = \frac{C_{escala}}{P}$$

*Impacto isolado:* Absorve o custo de oportunidade de frentes de serviço paradas aguardando condições de campo.

#### Nível 4 — Custo Operacional (Realidade)
O custo efetivamente medido no campo. O delta real e auditável é a diferença entre Nível 3 e Nível 4.

$$\Delta_{real} = C_{operacional} - C_{clima}$$

### D2 — Diagrama Conceitual (The Bridge)

```mermaid
flowchart LR
    A["Nível 1: Catálogo Base\nEx: R$ 9,1 M"] -->|"+ Erro de Escala\n(ceil de Frentes)"| B
    B["Nível 2: Catálogo Escalado\nEx: R$ 15,4 M"] -->|"+ Fator Chuva\n(Praticabilidade 83%)"| C
    C["Nível 3: Catálogo Normalizado\nEx: R$ 18,5 M"] -->|"+ Consumo/Suporte Ocioso\n(Ineficiências Reais)"| D
    D["Nível 4: Operacional de Equipes\nEx: R$ 20,4 M"]

    style A fill:#e1f5fe,stroke:#0288d1
    style B fill:#fff3e0,stroke:#f57c00
    style C fill:#fce4ec,stroke:#c2185b
    style D fill:#e8f5e9,stroke:#388e3c
```

### D3 — Extração do Fator $F_i$ na Skill 06

A Skill 06 (Consolidação Financeira) será refatorada para extrair a necessidade técnica fracionada de cada atividade:

```python
def calcular_necessidade_fracionada(
    quantidade: float,
    produtividade: float,    # m3/h ou m/h da equipe
    horas_disponiveis: float # horas no período de execução
) -> float:
    """Retorna F_i = Q / (P × T). Se > 1, há necessidade de múltiplas frentes."""
    return quantidade / (produtividade * horas_disponiveis)
```

### D4 — Injeção no Artefato Canônico

Os resultados de "The Bridge" são injetados no JSON de saída da Skill 06 como sub-estrutura `actionable_insights.bridge_analysis`:

```json
{
  "actionable_insights": {
    "bridge_analysis": {
      "nivel_1_catalogo_base": 9100000.00,
      "nivel_2_catalogo_escalado": 15400000.00,
      "nivel_3_catalogo_normalizado": 18500000.00,
      "nivel_4_operacional": 20400000.00,
      "delta_real_percentual": 10.27,
      "fator_quantizacao": 1.691,
      "fator_praticabilidade": 0.83,
      "desvio_escala": 6300000.00,
      "desvio_clima": 3100000.00,
      "desvio_operacional_real": 1900000.00
    }
  }
}
```

### D5 — Renderização na Skill 15 (Relatório Executivo)

O Relatório Executivo renderizará "The Bridge" como um gráfico waterfall, apresentando cada nível com sua contribuição individual ao desvio. O modelo deve apresentar o `delta_real_percentual` como o número principal de desvio, não o delta bruto.

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo da Rejeição |
|---|---|---|
| X1 | Aceitar o delta bruto como métrica de desvio oficial | Indefensável comercialmente; cria alarmes falsos que prejudicam a credibilidade do time de planejamento. |
| X2 | Corrigir o catálogo para refletir os custos de quantização | Contamina o benchmark unitário da empresa com ineficiências de contratos específicos; viola o princípio de separação de camadas do catálogo. |
| X3 | Fator de praticabilidade fixo por estado | Granularidade insuficiente; o regime pluviométrico varia por microrregião e por período do ano. Usar praticabilidade configurável por escopo/jurisdição. |

---

## Consequências

### Positivas

| ID | Consequência |
|---|---|
| C1 | **Governança de responsabilidade:** O relatório distingue matematicamente culpa do Orçamentista (Nível 1→2 não), da Diretoria/Contrato (Nível 1→2: escala/prazo) e da Natureza (Nível 2→3: chuva). |
| C2 | **Saneamento de relatórios:** Desvio real de ~10% no lugar de ruído bruto de ~124%; relatório defensável em reunião de diretoria. |
| C3 | **Análise sensitiva otimizada:** Evidencia que a maior alavanca financeira em obras sub-escaladas é alterar o cronograma para diluir o $\lceil F_i \rceil / F_i$. |
| C4 | **Reaproveitamento:** `bridge_analysis` alimenta a Skill 19 (Cenários) para simular o impacto de flexibilização de prazo. |

### Negativas / Riscos

| ID | Risco | Mitigação |
|---|---|---|
| R1 | Aumento de complexidade analítica na Skill 06. | Encapsular todo o cálculo em `BridgeAnalyzer` como classe de domínio separada, testável isoladamente. |
| R2 | Fator de praticabilidade $P$ pode não estar cadastrado no escopo. | Usar $P = 1.0$ como default (sem penalidade climática); emitir warning no relatório. |
| R3 | Treinamento do time: leitura do "Custo de Confronto Normalizado" requer entendimento do modelo. | Adicionar nota metodológica fixa no topo do relatório executivo explicando os 4 níveis. |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| **F1 — `BridgeAnalyzer`** | Classe de domínio com os 4 cálculos e extração de $F_i$ | ✅ Implementado |
| **F2 — Skill 06** | Integração do `BridgeAnalyzer`; injeção em `canonical.bridge_analysis` | ✅ Implementado |
| **F3 — Skill 15** | Renderização do gráfico waterfall e nota metodológica no relatório | ⏳ Pendente |
| **F4 — Testes** | Casos: obra com $F_i < 1$ (sem quantização), $P = 0.83$, delta real isolado | ⏳ Pendente |

---

## Definition of Done

### Fase 1 — `BridgeAnalyzer` (✅)
- [x] Classe `BridgeAnalyzer` criada em `domain/services/bridge_analyzer.py`.
- [x] Métodos: `calcular_necessidade_fracionada()`, `fator_quantizacao_medio()`, `calcular()` (integrado).
- [x] `BridgeAnalysis` é um dataclass imutável com 4 níveis, fatores e desvios por responsabilidade.
- [x] Propriedades derivadas: `delta_estrutural_abs`, `delta_estrutural_percentual`, `status_alerta` (VERDE/AMARELO/VERMELHO).
- [ ] Testes unitários para os 4 níveis com valores de referência do projeto PRIVATE_LOG.

### Fase 2 — Skill 06 (✅)
- [x] Skill 06 integra `BridgeAnalyzer.calcular()` com `nivel_1 = venda_sem_bdi`, `praticabilidade` de `inputs`.
- [x] `canonical.bridge_analysis` (dict) injetado no artefato canônico com todos os 4 níveis e `status_alerta`.
- [x] Fator de praticabilidade lido de `inputs["praticabilidade"]` com fallback para `1.0`.
- [x] Validação `VAL-BRIDGE-OK` / `VAL-BRIDGE-WARN` emitidas conforme resultado.
- [ ] `necessidades_fracionadas` extraídas automaticamente das atividades do cronograma.

### Fase 3 — Skill 15
- [ ] Relatório executivo renderiza waterfall com Níveis 1→4.
- [ ] `delta_real_percentual` é o número de destaque, não o delta bruto.
- [ ] Nota metodológica fixa explica os 4 níveis e a responsabilidade de cada agente.
