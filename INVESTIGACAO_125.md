# Investigação issue #125 — Golden test de decomposição de custo (ADR-104/NEP-043) "falhando" no main

## Sintoma original

`tests/integration/cost/test_cost_decomposition_adr104.py::TestCostDecompositionInvariant` reportava
duas falhas ao rodar isoladamente após o merge do #121/#122 (mas reproduzível também revertendo para
o estado do `main` anterior a esse PR — ou seja, aparentemente não causado por ele):

1. `test_agis_custo_direto_matches_reference`
   ```
   AGIS custo_direto=48,600,803.88, esperado=16,529,359.75, desvio=194.03%
   assert 194.02714088789799 < 0.5
   ```
2. `test_cost_decomposition_closes_with_pool_contracts`
   ```
   Item eap-1_4: decomposição não fecha (soma=6,658,246.05, total=6,615,839.83, desvio=42,406.22)
   assert 42406.22000000067 < 0.05
   ```

A hipótese de trabalho na issue era regressão de código (possivelmente no pipeline de custo de pool,
`application/skills/manifests/05-equipes-e-alocacao/` ou `equipe_custo_engine.py`) ou baseline de teste
desatualizado por mudança de comportamento legítima.

## Hipótese investigada: cache obsoleto de benchmark mascarando o resultado

A fixture `agis_benchmark` (`tests/integration/conftest.py`) é `session`-scoped e chama:

```python
facade.run_single("AGIS", reset=False)
```

Com `reset=False`, `BenchmarkRunner._load_existing_report_if_fresh()` devolve o canonical model e o
relatório **já persistidos em disco** em `benchmarks/projetos/AGIS/` sempre que esse diretório já
existir — sem rodar nenhum código do pipeline atual. Esse diretório é gitignored (não versionado),
mas **não é efêmero**: ele sobrevive entre execuções de pytest, entre checkouts de branch e entre
`git bisect`/`git checkout` de commits antigos usados para investigar a própria issue.

Ou seja: qualquer investigação anterior que tenha rodado o benchmark AGIS num commit diferente do
HEAD atual (por exemplo, o próprio processo de bisect sugerido no passo 1 da issue) deixa um resultado
"congelado" no working tree. Testes subsequentes no HEAD atual, com `reset=False`, continuam lendo
esse resultado antigo — reportando "falha" (ou "sucesso") que na verdade reflete o commit em que o
cache foi gerado, não o código do commit corrente.

## Como confirmei

1. Troquei a fixture para `facade.run_single("AGIS", reset=True)`, forçando o benchmark a rodar do
   zero a cada sessão de teste, ignorando qualquer resultado persistido em
   `benchmarks/projetos/AGIS/`.
2. Rodei isoladamente:
   ```
   PYDANTIC_DISABLE_PLUGINS=__all__ OTEL_SDK_DISABLED=true python3 -m pytest \
     tests/integration/cost/test_cost_decomposition_adr104.py -v --tb=long
   ```
   Resultado: **8 passed** (os 2 testes antes reportados como falhos — `test_agis_custo_direto_matches_reference`
   e `test_cost_decomposition_closes_with_pool_contracts` — agora passam, junto com os outros 6 do
   mesmo arquivo).
3. Rodei a suíte completa (`pytest tests/ -q`) com `reset=True` ativo — ver seção "Resultado da suíte completa"
   abaixo — sem falhas novas.

Isso confirma a hipótese: no HEAD atual (`worktree-issue-125-golden-test-custo-decomposicao`, que
inclui o estado pós-#121/#122), o pipeline de custo produz um resultado que **fecha** a invariante
ADR-104/NEP-043 dentro da tolerância esperada. O que a issue #125 capturou não foi uma regressão de
código — foi o teste servindo, sem saber, o relatório de uma execução anterior e independente do
commit sendo testado.

## Por que isso não é "só ajustar o teste"

Ajustar o baseline numérico do teste (por exemplo, aceitar R$48,6M como novo valor esperado) teria sido
o caminho errado aqui — teria "corrigido" o teste para concordar com um resultado que nunca foi
produzido pelo código do commit em avaliação, mascarando permanentemente a invariante real que o teste
existe para proteger (`custo_operacional ≤ custo_catálogo`, a base do #121).

O problema real é de **isolamento de teste**: uma fixture de benchmark que persiste estado em disco
fora do controle do pytest (fora de `tmp_path`, fora de fixtures com cleanup) e o reutiliza entre
execuções sem qualquer verificação de que o estado corresponde ao commit atual. Isso tem duas
consequências igualmente perigosas, e ambas já se manifestaram nesta investigação:

- **Falso-positivo**: um cache "bom" de um commit anterior pode fazer o teste passar mesmo que o
  commit atual tenha introduzido uma regressão real — escondendo o bug exatamente na suíte golden que
  deveria pegá-lo primeiro.
- **Falso-negativo** (o que aconteceu aqui): um cache de uma investigação anterior (rodada em outro
  commit, possivelmente durante o próprio processo de bisect sugerido pela issue) faz o teste "falhar"
  no HEAD atual mesmo que o código atual esteja correto — gerando uma issue de alta prioridade sobre
  uma regressão que não existe.

Em ambos os casos, o resultado do teste passa a depender de qual foi o **último commit que rodou o
benchmark localmente**, não do commit que está sendo testado agora. Isso quebra a premissa básica de
um "golden test": ele precisa refletir o código do commit atual, sempre.

A correção (`reset=True` na fixture) resolve isso porque a fixture já é `session`-scoped — dentro de
uma mesma sessão de pytest o benchmark roda uma única vez de qualquer forma, então `reset=False` nunca
trouxe ganho de velocidade real *dentro* de uma run de teste; ele só existia para reaproveitar cache
*entre* runs de pytest, que é exatamente o comportamento que causa a contaminação entre commits.

## Resultado da suíte completa

```
PYDANTIC_DISABLE_PLUGINS=__all__ OTEL_SDK_DISABLED=true python3 -m pytest tests/ -q
```

Ver saída completa no terminal da sessão que fez esta investigação. Nenhuma falha nova foi observada
além do já esperado (tempo de execução maior, já que `reset=True` faz o benchmark AGIS rodar de
verdade a cada sessão de teste que usa a fixture, em vez de reutilizar cache em disco).

## Conclusão

Causa raiz confirmada: **cache obsoleto de benchmark em disco (`benchmarks/projetos/AGIS/`, gitignored
mas persistente) mascarando o resultado real do pipeline de custo**, não uma regressão de código em
`equipe_custo_engine.py` ou nos manifests de skill. A invariante ADR-104/NEP-043 (decomposição de
custo instancial fecha com `custo_total`, e `custo_direto` AGIS bate com a referência histórica do
NEP-043 Bug 2) está válida no código atual.
