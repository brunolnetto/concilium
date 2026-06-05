# Sprint 1 - Matriz de Contratos Canonicos (NEP-026)

**Referencia:** [NEP-026](../neps/nep-026-descontinuacao-legacy-alias-lingua-franca.md)  
**Data:** 2026-05-22  
**Objetivo da sprint:** congelar lingua franca sem quebra externa.

---

## Escopo da Sprint 1

1. Publicar matriz canonica por entidade.
2. Marcar leitura legada com warning estruturado e codigo de validacao.
3. Garantir consumo interno no contrato canonico para EAP/CPU na UI de planejamento.

## Matriz canonica por entidade

### Entidade: Benchmark Reference - EAP

**Caminho canonico:** `cpus.itens_eap`

| Campo | Obrigatorio | Tipo | Regra |
|---|---|---|---|
| item_id | Sim | string | Chave de atividade na EAP |
| ordem | Sim | integer | Ordem logica na composicao |
| cpu_id | Sim | string | Codigo canonico da CPU |
| descricao | Sim | string | Descricao legivel da atividade |
| unidade | Sim | string | Unidade da atividade |
| quantitativo | Sim | number | Quantidade alvo da atividade |

**Entradas legadas aceitas apenas na fronteira (normalizacao):**

- `eap` (raiz)
- `skill_inputs.01-escopo-e-eap.eap`
- `skill_inputs.01-escopo-e-eap.inputs_escopo.eap`

**Codigo de validacao/telemetria da sprint:**

- `VAL-CONTRACT-LEGACY-EAP-SOURCE`

### Entidade: CPU de planejamento (consumo UI)

**Caminho canonico de consumo:** `cpus.itens_eap[*].cpu_id`

**Nao canonico na UI (removido no consumo principal):**

- `selected_cpu_id`
- `cpu`
- `cronograma.atividades[*].cpu_id` como fonte primaria de composicao/politica

### Entidade: BDI (estado da sprint)

**Observacao:** permanece com alias historico em parser de tela para nao ampliar escopo desta sprint.

## Regras de transicao (Sprint 1)

1. Compatibilidade legada permitida somente no backend de entrada.
2. Camadas consumidoras (UI de planejamento) devem ler apenas o contrato canonico.
3. Toda leitura de caminho legado deve emitir warning estruturado com codigo de validacao.

## Evidencias de implementacao

- `src/concilium/application/services/project_service.py`
  - normalizacao canonica de EAP
  - warning estruturado `VAL-CONTRACT-LEGACY-EAP-SOURCE`
- `src/concilium/presentation/ui/helpers/helpers.py`
  - extracao de politicas EAP apenas em `cpus.itens_eap`
- `src/concilium/presentation/ui/organisms/layout.py`
  - extracao de CPUs baseada apenas em `cpu_id` canonico
- `tests/unit/test_benchmark_reference_contract.py`
  - cobertura de normalizacao e consumo canonico
