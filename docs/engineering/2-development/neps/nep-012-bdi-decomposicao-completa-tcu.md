# NEP-012: BDI pré-reforma não expõe componentes TCU por categoria

**Status:** Concluído  
**Prioridade:** 🟡 Médio  
**Área:** Projetos  
**Tipo:** Feature + UX  
**Esforço:** M  
**Identificado em:** 2026-05-20  

---

## Contexto

O editor de BDI em modo Pré-Reforma exibe apenas 5 valores agregados por categoria (mao_obra, equipamentos, material, diesel, indireto) como números decimais (0.35 = 35%). Não expõe os **componentes individuais** que formam o BDI pela fórmula TCU:

```
BDI = (1 + AC + DF + R + CR + L) / (1 - T) - 1
onde:
  AC  = Administração Central
  DF  = Despesas Financeiras
  R   = Risco / Garantia / Seguros
  CR  = Contingência de Risco
  L   = Lucro / Margem
  T   = Tributos (COFINS + ISS + PIS + CSSL + IR)
```

**Problema:** O engenheiro não entende *por que* o BDI de MO é 35% — ele só vê o número final. Se precisar ajustar apenas o lucro para fechar uma margem, não tem como fazer sem recalcular manualmente.

## Visão de Produto

O modo PRE_REFORMA deve oferecer dois sub-modos:

**Modo Simplificado (padrão):** — atual, só o BDI total por categoria  
**Modo Detalhado (expandir):** — decomposição por componente

No modo detalhado, para cada categoria:
```
Mão de Obra (BDI = 35,2%)
  AC (Adm. Central):    4,0%
  DF (Desp. Financeiras): 1,0%
  R  (Risco/Garantia):   1,0%
  CR (Contingência):     2,0%
  L  (Lucro):            7,0%
  ──────────────────────────
  T  (Tributos efetivos): 16,5%
    COFINS: 3,0%  |  ISS: 5,0%  |  PIS: 0,65%  |  CSSL: 1,0%  |  IR: 1,5%
```

Editar qualquer componente recalcula o BDI total em tempo real.

## Critério de Aceite

1. Botão "▶ Ver decomposição TCU" expande o editor detalhado
2. Para cada categoria: 10 inputs de componentes (ac, df, r, cr, l, cofins, iss, pis, cssl, ir)
3. BDI total recalculado em tempo real com fórmula TCU
4. Modo simplificado mantido para quem só quer ajustar o total

## Notas Técnicas

- `ComponentesBdi` já existe em `domain/models/bdi.py` com os 10 campos
- `DEFAULT_BDI_TABELA` contém os defaults por categoria
- A fórmula já existe em `bdi.py` como propriedade `bdi_total`
- Override via `skill_inputs["06-precificacao-unitaria"]["tabela_bdi"]`
