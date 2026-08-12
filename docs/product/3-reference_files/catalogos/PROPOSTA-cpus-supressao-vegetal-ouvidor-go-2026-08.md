# Proposta — CPUs reais de Supressão Vegetal (SUPRESSÃO SERRA VERDE / OUVIDOR-GO, agosto/2026)

**Status:** 🆕 Proposta — não aplicada ao catálogo. Preparar para entrada via tool de governança
(`criar_cpu`/`atualizar_composicao_item_cpu`, fluxo rascunho → 4-olhos → merge).

**Origem:** planilha de composição unitária de serviço fornecida pelo usuário (fonte primária real,
substitui as reconstruções especulativas anteriores — `v7.json`/`v8.json`/`v11.json`/`v12.json` do
contexto `mendeslobo`). Todos os 9 totais (equipamento, mão de obra, produção, custo unitário) foram
recalculados e conferem exatamente com os valores da planilha — alta confiança de transcrição.

## Achado principal

**O catálogo `mendeslobo` nunca teve as CPUs reais deste projeto.** As CPUs usadas na EAP
(`CPU-TERRA-ATI-001`, `CPU-TERRA-ATI-002`) são placeholders genéricos, sem relação com a composição
real cotada:

| CPU usada na EAP | Descrição no catálogo | Composição no catálogo | Composição real (esta planilha) |
|---|---|---|---|
| `CPU-TERRA-ATI-001` | "Supressão vegetal DAP≥0,30 **e arbustos**" (genérica, combina tudo), unidade **un** | 1 motosserrista + 3 ajudantes + 2 equip., `valor_horario=6.0` | Mata densa: frota pesada (pá+caminhões+tratores+escavadeira+motosserras, ~15 pessoas), 582-667 m²/h — **9,3× mais produtivo** que árvore isolada, que usa frota menor (~7 pessoas), 62-64 m²/h. **A mesma CPU foi usada para as duas atividades na EAP**, apesar de serem fisicamente muito diferentes. |
| `CPU-TERRA-ATI-002` | "Limpeza camada vegetal 20cm" (usada só como aproximação, conforme comentário no item de EAP) | 1 escavadeira + 2 ajudantes, `valor_horario=750/500` | Vegetação arbustiva: frota pesada equivalente à mata densa (sem motosserra), 511-963 m²/h |
| — | Não existe CPU de topsoil nem de movimentação de madeira | — | Remoção de topsoil (267-365 m³/h) e movimentação de madeira (20,6 m³/h) — sem CPU dedicada hoje |

`CPU-TERRA-ATI-003` (a mais parecida em estrutura) usa códigos `AGIS-*` — frota emprestada de outro
projeto/benchmark (AGIS), com `valor_horario=738`, sem relação com nenhum dos 6 valores reais de
vegetação desta planilha.

**Conclusão:** a causa do "avanço quase-zero" investigada anteriormente não foi só a incompatibilidade
de unidade (un vs m²) — essa era um sintoma real, mas superficial, de um problema maior: nenhuma CPU
no catálogo corresponde à composição real cotada para este projeto.

## As 9 composições reais

Todas com `fonte_preco: "negociado"`, `data_referencia_preco: "2026-08-01"`,
`atributos_especificos.memoria_calculo: "Planilha SUPRESSÃO SERRA VERDE / OUVIDOR-GO, agosto/2026"`
(satisfaz o gate `VAL-CAT-NEGOCIADO-01` do ADR-181 F6).

### Convenção de código proposta

Próximos códigos livres na faixa `CPU-TERRA-ATI-0XX` (existente vai até 040, depois pula pra 080):

