# Insumos: Estrutura Separada por Tipo

**Data**: 2026-04-28  
**Estratégia**: Separação de dados + Loader agnóstico + Zero disruption

---

## 📁 Estrutura de Diretórios

```
config/catalogos/
├── agis/
│   ├── insumos/                    ← NOVO: Separado por tipo
│   │   ├── mao_obra.json           (78 insumos)
│   │   ├── equipamento.json        (55 insumos)
│   │   ├── material.json           (7 insumos)
│   │   └── README.md               (esta documentação)
// insumos.json removido (dados migrados)
│   ├── cpus.json
│   └── templates.json
│
├── samples/
│   ├── insumos/                    ← NOVO: Separado por tipo
│   │   ├── mao_obra.json
│   │   ├── equipamento.json
│   │   ├── material.json
│   │   └── README.md
// insumos.json removido (dados migrados)
│   └── ...
│
├── test/
│   ├── insumos/                    ← NOVO: Separado por tipo
│   │   ├── mao_obra.json
│   │   ├── equipamento.json
│   │   ├── material.json
│   │   └── README.md
// insumos.json removido (dados migrados)
│   └── ...
│
└── loaders.py                       ← NOVO: Agnóstico
```

---

## 📊 Distribuição de Insumos

| Tipo | AGIS | Samples | Test |
|------|------|---------|------|
| MAO_OBRA | 78 | 78 | 78 |
| EQUIPAMENTO | 55 | 55 | 55 |
| MATERIAL | 7 | 7 | 7 |
| TERCEIRIZADO | 0 | 0 | 0 |
| **TOTAL** | **140** | **140** | **140** |

---

## 🚀 Como Usar

### Opção 1: Novo Loader Agnóstico (Recomendado)

```python
from config.loaders import LoaderInsumoAgnóstico
from pathlib import Path

# Carrega de {catalogo}/insumos/ (separado por tipo)
dados = LoaderInsumoAgnóstico.carregar_insumos("config/catalogos/agis")
insumos = dados["insumos"]  # Lista com 140 insumos

# Ou usar conveniências
from config.loaders import carregar_insumos_agis
dados = carregar_insumos_agis()
```

### Opção 2: Código Existente (Sem Mudanças!)

```python
# Continua funcionando exatamente como antes
import json
// Exemplo removido: uso de insumos.json obsoleto
    dados = json.load(f)
```

---

## 🔄 Estratégia: Zero Disruption

### Por que isso funciona?

// Arquivo insumos.json removido (dados migrados)
   - Compatível 100% com código legado
   - Pode ser apagado depois se quiser

2. **Loader agnóstico**: `config/loaders.py`
   - Tenta carregar de `insumos/` primeiro (se existir)
// Fallback removido: agora sempre separado por tipo
   - Retorna sempre no mesmo formato

3. **Modelos Python inalterados**: `catalogo.py`
   - Nenhuma mudança obrigatória
   - Continua aceitando dados exatamente como antes
   - Pode ser melhorado incrementalmente

---

## 📋 Formato dos Arquivos

### Arquivo Único (Antigo)
```json
{
  "$comment": "...",
  "insumos": [
    { "codigo": "AJUDANTE", "tipo": "MAO_OBRA", ... },
    { "codigo": "ESCAV-HID", "tipo": "EQUIPAMENTO", ... }
  ]
}
```

### Arquivos Separados (Novo)
**`mao_obra.json`**:
```json
[
  { "codigo": "AJUDANTE", "tipo": "MAO_OBRA", ... },
  { "codigo": "ALMOXARIFE", "tipo": "MAO_OBRA", ... }
]
```

**`equipamento.json`**:
```json
[
  { "codigo": "ESCAV-HID-38T", "tipo": "EQUIPAMENTO", ... },
  { "codigo": "CAM-BASC-14M3", "tipo": "EQUIPAMENTO", ... }
]
```

**`material.json`**:
```json
[
  { "codigo": "DIESEL-S10", "tipo": "MATERIAL", ... }
]
```

---

## 🎯 Vantagens

✅ **Separação por domínio**: Cada tipo de insumo em arquivo dedicado
✅ **Escalabilidade**: Fácil adicionar novos tipos ou insumos
✅ **Clareza**: Estrutura óbvia (MAO_OBRA separado de EQUIPAMENTO)
✅ **Zero breaking changes**: Código existente continua funcionando
✅ **Flexibilidade**: Pode usar estrutura unificada OU separada
✅ **Manutenção**: Arquivo único só com ~200 linhas, não mais 1000+
✅ **Rastreabilidade**: Git diffs mais claros (mudança em tipo específico)

---

## 🔧 Próximos Passos (Opcionais)

1. **Documentar dados**: Adicionar `_metadata.json` em cada tipo com descrição
   ```json
   {
     "tipo": "MAO_OBRA",
     "descricao": "Profissões: Operários, ajudantes, líderes, etc",
     "contador": 78,
     "ultima_atualizacao": "2026-04-28"
   }
   ```

2. **Validar estrutura**: Script que garante cada arquivo segue schema
   ```bash
   python config/validar_insumos.py
   ```

3. **Gerar estatísticas**: Dashboard com distribuição por tipo
   ```bash
   python config/stats_insumos.py
   ```

// Arquivo insumos.json removido (dados migrados)

---

## ❓ FAQ

// Pergunta removida: insumos.json não existe mais
R: Continua funcionando! O arquivo ainda existe.

**P: Como migro meu código progressivamente?**  
R: Opção 1 é usar o loader novo. Opção 2 é não fazer nada (retrocompatível).

**P: Posso misturar arquivo único + separado?**  
R: Sim! O loader tenta separado primeiro, depois único.

**P: E se quiser SEMPRE usar o arquivo separado?**  
// Resposta removida: insumos.json não existe mais

---

## 🧪 Testando

```bash
# Verificar estrutura
ls -la config/catalogos/agis/insumos/

# Testar loader
python3 config/loaders.py

# Contar insumos
wc -l config/catalogos/agis/insumos/*.json
```

---

## 📚 Documentação Relacionada

- [INSUMO_CPU_RELACIONAL_DETALHADO.md](../../INSUMO_CPU_RELACIONAL_DETALHADO.md) - Análise conceitual
- [VALIDACOES_VAL_CPU_INS_01_07.md](../../VALIDACOES_VAL_CPU_INS_01_07.md) - Validações de compatibilização
