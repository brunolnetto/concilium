# ADR-048 — API e UI para iteracao rapida de execucao, override e comparacao de pipelines

**Status:** Implementado
**Data:** 2026-05-13
**Contexto:** MendesLobo Construtora — Concilium

---

## Contexto

### Problema

P1. O Concilium hoje opera principalmente por CLI e MCP, o que atende automacao e integracao tecnica, mas nao oferece uma superficie de iteracao rapida para analise humana e ajuste fino de projetos.

P2. O fluxo real de trabalho exige criar projeto, executar pipeline, aplicar ajuste local, rerodar com rastreabilidade e comparar execucoes sem perder o lineage.

P3. A experiencia atual depende de comandos e leitura de artefatos, o que reduz velocidade de validacao e dificulta comparacao visual entre cenarios.

P4. O produto ja possui as entidades e stores necessarios no dominio e na infraestrutura, entao a nova camada nao deve reinventar projeto, escopo, plano, lifecycle nem persistencia local.

P5. A UI deve acelerar a iteracao, mas a logica de negocio precisa permanecer no backend para preservar determinismo, auditoria e coerencia com a estrutura DDD.

## Decisao

### D1. Criar uma API canonica como contrato principal de operacao

A API deve expor a operacao de projeto, execucao de pipeline, override, rerun e comparacao entre execucoes. Ela e a fonte de verdade para a UI, para futuras integracoes e para automatizacao externa.

### D2. Criar uma UI web como superficie principal de iteracao rapida

A UI deve ser responsiva, orientada a projeto e focada em leitura, ajuste e comparacao. Ela nao recalcula regras; apenas consome os resultados da API e aciona novas execucoes.

### D3. Reutilizar as entidades e stores existentes do DDD

O desenho deve reaproveitar o que ja existe: entidades de Projeto, Escopo, Plano, Lifecycle/ProjectStore, stores locais e o canônico versionado. A nova camada se apoia nesses artefatos em vez de duplicar modelos.

### D4. Manter CLI e MCP como interfaces de apoio

CLI e MCP continuam validos para automacao, operacao tecnica e integracoes com agentes. A nova camada nao as substitui; ela organiza a experiencia de produto e torna o uso iterativo mais ergonomico.

### D5. Tratar override, bifurcacao e comparacao como capacidades de dominio

Override local, nova versao e comparacao entre execucoes devem ser operacoes de dominio com lineage e auditoria, nao simples mutacoes de tela.

### D6. Distinguir semantica de `project` e `hot_project`

Projeto criado por benchmark deve ser classificado como `hot_project`, preservando a referencia inicial como artefato imutavel do projeto para garantir rastreabilidade de origem.

### D7. Fixar raiz de configuracao/catalogo no ambiente de execucao

API e UI devem declarar `CONCILIUM_CONFIG_ROOT` e montar explicitamente `./config` no ambiente de desenvolvimento para evitar ambiguidade de fonte de catalogo.

### Reuso de entidades e DDD

#### Camada de Dominio

O dominio ja cobre as entidades e regras que a API/UI devem consumir, incluindo:

- `Projeto`
- `Escopo`
- `Plano`
- `CanonicalModel`
- `Resultado`
- `ResultadoReconciliado`
- `PontoEquilibrio`
- `BalancoControle`
- `DecisionVariables`
- `ConstraintViolation`
- `ReplannTrigger`, `ReplannCandidate`, `ReplannDecision`

#### Camada de Aplicacao

A orquestracao deve ser feita pelos servicos e workflows que ja existem, especialmente:

- runtime de execucao de skills;
- executor topologico;
- pipeline de benchmark;
- geracao de relatorios e artefatos;
- ferramentas de replanejamento e simulacao.

#### Camada de Infraestrutura

A persistencia local ja existente deve continuar sendo a base para:

- stores de projeto;
- versoes do canônico;
- artefatos de output;
- historico de invocacoes;
- snapshots e comparacoes;
- overrides locais do projeto.

## Requisitos de Produto

### Operacoes essenciais

1. Criar projeto a partir de contexto, tipo de obra, localizacao e EAP.
2. Executar pipeline completo com rastreabilidade por skill.
3. Aplicar override local sem contaminar o catalogo mestre.
4. Rerodar o pipeline com lineage preservado.
5. Comparar execucoes e versoes com diffs estruturados.