| Código proposto | Serviço | DMT | Unidade | Produção (C) | Custo direto unitário (D) |
|---|---|---|---|---|---|
| `CPU-TERRA-ATI-041` | Supressão vegetal Mata Densa | ≤6km | M² | 582,75/h | R$ 5,96 |
| `CPU-TERRA-ATI-042` | Supressão de árvore isolada | ≤6km | M² | 62,36/h | R$ 16,89 |
| `CPU-TERRA-ATI-043` | Supressão de vegetação arbustiva | ≤4,5km | M² | 510,75/h | R$ 5,65 |
| `CPU-TERRA-ATI-044` | Remoção de topsoil | ≤4,5km | M³ | 267,47/h | R$ 10,30 |
| `CPU-TERRA-ATI-045` | Supressão vegetal Mata Densa | ≤1km | M² | 666,90/h | R$ 4,49 |
| `CPU-TERRA-ATI-046` | Supressão de árvore isolada | ≤1km | M² | 64,05/h | R$ 16,06 |
| `CPU-TERRA-ATI-047` | Supressão de vegetação arbustiva | ≤1km | M² | 963,00/h | R$ 2,48 |
| `CPU-TERRA-ATI-048` | Remoção de topsoil | ≤1km | M³ | 365,05/h | R$ 5,30 |
| `CPU-TERRA-ATI-049` | Movimentação/armazenamento de madeira | ≤0,5km | M³ | 20,60/h | R$ 59,31 |

**Nota sobre a EAP existente**: os projetos `60d6decc-...`/`ddab7d94-...` (CMOC Ouvidor/GO) têm
`eap-1_1`/`eap-2_1` (mata densa) e `eap-1_2`/`eap-2_2` (árvores isoladas) apontando para a **mesma**
`CPU-TERRA-ATI-001` — precisam ser corrigidos para `CPU-TERRA-ATI-041`/`045` (mata densa) e
`CPU-TERRA-ATI-042`/`046` (árvore isolada) respectivamente, já que são composições 9× diferentes em
produtividade. `eap-1_3`/`eap-2_3` (arbustiva) migram de `CPU-TERRA-ATI-002` para
`CPU-TERRA-ATI-043`/`047`.

## Insumos — nenhum preço existente bate; recomendação é criar novos

Cruzei cada item de equipamento/mão de obra com o catálogo (`mendeslobo`, genérico e `SV-*` de Serra
Verde). **Nenhum preço existente está próximo o suficiente pra ser reaproveitado com segurança** — a
diferença mais provável é regional/contratual (este é um subcontrato específico para supressão
vegetal em Ouvidor-GO, agosto/2026), não uma duplicata do mesmo recurso. Reaproveitar um `insumo_id`
existente sobrescreveria o preço pra todos os outros consumidores desse insumo no catálogo — proposta
é criar códigos novos, prefixo `SV-OUV-` (Serra Verde / Ouvidor), preservando os preços genéricos e
os `SV-*` (Serra Verde, turno 12×36) intactos.

### Equipamento (preço/h + consumo de combustível)

| Código proposto | Descrição | Preço/h (RFI) | Combustível | Consumo (L/h) | Candidato mais próximo no catálogo (não reaproveitado) |
|---|---|---|---|---|---|
| `SV-OUV-EQ-PA-MANDIBULA` | Pá carregadeira com mandíbula | R$ 300,00 | Diesel S10 | 16,00 | `E0044`/`EQ-E0044` (R$134-250/h) |
| `SV-OUV-EQ-CAM-BASC-14M3` | Caminhão basculante 14 m³ | R$ 125,00 | Diesel S10 | 2,50 | `AGIS-E0002` (R$122,48/h) — mais próximo, ainda assim distinto |
| `SV-OUV-EQ-TRAT-EST-20T` | Trator de esteiras 20T | R$ 245,00 | Diesel S10 | 26,00 | `EQ-E0024`/`AGIS-TRAT-EST-20T` (R$238-239/h) |
| `SV-OUV-EQ-ESCAV-22T` | Escavadeira hidráulica sobre esteira 22T | R$ 190,00 | Diesel S10 | 22,00 | `EQ-E0016` (R$202,50/h) — mais próximo |
| `SV-OUV-EQ-MOTOSSERRA` | Motosserra a gasolina | R$ 30,00 | Gasolina | 1,50 | `E0018`/`EQ-MOTOSSERRA` — **match exato** (R$30,00/h), avaliar reaproveitar |
| `SV-OUV-EQ-PA-12T` | Pá carregadeira 12t | R$ 160,00 | Diesel S10 | 16,00 | `EQ-PA-CARREG-12T`/`E0024` (R$104,50/h) |
| `SV-OUV-EQ-PA-18T` | Pá carregadeira 18t | R$ 225,00 | Diesel S10 | 25,00 | Não existe 18t no catálogo — novo obrigatório |

