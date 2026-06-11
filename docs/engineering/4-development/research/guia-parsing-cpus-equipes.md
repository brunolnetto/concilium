# Guia de Parsing Manual: cpus.txt e equipes.txt

**Projeto:** Concilium — MendesLobo Construtora  
**Data:** 2026-06-09  
**Objetivo:** Instruções para extração fidedigna de dados de composição de equipe e calibração de insumos a partir dos arquivos raw dos benchmarks.

---

## 1. Arquivos Raw Disponíveis por Benchmark

| Benchmark | cpus.txt | cronograma.txt | planejamento.txt | producoes.txt |
|---|---|---|---|---|
| AGIS | ✅ 13 CPUs | ✅ | ✅ | ❌ |
| RUMO | ✅ 17 CPUs | ✅ | ✅ | ❌ |
| PRIVATE_LOG | ✅ 9 CPUs | ✅ | ✅ | ❌ |
| ODFJELL | ✅ 19 CPUs | ❌ | ✅ | ❌ |
| MATEC_GUARULHOS | ✅ 6 CPUs | ❌ | ✅ | ❌ |
| VALE | ✅ 11 CPUs | ✅ | ✅ | ❌ |
| CTC | ✅ 26 CPUs | ✅ | ✅ | ❌ |
| LUNDIN | ✅ 5 CPUs | ✅ | ✅ | ✅ (separado) |
| MARA_ROSA | ✅ 6 CPUs | ✅ | ✅ | ✅ (catálogo padrão) |
| ROSH | ✅ 6 CPUs | ✅ | ✅ | ✅ (= MARA_ROSA) |
| MATEC_HINES | ❌ sem CPUs | ✅ | ✅ | ❌ |
| MATEC_UBERLANDIA | ✅ 8 CPUs | ✅ | ✅ | ❌ |

> `producoes.txt` no LUNDIN contém produção horária por item de cronograma — substitui a extração da linha C das CPUs.

---

## 2. Estrutura do cpus.txt

Cada arquivo contém **N blocos de Composição Unitária de Serviço (CPU)**, separados por uma linha de traços (`---...---`).

### 2.1 Cabeçalho de bloco

```
	OBRA:		COMPOSIÇÃO UNITÁRIA DE SERVIÇO
	
	CÓDIGO	DATA BASE	SERVIÇO						UNIDADE
	2.1	maio, 2026	ESCAVAÇÃO (...) DMT ATÉ 2000M			M3
```

| Campo | Posição (tab-split) | Nota |
|---|---|---|
| `codigo` | col[1] | Pode ser `-` (sem SICRO/SINAPI associado) ou número como `4413984` |
| `data_base` | col[2] | Mês e ano da composição |
| `descricao` | col[4] ou col[3] | Nome completo do serviço |
| `unidade` | última col não-vazia | `M3`, `m²`, `und`, `m`, etc. |

> **Atenção:** A linha de código vem APÓS a linha de cabeçalho `CÓDIGO | DATA BASE | SERVIÇO | UNIDADE`. Sempre pule a linha de rótulos antes de parsear o código real.

### 2.2 Seção EQUIPAMENTO (A)

```
	EQUIPAMENTO (A)		CÓDIGO	QUANT.	UTILIZAÇÃO		CUSTO OPERACIONAL		CUSTO
					PROD.	IMPROD.	PROD.	IMPROD.	HORÁRIO
E0015	Escavadeira hidráulica 38T		 1,00 	 1,00 	 -   	 268,40 	 268,40 	 268,40
E0002	Caminhão basculante 14 m³		 7,00 	 1,00 	 -   	 122,48 	 122,48 	 857,33
	Caminhão carroceria				 1,00 	 -   	 50,00 	 50,00 	 -
								TOTAL	 1.125,73
```

Colunas relevantes (linha de cada equipamento):

| Col (tab) | Conteúdo | Extração |
|---|---|---|
| col[0] | Código SICRO (opcional, ex: `E0015`) ou vazio | Ignorar se vazio |
| col[1] | Nome do equipamento | **Chave de identificação** |
| col[3] | Quantidade produtiva | Quantidade da equipe |
| col[8] | **Custo horário total** (quant × custo unitário) | Valor a extrair |

> O **TOTAL** da seção (linha `TOTAL | valor`) representa o somatório `Σ(custo_horario_eq)` — pode ser usado como conferência.

**Cuidado:** Equipamentos com quantidade improdutiva (`Caminhão carroceria 0 horas prod`) têm custo produtivo `0` mas custo improdutivo. Eles aparecem com `-` na coluna produtiva.

### 2.3 Seção MÃO DE OBRA SUPLEMENTAR (B)

