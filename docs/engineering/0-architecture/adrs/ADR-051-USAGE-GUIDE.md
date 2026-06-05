# ADR-051: Validação Convergente de Preço Unitário — Guia de Uso

## Visão Geral

O sistema de validação em duas camadas ajuda a:
1. **Detectar inconsistências de composição/produção no catálogo** (isoladamente).
2. **Validar convergência entre hipótese construtiva e PU calculado** no pipeline de projeto.
3. **Rastrear desvios por categoria** (MO vs EQ vs DIESEL vs MATERIAL).
4. **Apoiar auditoria e refinamento de referências de planilha**.

---

## Camada 1: Validação de Catálogo (Estático)

### Quando usar
- Auditoria de governança do catálogo.
- Após atualizar composições ou produtividades de CPUs.
- Como linha de defesa antes de usar CPU em projeto.

### Como usar

#### Via CLI Script
```bash
python scripts/audit_pu_catalogo.py --contexto mendeslobo --output report_pu.json
```

**Saída**: relatório JSON com status (VERDE/AMARELO/VERMELHO) para cada CPU.

#### Programaticamente
```python
from concilium.domain.services.validador_pu_catalogo import validar_pu_catalogo
from concilium.config.loaders import load_catalogo
from concilium.infrastructure.repositories.insumo import RepositorioInsumo

catalogo = load_catalogo("mendeslobo")
repo = RepositorioInsumo(catalogo)

producoes_lookup = {p["id"]: p for p in catalogo["producoes"]}
insumos_lookup = {i["codigo"]: i for i in catalogo["insumos"]}

cpu = catalogo["cpus"][0]  # Exemplo

resultado = validar_pu_catalogo(
    cpu=cpu,
    producoes_lookup=producoes_lookup,
    insumos_lookup=insumos_lookup,
    repo=repo,
)

print(f"CPU {resultado.cpu_id}: {resultado.status_convergencia}")
print(f"  Desvio: {resultado.desvio_pct:.2f}%")
print(f"  PU teórico: R$ {resultado.pu_teorico_sem_bdi:.6f}")
print(f"  PU catalogado: R$ {resultado.pu_catalogado_sem_bdi:.6f}")

# Desvios por categoria
for cat, conv in resultado.detalhes.items():
    print(f"    {cat}: {conv.status} (desvio={conv.desvio_pct:.2f}%)")
```

### Interpretação de Status

| Status | Significado | Ação Recomendada |
|--------|-------------|-----------------|
| **VERDE** | Desvio ≤ 5% | OK — nenhuma ação necessária |
| **AMARELO** | 5% < Desvio ≤ 10% | AVISO — revisar composição ou atualizar catálogo |
| **VERMELHO** | Desvio > 10% | ERRO — investigar inconsistência antes de usar em projeto |

### Desvios por Categoria

Se desvio total é alto, examine `resultado.detalhes`:
```python
for cat, conv in resultado.detalhes.items():
    if conv.status != "VERDE":
        print(f"{cat}: teorico={conv.pu_teorico}, planejado={conv.pu_planejado}")
```

Identifique qual categoria diverge e corrija no catálogo.

---

## Camada 2: Validação de Convergência (Dinâmico)

### Quando usar
- **Automaticamente** durante execução de skill 06 (Precificação).
- **Manualmente** para debugar desvios após precificação.

### Execução Automática

A skill 06 (Precificação) já integra validação de convergência:

```python
# Dentro da skill, após calcular planejamento:
from concilium.domain.services.validador_pu_convergencia import validar_convergencia_pu

conv = validar_convergencia_pu(
    item=item,
    cpu=cpu,
    equipe=equipe,
    cronograma=cronograma,
    planejamento=planejamento,
    horas_dia=regime.horas_dia,
    dias_semana=regime.dias_semana,
)

# Validações aparecem no log e no relatório final
```

### Interpretação de Resultado

```python
resultado.status_convergencia  # "VERDE", "AMARELO", "VERMELHO"
resultado.desvio_pct_total     # desvio total em %
resultado.desvio_por_categoria # {"material": {...}, "diesel": {...}, ...}
resultado.modo_precificacao    # "PLANILHA_FIRST", "COMPOSICAO", "PARAMETRICO"
resultado.raiz_diagnostico    # "OK", "EQUIPAMENTO_SEM_DECOMP", "CRONOGRAMA_AUSENTE", ...
```

### Exemplo: Debugar Desvio Alto

```python
# Do resultado de convergência
if conv.status_convergencia == "VERMELHO":
    print(f"Item {conv.item_id}: desvio={conv.desvio_pct_total:.2f}%")
    print(f"  Raiz diagnosticada: {conv.raiz_diagnostico}")
    print(f"  Modo de precificação: {conv.modo_precificacao}")
    
    for cat, desvio in conv.desvio_por_categoria.items():
        if desvio["desvio_pct"] > 5:
            print(f"    {cat}: teorico={desvio['teorico']:.4f}, planejado={desvio['planejado']:.4f}")
```

---

