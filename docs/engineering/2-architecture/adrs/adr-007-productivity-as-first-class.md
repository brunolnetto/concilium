# ADR-007: Productivity as First-Class Artifact

**Status:** Implementado  
**Date Decided:** 2026-04-27  
**Date Implemented:** 2026-04-27  
**Implementers:** config/producoes/, models/producao.py, catalog/completeness.py  
**Context:** Productivity must be a first-class artifact, not a field within CPU. It lives in separate files (`config/producoes/`), is referenced by CPUs, and has traceability, versioning, and observation history.

---

## Decision

Isso permite:
- ✓ **Rastreabilidade**: De onde veio cada produtividade?
- ✓ **Escalabilidade**: Trocar fonte de dados (obra real → SICRO → ML) sem quebrar CPUs
- ✓ **Auditoria**: Quem alterou? Quando? Por quê?
- ✓ **Evolução**: Histórico completo de observações e refinamento

---

## Estrutura: Produtividade como Artefato

### Arquivo: `config/producoes/ESCO-CARGA-1CAT-PROD-001.json`

```json
{
  "id": "ESCO-CARGA-1CAT-PROD-001",
  "codigo": "ESCO-CARGA-1CAT",
  "descricao": "Escavação, carga, transporte, descarga e espalhamento - 1ª categoria",
  
  "valor_horario": 233.54,
  "unidade": "m3",
  
  "origem": {
    "tipo": "calibrado_contra_obra_real",
    "fonte_id": "Lote_09_10_CE_2025",
    "data_calibracao": "2025-09-30",
    "referencia": "Planilha AGIS; aba PLANEJAMENTO, CPU 2.1; 45 dias de dados"
  },
  
  "condicoes_calibracao": {
    "tipo_solo": "argila_e_laterita",
    "dmt_medio": 1850,
    "season": "seco",
    "sequenciamento": "linear_continuo",
    "equipamento_idade": 3,
    "notas": "Obra ferroviária Ceará; DMT 1800-2100m; argila/laterita bem compactada"
  },
  
  "qualidade": {
    "confianca_pct": 95,
    "intervalo_confianca": [220, 247],
    "quantidade_amostras": 45,
    "desvio_padrao": 8.5
  },
  
  "composicao_padrao_equipe": {
    "funcoes": [
      {"funcao_id": "OPER-ESCAV", "num_pessoas": 1},
      {"funcao_id": "MOTOR-CAM-BASC", "num_pessoas": 7},
      {"funcao_id": "AJUDANTE", "num_pessoas": 1},
      {"funcao_id": "ENCARREGADO-DE-FRENT", "num_pessoas": 1}
    ],
    "equipamentos": [
      {"equip_id": "ESCAV-HID-38T", "num_unidades": 1},
      {"equip_id": "CAM-BASC-14M3", "num_unidades": 7}
    ]
  },
  
  "historico_observacoes": [
    {
      "obra_id": "Lote_09_10_CE_2025",
      "periodo": "2025-06-01/2025-09-30",
      "producao_realizada": 298.5,
      "delta_pct": 27.8,
      "contexto_observado": {
        "solo": "laterita_compactada",
        "dmt": 1850,
        "season": "seco",
        "sequenciamento": "linear_continuo"
      },
      "confiabilidade": 0.98,
      "notas": "Condições ideais; operador experiente; sem obstáculos",
      "timestamp": "2025-10-15T10:30:00Z"
    }
  ],
  
  "auditoria": {
    "criado_por": "eng_senhor_silva",
    "data_criacao": "2025-09-30T14:22:00Z",
    "ultima_modificacao": "2025-10-15T10:30:00Z",
    "modificado_por": "eng_senhor_silva",
    "versao": "1.1"
  }
}
```