### Requisitos nao funcionais

1. Determinismo.
2. Auditoria completa.
3. Reutilizacao do dominio existente.
4. Baixa duplicacao de regra de negocio.
5. Compatibilidade com CLI e MCP.

## Contrato Inicial da API

### Recursos principais

#### Projeto

`POST /api/projects`

Cria um projeto com base em um contexto, um tipo de obra, uma localizacao e uma EAP inicial.

Exemplo de request:

```json
{
	"nome": "Lote 09/10 CE",
	"contexto_id": "mendeslobo",
	"tipo_obra": "terraplenagem",
	"localizacao": "Aracoiaba, CE",
	"data_inicio": "2026-06-01",
	"data_termino": "2027-06-27",
	"eap": [
		{
			"item_id": "eap-1_0",
			"ordem": 1,
			"cpu_id": "CPU-TERRA-ATI-003",
			"descricao": "Desmatamento e limpeza de area vegetada",
			"unidade": "m2",
			"quantitativo": 2400000
		}
	]
}
```

`GET /api/projects/{project_id}`

Retorna metadados do projeto, versao ativa, status e lineage resumido.

`GET /api/projects/{project_id}/versions`

Lista versoes, bifurcacoes e execucoes associadas.

#### Execucao

`POST /api/projects/{project_id}/runs`

Executa o pipeline sobre a versao ativa ou sobre uma base explicitada.

Exemplo de request:

```json
{
	"base_version": "v1",
	"inputs": {
		"gerar_modelo_vivo": false,
		"executar_apenas": ["01-escopo-e-eap", "02-produtividade-climatica"]
	}
}
```

`GET /api/projects/{project_id}/runs/{run_id}`

Retorna status por skill, validacoes, logs resumidos e artefatos gerados.

#### Re-run e bifurcacao

`POST /api/projects/{project_id}/rerun`

Reexecuta o pipeline com overrides ou inputs ajustados.

Exemplo de request:

```json
{
	"base_run_id": "run_20260513_001",
	"fork_version": true,
	"overrides": [
		{
			"scope": "project",
			"target": "CPU-TERRA-ATI-003",
			"field": "produtividade",
			"value": 1.08
		}
	]
}
```

`POST /api/projects/{project_id}/versions/{version}/fork`

Cria nova versao filha a partir de uma base aprovada ou corrente.

#### Override

`POST /api/projects/{project_id}/overrides`

Aplica override local ao projeto.

`GET /api/projects/{project_id}/overrides`

Lista overrides ativos por escopo e alvo.

`DELETE /api/projects/{project_id}/overrides/{override_id}`

Remove um override local, mantendo historico.

#### Comparacao

`GET /api/projects/{project_id}/compare?left={run_a}&right={run_b}`

Compara duas execucoes, duas versoes ou dois cenarios.

### Schemas base

#### ProjectCreateRequest

```json
{
	"nome": "string",
	"contexto_id": "string",
	"benchmark_slug": "string|null",
	"referencia_path": "string|null",
	"tipo_obra": "string",
	"localizacao": "string",
	"data_inicio": "YYYY-MM-DD",
	"data_termino": "YYYY-MM-DD",
	"eap": []
}
```

#### CreateProjectResponse

```json
{
	"project_id": "string",
	"nome": "string",
	"contexto_id": "string",
	"current_version": "string",
	"project_kind": "project|hot_project",
	"benchmark_slug": "string|null",
	"benchmark_reference_file": "string|null"
}
```

#### RunRequest

```json
{
	"base_version": "string",
	"inputs": {},
	"overrides": []
}
```

#### OverrideRequest

```json
{
	"scope": "project",
	"target": "string",
	"field": "string",
	"value": "any",
	"reason": "string"
}
```

#### CompareResponse

```json
{
	"left": { "run_id": "string", "version": "string" },
	"right": { "run_id": "string", "version": "string" },
	"deltas": {
		"custo_total": 0,
		"margem_pct": 0,
		"pe_estrutural": 0,
		"pe_operacional": 0
	},
	"changed_items": []
}
```

## Infraestrutura recomendada

### Decisao de curto prazo (agora)

Adotar um **modular monolith** no mesmo repositorio e no mesmo deploy:

1. Camada `presentation/api` para endpoints HTTP.
2. Camada `application` e `domain` reaproveitadas sem duplicacao.
3. Infra local atual de storage (ProjectStore e artefatos em disco) mantida.

Isso evita separacao prematura entre backend e frontend, preserva velocidade e reduz custo operacional inicial.

### Prototipo de UI

**Streamlit e aceitavel para prototipo de descoberta**, principalmente para:

- dashboard inicial;
- leitura de resultados;
- compare view basica;
- painel simples de override.

Limites esperados do Streamlit para fase posterior:

- UX mais limitada para fluxo complexo de lineage e fork;
- controle de estado/navegacao menos robusto;
- dificuldade para interacoes ricas de pipeline monitor em tempo real.

### Decisao de medio prazo

Separar em duas apps **logicamente**, nao necessariamente em dois deploys imediatos:

1. Backend API (ex.: FastAPI) dentro do mesmo monorepo.
2. Frontend web dedicado (ex.: React/Vite) consumindo a API.

No inicio, ambos podem rodar no mesmo host/process manager para simplificar operacao.

### Quando separar backend e frontend de fato

Fazer separacao de deploy apenas quando houver sinais objetivos:

1. equipes distintas com cadencia independente;
2. necessidade de escala isolada de API ou UI;
3. requisitos de seguranca/rede distintos;
4. necessidade de uptime diferenciado por componente.

### Stack minima sugerida

- API: FastAPI + Pydantic + Uvicorn.
- UI prototipo: Streamlit.
- UI produto: React + Vite + componente de tabela/diff.
- Execucao longa: fila em processo (fase 1) e evolucao para worker dedicado (fase 2).
- Notificacao de progresso: polling inicial e evolucao para SSE.
- Persistencia: ProjectStore local (atual), com abstracao para backend remoto futuro.

### Padrao de compose para desenvolvimento

Os servicos de API e UI devem compartilhar os mesmos volumes de projeto e benchmark, e declarar explicitamente:

- `CONCILIUM_ROOT=/workspace/concilium`
- `CONCILIUM_CONFIG_ROOT=/workspace/concilium/config`
- bind mount `./config:/workspace/concilium/config`

Essa definicao evita divergencia entre execucao local e container ao carregar catalogos, perfis e referencias.

### Implicacao para o ADR

A diretriz e: **separacao logica ja, separacao fisica depois**. Assim o time aprende rapido com prototipo sem comprometer a arquitetura alvo de API + UI de produto.

## Arquitetura da UI

### Objetivo

A UI precisa oferecer leitura e escrita controlada em um ciclo curto de iteracao. O foco e reduzir o intervalo entre diagnosticar um problema, ajustar um parametro e enxergar o impacto.

### Telas principais

#### 1. Dashboard do projeto

- resumo do projeto;
- status do pipeline;
- versao ativa;
- ultimo run;
- alertas e validacoes;
- atalhos para executar, ajustar e comparar.

#### 2. Setup wizard

- contexto;
- tipo de obra;
- localizacao;
- periodo;
- EAP inicial;
- confirmacao antes de criar o projeto.

#### 3. Pipeline monitor

- progresso por skill;
- status e duracao;
- validacoes por etapa;
- artefatos parciais;
- logs resumidos.

#### 4. Override editor

- edicao de produtividade;
- edicao de equipe;
- substituicao de maquina;
- ajuste de BDI operacional;
- ajuste de custos indiretos;
- simulacao antes de persistir.

#### 5. Compare view

- comparacao lado a lado;
- custo total, direto, indireto e margem;
- PE estrutural e operacional;
- criticidade e intervencoes;
- diffs de overrides.

#### 6. Lineage / history

- arvore de versoes;
- bifurcacoes;
- execucoes;
- aprovacoes;
- comparacoes anteriores.

### Fluxo de navegacao

1. Usuario entra no dashboard do projeto.
2. Abre uma execucao ou roda um novo pipeline.
3. Visualiza o resultado em paines por dominio.
4. Ajusta overrides em um painel lateral.
5. Dispara rerun com opcao de bifurcacao.
6. Compara execucoes em uma tela dedicada.

### Estrutura sugerida de composicao visual

- Sidebar com projetos, versoes e atalhos.
- Topbar com contexto, status e acoes.
- Main canvas com cards analiticos e tabelas.
- Drawer lateral para overrides e simulacao.
- Compare pane com duas colunas sincronizadas.

