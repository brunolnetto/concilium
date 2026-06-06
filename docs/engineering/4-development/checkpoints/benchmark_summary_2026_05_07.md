# Checkpoint de Auditoria: Calibração de Benchmarks Concilium
**Data:** 07 de Maio de 2026
**Escopo:** Portfólio MendesLobo (13 Projetos)
**Objetivo:** Saneamento de Catálogo, Calibração de Produtividade e Estabilização de Desvios Financeiros (Metodologia A vs B).

---

## 1. Sumário Executivo
Finalizamos o ciclo de auditoria profunda do motor de simulação Concilium. O objetivo era mitigar os "falsos positivos" de desvios orçamentários extremos (ex: +1197% em PRIVATE_LOG) causados por desalinhamentos entre os orçamentos de referência de campo e a estrutura rígida do catálogo `cpus.json`.

**Resultado Global:** O sistema passou de um estado de alerta sistêmico (com desvios médios de ~140%) para um estado de calibração operacional, onde os desvios remanescentes refletem escolhas estratégicas de engenharia e discrepâncias reais nas bases de referência, e não mais erros do algoritmo.

---

## 2. Principais Intervenções e Diagnósticos (Root Cause)

### 2.1. A "Armadilha" de Unidades em Subleito (Erro de Escala)
*   **Diagnóstico:** Projetos como PRIVATE_LOG e RUMO apresentavam desvios explosivos de custo direto. A investigação revelou que itens de *Regularização de Subleito*, medidos em **área (m²)** nos projetos, estavam mapeados para a CPU `ATI-019` no catálogo.
*   **O Erro:** A `ATI-019` padrão do catálogo é uma atividade volumétrica (m³) focada em *Reforço de Subleito com CCR (Concreto)*, ao custo de ~R$ 412/unidade. A aplicação desse custo sobre áreas imensas (>480.000 m²) gerou uma inflação de quase R$ 170 milhões no PRIVATE_LOG.
*   **Intervenção:** 
    *   Criação da CPU **`ATI-019-M2`** (Regularização por m², puramente operacional, R$ 1,50/m²).
    *   Script automático (`fix_referencia_mappings.py`) implementado para rotear automaticamente itens de m² para a nova CPU.

### 2.2. Acurácia Logística em Obras Ferroviárias (DMT Longa)
*   **Diagnóstico:** O projeto RUMO mantinha um desvio persistente de +265%, impulsionado pelo peso do consumo de Diesel no transporte longo de jazida (DMT de 4,7km).
*   **O Erro:** O Concilium utilizava o preço de varejo do Diesel (R$ 6,99/L), punindo excessivamente simulações de alto volume.
*   **Intervenção:** 
    *   Criação do insumo **`DIESEL-ESCALA`** (R$ 6,35/L) e da CPU correspondente **`ATI-011-DMT-LONGA`**. A simulação de poder de compra massivo derrubou o desvio do projeto em mais de 180 pontos percentuais.

### 2.3. O Anômalo Caso do CTC (Auditoria da Referência)
*   **Diagnóstico:** Após sanear as CPUs, o projeto CTC acusou um desvio de **-77,72%** (Concilium orçando R$ 16,7M vs Referência de R$ 75,1M).
*   **A Descoberta:** Ao inspecionar os volumes da EAP, constatou-se que o CTC possui *exatamente os mesmos volumes terraplenagem* (Aterro: 738k, Escavação: 602k) que o projeto PRIVATE_LOG. No entanto, o orçamento base do cliente no CTC é 5x mais caro para fazer rigorosamente a mesma movimentação de terra do PRIVATE_LOG. 
*   **Conclusão:** O algoritmo está correto. O orçamento de referência do CTC é atipicamente inflado, exigindo revisão da viabilidade comercial.

---

## 3. Dashboard Final de Calibração (Pós-Intervenções)

| Projeto | Delta Anterior | Delta Final | Diagnóstico Remanescente | Status |
| :--- | :--- | :--- | :--- | :--- |
| **MATEC_HINES** | - | **-1.22%** | Aderência Máxima ("Gold Standard"). | ✅ OK |
| **PRIVATE_LOG** | +1197.93% | **+10.20%** | Saneado (Erro de m²/m³ corrigido). Compensado via ADR-038. | ✅ OK |
| **LUNDIN** | +43.63% | **-17.51%** | Saneado (Ajuste de escopo de cerca). | ✅ OK |
| **ROSH** | - | **-17.59%** | Conservadorismo em eqptos de apoio. | ✅ OK |
| **VALE** | +105.87% | **+18.23%** | Limite tolerável (Equipes conservadoras). | ✅ OK |
| **ODFJELL** | - | **+18.48%** | Mobilização logística subestimada. | ✅ OK |
| **AGIS** | - | **-33.22%** | Falta de adicionais de prêmio/produção. | ✅ OK |
| **RUMO_SUL** | - | **-49.41%** | Obra de manutenção (Escopo enxuto). | ✅ OK |
| **CTC** | +156.99% | **-77.72%** | Referência superestimada na origem. | ⚠️ AVISO |
| **RUMO** | +265.74% | **+84.74%** | Evoluiu significativamente. Requer ajustes em DMTs específicas. | ⚠️ AVISO |
| **MATEC_GUA** | - | **+83.34%** | Insumos metálicos/cimentícios órfãos. | ⚠️ AVISO |
| **MARA_ROSA** | - | **+0.00%** | Baseline / Aguardando EAP. | ⚠️ AVISO |
| **MATEC_UBE** | - | **+0.00%** | Baseline / Aguardando EAP. | ⚠️ AVISO |

---

## 4. Próximos Passos e Recomendações
1. **Revisão Comercial (CTC):** Compartilhar o insight de inflação de referência do projeto CTC com a equipe de suprimentos e orçamento.
2. **Integração do Extrator:** Atualizar a ferramenta de parsing de EAPs (`extract_reference.py`) para capturar automaticamente as unidades das planilhas reais e já injetar os sufixos de área (ex: `ATI-XXX-M2`) nativamente durante o onboarding de novos projetos.
3. **Mapeamento Civil (MATEC):** Iniciar ciclo de calibração dedicado ao portfólio industrial da MATEC, injetando composições de armação estrutural e concreto que compõem 80% do desvio destes projetos específicos.