### Campos Explicados

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id` | string | ID único (ESCO-CARGA-1CAT-PROD-001) |
| `codigo` | string | Código funcional (pode ser compartilhado entre versões) |
| `valor_horario` | float | m³/h (ou unidade apropriada) |
| `origem.tipo` | enum | "calibrado_contra_obra_real" \| "tabela_referencia" \| "estimado" \| "regressao" |
| `origem.fonte_id` | string | "Lote_09_10_CE_2025" ou "SICRO_2024_CE" |
| `condicoes_calibracao` | dict | Solo, DMT, season, seq, idade_equip, notas |
| `qualidade.confianca_pct` | int | 0-100 (qual confiança temos neste número?) |
| `composicao_padrao_equipe` | dict | Funcões + equipamentos que produzem este valor |
| `historico_observacoes` | list | Todos os dados reais que validaram/refinaram este valor |
| `auditoria` | dict | Quem criou, modificou, quando, versão |

---

## Como CPU Referencia Produtividade

### CPU: `config/catalogos/agis/cpus.json`

```json
{
  "codigo": "ESCO-CARGA-1CAT-DMT2000",
  "descricao": "Escavação, carga, transporte, descarga e espalhamento de material de 1ª categoria - DMT até 2000m",
  "categoria": "TERRAPLENAGEM",
  "unidade": "m3",
  
  "producao_id": "ESCO-CARGA-1CAT-PROD-001",  // ← Referência FK
  
  "composicao_padrao_equipe": { ... },
  "composicao_itens": [ ... ]
}
```

**Benefício:** Um arquivo de produtividade (PROD-001) pode ser compartilhado por múltiplas CPUs:
- `ESCO-CARGA-1CAT-DMT2000` → PROD-001
- `ESCO-CARGA-1CAT-DMT3000` → PROD-001 (mesma produtividade, equipamento não muda)
- Zero duplicação

---

## Índice de Produtividades

### Arquivo: `config/catalogos/agis/producoes.json`

```json
{
  "versao": "2.4",
  "producoes": [
    {
      "id": "ESCO-CARGA-1CAT-PROD-001",
      "codigo": "ESCO-CARGA-1CAT",
      "valor_horario": 233.54,
      "origem": "calibrado_contra_obra_real",
      "confianca": 95,
      "ultima_atualizacao": "2025-10-15T10:30:00Z"
    },
    {
      "id": "ESCO-CARGA-2CAT-PROD-001",
      "codigo": "ESCO-CARGA-2CAT",
      "valor_horario": 159.11,
      "origem": "calibrado_contra_obra_real",
      "confianca": 95,
      "ultima_atualizacao": "2025-10-15T10:30:00Z"
    }
  ]
}
```

**Propósito:** Índice rápido para listar todas as produtividades sem desempacotar todos os arquivos.

---

## Estrutura de Diretórios

```
config/
├── catalogos/
│   └── agis/
│       ├── insumos.json          (140 insumos — existente)
│       ├── cpus.json              (11 CPUs — refatorado para referenciar producoes)
│       ├── producoes.json         (NOVO — índice rápido)
│       └── templates-obra.json    (existente)
│
├── producoes/                     (NOVO — artefatos de produtividade)
│   ├── ESCO-CARGA-1CAT-PROD-001.json
│   ├── ESCO-CARGA-1CAT-PROD-002.json  (próxima versão, quando calibrada)
│   ├── ESCO-CARGA-2CAT-PROD-001.json
│   ├── ESCO-CARGA-3CAT-PROD-001.json
│   ├── COMPACT-ATERRO-100PN-PROD-001.json
│   ├── DREN-MAN-DN300-PROD-001.json
│   ├── POCO-VISITA-PADRAO-PROD-001.json
│   └── PAV-BASE-BGTC-PROD-001.json
│
├── referencias/
│   └── SICRO_2024_CE.json
├── jurisdicoes/
│   └── BR.json
└── contextos/
    └── agis.json
```

---

## Modelo de Dados (Python Pydantic)

```python
from datetime import datetime
from typing import Optional, List, Dict