## Integracao com o DDD existente

### Entidades de dominio reutilizadas

- `Projeto`
- `Escopo`
- `PlanoTrabalho` ou entidade equivalente de plano
- `CanonicalModel`
- `Resultado`
- `ResultadoReconciliado`
- `PontoEquilibrio`
- `BalancoControle`
- `DecisionVariables`

### Servicos de aplicacao reutilizados

- runtime de execucao;
- executor de skills;
- geradores de benchmark e relatorio;
- motor de replanejamento;
- validadores de governanca;
- calculadoras de comparacao e sensibilidades.

### Infraestrutura reutilizada

- ProjectStore;
- stores de escopo e plano;
- storage local de artefatos;
- snapshots versionados;
- logs de invocacao;
- historico de overrides e bifurcacoes.

## Consequencias

### Positivas

| Impacto | Efeito |
|---|---|
| Iteracao | Reduz drasticamente o tempo entre ajuste e validacao |
| Usabilidade | Habilita uso por perfis nao dependentes de CLI |
| Comparacao | Torna diffs estruturados e visuais nativos |
| Governanca | Mantem lineage, overrides e auditoria |
| Reuso | Evita duplicar entidades e regras do DDD |

### Negativas

| Risco | Efeito |
|---|---|
| Escopo | Aumenta a superficie inicial de implementacao |
| Complexidade | Exige desenho firme de contrato API/UI |
| Concorrencia | Introduz desafios de estado e invalidacao |
| Duplicacao | Pode haver tentacao de recalcular regras na UI |

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Manter apenas CLI e MCP | Nao atende o ciclo de iteracao visual e comparacao rapida |
| A2 | Criar UI sem API canonica | Geraria duplicacao e acoplamento fragil |
| A3 | Reescrever dominio para UI-first | Desperdiçaria o DDD e quebraria determinismo |

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| 1 | Contrato da API, schemas e rotas basicas | Implementado no prototipo |
| 2 | UI de leitura: dashboard, execucao e historico | Implementado parcialmente no prototipo |
| 3 | UI de escrita controlada: override e rerun | Implementado no prototipo |
| 4 | Compare view estruturada | Implementado no prototipo |
| 5 | Integracao fina com MCP e CLI | Implementado |

## Definition of Done

### Fase 1

- [x] Criar projeto pela API.
- [x] Suportar `project` e `hot_project` na criacao.
- [x] Persistir referencia inicial de benchmark no `hot_project`.
- [x] Executar pipeline pela API.
- [x] Aplicar override e rerodar com lineage.
- [x] Comparar duas versoes com diff estruturado.
- [x] Expor listagem de artefatos por projeto/versao.
- [x] Expor consulta dedicada de run por `run_id` com status por skill e logs resumidos.

### Fase 2

- [x] Dashboard base com selecao de projeto, execucao e artefatos.
- [x] Exibir tipo de projeto (`project`/`hot_project`) na UI.
- [x] Exibir referencia inicial persistida quando aplicavel.
- [x] Override editor basico com salvar/remover por skill.
- [x] Compare view basica entre versoes.
- [x] Pipeline monitor com progresso em tempo real por skill (polling em endpoint de run).
- [x] Compare view avancada com destaque visual de deltas e criticidade.

### Fase 3

- [x] Navegacao entre versoes e artefatos.
- [x] Preservacao de lineage de versao base e derivada nos reruns.
- [x] Configurar ambiente de dev com `CONCILIUM_CONFIG_ROOT` e mount explicito de `./config`.
- [x] Historico de execucoes e bifurcacoes com visualizacao dedicada (timeline/arvore).
- [x] Consolidar audit trail completo por acao de UI (usuario, timestamp, payload e resultado).

## Decisao final

A plataforma deve evoluir para uma arquitetura com API canonica e UI web de iteracao rapida, preservando CLI e MCP como superficies de apoio. A implementacao precisa reusar as entidades e stores do DDD existentes, mantendo a logica de negocio no backend e expondo apenas contratos declarativos para a UI.

### 1. Determinismo acima de conveniencia

Toda execucao deve ser reprodutivel. A UI pode facilitar a edicao, mas nao pode recalcular regras por conta propria. A API deve receber inputs declarativos e retornar estados canônicos e artefatos derivados.

### 2. Versao e lineage como primeira classe