```
	MÃO DE OBRA SUPLEMENTAR (B)			CÓDIGO		QUANT	SALÁRIO BASE	CUSTO HORÁRIO
	Operador de escavadeira					 1,00 	 42,70 	 42,70
	Ajudante						 1,00 	 19,45 	 19,45
	Encarregado de Frente					 0,50 	 34,09 	 17,05
							TOTAL	 345,93
```

Colunas relevantes:

| Col posição | Conteúdo | Extração |
|---|---|---|
| col[1] | Nome da função/cargo | **Chave de identificação** |
| col[-2] | **Salário-base R$/h** | Preço do insumo — calibrar aqui |
| col[-1] | Custo horário total (quant × salário) | Valor calculado |

> O salário-base é o insumo que queremos em `insumos_overlay.json`. Multiplicado pela quantidade, dá o custo horário MO total da CPU.

### 2.4 Linha de Produção — PRODUÇÃO DA EQUIPE (C)

```
	PRODUÇÃO DA EQUIPE (C)	231,87	M3		CUSTO HORÁRIO TOTAL (A+B)     	 1.471,66
```

| Dado | Posição | Variável no sistema |
|---|---|---|
| **P** (produção) | Primeiro valor numérico após `(C)` | `valor_horario` [unid/h] |
| **C_ref** (custo hora) | Último valor numérico da linha | `custo_hora_total_referencia` [R$/h] |

> **Regra:** `C_ref = A_total + B_total`. Ou seja: `custo_hora_total_referencia = soma(equipamentos) + soma(mao_de_obra)`. Não inclui diesel.

### 2.5 Seção COMBUSTÍVEL

```
	COMBUSTÍVEL		CÓDIGO	UNID.	CUSTO	CONSUMO	CUSTO UNITÁRIO
	Escavadeira 38T		Diesel S10	L	 6,99 	 26,00 	 181,74
	Caminhão bascul 14m³	Diesel S10	L	 6,99 	 2,50 	 122,33
							TOTAL	 304,07
```

| Dado | Posição | Extração |
|---|---|---|
| Nome do combustível | após código SICRO | `Diesel S10`, `Gasolina`, etc. |
| **Preço R$/L** | col após `UNID.` | **Insumo: preço diesel do projeto** |
| Consumo l/h por equipamento | col seguinte | Consumo do equipamento específico |
| Custo unitário | última col | Calculado = preço × consumo × quant |

> **Importante:** Quando diesel está com `-` em todas as células (ex: LUNDIN), significa que o custo de combustível já está embutido no **Custo Operacional** da seção (A). Não somar neste caso.

---

## 3. Regras de Parsing por Seção

### 3.1 Identificação de limites de bloco

```
Início de bloco: linha contém "COMPOSIÇÃO UNITÁRIA DE SERVIÇO"
Fim de bloco: linha de traços "---...---" (70+ caracteres)
             OU início de novo bloco
```

### 3.2 Normalização de valores numéricos brasileiros

Todos os valores seguem o padrão PT-BR:
- Separador decimal: vírgula → substituir por ponto
- Separador de milhar: ponto → remover

```python
def br_float(s: str) -> float:
    return float(s.strip().replace(' ', '').replace('.', '').replace(',', '.'))
```

Tratamento de valores especiais:
- `" -   "` → `0.0`
- `" -  "` → `0.0`
- Células vazias → `0.0`

### 3.3 Pular linhas de cabeçalho

As seguintes strings indicam linhas de cabeçalho/rótulo — **nunca parsear como dados**:

```
"TOTAL", "CÓDIGO", "QUANT", "SALÁRIO BASE", "CUSTO HORÁRIO",
"PROD.", "IMPROD.", "EQUIPAMENTO (A)", "MÃO DE OBRA SUPLEMENTAR",
"COMBUSTÍVEL", "PRODUÇÃO DA EQUIPE", "ATIVIDADES AUXILIARES",
"MATERIAIS / ATIVIDADES", "TRANSPORTE", "CUSTO DIRETO TOTAL",
"BDI:", "CUSTO TOTAL UNITÁRIO"
```

---

## 4. Preços de Diesel por Benchmark (Extraídos)

| Benchmark | Diesel S10 (R$/L) | Gasolina (R$/L) | Nota |
|---|---|---|---|
| AGIS | **6,99** | 6,49 | CE |
| RUMO | **6,10** | 7,00 | MT |
| PRIVATE_LOG | **6,17** | 6,00 | ES |
| ODFJELL | **6,15** | 5,82 | GO |
| MATEC_GUARULHOS | **6,54** | — | SP |
| VALE | **6,50** / 6,80 | — | GO (dois valores — CPUs distintas) |
| CTC | **6,30** | 6,70 | RS |
| LUNDIN | **embutido** | 6,80 | GO (sem preço explícito na seção C) |

---

## 5. Salários-Base por Benchmark