class OrigemProducao(BaseModel):
    tipo: str  # "calibrado_contra_obra_real" | "tabela_referencia" | "estimado" | "regressao"
    fonte_id: str  # "Lote_09_10_CE_2025" | "SICRO_2024_CE" | etc.
    data_calibracao: datetime
    referencia: str  # Contextual info

class CondicoesCalibra cao(BaseModel):
    tipo_solo: Optional[str]
    dmt_medio: Optional[float]
    season: Optional[str]
    sequenciamento: Optional[str]
    equipamento_idade: Optional[int]
    notas: str

class QualidadeProducao(BaseModel):
    confianca_pct: int  # 0-100
    intervalo_confianca: tuple[float, float]
    quantidade_amostras: int
    desvio_padrao: float

class ComposicaoPadraoEquipe(BaseModel):
    funcoes: List[Dict[str, any]]
    equipamentos: List[Dict[str, any]]

class ObservacaoProducao(BaseModel):
    obra_id: str
    periodo: str
    producao_realizada: float
    delta_pct: float
    contexto_observado: Dict
    confiabilidade: float
    notas: Optional[str]
    timestamp: datetime

class AuditoriaProducao(BaseModel):
    criado_por: str
    data_criacao: datetime
    ultima_modificacao: datetime
    modificado_por: str
    versao: str

class Producao(BaseModel):
    id: str  # ESCO-CARGA-1CAT-PROD-001
    codigo: str  # ESCO-CARGA-1CAT (compartilhado entre versões)
    descricao: str
    
    valor_horario: float
    unidade: str
    
    origem: OrigemProducao
    condicoes_calibracao: CondicoesCalibracao
    qualidade: QualidadeProducao
    composicao_padrao_equipe: ComposicaoPadraoEquipe
    
    historico_observacoes: List[ObservacaoProducao]
    auditoria: AuditoriaProducao
```

---

## Uso em Skill 02 (Cronograma)

```python
def run_skill_02_cronograma(canonical, inputs, catalogo, perfil, producoes):
    """
    Skill 02: Cronograma com produtividades como artefatos.
    """
    for item in canonical.eap:
        cpu = catalogo.find_cpu(item.cpu_id)
        
        # Resolve produtividade via artefato
        producao = producoes.find(cpu.producao_id)
        P = producao.valor_horario
        
        # Validação: produtividade tem qual confiança?
        if producao.qualidade.confianca_pct < 80:
            VAL_PROD_BAIXA_CONFIANCA: AVISO
        
        # Cronograma
        horas_uteis_mes = 8 × 22 × praticabilidade[mes]
        meses_necessarios = item.quantitativo / (P × horas_uteis_mes)
        
        canonical.cronograma.append({
            "item_id": item.item_id,
            "producao_id": producao.id,
            "producao_horaria": P,
            "confianca_producao": producao.qualidade.confianca_pct,
            "meses_necessarios": meses_necessarios
        })
    
    return canonical
```

---

## Evolução: Criar Nova Versão de Produtividade

### Scenario: Após rodar Obra 2, observar delta +28%

```python
def propor_nova_versao_producao(obra_id, observacoes, producao_atual):
    """
    Propõe nova versão de produtividade baseada em observação real.
    """
    delta_pct = (observacoes.producao_realizada / producao_atual.valor_horario - 1) * 100
    
    if delta_pct > 20 and observacoes.confiabilidade > 0.80:
        # Cria nova versão
        nova_producao = Producao(
            id=f"{producao_atual.codigo}-PROD-{producao_atual.versao + 1}",
            codigo=producao_atual.codigo,  # Mesmo código!
            valor_horario=producao_atual.valor_horario × (1 + delta_pct/100),
            origem=OrigemProducao(
                tipo="calibrado_contra_obra_real",
                fonte_id=obra_id,
                data_calibracao=datetime.utcnow()
            ),
            condicoes_calibracao=observacoes.contexto_observado,
            historico_observacoes=[
                *producao_atual.historico_observacoes,
                observacoes  # Adiciona nova observação
            ],
            auditoria=AuditoriaProducao(
                criado_por=usuario_id,
                data_criacao=datetime.utcnow(),
                versao=f"1.{producao_atual.versao + 1}"
            )
        )
        
        return nova_producao
