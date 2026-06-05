# ADR-059: Permanência de Recursos sem Dismissal — Construção de Cronograma Baseada no Espaço Ontológico

**Status:** Aceito  
**Data:** 2026-05-16  
**Autor:** Engenheiro Sênior  
**Relacionado:** ADR-004 (Scheduling Algorithms), ADR-016 (Resource Sharing Taxonomy), ADR-030 (CPU Team Composition), ADR-046 (RCPSP), ADR-054 (WMP)

---

## 1. Contexto

### 1.1 O Problema

O RCPSP atual modela recursos como **tipos contáveis e homogêneos** (`ResourcePool: dict[tipo_id → quantidade]`). Uma escavadeira HID-38T na atividade A é indistinguível de uma escavadeira na atividade B — o solver apenas garante que a demanda total não excede a capacidade do tipo.

Isso cria um conflito com a realidade da obra:

```
Atividade A (eap-1_0): Escavação de corte  —  semanas 1–8   usa 1× ESCAV-HID-38T
Atividade B (eap-2_0): Retaludamento        —  semanas 9–12  usa 1× ESCAV-HID-38T
```

O RCPSP não modela a continuidade. Na perspectiva do modelo:
- A acaba na semana 8 → **ESCAV-HID-38T demobiliza**
- B começa na semana 9 → **ESCAV-HID-38T mobiliza**

Na obra real:
- A mesma escavadeira, que estava operando, simplesmente prossegue
- **Não há custo de remobilização** — ela nunca saiu
- O custo de `MOB` deve ser pago **uma única vez** para o período contínuo W1–W12

A diferença financeira pode ser significativa: mobilização de uma escavadeira pode custar R$15.000–R$50.000. Se o modelo a cobra duas vezes (para A e para B), a proposta de preço está incorreta.

### 1.2 O Espaço Ontológico Já Contém a Solução

O modelo já tem:
- `CPU.composicao_padrao_equipe.equipamentos[i].equip_id` — qual equipamento
- `EquipeDireta.equipamentos[i]` — por atividade, qual equipamento e quantas unidades
- `IndiretoSemanal[MOB]` — custo de mobilização existe como categoria
- `Alocacao` — model de alocação de recurso a atividade

O que **falta** é:
1. **Identidade de instância**: "a escavadeira #1 específica" — hoje só há "1 unidade do tipo ESCAV-HID-38T"
2. **Cadeia de permanência**: A → B → C usando o mesmo equipamento continuamente
3. **Regra de dismissal/retenção**: quando o equipment deve ser retornado vs. mantido
4. **Custo de permanência idle**: custo de manter o equipamento em standby entre atividades (menor que demob+remob)

### 1.3 Conexão com WMP (ADR-054)

A política de mobilização (WMP) define como as equipes rampeiam ao longo de uma atividade. Mas equipes diferentes podem compartilhar o mesmo equipamento. Um `n(t)` de 3 equipes implica 3 escavadeiras — mas se a próxima atividade também usa 3 escavadeiras do mesmo tipo, elas não precisam ser substituídas.

O WMP atua sobre a equipe por atividade. A permanência atua sobre o equipamento através de atividades.

---

## 2. Análise do Espaço Ontológico para Permanência

### 2.1 Grafo de Compartilhamento de Recursos

O espaço ontológico permite construir, por projeto, um grafo:

```
Vértices: (atividade, equip_id, num_unidades)
Arestas:  (atividade_A, atividade_B) se compartilham equip_id E o intervalo de A termina
           ≤ δ semanas antes do início de B (δ = buffer de tolerância)
```

Esse grafo identifica naturalmente os **candidatos a permanência** — atividades que, se sequenciadas adequadamente, não precisam demobilizar o equipamento entre si.

### 2.2 Campanha de Equipamento

Uma **campanha** é o período contínuo durante o qual um equipamento permanece no canteiro, servindo a uma ou mais atividades:

```
Campanha(ESCAV-HID-38T, unidade=1):
    semana_entrada:  1
    semana_saida:    12
    atividades:      [eap-1_0 (1–8), eap-2_0 (9–12)]
    custo_mob:       R$ 15.000  (pago uma vez)
    custo_standby:   R$ 0       (sem intervalo entre atividades)
    custo_demob:     R$ 10.000  (pago uma vez)
    custo_total_mob: R$ 25.000

vs. sem campanha (dismissal entre atividades):
    eap-1_0: mob(R$15k) + demob(R$10k) = R$25.000
    eap-2_0: mob(R$15k) + demob(R$10k) = R$25.000
    total: R$50.000 — duplicação desnecessária de R$25.000
```

### 2.3 Custo de Standby (Idle Period)

Quando há um intervalo entre atividades que compartilham equipamento, o planejador tem três opções:

| Opção | Custo | Quando preferir |
|-------|-------|----------------|
| **Permanência** (keep on site) | custo_aluguel_idle × semanas_idle | intervalo ≤ threshold |
| **Dismissal** (devolver e remobilizar) | mob + demob | intervalo > threshold ou equipamento escasso |
| **Compartilhamento** (outra atividade usa no intervalo) | 0 custo adicional | existe atividade B compatível no intervalo |

O threshold de decisão permanência vs. dismissal é:
```
threshold(equip_id) = (custo_mob + custo_demob) / custo_aluguel_semanal_idle
```

Se o intervalo idle ≤ threshold, é mais barato manter o equipamento em standby.

---

## 3. Lacunas no Modelo Atual

### L1 — Sem identidade de instância de equipamento

`ResourcePool` e `EquipamentoEquipeDireta` rastreiam apenas `num_unidades: int`. Para modelar campanhas, precisamos de **instâncias nomeadas**:

```python
# Proposto:
@dataclass(frozen=True)
class InstanciaEquipamento:
    instancia_id: str          # "ESCAV-HID-38T#1", "ESCAV-HID-38T#2"
    tipo_id: str               # "ESCAV-HID-38T"
    custo_mob: float           # R$ para trazer ao canteiro
    custo_demob: float         # R$ para remover do canteiro
    custo_standby_semanal: float  # R$ por semana idle no canteiro
```

### L2 — Sem modelo de campanha de equipamento

```python
@dataclass(frozen=True)
class CampanhaEquipamento:
    instancia_id: str
    semana_entrada: int
    semana_saida: int
    atividades: list[str]      # ordered list of activity_ids during campaign
    semanas_ativas: int        # semanas com trabalho efetivo
    semanas_standby: int       # semanas idle dentro da campanha
    custo_mob_total: float     # mob + demob (once per campaign)
    custo_standby_total: float # standby_semanal × semanas_standby
    custo_campanha: float      # total
```

### L3 — Sem regra de compartilhamento entre atividades

O RCPSP resolve conflitos de recurso por nível (leveling) mas não por sequência. A regra "se A e B usam o mesmo equipamento e A termina na semana K e B começa em K+1, não desmobilize" requer uma **constraint de continuidade** que o solver não tem.

### L4 — Sem custo de mobilização por instância no MOB

`Indireto[MOB]` existe, mas é uma verba fixa ou mensal, não ligada a `equip_id` específico. O custo de MOB por instância precisa ser derivado do catálogo de equipamentos.

### L5 — RCPSP não conhece o histórico de alocação para continuidade

O SGS (Serial Generation Scheme) do RCPSP decide o start time de cada atividade independentemente. Não tem acesso a "quais instâncias estão atualmente no canteiro" para decidir se pode aproveitar a permanência.

---

## 4. Decisões

### D1 — `InstanciaEquipamento` como novo value object

Adicionar ao domínio. Derivado do catálogo de equipamentos quando o projeto é criado ou quando a alocação é planejada. Não modela identidade física real — é uma identidade lógica para rastreamento de custo.

### D2 — `CampanhaEquipamento` como artifact gerado pelo otimizador de permanência

Derivado após o RCPSP resolver o cronograma. Para cada `equip_id` no projeto, analisa as atividades que o usam e determina campanhas ótimas: quais grupos de atividades devem compartilhar uma campanha vs. quais justificam dismissal.

### D3 — Regra de permanência como restrição de custo no scheduler

Introduzir `ResourcePermanenceRule` como pré-processamento do RCPSP:

```
Para cada par (A, B) de atividades que compartilham equip_id E:
    se sequencia_proposta(A, B) e gap(A,B) ≤ threshold(equip_id):
        adicionar restrição: custo_campanha(A,B) < custo_mob(A) + custo_mob(B)
        marcar par como candidato a campanha compartilhada
```

Isso não substitui o RCPSP — o RCPSP ainda decide start times. Mas o **objetivo** é enriquecido com o custo de campanh vs. dismissal.

### D4 — `canonical.campanhas_equipamento` como campo opcional

Análogo a `curvas_forca` (ADR-054) — derivado e auditável, não prescritivo:

```python
campanhas_equipamento: list[CampanhaEquipamento] = Field(default_factory=list)
```

Populado por um novo serviço `CampanhaEquipamentoBuilder` após a geração do cronograma.

### D5 — Integração com WMP (ADR-054)

A política WMP define `n(t)` por atividade. A análise de campanha usa essa curva para determinar quais semanas de cada atividade têm `n > 0` — só semanas ativas implicam equipamento em uso. Semanas com `n = 0` contribuem para `semanas_standby` da campanha.

### D6 — Alertas de custo duplicado de mobilização