Salários em R$/hora que devem alimentar `insumos_overlay.json`:

| Função | AGIS | RUMO | PRIVATE_LOG | VALE | LUNDIN |
|---|---|---|---|---|---|
| Operador de Escavadeira | 42,70 | 31,77 | 31,77 | 38,12 | 34,94 |
| Operador de Trator de Esteiras | 42,70 | 39,33 | 39,33 | 47,19 | 43,26 |
| Operador de Motoniveladora | 42,70 | 31,77 | 31,77 | 38,12 | — |
| Motorista Caminhão Basculante | 38,10 | 23,69 | 23,69 | — | 31,76 |
| Operador de Rolo Compactador | 38,10 | 19,06 | 19,06 | — | — |
| Encarregado de Frente | 34,09 | — | — | — | — |
| Ajudante | 19,45 | 14,50 | 15,73 | 18,88 | 15,73 |

> A diferença entre AGIS e os demais reflete **convenções coletivas estaduais** distintas (CE vs MT/ES/GO/RS). Isso é exatamente a variável de calibração para `insumos_overlay.json`.

---

## 6. Como Contribuir com o Parsing

### 6.1 O que extrair por CPU

Para cada bloco de CPU no cpus.txt, registre:

```
CÓDIGO:    [código ou "-" se sem SICRO]
SERVIÇO:   [descrição completa]
UNIDADE:   [M3, m², und, m, etc.]

PRODUÇÃO:  P = [valor] [unid]/h
CUSTO_REF: C = [valor] R$/h (= A_total + B_total)

EQUIPAMENTOS:
  [Nome] | quant=[n] | custo_horario=[A] R$/h

MÃO DE OBRA:
  [Função] | quant=[n] | salario_base=[R$/h] | custo_horario=[total] R$/h

DIESEL: preço=[R$/L]  (ou "embutido" se zerado na seção)
```

### 6.2 Casos especiais a documentar

**Equipamentos zerados (só improdutivos):** Caminhões de suporte, motoniveladoras como backup. Custo produtivo = 0, mas fazem parte da composição.

**Funções com quantidade fracionada:** Ex: `Encarregado de Frente: 0,50` → um encarregado atende 2 frentes. O custo horário é `salario × 0,50`.

**CPUs com código "-":** Composição proprietária do projetista, sem código SICRO/SINAPI. A calibração deve ser feita exclusivamente pelos salários e preços de diesel informados.

**LUNDIN producoes.txt:** Substitui a extração de P da linha (C) das CPUs. Tem formato distinto:

```
ITEM    SERVIÇO             UNID    PRODUÇÃO HORARIA/EQUIPE    PRODUÇÃO DIÁRIA/EQUIPE
1.3     SUPRESSÃO VEGETAL   M2      884,80                     7.078,40
```

A produção diária = `P × horas_dia` (conferência).

### 6.3 Identificação de merges EAP↔Cronograma

Ao parsear um cronograma com itens consolidados, verifique se a CPU associada no referencia.json cobre **todos** os subitens do planejamento com o mesmo código de equipe. Exemplos documentados:

- **AGIS 1.1:** Cobre itens de cronograma 1.1 (DMT≤2km) + 1.2 (DMT 2-3km) do planejamento. A CPU 2.1 é usada para ambos mesmo tendo CPUs distintas (2.1 e 2.2) — merge por simplificação.
- **RUMO seção 5:** Itens 5.10–5.19 no planejamento (escavações de valas de drenagem repetidas para trechos distintos) ausentes do cronograma — redução de escopo.
- **CTC:** Cronograma tem apenas 6 atividades (somente terraplenagem) para 45 itens no planejamento — redução drástica de escopo; as seções 2 (drenagem), 3 (pavimentação) e 4 (administração) foram removidas.

---

## 7. Estrutura-Alvo: insumos_overlay.json

Cada projeto deve ter um `overrides/insumos_overlay.json` com:

```json
{
  "diesel_s10": 6.99,
  "gasolina": 6.49,
  "salarios": {
    "operador_escavadeira": 42.70,
    "operador_trator_esteiras": 42.70,
    "operador_motoniveladora": 42.70,
    "motorista_caminhao_basculante": 38.10,
    "operador_rolo_compactador": 38.10,
    "encarregado_frente": 34.09,
    "ajudante": 19.45
  }
}
```

Com esses valores, o sistema recomputa `custo_hora = f(composicao, insumos)` sem necessitar de `custo_hora_total_referencia` como shortcut.

> **Por que isso é correto:** O `custo_hora_total_referencia` da planilha já é resultado de `A + B = Σ(eq_custo_horario) + Σ(mo_quant × salario)`. Se calibramos os salários e custos de equipamento por projeto, o `custo_hora` calculado **automaticamente converge** para o valor da planilha — sem override por CPU.