Cada execucao precisa ter identidade propria e referencia clara para:

- projeto;
- versao base;
- override aplicado;
- origem da execucao;
- skill chain executada;
- artefatos produzidos.

### 3. Override e bifurcacao sao distintos

Override e ajuste localizado dentro de um contexto projetual.
Bifurcacao e criacao de uma nova versao derivada de uma base aprovada ou base corrente.

A UI deve permitir ambos, mas a API precisa distingui-los semanticamente para manter governanca.

### 4. Comparacao e diff devem ser nativos

Comparar execucoes nao e um relatorio opcional. E uma capacidade central do produto. A API deve devolver diffs estruturados entre execucoes para permitir comparacao visual, auditoria e exportacao.

### 5. CLI e MCP continuam validos

A nova camada nao substitui CLI/MCP. Ela oferece uma via mais ergonomica de operacao humana e pode reutilizar os mesmos servicos internos.

## Alcance funcional minimo da API

### 1. Projeto

Operacoes esperadas:

- criar projeto a partir de contexto, tipo de obra, localizacao e EAP;
- carregar projeto existente;
- listar versoes e execucoes;
- obter estado atual canônico;
- obter artefatos da versao.

### 2. Execucao de pipeline

Operacoes esperadas:

- executar pipeline completo;
- executar uma skill ou etapa especifica;
- executar pipeline a partir de uma base ou de uma versao derivada;
- retornar status por skill, validacoes e logs;
- registrar tempo de execucao e trilha de auditoria.

### 3. Override

Operacoes esperadas:

- aplicar override de projeto em insumo, CPU, equipe, produtividade, BDI, recursos indiretos ou parametros analogos;
- listar overrides ativos;
- remover override;
- distinguir override master de override local do projeto;
- refletir override em nova execucao sem contaminar a base global.

### 4. Re-run / bifurcacao

Operacoes esperadas:

- criar nova versao a partir de uma versao aprovada ou da versao corrente;
- reexecutar pipeline sobre a nova versao;
- preservar lineage da versao base;
- permitir ajuste de overrides antes da reexecucao.

### 5. Comparacao

Operacoes esperadas:

- comparar execucao A vs B;
- comparar versao base vs versao com override;
- comparar dois cenarios de planejamento;
- comparar custo, margem, pe de equilibrio, criticidade, intervencoes, indiretos e componente operacional.

## Alcance funcional minimo da UI

### 1. Home do projeto

A UI deve mostrar:

- resumo do projeto;
- status atual;
- versao ativa;
- ultimo pipeline executado;
- alertas de integridade;
- atalhos para executar, ajustar e comparar.

### 2. Constructor / setup wizard

Fluxo guiado para criar projeto:

- contexto;
- tipo de obra;
- localizacao;
- janela temporal;
- EAP inicial;
- catalogo e referencia associados.

### 3. Pipeline monitor

Tela de execucao com:

- barra de progresso por skill;
- status por etapa;
- validacoes;
- logs resumidos;
- artefatos gerados;
- pontos de falha ou alerta.

### 4. Override editor

Editor visual para:

- alterar produtividade;
- substituir maquina ou composicao de equipe;
- ajustar BDI operacional de resguardo;
- alterar recursos indiretos;
- ajustar custos locais;
- simular impacto antes de persistir.

### 5. Compare view

Comparacao entre execucoes com:

- tabela resumo;
- diff em custo total, custo direto, indireto, venda e margem;
- diff de PE estrutural e operacional;
- diff de criticidade e recomendacoes;
- diff de overrides aplicados.

### 6. History / lineage

Linha do tempo com:

- versao original;
- bifurcacoes;
- overrides aplicados;
- reexecucoes;
- aprovacoes;
- artefatos por versao.

## Modelo de operacao proposto

### Fluxo 1: criar e executar

1. Usuario cria um projeto na UI ou via API.
2. O backend persiste o contexto, a configuracao base e a referencia.
3. O pipeline e executado.
4. A UI exibe progresso, validacoes e resultados.
5. O usuario navega entre resumo, planejamento, financeiro e comparacoes.

### Fluxo 2: ajustar e rerodar com override

1. Usuario abre uma execucao previa.
2. Aplica override em um item local.
3. A plataforma cria um contexto de reexecucao.
4. O pipeline e rerodado com lineage preservado.
5. A UI mostra diff entre a execucao anterior e a nova.

