---
name: 09-registro-decisoes
description: Use when recording the justification for a human decision about which interventions to apply (or not apply) to a project version.
---

# Skill 11 — Decision Log

Registra justificativa de uma decisão tomada pelo humano sobre quais intervenções aplicar (ou não aplicar) em uma versão do projeto. Não computa nada — apenas estrutura e persiste o raciocínio.

> **Skill transversal.** Diferente das skills 00-10 que têm posição fixa no pipeline, esta pode ser invocada a qualquer momento que uma decisão importante seja tomada — após análise de criticidade, após comparação de cenários, ao aprovar uma versão.

## Quando ativar

Sempre que uma decisão modificar inputs do projeto e gerar uma nova versão. Ou quando uma decisão for explicitamente "não fazer nada" (preservar inputs atuais) — também merece registro.

## Princípio fundamental

```
Decision logs justificam escolhas.
Não computam escolhas.
```

A skill não pode decidir. Apenas estrutura o que o humano decidiu, suas alternativas consideradas, e por que rejeitou as outras.

## Inputs

| Nome | Tipo | Origem | Obrigatório |
|------|------|--------|-------------|
| `decision_id` | string | Gerado | sim |
| `project_version` | string | Canônico atual | sim |
| `objective` | string | Usuário | sim |
| `constraints[]` | array | Usuário | não |
| `considered_interventions[]` | array | Canônico (skill 10) | sim |
| `selected_intervention` | string ou null | Usuário | sim |
| `justification` | object | Usuário | sim |
| `decided_by` | object | Usuário | sim |

**Modo lean (versão mínima viável)**:
```json
{
  "selected": "regime_6d",
  "objective": "reduzir prazo",
  "main_tradeoff": "menor margem vs menor risco",
  "rejected": ["produtividade_terraplenagem"],
  "timestamp": "2026-04-25T18:00:00Z"
}
```

Modo lean é suficiente para começar. Estrutura completa pode ser adotada quando o time amadurecer.

## Depende de

**Skills predecessoras**:
- [`08-avaliacao-intervencoes`](../08-avaliacao-intervencoes/SKILL.md) — fornece classificação das intervenções consideradas
- Qualquer skill anterior que tenha gerado dados referenciados na justificativa

**Recursos consumidos**: nenhum externo.

## Produz

**Artefato**: `decision_log.json` salvo em `projetos/{uuid}/v{N}/decision_log.json`.

Estrutura completa:
```json
{
  "decision_id": "dec_001",
  "project_version": "v3",
  "context": {
    "objective": "reduzir prazo mantendo margem mínima de 18%",
    "constraints": ["prazo máximo: 520 dias", "limite de CAPEX adicional"]
  },
  "considered_interventions": [
    {
      "variavel": "produtividade_terraplenagem",
      "matrix_position": "HIGH_ROI / HIGH_EFFORT / MED_RISK",
      "decision_class": "strategic_move"
    },
    {
      "variavel": "regime_6d",
      "matrix_position": "MED_ROI / MED_EFFORT / LOW_RISK",
      "decision_class": "balanced_tradeoff"
    }
  ],
  "selected_intervention": "regime_6d",
  "justification": {
    "primary_driver": "redução de prazo com risco controlado",
    "tradeoffs": [
      "menor ganho de margem comparado à produtividade",
      "aceitável devido à restrição de prazo"
    ],
    "rejected_reasons": [
      {
        "variavel": "produtividade_terraplenagem",
        "reason": "alto esforço e necessidade de CAPEX imediato"
      }
    ]
  },
  "expected_outcome": {
    "margem": 0.20,
    "prazo_dias": 515
  },
  "decision_type": "balanced_tradeoff",
  "decided_by": {
    "type": "human",
    "id": "engenheiro_responsavel"
  },
  "timestamp": "2026-04-25T18:00:00Z"
}
```

**Validações**:
- `VAL-DEC-01` (ERRO): `selected_intervention` ou explicitamente `null` — não pode ser indefinido
- `VAL-DEC-02` (ERRO): `considered_interventions` não vazio (pelo menos uma alternativa avaliada)
- `VAL-DEC-03` (AVISO): se houver intervenções consideradas mas rejeitadas, `rejected_reasons` deve listá-las

## Princípios não-negociáveis

- **Trade-offs explícitos.** O que se ganha e o que se sacrifica. Sem isso, decisão não é auditável.
- **Rejeição é obrigatória registrar.** Por que outras opções não foram escolhidas. Previne racionalização pós-hoc.
- **Reference, don't duplicate.** Não recomputa ROI, risk, effort — apenas referencia valores das skills anteriores.
- **Objetivos explícitos.** Mesmo que informais, declarar o que se quer otimizar (prazo, margem, risco). Prevenir objetivos implícitos escondidos.

## O que NÃO fazer

- **Auto-gerar justificativa via LLM.** Decisão precisa ser do humano. LLM pode ajudar a estruturar a justificativa que o humano escreveu, mas não inventar razões.
- **Omitir intervenções rejeitadas.** Apenas registrar a vencedora destrói o contexto.
- **Editar log retroativamente.** Após criação, log é imutável. Mudança de opinião gera novo decision_log com referência ao anterior.

## Notas de implementação

- **Modo lean para começar.** Os 5 campos mínimos (selected, objective, main_tradeoff, rejected, timestamp) já previnem o pior dos cenários — não saber por que algo foi feito daqui a 6 meses.
- **Vinculação à versão.** Decision log pertence a uma versão específica do projeto (DEC-15: append-only). Se a decisão mudar inputs, nova versão é criada e novo decision_log a justifica.
- **Decided_by pode ser papel ou pessoa.** No mínimo, registrar que humano (não sistema) tomou a decisão. Ideal: identificação específica para auditoria.

## Posição no pipeline

Fase **Decisão** — último passo antes da renderização final (10-relatorio-e-artefatos).
Documenta a decisão humana tomada com base nos outputs de 09, 10, 13 e 14.