## Matriz de Decisão: O que Fazer Quando Desvio é Alto?

### Camada 1 (Catálogo)

**Se CPU está em VERMELHO**:
1. Verifique `resultado.detalhes` para saber qual categoria diverge.
2. Se é EQUIPAMENTO:
   - Confirme se equipamento tem `decomposicao_equip` definida.
   - Se não, adicione decomposição ou use ponderação padrão (70% MO / 30% DIESEL).
3. Se é PRODUÇÃO:
   - Verifique `producao_horaria` ou `producao_id`.
   - Recalibre contra obra real se disponível.
4. Se é INSUMO:
   - Verifique se insumo está catalogado com preço correto.
   - Atualize preços desatualizados.

### Camada 2 (Projeto)

**Se item está em VERMELHO**:
1. Verifique `raiz_diagnostico`:
   - `CRONOGRAMA_AUSENTE`: Cronograma não foi gerado (skill 04 falhou?).
   - `EQUIPE_AUSENTE`: Equipe não foi dimensionada (skill 05 falhou?).
   - `PERMANENCIA_ZERO`: Equipe tem permanência=0 (cronograma vazio?).
   - `EQUIPAMENTO_CUSTO_ZERO`: Equipamento sem custo mensalizado.
   - `OK`: Precondições OK, mas fórmula diverge.

2. Se raiz é `OK`, examine `desvio_por_categoria`:
   - Qual categoria (MO/EQ/DIESEL/MAT) diverge mais?
   - Isso pode indicar: produção super/subestimada, eficiência mal calculada, composição parametrizada incorretamente.

3. Opções de ação:
   - **Refinamento de cronograma**: Ajustar `distribuicao_semanal` (num_equipes, eficiência).
   - **Recalibração de equipe**: Atualizar `composicao_padrao_equipe` (funcões, equipamentos).
   - **Override de PU**: Se justified, usar `planejamento_item_overrides` para corrigir.

---

## Exemplo Completo: Auditoria + Debugging

### Passo 1: Auditar Catálogo
```bash
python scripts/audit_pu_catalogo.py --contexto mendeslobo --output audit.json
```

Resultado:
```json
{
  "resumo": {"verde": 150, "amarelo": 12, "vermelho": 3},
  "resultados": [
    {
      "cpu_id": "ESCO-CARGA-CAT",
      "status_convergencia": "VERMELHO",
      "desvio_pct": 15.3,
      "detalhes": {
        "equipamentos": {"status": "VERMELHO", "desvio_pct": 25.2},
        ...
      }
    }
  ]
}
```

**Ação**: Revisar CPUs com status VERMELHO — procurar por decomposição de equipamento faltante.

### Passo 2: Rodar Precificação de Projeto
```python
from concilium.application.skills.manifests import skill_06_precificacao

resultado = skill_06_precificacao.run_precificacao_unitaria(
    canonical_in=projeto_canonico,
    inputs=inputs,
    catalogo=catalogo,
    perfil=perfil,
)

# Validações incluem agora convergência
for val in resultado.validacoes:
    if val.codigo.startswith("VAL-CONV-PU"):
        print(f"{val.codigo}: {val.status} - {val.mensagem}")
```

### Passo 3: Analisar Desvios de Projeto
```python
# Se houver VERMELHO, debugar
for conv_val in [v for v in resultado.validacoes if "CONV-PU" in v.codigo]:
    if "VERMELHO" in conv_val.mensagem:
        # Extrair item_id da mensagem e revisitar convergência
        print(f"Debug: {conv_val.mensagem}")
        # Ajustar cronograma, equipe ou usar override conforme necessário
```

---

## Integração no Relatório Final

O relatório de consolidação financeira (skill 08) pode expor:

```json
{
  "validacao_pu": {
    "status_geral": "AMARELO",
    "num_items": 100,
    "convergencia": {
      "verde": 95,
      "amarelo": 4,
      "vermelho": 1
    },
    "items_criticos": [
      {
        "item_id": "ITEM-045",
        "status": "VERMELHO",
        "desvio_pct": 12.5,
        "raiz": "PERMANENCIA_ZERO",
        "recomendacao": "Revisar cronograma ou equipe para item"
      }
    ]
  }
}
```

---

## Recomendações

1. **Auditoria Regular**: Executar `audit_pu_catalogo.py` toda vez que atualizar catálogo.
2. **Threshold de Ação**:
   - Aceitar desvios até 5% (VERDE) sem ação.
   - Revisar 5–10% (AMARELO) antes de usar em projeto crítico.
   - Bloquear > 10% (VERMELHO) até correto.
3. **Documentação**: Adicionar notas a CPUs que tiveram override ou recalibração.
4. **Rastreabilidade**: Manter histórico de auditorias para benchmarking futuro.

---

## Referências

- **ADR-051**: [ADR-051-PU-validation-framework.md](../docs/engineering/business_rules/ADR-051-PU-validation-framework.md)
- **ADR-038**: Modo paramétrico de precificação.
- **ADR-050**: Planilha-first precedence.
- **ADR-023**: Decomposição de equipamento.