### Fluxo 3: bifurcar versao

1. Usuario escolhe uma execucao aprovada ou corrente.
2. A plataforma cria nova versao filha.
3. O usuario altera alguns parametros e reroda.
4. A nova versao fica isolada para comparacao e possivel aprovacao posterior.

### Fluxo 4: comparar execucoes

1. Usuario seleciona duas execucoes ou versoes.
2. A API produz diffs estruturados.
3. A UI mostra o antes e depois em blocos comparaveis.
4. O usuario avalia ganho, risco e necessidade de aprovacao.

## Estrutura da API sugerida

A definicao exata pode ser REST-first, com opcao futura de SSE/WebSocket para progresso em tempo real.

Endpoints principais sugeridos:

- `POST /projects`
- `GET /projects/{project_id}`
- `GET /projects/{project_id}/versions`
- `POST /projects/{project_id}/run`
- `POST /projects/{project_id}/rerun`
- `POST /projects/{project_id}/versions/{version}/fork`
- `POST /projects/{project_id}/overrides`
- `GET /projects/{project_id}/overrides`
- `DELETE /projects/{project_id}/overrides/{override_id}`
- `GET /projects/{project_id}/runs/{run_id}`
- `GET /projects/{project_id}/compare?left=...&right=...`
- `GET /projects/{project_id}/artefacts/{version}`

A API deve retornar:

- estado canônico;
- validacoes;
- logs resumidos;
- artefatos gerados;
- diff estrutural quando solicitado;
- metadados de lineage.

## Estrutura de UI sugerida

A UI pode ser implementada como aplicacao web moderna com foco em:

- layout de projeto;
- cards de status;
- tabelas comparativas;
- painel lateral de overrides;
- viewer de pipeline;
- charts simples para margem, custo e criticidade;
- comparador de versoes em duas colunas.

O objetivo nao e estetica vazia. O objetivo e reduzir o tempo entre:

- perceber um problema;
- ajustar o valor;
- rerodar;
- entender o impacto.

## Regras de override

### Override permitido

- valores de insumos;
- parametros de produtividade;
- composicao de equipes;
- uso de maquinas alternativas;
- BDI operacional/local;
- custos indiretos locais;
- fatores de resguardo e pressupostos de simulacao.

### Override proibido ou controlado

- alterar saidas derivadas diretamente pela UI sem recálculo;
- modificar catalogo mestre sem governanca;
- sobrescrever historico de execucao;
- editar resultados aprovados sem nova versao.

### Regra de precedencia

1. Override da execucao atual.
2. Override local do projeto.
3. Configuracao base da versao.
4. Catalogo mestre.

## Comparacao entre execucoes

A comparacao precisa cobrir, no minimo:

- custo direto;
- custo indireto;
- custo total;
- preco de venda;
- margem;
- delta de ponto de equilibrio;
- itens que mudaram de criticidade;
- intervencoes sugeridas;
- componentes dominantes de custo;
- overrides aplicados;
- duracao do pipeline;
- skills que alteraram o resultado.

A comparacao deve ser estruturada por entidades e nao apenas por texto.

Exemplos de perguntas que a UI deve responder visualmente:

- o custo baixou porque o equipamento foi trocado ou porque a produtividade melhorou?
- o preco de venda subiu por ajuste de BDI ou por aumento de material?
- a margem melhorou, mas a criticidade aumentou em algum item isolado?
- o rerun com override gerou ganho real ou apenas mascarou risco estrutural?

## Persistencia e governanca

A API e a UI devem persistir um historico imutavel de execucoes, incluindo:

- inputs declarados;
- overrides;
- versao base;
- versao derivada;
- resultados do pipeline;
- comparativos;
- artefatos;
- aprovacoes.

Nada na UI deve ser fonte primaria de verdade. A fonte primaria e o canônico do projeto + os artefatos de execucao.

## Relacao com o que ja existe

Esse ADR nao substitui o que ja existe. Ele organiza a evolucao natural do que ja foi construindo:

- CLI continua para operacao tecnica, automacao e manutencao.
- MCP continua para integracao com agentes e fluxos externos.
- API vira o contrato padrao do produto.
- UI vira a interface principal de iteracao rapida.