```

**Resultado:**
- `ESCO-CARGA-1CAT-PROD-001` (v1.0 — base, 233.54 m³/h)
- `ESCO-CARGA-1CAT-PROD-002` (v1.1 — refinada, 260+ m³/h, baseada em Obra 2)
- `ESCO-CARGA-1CAT-PROD-003` (v1.2 — refinada novamente, baseada em Obra N)

CPUs escolhem qual versão usar por contexto (ou data de calibração).

---

## Validações (VAL-PROD-XX)

| Código | Condição | Ação |
|--------|----------|------|
| **VAL-PROD-01** | `producao.origem.tipo == null`? | ERRO: "Origem de produtividade não documentada" |
| **VAL-PROD-02** | `producao.qualidade.confianca_pct < 60`? | AVISO: "Confiança baixa. Use com cautela." |
| **VAL-PROD-03** | `producao.condicoes_calibracao` vaga? | AVISO: "Documente solo, DMT, season, seq." |
| **VAL-PROD-04** | CPU referencia prod_id inexistente? | ERRO: "Produtividade não encontrada" |
| **VAL-PROD-05** | `producao.valor_horario` implausível? | ERRO: "Fora de range (< 0.1 ou > 10000)" |

---

## Query & Análise

### Exemplos de Queries Viáveis

```python
# "Quais obras alimentaram a calibração de ESCO-CARGA-1CAT-PROD-001?"
producao = carrega("ESCO-CARGA-1CAT-PROD-001")
obras = [obs.obra_id for obs in producao.historico_observacoes]

# "Qual é a variação histórica de produtividade em argila?"
todas_producoes = carrega_todas("config/producoes/")
argila_producoes = [
    p for p in todas_producoes
    if "argila" in p.condicoes_calibracao.tipo_solo
]
deltas = [obs.delta_pct for p in argila_producoes for obs in p.historico_observacoes]
print(f"Variação em argila: {min(deltas)} % a {max(deltas)} %")

# "Que produtividades têm confiança < 80%?"
baixa_confianca = [
    p for p in todas_producoes
    if p.qualidade.confianca_pct < 80
]
```

---

## Integração com MCP Server

### Novas Ferramentas

```python
@server.tool()
def listar_producoes_por_categoria(categoria: str) -> list[dict]:
    """List all productivity definitions for a category (TERRAPLENAGEM, SANEAMENTO, etc.)"""
    producoes = carrega_indice("config/catalogos/agis/producoes.json")
    cpus = carrega("config/catalogos/agis/cpus.json")
    
    cpu_ids_categoria = [c["codigo"] for c in cpus if c["categoria"] == categoria]
    prod_ids = [c["producao_id"] for c in cpus if c["codigo"] in cpu_ids_categoria]
    
    return [p for p in producoes if p["id"] in prod_ids]

@server.tool()
def consultar_historico_producao(producao_id: str) -> dict:
    """Get full productivity history: calibration, observations, evolution."""
    producao = carrega(f"config/producoes/{producao_id}.json")
    return {
        "id": producao.id,
        "valor_atual": producao.valor_horario,
        "confianca": producao.qualidade.confianca_pct,
        "origem": producao.origem,
        "historico_observacoes": producao.historico_observacoes,
        "auditoria": producao.auditoria
    }

@server.tool()
def propor_nova_producao(obra_id: str, producao_id: str, observacoes: dict) -> dict:
    """Propose a new productivity version based on real job data."""
    producao_atual = carrega(f"config/producoes/{producao_id}.json")
    
    nova = propor_nova_versao_producao(obra_id, observacoes, producao_atual)
    
    return {
        "producao_proposta": nova,
        "delta_pct": (nova.valor_horario / producao_atual.valor_horario - 1) * 100,
        "confiabilidade": observacoes["confiabilidade"],
        "recomendacao": "Pendente aprovação de Engenheiro Sênior"
    }
