# NEP-024: Cubo analítico multidimensional com granularidade temporal múltipla

**Status:** Conclu?do  
**Prioridade:** 🟠 Alto  
**Área:** Domínio  
**Tipo:** Feature + Governança  
**Esforço:** L  
**Identificado em:** 2026-05-22

---

## Contexto

O cubo atual já materializa dimensões relevantes para composição de preço e análise temporal, mas a leitura ainda está concentrada em semana ISO e com foco forte no consumo via Excel.

A necessidade de produto é avançar para um cubo analítico com visão de negócio mais explícita para:
- natureza de custo,
- categoria operacional,
- tempo em diferentes granularidades,
- decomposição de BDI,
- rastreabilidade por atividade.

---

## Proposta de modelagem

Faz sentido evoluir para o modelo sugerido, com um ajuste de nomenclatura para evitar ambiguidades:

1. Dimensões principais
- Natureza de custo: `direto` e `indireto`
- Tempo: `semana`, `mes`, `bimestre`, `trimestre`, `semestre`, `ano`
- BDI: componentes de decomposição (custo direto, overheads, margem, tributos)

2. Granularidade associada
- Atividade
- Categoria operacional da atividade: `MO`, `EQ`, `DIESEL`, `MAT`, `VB`

3. Ajuste recomendado
- Tratar `categoria de custo (direto/indireto)` e `categoria operacional (MO/EQ/DIESEL/MAT/VB)` como eixos separados.
  Isso reduz conflito semântico e facilita agregações corretas.

---

## Oportunidades

1. Explicabilidade executiva
- Permite responder rapidamente "quanto do preço vem de custo direto/indireto e onde está concentrado por atividade e período".

2. Reuso analítico
- Mesmo cubo alimenta Excel, API e UI sem recalcular múltiplas visões ad hoc.

3. Governança de dados
- Com dimensões explícitas, validações automáticas de consistência ficam mais simples (ex.: soma por período e por BDI).

4. Integração com PE/backtracking
- O PE passa a consumir visões consistentes do cubo para localizar ineficiências por causa e tempo.

---

## Fraquezas e riscos

1. Complexidade de modelagem
- Mais eixos e granularidades podem aumentar custo de manutenção se não houver contratos claros de agregação.

2. Risco de dupla contagem
- Agregações temporais derivadas (ex.: semana para trimestre) precisam regras únicas para evitar sobreposição.

3. Performance
- Consultas multi-eixo podem degradar sem materializações/parciais para UI/API.

4. Lacuna de produto atual
- Sem endpoints e visualizações nativas, o valor continua preso na exportação Excel.

---

## Critério de aceite

1. O cubo expõe explicitamente eixos separados para:
- natureza de custo,
- categoria operacional,
- tempo,
- componente BDI,
- atividade.

2. Existe camada de agregação temporal padronizada para:
- semana, mes, bimestre, trimestre, semestre, ano.

3. Validações garantem reconciliação:
- soma das visões agregadas = total de venda/custo da base semanal.

4. API e UI conseguem consumir pelo menos duas visões novas sem depender exclusivamente de Excel.

---

## Notas técnicas

- Priorizar compatibilidade com artefatos existentes.
- Evitar alterar semântica histórica de células antigas sem versão de schema.
- Introduzir testes de regressão para paridade entre agregação semanal e agregações derivadas.
