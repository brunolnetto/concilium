# Excel Architecture Analyzer 🏗️📊

Bem-vindo ao **Sheet Layer Precedence Analyzer**. Este projeto nasceu de uma necessidade real em modelagem financeira e engenharia de custos: garantir que planilhas críticas não se transformem em caixas-pretas impossíveis de auditar.

---

## 📈 Para Analistas (A Visão de Negócios)

Se você trabalha com Excel diariamente, já sabe o que acontece quando uma planilha cresce demais. Você tem uma aba de "Dados", abas de "Cálculos" e abas de "Resultado". Mas, com o tempo, a aba de "Dados" acaba puxando uma informação que está lá no "Resultado". 

O fluxo, que deveria ser um **rio contínuo**, vira uma **teia de aranha**.

### O que esta ferramenta faz?
Ela atua como um **"Corretor Ortográfico de Arquitetura"** para o seu arquivo Excel. 

Em modelos robustos, nós definimos regras simples, chamadas de "Camadas" (Layers):
*   **L1 (Base):** Dados puros e premissas.
*   **L2 (Meio):** Cálculos intermediários.
*   **L3 (Fim):** Resultados e Dashboards.

**A regra de ouro é: a água só desce o rio.** Uma célula em L3 pode ler L1, mas **L1 nunca pode ler L3**. Quando isso ocorre, o modelo fica instável e propenso a erros em cascata ao realizar simulações de cenários.

### Como usar o resultado?
O Analyzer varre o seu arquivo e entrega um **Plano de Ação**. Ele te diz:
1. **Onde está o problema:** (Ex: Aba `PRODUÇÕES`, célula `B15`)
2. **Qual é o erro:** (Ex: Está puxando uma fórmula de `RESULTADOS`)
3. **O Impacto:** Ele rastreia o rastro da fórmula e te diz quantas outras células estão sendo arrastadas junto.

Você usa esse relatório para **refatorar** (arrumar) a planilha de forma guiada, movendo lógicas de negócio das abas finais para as iniciais, garantindo que o seu modelo fique à prova de balas.

---

## 🧠 Por Baixo do Capô (Para Engenheiros e Entusiastas)

Para quem se interessa por algoritmos e estrutura de dados, o "corretor de planilhas" opera usando **Teoria dos Grafos** e parsing de **Abstract Syntax Trees (AST)**.

O Excel não é um banco de dados; ele é um ambiente de programação reativa bidimensional. Para auditar sua lógica, nós o tratamos como um enorme código-fonte.

### 1. Construção do Grafo Computacional
Utilizando a biblioteca `openpyxl`, nós extraímos a string das fórmulas. Com expressões regulares e tokenização, isolamos as referências espaciais (Ex: `Escavação!$C$10`). 
Cada célula vira um **Nó (Vértice)**, e cada referência vira uma **Aresta Direcionada**. Uma planilha complexa pode ter milhares de vértices interconectados.

### 2. Validação Topológica
Em vez de depender do motor de cálculo da Microsoft, nós executamos algoritmos clássicos de grafos (como busca em profundidade/DFS) sobre a estrutura:
*   **Ciclos Estruturais:** Identificamos dependências circulares ocultas que muitas vezes mascaram erros profundos de modelagem conceitual (o nó A depende do B, que depende do C, que volta para o A).
*   **V-UPs (Violações Upward):** Verificamos matematicamente se a Camada da `Origem` > Camada do `Destino`. Se sim, a integridade do Directed Acyclic Graph (DAG) planejado foi rompida.

### 3. Análise de Cone e Cauda (Sub-grafos)
Este é o coração heurístico do motor. Quando quebramos a regra `L1 -> L2`, não olhamos apenas para as duas células isoladas. 
Nós geramos estatísticas do sub-grafo (a árvore de dependência) puxado pela célula transgressora:
*   **Caminho mais longo (Tail length):** Indica a complexidade do cálculo interno do nó alvo.
*   **Fontes Independentes:** Quantos dados brutos sem arestas de entrada estão alimentando essa sub-árvore.
Isso nos diz se a violação é apenas o espelho de um valor constante (fácil de consertar, *Assisted Action*) ou se é um vazamento da lógica de negócio (*Refactoring Action*).

### 4. Pipeline de Circuit Breaker (Auto-Fix)
Para simular isolamentos e testar a resiliência do modelo, o Analyzer possui o modo `--fix-all`. 
Ele atua diretamente no AST (via string replacement), alterando a fórmula em nível binário/XML (injetando literais `0`) nas arestas que violam o fluxo topológico. É uma intervenção cirúrgica na AST que força as dependências reversas a estancarem, agindo como um *Circuit Breaker* isolando domínios (abas) de negócio acoplados.
