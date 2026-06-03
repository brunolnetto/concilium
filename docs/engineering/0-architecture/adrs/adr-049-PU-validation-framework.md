# ADR-049: Validação Convergente de Preço Unitário (Catálogo + Projeto)

**Status**: IMPLEMENTADO  
**Data**: 2026-05-14  
**Contexto**: Concilium v0.2 (skills 05-06-08)  
**Decidor**: Engenheiro Sênior  
**Afetados**: Skill 06 (Precificação), Skill 05 (Equipes), Relatório de Consolidação Financeira

---

## Problema

A precificação unitária de venda (sem BDI) segue múltiplos caminhos:
1. **Planilha-first** (ADR-044): preços catalogados diretos.
2. **Composição** (ADR-023): decomposição de insumos por categoria.
3. **Paramétrico** (ADR-038): custo operacional real de equipe dividido por quantitativo.

Hoje não há mecanismo que:
- Valide convergência entre hipótese construtiva (equipe + cronograma + produção) e PU calculado.
- Detecte inconsistências de composição/produção no catálogo isoladamente.
- Rastreie desvios por categoria (MO vs EQ vs DIESEL vs MATERIAL).
- Ofereça signal de confiança para auditoria e refinamento de referência de planilha.

**Risco**: Preços derivados de composição errada ou produção faltante propagam invisíveis até consolidação.

---

## Governança Documental

Este arquivo ADR raiz é a **fonte única de verdade** para ADR-049.

Regras de manutenção:
- Atualizações de escopo, implementação e critérios de aceitação devem ocorrer neste arquivo.
- Documentos satélites de resumo/checklist para ADR-049 não devem ser mantidos em paralelo.
- Se houver tema novo que mude escopo arquitetural (ex.: desenho de CLI unificado com novas semânticas), deve ser aberto como novo ADR.

---

## Solução: Validação em Duas Camadas

### Camada 1: Catálogo (Estático)

**Quando**: Build de catálogo ou auditoria de governança.  
**O que valida**: CPU isolada, sem contexto de projeto.

#### Saída: `ValidacaoCatalogoPU`
```python
class ValidacaoCatalogoPUItem(BaseModel):
    cpu_id: str
    unidade: str
    
    producao_horaria: float
    custo_hora_teorico: float  # soma componentes
    
    pu_teorico_sem_bdi: float  # = custo_hora / producao_hora
    pu_catalogado_sem_bdi: float | None  # precos_unitarios_sbdi.total
    
    desvio_pct: float  # (catalogado - teorico) / teorico × 100%
    status_convergencia: Literal["VERDE", "AMARELO", "VERMELHO"]  # ±5% / ±10% / >10%
    
    # Por categoria
    detalhes: dict[str, CategoriaConvergencia]  # {material, diesel, mao_obra, equipamentos}
    
    validacoes: list[ValidacaoItem]
```

**Escopo de validação**:
- ✓ Produção horária definida ou derivável via producao_id.
- ✓ Composição completa (não há insumos faltando).
- ✓ Equipamentos têm decomposição ou fallback padronizado é aceitável.
- ✓ PU catalogado existe e converge com teórico (se não, marca desvio).
- ✓ Unidades de composição vs unidades de preço são coerentes (ADR-034).

---

### Camada 2: Projeto (Dinâmico)

**Quando**: Após skill 05 (equipes) e antes/durante skill 06 (precificação final).  
**O que valida**: Item do projeto com cronograma, equipe e produção reais.