```

---

## Implementação: Timeline

### Fase 1B (esta semana — 4h)

1. Criar estrutura `config/producoes/` (30 min)
2. Gerar 11 arquivos de produtividade (1 por CPU AGIS) (1h)
3. Refatorar `config/catalogos/agis/cpus.json` para referenciar `producao_id` (30 min)
4. Criar `config/catalogos/agis/producoes.json` (índice) (30 min)
5. Atualizar Skill 02 para resolver produtividade via artefato (1h)
6. Testes (20 min)

### Fase 1B+ (próximas semanas)

7. Implementar MCP tools (listar_producoes, consultar_historico, propor_nova)
8. Dashboard: evolução de produtividade ao longo do tempo
9. Validações VAL-PROD-XX

---

## Benefícios Dessa Abordagem

| Aspecto | Ganho |
|---------|-------|
| **Rastreabilidade** | Cada produtividade tem origem documentada, histórico completo |
| **Escalabilidade** | Trocar fonte (obra real → SICRO → ML) sem quebrar CPUs |
| **Auditoria** | Quem criou? Modificou? Quando? Por quê? Tudo registrado |
| **Reusabilidade** | Uma produtividade pode ser compartilhada por múltiplas CPUs |
| **Evolução** | Histórico completo v1 → v2 → v3; sem apagar dados |
| **Query/Análise** | SQL-like queries sobre produtividades, origens, deltas |
| **Manutenção** | Produtividade é objeto de primeira classe; UI pode gerenciá-la |
| **Integração MCP** | Tools naturais para explorar e propor mudanças |

---

## Próximos Passos

1. **Esta semana:** Criar 11 arquivos de produtividade em `config/producoes/`
2. **Esta semana:** Refatorar `cpus.json` para referenciar `producao_id`
3. **Esta semana:** Atualizar Skill 02
4. **Próximas semanas:** Implementar MCP tools e validações
5. **Próximas semanas:** Dashboard de evolução

---

## Definition of Done

- [x] `Producao` Pydantic model with `id`, `codigo`, `valor_horario`, `unidade`, `origem`, `condicoes_calibracao`, `qualidade`, `composicao_padrao_equipe`, `historico_observacoes`, `auditoria`
- [x] `config/producoes/` directory with one JSON artifact per productivity definition
- [x] 11 productivity artifacts covering all AGIS catalog CPUs
- [x] `config/catalogos/agis/producoes.json` index file for fast lookup (id, codigo, valor_horario, confianca, ultima_atualizacao)
- [x] CPUs reference productivity via `producao_id` FK — no duplication across CPUs sharing the same productivity
- [x] Skill 02 (cronograma) resolves productivity via artifact (`producao_id`) — not hardcoded values
- [x] VAL-PROD-01: `origem.tipo` absent → ERRO
- [x] VAL-PROD-02: `confianca_pct < 60` → AVISO
- [x] VAL-PROD-03: `condicoes_calibracao` vague → AVISO
- [x] VAL-PROD-04: `producao_id` not found in catalog → ERRO
- [x] VAL-PROD-05: `valor_horario` out of plausible range → ERRO
- [x] MCP tools: `listar_producoes_por_categoria`, `consultar_historico_producao`, `propor_nova_producao`
- [x] Versioning workflow: new `PROD-00N` created on observed delta > 20%; prior version preserved

## Conclusão

ADR-006 com **Produtividade como Artefato** é a forma **correta, escalável e auditável** de gerenciar conhecimento de produtividades.

Segue o mesmo padrão de todo o Concilium: insumos, CPUs, referências, jurisdições — todos são artefatos versionados, rastreáveis, com histórico.

**Status: READY TO IMPLEMENT**