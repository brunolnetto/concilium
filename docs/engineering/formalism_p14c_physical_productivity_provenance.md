# P14-C — Proveniência física e fechamento de escopo no limite da Skill 04

**Issue:** #14 · **Epic:** #8 · **Status:** implementação em revisão, não certificada.

## Contrato executável

A entrada `certification_intent` aceita somente `PREVIEW` e `CERTIFIED`; o default permanece `PREVIEW`. Antes da construção do contexto de custo e do solver, a Skill 04 verifica os valores físicos brutos do catálogo. Valores booleanos, não numéricos, não finitos, não positivos ou grandes demais para conversão finita são rejeitados; todas as capacidades e arestas do grafo são inspecionadas antes da coerção de Pydantic. Um rótulo ou taxa isolada não substitui grafo físico com origem e versão.

`CERTIFIED` exige referência de produção, grafo validável, `origem.fonte_id`, `auditoria.versao` e nenhuma sobreposição de taxa legada `cpu_meta.producao_horaria`. A rejeição não publica cronograma e invalida projeções financeiras/analíticas derivadas. `PREVIEW` pode usar produtividade não verificada, mas expõe `VAL-CRON-PROD-PREVIEW`; isso não representa certificação de preço/GO. Unidade da EAP, produção e cada capacidade horária é comparada dimensionalmente; `t/h` e `t/hr` são aliases, não conversão entre massa e volume.

## Evidência física e estado derivado

`TipoRecurso.proveniencia` e `RecursoPool.proveniencia` distinguem `CONFIGURADO`, `DERIVADO_SKILL03`, `DERIVADO_SKILL05` e `LEGACY_UNVERIFIED`. O pool físico consumido pelo cronograma contém somente disponibilidade explicitamente configurada; defaults de catálogo e pools sintéticos de Skill 05 não podem fabricar capacidade. Um pool legado com formato sintético 1000/1000, custo de aquisição zero e sem proveniência é preservado como `LEGACY_UNVERIFIED`, não como prova física nem como recurso descartável por suposição.

O módulo `_closure.py` declara `scope-closure/v1`, tolerância absoluta (10^{-9}), relativa (10^{-12}), e resultado tipado PASS/FAIL/UNKNOWN. Na rota manual, o fechamento é recalculado de `qtd_executada` semanal materializada (não do acumulado armazenado); o erro `VAL-CRON-01` publica Q, Σq, resíduo, erro absoluto, tolerância, horizonte e motivo. Escopo incompleto, superprodução ou evidência numérica inválida não permite publicar cronograma autoritativo.

Uma nova tentativa, mesmo que fisicamente válida, invalida resultados financeiros/analíticos previamente armazenados; os consumíveis/estoque calculados na tentativa atual são reinseridos após a invalidação. Rejeição e sucesso são tratados separadamente.

## Verificações adicionadas

- Execução real da Skill 04 para produtividade ausente, PREVIEW versus CERTIFIED, fechamento físico e invalidação de estado antigo.
- Taxas malformadas, não finitas, booleanas, overflow, grafo/capacidade/origem ausentes, incompatibilidade dimensional e capacidade de gargalo/não-gargalo.
- Preservação de configuração declarada e quarentena de pool sintético legado.
- A prova de fechamento é física/local; não é certificado de projeto GO. P15 deve reotimizar o calendário, P16 corrige o contraexemplo da optimalidade global de pool, e #23 continua dona do certificado persistente.

## Estado de validação

Este branch foi criado a partir de `main@c017933dea6898d08856ff5baac7319402ef026d`, e não reutiliza a antiga branch divergente do PR #102. Os testes hospedados/locais para o SHA atual **ainda precisam ser executados**; nenhum resultado verde é afirmado por este documento.