#### Saída: `ValidacaoConvergenciaPU`
```python
class ValidacaoConvergenciaPUItem(BaseModel):
    item_id: str
    cpu_id: str
    quantitativo: float
    
    # Entrada: hipótese construtiva do projeto
    producao_semanal_base: float
    eficiencia_media_ponderada: float  # média de cronograma.distribuicao_semanal
    permanencia_meses: float  # de equipe.permanencia_meses
    
    num_equipes_medio: float
    
    # Custos operacionais da equipe (monthly)
    custo_mao_obra_mensal: float
    custo_equipamentos_mensal: float
    custo_combustivel_mensal: float
    custo_material_mensal: float
    
    # Cálculo teórico (hipótese)
    custo_horario_hipotese: float  # soma mensal / horas_mes
    producao_horaria_hipotese: float  # producao_semanal / horas_semana
    pu_teorico_hipotese: float  # custo_hora / producao_hora
    
    # Cálculo planejado (skill 06 executada)
    pu_planejado_sem_bdi: float  # planejamento[item_id].preco_unitario.total
    
    # Desvios
    desvio_pct_total: float
    desvio_por_categoria: dict[str, dict[str, float]]  # {material: {teorico, planejado, desvio_pct}, ...}
    
    status_convergencia: Literal["VERDE", "AMARELO", "VERMELHO"]
    
    # Rastreio
    modo_precificacao: Literal["PLANILHA_FIRST", "COMPOSICAO", "PARAMETRICO"]
    raiz_diagnostico: str  # ex: "EQUIPAMENTO_SEM_DECOMP", "PRODUCAO_FALTANTE", "OK"
    
    validacoes: list[ValidacaoItem]
```

**Escopo de validação**:
- ✓ Cronograma presente e com distribuição semanal.
- ✓ Equipe presente e custo_total > 0.
- ✓ Permanência não nula (pelo menos 1 semana ativa).
- ✓ Produção horária derivável.
- ✓ Desvio por categoria identifica qual componente diverge (MO vs EQ vs MAT vs DIESEL).
- ✓ Modo de precificação detectado (qual regra de precedência foi usada).
- ✓ Se > 10% desvio, sugere raiz: composição incompleta, eficiência diferente, produção faltante, etc.

---

## Implementação

### Fase 1: Validador de Catálogo
**Arquivo**: `src/concilium/domain/services/validador_pu_catalogo.py`

Função pública:
```python
def validar_pu_catalogo(
    cpu: dict,
    producoes_lookup: dict[str, dict],
    insumos_lookup: dict[str, dict],
    repo: RepositorioInsumo,
) -> ValidacaoCatalogoPUItem:
    """Valida PU teórico vs catalogado para uma CPU."""
    # 1. Deriva custo_hora_teorico de composição
    # 2. Revluta producao_horaria
    # 3. Calcula PU teórico
    # 4. Compara com precos_unitarios_sbdi.total (se existe)
    # 5. Emite desvios por categoria
    # 6. Classifica status (VERDE/AMARELO/VERMELHO)
    pass
```

**Integração**: Executado em script de auditoria `scripts/validate_catalog_pu.py` ou como skill auxiliar.

---

### Fase 2: Validador de Convergência de Projeto
**Arquivo**: `src/concilium/domain/services/validador_pu_convergencia.py`

Função pública:
```python
def validar_convergencia_pu(
    item: EAPItem,
    cpu: dict,
    equipe: EquipeDireta,
    cronograma: ScheduledActivityCanonical,
    planejamento: Planejamento,
    producoes_lookup: dict[str, dict],
    horas_dia: int,
    dias_semana: int,
) -> ValidacaoConvergenciaPUItem:
    """Valida convergência entre hipótese construtiva e PU planejado."""
    # 1. Extrai produção semanal base e eficiência média
    # 2. Calcula custos horários de equipe
    # 3. Deriva PU teórico por hipótese
    # 4. Compara com planejamento.preco_unitario
    # 5. Decompõe desvio por categoria
    # 6. Diagnostica raiz e classifica status
    pass
```

**Integração**: Executado dentro da skill 06 (Precificação), **após** calcular PU definitivo, e emitido em validacoes.

---

### Fase 3: Modelos Canônicos
**Arquivo**: `src/concilium/domain/models/canonical.py`

Adicionar:
```python
class CategoriaConvergencia(BaseModel):
    pu_teorico: float
    pu_planejado: float
    desvio_pct: float
    status: Literal["VERDE", "AMARELO", "VERMELHO"]

class ValidacaoCatalogoPUItem(BaseModel):
    cpu_id: str
    ...
    detalhes: dict[str, CategoriaConvergencia]

class ValidacaoConvergenciaPUItem(BaseModel):
    item_id: str
    ...
```

---

### Fase 4: Integração em Skills