### Mão de obra (salário base/h)

| Código proposto | Descrição | Custo/h (RFI) | Candidato mais próximo (SV-*, turno 12×36) |
|---|---|---|---|
| `SV-OUV-MO-OPER-PA` | Operador de pá carregadeira | R$ 30,40 | `SV-P0045-D` (R$22,84/h) |
| `SV-OUV-MO-OPER-ESCAV` | Operador de escavadeira | R$ 43,19 | `SV-P0040-D` (R$27,08/h) |
| `SV-OUV-MO-MOTOR-BASC` | Motorista de caminhão basculante | R$ 28,15 | `SV-P0032-D` (R$18,48/h) |
| `SV-OUV-MO-AJUDANTE` | Ajudante | R$ 18,24 | sem equivalente horário (só mensal, ex. `MO-AJUDANTE` R$2043,36/mês) |
| `SV-OUV-MO-SINALEIRO` | Sinaleiro | R$ 18,81 | sem equivalente horário |
| `SV-OUV-MO-OPER-TRAT-EST` | Operador de Trator de Esteiras | R$ 43,23 | `SV-P0048-D` (R$26,91/h) |
| `SV-OUV-MO-OPER-MOTOSSERRA` | Operador de motosserra | R$ 24,75 | `AGIS-FN-OPER-MOTOSSERRA` (R$42,70/h) |

## Composições completas (funções + equipamentos por CPU)

