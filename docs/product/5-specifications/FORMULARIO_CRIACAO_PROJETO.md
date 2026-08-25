# Formulário de Criação de Projeto (preenchível)

**Baseado em:** [`spec-formulario-projeto.md`](spec-formulario-projeto.md) (v3.0)
**Schema canônico:** `config/schemas/projeto_spec.schema.json`
**Ponto de entrada MCP:** `criar_projeto_formulario`

> Este documento é a versão "papel" da especificação acima: os mesmos Blocos 1-7,
> mas como campos a preencher em vez de um roteiro de conversa. Use-o para levantar
> os dados em campo/reunião antes de repassar ao agente (ou preencher direto, se
> quem estiver conduzindo já conhece o sistema). Campos marcados **(obrigatório)**
> não têm default — sem eles o projeto não pode ser criado.

---

## Bloco 1 — Identificação **(obrigatório)**

| Campo | Valor |
|---|---|
| Nome da obra | |
| Tipo de obra (`terraplenagem` / `pavimentacao` / `saneamento`) | |
| Localização (Cidade, UF) | |
| Data de início | |
| Prazo contratual / data de término | |

---

## Bloco 2 — Regime de trabalho

*Padrão MendesLobo: 6 dias/semana, 8h/dia. Só preencha se a obra for diferente.*

| Campo | Valor | Default |
|---|---|---|
| Dias por semana | | 6 |
| Horas por dia | | 8 |
| Horas improdutivas por dia (deslocamento interno, preparação de frente) | | 0,5 |

---

## Bloco 3 — Serviços do escopo (EAP) **(obrigatório)**

Liste todos os serviços do escopo. Não precisa saber o `cpu_id` — descreva em linguagem
de obra que o agente resolve a composição correspondente.

| Item (EAP) | Descrição do serviço | Quantitativo | Unidade | Predecessor(es) | % do predecessor concluído para iniciar | Defasagem (lag, semanas) |
|---|---|---|---|---|---|---|
| | | | | | | |
| | | | | | | |
| | | | | | | |

> Deixe "Predecessor(es)" em branco se o item pode começar junto com o início da obra.
> Toda dependência é finish-to-start (o sucessor não termina antes de o predecessor
> começar). Por padrão o sucessor só inicia com o predecessor **100% concluído**;
> para permitir sobreposição (ex.: começar a compactar quando 80% do aterro já foi
> lançado), informe o percentual na coluna acima.

---

## Bloco 4 — Custos de canteiro (indiretos)

*Deixe todos os campos em branco por padrão. O sistema já deriva ADM, TOP, LAB,
QSMS e o benefício de Alojamento automaticamente a partir do catálogo (preço
real por função/insumo) e da composição de recursos do próprio projeto — o
mesmo mecanismo usado para EPI/treinamento/exame por função (ADR-165–170). Só
preencha um campo abaixo quando existir um **valor contratual ou negociado**
que deva substituir esse cálculo (ex.: acordo já fechado com um fornecedor
terceirizado de QSMS por um preço fixo diferente do catálogo).*

> **Atenção:** preencher um valor aqui **substitui inteiramente** o cálculo
> automático daquela categoria — não é somado a ele. Não preencha "para ser
> completo": isso descarta um número mais preciso vindo do catálogo em favor de
> uma estimativa manual.

| Categoria | Override mensal (R$) — deixe em branco para cálculo automático |
|---|---|
| ADM (administrativo) | |
| TOP (supervisão/topografia) | |
| LAB (laboratório) | |
| QSMS (segurança/qualidade/meio ambiente) | |

### Mobilização e desmobilização

*Hoje sem derivação automática por composição de recursos (informe o valor
total quando conhecido; sem esse dado, o agente usa defaults de benchmark —
MARA_ROSA para obras pequenas/curtas, AGIS para médias/grandes). A ADR-176
propõe unificar este custo com o de mobilização de equipamentos/mão de obra
já calculado em outras partes do pipeline — quando isso for implementado,
este campo passa a ser overload no mesmo sentido do Bloco 4 acima, não mais
o único caminho.*

| Fase | Valor total (R$, one-time) |
|---|---|
| Mobilização | |
| Desmobilização | |

---

## Bloco 5 — Regime tributário e lucro

| Campo | Valor | Default |
|---|---|---|
| Regime tributário (`lucro_presumido` / `simples_nacional` / `lucro_real`) | | `lucro_presumido` |
| Lucro objetivo da obra (%) | | 9% direto / 5% indireto |
| ISS do município, se diferente do padrão da jurisdição (%) | | — |

> Um único percentual de lucro informado aqui é traduzido pelo agente para todas as
> categorias de BDI (mão de obra, serviços, material, diesel, indireto), com os tetos
> de 4% (material/diesel) e 5% (indireto) previstos na spec.

---

## Bloco 6 — Ritmo e mobilização

| Campo | Valor | Default |
|---|---|---|
| Semanas de mobilização (montagem de canteiro antes da produção) | | 2 |
| Semanas de desmobilização (após a última semana de produção) | | 1 |

> Obras grandes (>R$50M ou >24 meses): considerar 3 semanas de mobilização e 2 de
> desmobilização.

---

## Bloco 7 — Disponibilidade de equipamentos

*Preencher só se a região tiver restrição real de mercado (localidade remota ou de
difícil acesso). Deixe em branco para irrestrito.*

| Tipo de equipamento/recurso | Quantidade máxima disponível na região |
|---|---|
| | |
| | |

---

## Checklist antes de entregar o formulário

- [ ] Bloco 1 completo (nome, tipo de obra, localização, datas)
- [ ] Bloco 3 completo — todos os serviços do escopo, com quantitativo e unidade
- [ ] Predecessores da EAP revisados (dependências entre itens fazem sentido)
- [ ] Overrides de indiretos deixados em branco, salvo quando há valor contratual/negociado real que deva substituir o cálculo automático
- [ ] Lucro objetivo e regime tributário confirmados
- [ ] Restrição de equipamento revisada com o time de suprimentos, se aplicável

Depois de preenchido, entregue este formulário ao engenheiro/agente responsável pela
criação do projeto (`criar_projeto_formulario`). Dúvidas sobre um campo específico:
consulte a tabela de mapeamento técnico em
[`spec-formulario-projeto.md`](spec-formulario-projeto.md#mapeamento-técnico-referência-para-o-agente).