Quando o solver não otimiza campanhas (e.g., atividades não consecutivas), emitir `VAL-CAMP-01` como alerta quando `custo_mob × 2 < custo_standby_total` — ou seja, quando seria mais barato manter o equipamento do que demobilizar e remobilizar.

---

## 5. Regras de Construção do Cronograma Derivadas do Espaço Ontológico

### R1 — Precedência por compartilhamento de equipamento

Se A usa `ESCAV-HID-38T#1` e B usa `ESCAV-HID-38T#1`, e o canteiro tem apenas 1 unidade:
- Não é apenas uma precedência de capacidade (o que o RCPSP já modela)
- É também uma oportunidade de **redução de custo** se A precede B diretamente

O scheduler pode priorizar essa sequência.

### R2 — Afinidade de equipe (crew continuity)

Se `FuncaoEquipe["OPER-ESCAV"]` aparece em A e em B, e o operador é o mesmo (por exemplo, ele está especializado nesse equipamento e não pode ser facilmente substituído), então A → B deve ser contíguo ou ter gap mínimo.

O espaço ontológico já tem `funcao_id` por atividade. A regra é:
```
Se mesma funcao_id em atividades consecutivas E funcao tem papel "direto":
    minimizar gap entre fim de A e início de B
```

### R3 — Threshold de dismissal como parâmetro configurável

```python
@dataclass(frozen=True)
class RegimePermanencia:
    equip_id: str
    custo_mob: float
    custo_demob: float
    custo_standby_semanal: float
    threshold_semanas: float   # = (mob + demob) / standby_semanal
    # Se gap ≤ threshold → campanha compartilhada
    # Se gap > threshold → dismissal (mais barato remobilizar)
```

### R4 — Sequenciamento de atividades por campanha ótima

Ao definir prioridades no RCPSP (Activity Priority Rules):
- Atividade B que compartilha equipamento com A em campanha → prioridade aumentada para ser agendada imediatamente após A
- MINSLK (Minimum Slack) já aproxima disso; adicionar `campanha_bonus` ao cálculo de prioridade

---

## 6. Consequências

### Positivas
- Eliminação de duplicidade de custo MOB para equipamentos permanentes
- Proposta de preço mais precisa (nem super nem subdimensionada em mobilização)
- Visibilidade explícita do plano de frota (quais equipamentos entram e saem em que semanas)
- Base para gestão consciente de recursos alugados vs. próprios

### Negativas / Riscos
- Instâncias de equipamento são lógicas, não físicas — o modelo não rastreia qual máquina específica está em qual obra (isso seria gestão de frota)
- `threshold_semanas` é sensível ao regime de aluguel vs. mobilização — precisa ser configurável por projeto
- O otimizador de campanha adiciona complexidade ao pipeline de scheduling

---

## 7. Questões Abertas

### Q1 — Equipamento próprio vs. alugado
O modelo de campanha é mais relevante para equipamentos alugados (custo de mobilização definido pelo contrato). Para equipamentos próprios, o custo pode ser diferente (depreciação, transporte). O `RegimePermanencia` deve ter um campo `modalidade: "aluguel" | "proprio"` que influencia os valores de mob/demob/standby.

### Q2 — Compartilhamento entre lotes
Se o projeto tem múltiplos lotes/frentes, uma escavadeira pode estar em uso no Lote A enquanto o Lote B aguarda. O modelo de campanha deve funcionar por `(projeto_id, lote_id)` para suportar múltiplas frentes simultâneas.

### Q3 — Integração com gestão real de frota
ADR-059 modela permanência para fins de **precificação e planejamento**, não para rastreamento físico de ativos. A integração com sistemas de gestão de frota (ERP, telemetria) é um trabalho futuro.

---

## 8. Plano de Implementação

| Fase | Entrega | Prioridade |
|------|---------|-----------|
| 1 | `InstanciaEquipamento` + `RegimePermanencia` como value objects | Alta |
| 1 | `CampanhaEquipamento` + `CampanhaEquipamentoBuilder` serviço puro | Alta |
| 2 | `canonical.campanhas_equipamento` field | Alta |
| 2 | `CampanhaEquipamentoBuilder.build()` pós-Skill 04 | Alta |
| 3 | `VAL-CAMP-01`: alerta de custo duplicado de mobilização | Média |
| 3 | Integração com Skill 05: ajustar custo MOB para campanhas detectadas | Média |
| 4 | `ResourcePermanenceRule` como pré-processamento opcional do RCPSP | Média |
| 4 | `campanha_bonus` no Activity Priority Rule do scheduler | Baixa |
| 5 | Export Excel: aba `CAMPANHA.FROTA` com plano de entrada/saída de equipamentos | Baixa |
