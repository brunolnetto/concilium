# NEP-001: Jurisdições não expõem provedores de referência SINAPI/SICRO

**Status:** Concluído  
**Prioridade:** 🟡 Médio  
**Área:** Configuração  
**Tipo:** Feature + Dados  
**Esforço:** M  
**Identificado em:** 2026-05-20  

---

## Contexto

Os arquivos de jurisdição (`config/jurisdicoes/BR-CE.json`, etc.) contêm o campo `provedores_referencia` com definições estruturadas dos sistemas de referência de preços usados naquela jurisdição — tipicamente SINAPI (CAIXA) e SICRO (DNIT):

```json
"provedores_referencia": [
  {
    "id": "SINAPI",
    "nome": "SINAPI — Sistema Nacional de Pesquisa de Custos e Índices da Construção Civil",
    "base": "CAIXA",
    "data_referencia": "2024-01",
    "url_fonte": "https://..."
  },
  {
    "id": "SICRO",
    "nome": "SICRO — Sistema de Custos de Infraestrutura Rodoviária",
    "base": "DNIT",
    "data_referencia": "2024-CE",
    "url_fonte": "https://..."
  }
]
```

A aba "⚖️ Jurisdições" na página de Configuração atualmente exibe apenas os overlays de CPU/insumo, ignorando completamente esses provedores. O usuário não consegue visualizar, editar ou atualizar as bases de referência de preços.

## Impacto

- Engenheiro não sabe qual tabela SINAPI está configurada para o CE sem abrir o arquivo manualmente
- Atualizações de base (ex: SINAPI Jan/2026 → Mar/2026) não têm fluxo de aprovação no sistema
- Sem versionamento do provedor, não é possível auditar qual base foi usada numa cotação anterior

## Critério de Aceite

Na aba ⚖️ Jurisdições, nova seção "📡 Provedores de Referência":
- Lista os provedores com: nome, base, data_referencia (editável), url_fonte (link clicável)
- Botão "Atualizar base" que cria nova versão do overlay com nova `data_referencia`
- Histórico de versões inclui o provedor usado em cada versão (rastreabilidade de auditorias)
- Para cada provedor, badge de status: `🟢 Vigente` / `🟡 Desatualizado (>6 meses)` / `🔴 Sem referência`

## Notas Técnicas

- A estrutura `provedores_referencia` já existe nos JSONs — é leitura+exposição, não nova modelagem
- Edição de `data_referencia` deve criar uma nova versão via `JurisdictionVersionService` (ADR-066)
- Badge de desatualização: comparar `data_referencia` com data atual
- Sem necessidade de novo endpoint — `GET /api/jurisdicoes` já retorna a estrutura completa