#### Skill 06 (Precificacao)
Após calcular `preco_unitario` e `preco_unitario_com_bdi`:
```python
# Em run_precificacao_unitaria, após loop de itens:
for planej in plan_out:
    item = next(i for i in canonical_in.eap if i.item_id == planej.item_id)
    equipe = next((e for e in canonical_in.equipes_diretas if e.item_id == item.item_id), None)
    cron = cronograma_lookup.get(item.item_id)
    
    if equipe and cron:
        conv = validador_pu_convergencia.validar_convergencia_pu(
            item, cpu, equipe, cron, planej, ...
        )
        validacoes.extend(conv.validacoes)
        # Emite status convergência para rastreio
```

---

## Impacto em Ponto de Equilíbrio (PE) — Skill 08

### Conexão Crítica

A validação de PU em ADR-049 **afeta diretamente a confiabilidade do Ponto de Equilíbrio** calculado em skill 08:

$$
\text{Receita de Venda} = PU \times \text{Quantitativo} \times (1 + BDI)
$$

$$
\delta_{PE} = \text{Receita de Venda} - \text{Custo Fixo Total}
$$

**Se PU está errado → Receita está errada → Delta PE é falso**

### Matriz de Confiança PE × Status de PU

| PE Status | PU Status (ADR-049) | Confiança | Ação Recomendada |
|-----------|-----------|-----------|------------------|
| **VERDE** | VERDE | ✅ ALTA | Proceder com confiança |
| **VERDE** | AMARELO | ⚠️ MÉDIA | Revisar detalhe; possível surpresa em execução |
| **VERDE** | VERMELHO | ⚠️⚠️ BAIXA | **NÃO PROCEDER** — PU pode estar falso |
| **ERRO** | VERDE | ✅ MÉDIA | Diagnóstico confiável; item realmente inviável |
| **ERRO** | AMARELO | ⚠️⚠️ BAIXA | Duplo risco: PE frágil + PU incerta |
| **ERRO** | VERMELHO | ❌ CRÍTICO | **BLOQUEIO** — refazer cálculo inteiro |

### Implementação: Propagação de Confiança para PE (Skill 08)

Na skill 08 (Consolidação Financeira), após calcular cada `PontoEquilibrio`:

```python
class PontoEquilibrio(BaseModel):
    # Campos existentes
    item_id: str
    custo_fixo_equipe: float
    custo_venda_cpu: float
    delta: float
    status_validacao: StatusValidacao
    
    # NOVO: ADR-049 Link
    validacao_pu_status: Literal["VERDE", "AMARELO", "VERMELHO"] | None = None
    confianca_pe: Literal["ALTA", "MEDIA", "BAIXA"] | None = None
    diagnostico_pu: str | None = None
    # Exemplos:
    # "PU subestimado em 8%, PE pode ser otimista."
    # "Raiz: CRONOGRAMA_AUSENTE — não foi possível validar."
```

**Lógica de preenchimento**:

```python
for pe_item in ponto_equilibrio_items:
    # Buscar validação de convergência de PU (da skill 06)
    conv_val = find_convergencia_pu(pe_item.item_id, canonical_in.validacoes_convergencia_pu)
    
    if conv_val:
        pe_item.validacao_pu_status = conv_val.status_convergencia
        
        # Mapear status → confiança
        if conv_val.status_convergencia == "VERDE":
            pe_item.confianca_pe = "ALTA"
        elif conv_val.status_convergencia == "AMARELO":
            pe_item.confianca_pe = "MEDIA"
        else:  # VERMELHO
            pe_item.confianca_pe = "BAIXA"
            pe_item.diagnostico_pu = (
                f"PU desvio={conv_val.desvio_pct_total:+.1f}%. "
                f"Raiz: {conv_val.raiz_diagnostico}. "
                f"PE {'otimista' if conv_val.desvio_pct_total > 0 else 'pessimista'}."
            )
    
    # Emitir aviso se duplo risco: PE ERRO + PU not VERDE
    if pe_item.status_validacao == "ERRO" and pe_item.confianca_pe in ("MEDIA", "BAIXA"):
        validacoes.append(ValidacaoItem(
            codigo="VAL-PE-PU-DUPLO-RISCO",
            status="AVISO" if pe_item.confianca_pe == "MEDIA" else "ERRO",
            mensagem=(
                f"Item '{pe_item.item_id}': PE DEFICITÁRIO com PU "
                f"{pe_item.validacao_pu_status}. Item pode ser inviável. "
                f"{pe_item.diagnostico_pu or ''}"
            ),
        ))
```

### Exemplos de Cascata