```
CPU-TERRA-ATI-041 — Mata Densa, DMT≤6km, M², produção 582,75/h
  equipamentos: PA-MANDIBULA×1, CAM-BASC-14M3×3, TRAT-EST-20T×4, ESCAV-22T×1, MOTOSSERRA×2
  funcoes: OPER-PA×1, OPER-ESCAV×1, MOTOR-BASC×3, AJUDANTE×4, SINALEIRO×1, OPER-TRAT-EST×4, OPER-MOTOSSERRA×2

CPU-TERRA-ATI-042 — Árvore isolada, DMT≤6km, M², produção 62,36/h
  equipamentos: PA-12T×1, CAM-BASC-14M3×1, MOTOSSERRA×2, ESCAV-22T×1
  funcoes: OPER-PA×1, OPER-ESCAV×1, MOTOR-BASC×1, AJUDANTE×2, SINALEIRO×1, OPER-MOTOSSERRA×2

CPU-TERRA-ATI-043 — Vegetação arbustiva, DMT≤4,5km, M², produção 510,75/h
  equipamentos: PA-MANDIBULA×1, CAM-BASC-14M3×3, TRAT-EST-20T×3, ESCAV-22T×1
  funcoes: OPER-PA×1, OPER-ESCAV×1, MOTOR-BASC×3, AJUDANTE×4, SINALEIRO×2, OPER-TRAT-EST×3

CPU-TERRA-ATI-044 — Remoção topsoil, DMT≤4,5km, M³, produção 267,47/h
  equipamentos: PA-18T×1, CAM-BASC-14M3×8, TRAT-EST-20T×2
  funcoes: OPER-PA×1, MOTOR-BASC×8, OPER-TRAT-EST×2

CPU-TERRA-ATI-045 — Mata Densa, DMT≤1km, M², produção 666,90/h
  equipamentos: PA-MANDIBULA×1, CAM-BASC-14M3×3, TRAT-EST-20T×3, ESCAV-22T×1, MOTOSSERRA×2
  funcoes: OPER-PA×1, OPER-ESCAV×1, MOTOR-BASC×3, AJUDANTE×4, SINALEIRO×1, OPER-TRAT-EST×3, OPER-MOTOSSERRA×2

CPU-TERRA-ATI-046 — Árvore isolada, DMT≤1km, M², produção 64,05/h
  equipamentos: PA-12T×1, CAM-BASC-14M3×1, MOTOSSERRA×2, ESCAV-22T×1
  funcoes: OPER-PA×1, OPER-ESCAV×1, MOTOR-BASC×1, AJUDANTE×2, SINALEIRO×1, OPER-MOTOSSERRA×1
  ⚠️ nota da fonte: 2 motosserras em campo mas só 1 operador orçado na planilha original — preservado
     como está na fonte, não "corrigido"; sinalizar para confirmação com quem preencheu o RFI.

CPU-TERRA-ATI-047 — Vegetação arbustiva, DMT≤1km, M², produção 963,00/h
  equipamentos: PA-MANDIBULA×1, CAM-BASC-14M3×3, TRAT-EST-20T×2, ESCAV-22T×1
  funcoes: OPER-PA×1, OPER-ESCAV×1, MOTOR-BASC×3, AJUDANTE×4, SINALEIRO×1, OPER-TRAT-EST×2

CPU-TERRA-ATI-048 — Remoção topsoil, DMT≤1km, M³, produção 365,05/h
  equipamentos: TRAT-EST-20T×2, PA-18T×1, CAM-BASC-14M3×3
  funcoes: OPER-TRAT-EST×2, OPER-PA×1, MOTOR-BASC×3, SINALEIRO×2
  nota: material auxiliar "BRITA" listado na planilha com custo unitário R$0 (referência, não custeado)

CPU-TERRA-ATI-049 — Movimentação/armazenamento de madeira, DMT≤0,5km, M³, produção 20,60/h
  equipamentos: PA-MANDIBULA×1, CAM-BASC-14M3×4
  funcoes: OPER-PA×1, MOTOR-BASC×4, AJUDANTE×4, SINALEIRO×1
```

Todos os totais (equipamento + mão de obra + combustível → custo unitário D) foram recalculados e
conferem exatamente com a planilha original — ver seção de conferência interna (não incluída aqui,
disponível sob pedido).

## Próximos passos recomendados

1. Criar os 12 insumos novos (`SV-OUV-EQ-*`/`SV-OUV-MO-*`) via `criar_insumo` — avaliar caso a caso se
   `SV-OUV-EQ-MOTOSSERRA` deve reaproveitar `EQ-MOTOSSERRA`/`E0018` (match exato de preço) ou seguir o
   padrão de isolamento por escopo negociado.
2. Criar as 9 CPUs (`CPU-TERRA-ATI-041` a `049`) + suas produtividades, via `criar_cpu`/tool
   equivalente, com `origem: {tipo: "negociado", referencia: "RFI SUPRESSÃO SERRA VERDE / OUVIDOR-GO ago/2026"}`.
3. Corrigir os itens de EAP dos projetos `60d6decc-...`/`ddab7d94-...` para apontar para as CPUs
   corretas (ver "Nota sobre a EAP existente" acima) — isso deve resolver o cronograma sem precisar de
   92 equipes nem deixar infactível com 8.
4. Os valores de mob/desmob/canteiro/madeira do `v7.json` (lump "negociado" sem composição) continuam
   pendentes — esta planilha não os cobre (é só produção/custo direto das atividades de supressão em
   si). Confirmar com o cliente/fornecedor se existe uma planilha equivalente pra esses 4 itens.
