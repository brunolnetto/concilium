═══════════════════════════════════════════════════════════════════════════════
PESQUISA DE MERCADO — CATÁLOGO MENDESLOBO
Atualização de Custos e Validação de Equipamentos
═══════════════════════════════════════════════════════════════════════════════

CONTEXTO
────────
Este catálogo foi gerado automaticamente da planilha PLANILHA PADRÃO RFI.xlsm e
contém 73 serviços (CPUs) baseados em dados de Mão de Obra, Equipamentos e 
Materiais de referência. Detectamos 3 questões críticas que requerem pesquisa 
e/ou confirmação com o mercado.

═══════════════════════════════════════════════════════════════════════════════
ITEM 1: COTAÇÃO URGENTE — EQUIPAMENTO SEM PREÇO
═══════════════════════════════════════════════════════════════════════════════

EQUIPAMENTO: Roçadeira Costal (E0048)
SITUAÇÃO: R$/h = 0 (sem cotação no catálogo)
IMPACTO: Custos subestimados em 2 serviços:
  • ATI-006: Aceiro (Terceirizado — Maquinaria)
  • ATI-068: Aceiro (com mão de obra)

ESPECIFICAÇÃO NECESSÁRIA:
  ┌─────────────────────────────────────────────────────┐
  │ Roçadeira Costal / Roçadeira Portátil               │
  │ • Tipo: máquina portátil para roçagem de grama/mato │
  │ • Combustível: gasolina / 2 tempos                  │
  │ • Potência típica: 2–3 HP                           │
  │ • Uso: acabamento de aceiros, limpeza lateral       │
  │ • Operação: 1 pessoa                                │
  └─────────────────────────────────────────────────────┘

CAMPOS DE PREÇO A OBTER:
  [ ] Custo de locação mensal (R$/mês)
  [ ] Custo horário de funcionamento — alocação (R$/h)
  [ ] Consumo de combustível (L/h) — para BDI diesel
  [ ] Custo de manutenção anual (% sobre custo produtivo)
  [ ] Vida útil da máquina (anos)
  [ ] Fornecedor(es) recomendado(s)

INSTRUÇÃO:
  1. Contate fornecedores locais de aluguel de máquinas (Mato Grosso do Sul / CE)
  2. Peça orçamento para locação de 30 dias (referência mensal)
  3. Pergunte se o preço inclui combustível (gasolina) e manutenção
  4. Escreva a resposta em formato:
     
     E0048 | Roçadeira Costal
     Fornecedor: ___________
     Custo locação/mês: R$ ___________
     Custo horário (alocado): R$ ___________
     Consumo combustível: ___ L/h
     Manutenção: ___ % ao ano
     Data da cotação: ___________

═══════════════════════════════════════════════════════════════════════════════
ITEM 2: VALIDAÇÃO DE COEFICIENTE — POSSÍVEL ANOMALIA
═══════════════════════════════════════════════════════════════════════════════

SERVIÇO: ATI-042 — Corpo BDCC D=1,50m PA2 — Padrão VALEC
SITUAÇÃO: Custo muito alto para unidade (R$11.249,78)
PROBLEMA: Coeficiente de Escavadeira E0016 = 55,56 unidades

COMPOSIÇÃO DA CPU ATI-042:
  • Produção horária: 0,03 m (27 metros por turno de 8h)
  • Mão de obra: P0040×1 + P0001×3 = 4 pessoas
  • Equipamento: E0016×55,56 (Escavadeira Hidráulica 22t)
  • Material: Sem material principal

CÁLCULO DETECTADO COMO ANÔMALO:
  Coeficiente E0016 = 55,56 horas de escavação por metro de bueiro
  → R$202,50/h × 55,56 = R$11.249,78 POR UNIDADE (1 metro)
  
  PERGUNTA: Isto está correto?
  • Um bueiro celular 1,50×1,50×2,00m realmente requer 55+ horas de
    escavação com Esc. 22t?
  • Ou o coeficiente deveria ser menor (ex: 5–8 horas)?

INSTRUÇÃO:
  1. Valide com engenheiro ou cronometrista de campo
  2. Verifique cronograma ou orçamento base para bueiros VALEC similares
  3. Responda:
     
     ATI-042 | Corpo BDCC D=1,50m PA2
     Coeficiente de Esc. 22t: ___ horas/metro
     Justificativa/cronograma: _____________________________
     Fonte da validação: ______ (orçamento/cronograma/campo)
     Data: ___________

═══════════════════════════════════════════════════════════════════════════════
ITEM 3: REVISÃO DE TAXAS DUPLICADAS — 30 CPUs COM MESMA PRODUÇÃO
═══════════════════════════════════════════════════════════════════════════════

SITUAÇÃO: 30 das 73 CPUs têm taxa de produção idêntica a outra CPU com mesma 
unidade. Pode indicar cópia de fórmula não revisada.

EXEMPLOS CRÍTICOS:

1️⃣  TERRAPLENAGEM — Transporte por DMT:
    ├─ ATI-011: Esc/carg/transp 1ªcat DMT≤2000m → 159,63 m³/h (3 caminhões)
    └─ ATI-012: Esc/carg/transp 1ªcat DMT 2000-3000m → 239,04 m³/h (4 caminhões)
    
    ⚠️ FLAGGED: ATI-012 tem taxa MAIOR (239 vs 159) com DMT mais longo!
       → Verificar se o ganho de 1 caminhão compensa DMT maior
       → Confirmar se 4 caminhões realmente viabiliza tal ganho

2️⃣  ESCAVAÇÃO — Profundidade de aterro diferente, mesma taxa:
    ├─ ATI-027: BSCC D=1,50m PA1 → 0,75 m/h
    ├─ ATI-028: BSCC D=1,50m PA2 → 0,75 m/h
    ├─ ATI-033: BSCC D=1,50m aterro 0-2m → 0,75 m/h (!)
    └─ ATI-034: BSCC D=1,50m aterro 6-10m → 0,75 m/h (!)
    
    ⚠️ PROBLEMA: ATI-033 (aterro 0-2m) e ATI-034 (aterro 6-10m) têm mesma
       taxa. Aterros mais profundos (6-10m) devem ser mais lentos!

3️⃣  PAVIMENTAÇÃO — Tipos completamente diferentes, mesma taxa:
    ├─ ATI-057: Pintura de ligação → 816,67 m²/h
    └─ ATI-058: CBUQ E=3,0cm → 816,67 m²/h
    
    ⚠️ CRÍTICO: Pintura é simples (~aplicação); CBUQ é compactação de
       asfalto. Como podem ter mesma produção?

LISTA COMPLETA DE DUPLICADAS (30 total):
┌──────────────────────────────────────────────────────────────────┐
│ ATI-013/014 (165,74 m³/h)  │ ATI-015/016 (144,92 m³/h)          │
│ ATI-025/026 (1,0 m/h)      │ ATI-027/028/033/034 (0,75 m/h)     │
│ ATI-029/030 (0,5 m/h)      │ ATI-032/036/037 (0,25 m/h)         │
│ ATI-043/064/072 (15,0 m/h) │ ATI-045/046 (12,825 m/h)           │
│ ATI-047/048 (11,5425 m/h)  │ ATI-054/055 (55,0 m³/h)            │
│ ATI-057/058 (816,67 m²/h)  │ ATI-063/071/073 (25,0 m²/h)        │
└──────────────────────────────────────────────────────────────────┘

INSTRUÇÃO:
  1. Para cada grupo de duplicadas, verifique:
     ✓ As especificações REALMENTE justificam a mesma taxa?
     ✓ Há diferença de equipamento, mão de obra, ou condições?
     ✓ Qual é a fonte (cronograma, experiência, norma)?
  
  2. Preencha para cada grupo problemático:
     
     GRUPO: ATI-XXX/ATI-YYY (Taxa: ___ un/h)
     Especificação ATI-XXX: _____________________________
     Especificação ATI-YYY: _____________________________
     São realmente iguais? ☐ Sim / ☐ Não
     Se NÃO, qual deveria ser a taxa correta?
       • ATI-XXX: ___ un/h (justificativa: ___________) 
       • ATI-YYY: ___ un/h (justificativa: ___________)
     Fonte de validação: ________________
     Data: ___________

═══════════════════════════════════════════════════════════════════════════════
RESUMO: O QUE FAZER AGORA
═══════════════════════════════════════════════════════════════════════════════

PRIORIDADE 1 (BLOQUEADOR) — Próximas 2 semanas:
  □ Cotação de E0048 (Roçadeira Costal)
  □ Validação de ATI-042 (coeficiente de escavação)
  □ Revisão de ATI-012 (inversão de DMT na produção)
  □ Revisão de ATI-033/034 (aterro 0-2m vs 6-10m com mesma taxa)
  □ Revisão de ATI-057/058 (pintura × CBUQ com mesma taxa)

PRIORIDADE 2 (IMPORTANTE) — Próximas 4 semanas:
  □ Validar demais 25 CPUs com taxa duplicada (se houver dúvida)
  □ Confirmar se insumos não usados (66 itens) devem permanecer

ANTES DE USAR O CATÁLOGO EM ORÇAMENTO:
  ✓ Todos os alertas [FIX-3] e [FIX-4] revisados
  ✓ E0048 recebeu cotação (ou removido das CPUs)
  ✓ Coeficientes anômalos validados
  ✓ Assinar termo de aceite: "Catálogo revisado e aprovado para uso"

═══════════════════════════════════════════════════════════════════════════════
COMO USAR ESTE PROMPT
═══════════════════════════════════════════════════════════════════════════════

1. ENVIE para:
   • Fornecedores de equipamentos (E0048)
   • Engenheiro de campo / cronometrista (ATI-042, ATI-012, ATI-033/034, ATI-057/058)
   • Gerente de projetos (validação geral)

2. COLETE as respostas em formato estruturado (cópia/cola de cada item acima)

3. RETORNE para integração:
   python scripts/integrate_market_research.py < respostas.txt
   
   (Script a ser criado para atualizar JSON com novos preços e alertas)

4. RE-AUDITE:
   python scripts/audit_mendeslobo_catalog.py
   
   Deve remover todos os alertas [FIX-3] e [FIX-4] se todas as revisões forem OK

═══════════════════════════════════════════════════════════════════════════════