O backend deve reutilizar os mesmos servicos internos de execucao, replanejamento, comparacao e persistencia.

## Consequencias

### Positivas

- reduz drasticamente o tempo de iteracao;
- melhora a experiencia do usuario tecnico e nao tecnico;
- viabiliza comparacao visual de cenarios;
- melhora rastreabilidade de overrides e reruns;
- abre caminho para fluxos colaborativos e aprovacao assistida;
- permite observar o efeito de cada ajuste sem depender de CLI.

### Negativas

- aumenta o custo inicial de implementacao;
- exige disciplina forte para nao duplicar regras entre UI e backend;
- adiciona novas superficies de erro em autenticacao, autorizacao e concorrencia;
- demanda desenho cuidadoso de cache, versionamento e invalidacao;
- exige contrato consistente entre API, UI, CLI e MCP.

## Riscos

1. **Duplicacao de logica**: a UI pode acabar reimplementando regras que ja pertencem ao backend.
2. **Estado divergente**: override local, versao base e execucao atual podem se confundir se o lineage nao for explicito.
3. **Comparacao opaca**: sem diff estruturado, a comparacao vira apenas visual e perde valor analitico.
4. **Overengineering**: a UI pode crescer antes da API estabilizar.
5. **Performance**: comparacoes e reruns podem ficar pesados sem snapshots eficientes.

## Mitigacoes

- manter o backend como unica fonte de verdade;
- padronizar modelos de request/response;
- versionar execucoes e overrides;
- tratar comparacao como entidade de dominio;
- implementar a UI em fatias pequenas, com primeiro foco em leitura e depois em escrita;
- preservar CLI/MCP como canais de fallback.

## Plano de implementacao recomendado

### Fase 1 - Contrato de API

- definir schemas de projeto, execucao, override, diff e compare;
- expor endpoints de leitura;
- expor endpoint de execucao do pipeline;
- expor endpoint de rerun e fork;
- expor endpoint de listagem de artefatos.

### Fase 2 - UI de leitura

- dashboard do projeto;
- pagina de execucao;
- pagina de historico;
- pagina de comparacao entre execucoes.

### Fase 3 - UI de escrita controlada

- editor de override;
- wizard de rerun;
- fluxo de fork de versao;
- confirmacao de impacto antes de persistir.

### Fase 4 - Comparacao avancada

- diffs por skill e por artefato;
- comparacao financeira detalhada;
- comparacao de criticidade e ponto de equilibrio;
- comparacao entre estrategias de replanejamento.

### Fase 5 - Integracao com MCP e automacao

- usar a mesma API por tras do MCP quando fizer sentido;
- expor operacoes de simulacao e aplicacao de replan como wrappers finos;
- alinhar logs e lineage entre as interfaces.

## Critario de aceite da arquitetura

Este ADR pode ser considerado implementado quando o sistema conseguir, em uma interface web ou via API:

1. Criar um projeto.
2. Executar o pipeline completo.
3. Aplicar override local em um parametro relevante.
4. Rerodar a partir da mesma base ou por nova bifurcacao.
5. Comparar duas execucoes com diffs estruturados e auditaveis.
6. Navegar entre resultados sem recorrer obrigatoriamente a CLI.

## Atualizacao de Implementacao (2026-05-14)

- Endpoints adicionados para aderencia do contrato de rerun e fork:
	- `POST /api/projects/{project_id}/rerun`
	- `POST /api/projects/{project_id}/versions/{version}/fork`
- Endpoint de comparacao por query string adicionado:
	- `GET /api/projects/{project_id}/compare?left=...&right=...`
- Alias de compatibilidade para artefatos adicionado:
	- `GET /api/projects/{project_id}/artefacts`
	- `GET /api/projects/{project_id}/artefacts/{version}`
- Rota de validacao unificada de CLI integrada ao fluxo de operacao humana:
	- `concilium validate project`
	- `concilium validate benchmark`
	- `concilium validate projeto` (alias)

## Decisao final

A arquitetura de produto deve evoluir para um modelo com API canonica e UI web de iteracao rapida, mantendo CLI e MCP como interfaces de suporte. O foco deve estar em execucao deterministica, rerun governado por override, bifurcacao de versoes e comparacao estruturada entre execucoes.

Essa decisao e coerente com a forma como o Concilium ja opera internamente e cria a base para um produto mais util, rapido e analitico.