**Cenário A: PU Incorreta (Decomposição)**
```
CPU real: Prod 26 m³/h, Custo R$ 413/h → PU teórico = R$ 15.56/m³
PU planejado: R$ 0.139/m³ (decomposição CPU teórica de 250 m³/h)

Convergência status: VERMELHO (−99.1% desvio)

PE Resultado:
  Receita: R$ 319.70 (errada)
  Custo fixo: R$ 240.000
  Delta: −R$ 239.680 → Status ERRO
  Confiança PE: BAIXA
  
Decisão errada: Rejeitar item que poderia ser viável
```

**Cenário B: PU Correta (Planilha-First)**
```
CPU real: Prod 26 m³/h, Custo R$ 413/h → PU teórico = R$ 15.56/m³
PU planejado: R$ 15.44/m³ (planilha calibrada ao projeto)

Convergência status: VERDE (−0.77% desvio)

PE Resultado:
  Receita: R$ 35.512 (correta)
  Custo fixo: R$ 240.000
  Delta: −R$ 204.488 → Status ERRO
  Confiança PE: ALTA
  
Decisão confiável: Item estruturalmente inviável; replanning justificado
```

### Emissão de Validação (Duplo Risco)

A skill 08 emitirá `ValidacaoItem` especial quando PE e PU divergem:

```json
{
  "codigo": "VAL-PE-PU-DUPLO-RISCO",
  "status": "AVISO",
  "mensagem": "Item 'ESCO-CARGA': PE DEFICITÁRIO com PU AMARELO. Item pode ser inviável. PU desvio=+8.3%. Raiz: OK. PE pode estar otimista."
}
```

---

## Critérios de Aceitação

- [ ] Validador de catálogo existe e testa CPU isolada.
- [ ] Validador de convergência existe e compara hipótese vs planejado.
- [ ] Ambos emitem `ValidacaoItem` padronizada (código, status, mensagem).
- [ ] Skill 06 executa validação de convergência sem bloquear pipeline.
- [ ] Skill 08 popula novos campos em `PontoEquilibrio` (validacao_pu_status, confianca_pe, diagnostico_pu).
- [ ] Skill 08 emite VAL-PE-PU-DUPLO-RISCO quando PE ERRO + PU not VERDE.
- [ ] Relatório expõe status de convergência por item (VERDE/AMARELO/VERMELHO).
- [ ] Desvios > 10% aparecem em destaque no relatório com diagnóstico.
- [ ] PE items exportados com confiança e diagnostico_pu inclusos em JSON.

---

## Alternativas Consideradas

1. **Validação só no catálogo**: Não detecta divergências operacionais (praticabilidade, cronograma diferentes).
2. **Validação só no projeto**: Não encontra erros de composição/produção isolados antes de rodar projeto.
3. **Validação em script externo**: Perde rastreabilidade no pipeline oficial.

**Escolhida**: Abordagem em duas camadas → ambas as classes de erro capturadas.

---

## Impactos

| Componente | Impacto |
|-----------|--------|
| Catálogo | Enriquecimento de auditoria; sem mudança em forma de dados |
| Skill 05 | Nenhum (validação é leitura) |
| Skill 06 | +1 função de validação pós-cálculo; emite validações adicionais |
| Skill 08 | Consolidação pode expor status de convergência em matriz |
| Relatório | Nova seção "Convergência PU" com desvios por categoria |

---

## Rastreabilidade

- **ADR-023**: Decomposição de equipamento influencia validação de categoria.
- **ADR-034**: Normalização de unidades impacta cálculo de custo horário.
- **ADR-038**: Modo paramétrico de precificação é alvo central desta validação.
- **ADR-044**: Validação também confronta planilha-first vs teórico.

---

## Próximas Etapas

1. Consolidar evolução de CLI para expor validação PU em comandos de projeto e benchmark.
2. Padronizar interface de comando para `project` e `benchmark` (incluindo alias compatível `projeto` quando aplicável).
3. Definir contrato de saída comum para os modos (JSON e resumo humano com mesmas métricas-chave).
4. Implementar testes de integração de CLI cobrindo cenários de catálogo, projeto e benchmark.
5. Evoluir ADR-050 para tratar benchmark aninhado em projeto usando `benchmarks/data` como fonte de benchmark (fora do escopo deste ADR).
