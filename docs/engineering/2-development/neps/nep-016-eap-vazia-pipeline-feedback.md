# NEP-016: Pipeline falha com "EAP vazia" sem diagnóstico claro ao usuário

**Status:** Concluído  
**Prioridade:** 🔴 Crítico  
**Área:** Projetos  
**Tipo:** Bug + UX  
**Esforço:** S  
**Identificado em:** 2026-05-20  

---

## Contexto

Ao tentar executar o pipeline de um projeto, o skill `04-cronograma` retorna erro `VAL-CRON-PRECONDICAO: EAP vazia no canônico.`. O usuário vê apenas a mensagem técnica no log de auditoria, sem orientação de como resolver.

## Causa Raiz

**Skill 04 (layout.py, linha 267):**
```python
if not canonical.eap:
    raise RuntimeDomainError("EAP vazia no canônico.")
```

Para projetos do tipo `project` com `status_eap == "RASCUNHO"`, o canonical pode existir (de um run anterior parcial) mas com EAP vazia. Para `hot_project`, a EAP vem da referência do benchmark — se o benchmark não foi carregado corretamente, a EAP também fica vazia.

## Dois cenários de falha

**Cenário A — projeto `project` sem EAP definida:**
- `status_eap` é `"RASCUNHO"` → o ADR-063 já implementou `ProjectStrategy.validate_preconditions` que bloqueia o pipeline, mas a UI não exibe mensagem clara antes do usuário clicar
- O botão "Iniciar Pipeline" deveria estar desabilitado com tooltip explicativo

**Cenário B — `hot_project` com benchmark não carregado:**
- Pipeline inicia, mas skill 03 não popula a EAP
- Skill 04 recebe canonical sem EAP
- Feedback chega apenas como erro técnico na auditoria

## Critério de Aceite

1. Para `project` com `status_eap == "RASCUNHO"`:
   - Botão "Iniciar Pipeline" desabilitado visualmente
   - Caption explicativo: "Defina a EAP na aba 🔍 Catálogo antes de executar"

2. Para `hot_project` com EAP vazia após pipeline:
   - Mensagem amigável na aba Auditoria: "A EAP não foi populada pelo benchmark. Verifique se a referência foi carregada corretamente."
   - Link direto para recarregar a referência

3. Em nenhum caso o usuário deve ver a mensagem técnica `VAL-CRON-PRECONDICAO` sem contexto

## Notas Técnicas

- O guard UI pode ser implementado verificando `project.get("status_eap") == "RASCUNHO"` antes de renderizar `render_run`
- A melhoria de feedback no log de auditoria requer enriquecer o handler de erro em `PipelineService._execute_run` para capturar `RuntimeDomainError` com código `VAL-CRON-*` e adicionar contexto ao `skills_log`
