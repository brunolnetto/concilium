# ADR-161 — Distribuição do Proxy MCP via Desktop Extension (`.mcpb`)

**Status:** 💡 Proposta
**Data:** 2026-07-27
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-123 (notificação e gestão de dispositivos), ADR-099 (RBAC)

---

## Contexto

### Problema

P1. **Distribuição hoje é manual e frágil.** `concilium ops auth add-user` gera um `client_code`
único por usuário e monta dois blocos JSON prontos (Windows / macOS-Linux) com o `client_code` já
embutido no `env`, enviados por email junto com um link de download (7 dias) do binário PyInstaller
do proxy (`_build_mcp_config_jsons`, `commands_auth.py`). O usuário precisa: baixar o binário certo
pro seu SO, salvar exatamente no caminho fixo esperado (`C:\Concilium\...` ou
`~/.concilium/bin/...`, com `chmod +x`), colar o bloco JSON certo em
`claude_desktop_config.json`, e reiniciar o Claude Desktop. Qualquer erro nesse processo (caminho
errado, JSON mal colado, SO errado) só aparece como falha de ativação sem diagnóstico direto.

P2. **Bug conhecido do cliente sobrescreve a configuração manual.** Quando team cloud sync está
ativo no Claude Desktop (indicado pela chave `remoteToolsDeviceName` no config), o app busca a
config do time na nuvem ao iniciar e substitui `mcpServers` inteiro **sem merge**, apagando
silenciosamente qualquer servidor adicionado manualmente — sem aviso, sem log. Documentado só como
issues públicas no GitHub (#59368, #34359, #56296, #32345), todas fechadas como "invalid"/"not
planned" — não é comportamento reconhecido oficialmente pela Anthropic. A mitigação atual (cache do
`refresh_token` em `~/.concilium/tokens/`, que sobrevive ao reset do JSON) reduz o impacto mas não
resolve a fragilidade da configuração inicial nem de reativações.

P3. **Secret em texto plano no disco.** O `client_code` de bootstrap (e, até a primeira ativação,
efetivamente a chave de acesso ao dispositivo) fica gravado sem criptografia dentro do
`claude_desktop_config.json` local — sem controle de acesso do SO, sujeito ao mesmo bug de P2 expor
o arquivo em backups/sync não intencionais.

P4. **Admin não sabe o SO do usuário no momento do cadastro.** O fluxo atual contorna isso enviando
sempre os dois blocos (Windows e macOS/Linux) juntos, deixando o próprio usuário escolher o
correto — funciona, mas duplica o artefato gerado por cadastro.

---

## Decisão

D1. Empacotar o proxy (`concilium-mcp-proxy`, hoje distribuído como binário PyInstaller cru) como
uma **Desktop Extension (`.mcpb`)**, usando o CLI oficial `@anthropic-ai/mcpb` (`mcpb init` /
`mcpb pack`), referenciando o binário existente via `server.binary` no manifest. O proxy em si não
é reescrito — o `.mcpb` só empacota o artefato que o `build-proxy.yml` já produz.

D2. Usar a seção `user_config` do `manifest.json` para pedir o `CONCILIUM_CLIENT_CODE` **na própria
UI de instalação** do Claude Desktop (campo `sensitive: true` — mascarado na tela, armazenado no
Keychain/Credential Manager do SO em vez de texto plano num arquivo). `CONCILIUM_SERVER_URL` é
fixo no manifest (igual pra todos os usuários) e não precisa ser pedido.

```json
{
  "manifest_version": "0.3",
  "name": "concilium-mcp-proxy",
  "version": "1.0.0",
  "server": { "type": "binary", "entry_point": "concilium-mcp-proxy" },
  "user_config": {
    "concilium_client_code": {
      "description": "Código de ativação do seu dispositivo (RCODE-...)",
      "type": "string",
      "required": true,
      "sensitive": true
    }
  }
}
```

D3. Um `.mcpb` **por sistema operacional** (Windows / macOS-Linux) substitui os dois blocos JSON —
não um pacote por usuário. `add-user` / `regenerate-code` / `migrate-legacy-codes` passam a enviar
o link fixo do `.mcpb` do SO do usuário (não muda por cadastro) + o `client_code` em separado, pra
colar na tela de instalação — em vez de montar e enviar um JSON completo por pessoa.

D4. O pipeline de build do proxy (`build-proxy.yml`, PyInstaller por SO) não muda — o `.mcpb`
consome o binário resultante como está.

D5. **Validar experimentalmente antes de migrar a distribuição de produção**: instalar o `.mcpb`
numa máquina com team cloud sync ativo (`remoteToolsDeviceName` presente) e confirmar, através de
múltiplos reinícios, se a extensão (armazenada em `extensions-installations.json`, separado de
`mcpServers`) sobrevive ao bug de P2. Não há confirmação oficial da Anthropic de que `.mcpb` escapa
desse comportamento — só o indício de que usa um mecanismo de armazenamento diferente do que o bug
afeta.

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Manter `claude_desktop_config.json` manual como está | Não resolve P1-P3; é o problema que esta ADR existe pra resolver |
| A2 | Implementar OAuth2 completo (authorization server próprio) para usar "Add custom connector" nativo — URL remota, sem proxy local nenhum | Já avaliado e rejeitado em ADR-099 (R4): dependência pesada, LDAP/Entra ID necessários, prematuro pro estágio do projeto. O motivo permanece válido; esta ADR não o reabre |
| A3 | Gerar um `.mcpb` por usuário, com o `client_code` já embutido no pacote (em vez de pedido via `user_config`) | Perde a vantagem central do formato — reintroduz "um artefato por pessoa" (P1/P4), só trocando JSON por ZIP |

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Menos artefato por cadastro | Um `.mcpb` por SO (link fixo, reaproveitado entre cadastros) em vez de um JSON por usuário — `add-user` só precisa gerar o `client_code` e apontar pro link |
| Secret fora de texto plano | `client_code`/credencial de dispositivo saem do JSON local e vão para o Keychain/Credential Manager do SO via campo `sensitive` |
| UX de instalação | Elimina "baixar binário → salvar em caminho fixo → editar JSON à mão → reiniciar"; vira instalação nativa com formulário de configuração |
| Candidato a resolver P2 | Armazenamento em `extensions-installations.json` (separado de `mcpServers`) é indício de que escapa do bug de team sync — a confirmar em D5/F1 |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| `.mcpb` pode sofrer do mesmo bug de team sync — não confirmado oficialmente pela Anthropic | D5/F1: validar em ambiente controlado antes de qualquer rollout; se falhar, registrar aqui e reavaliar a decisão sem prosseguir |
| Assinatura do pacote não está claramente documentada — risco de aviso de "extensão não confiável" na instalação | Testar instalação local (F0) antes do rollout; investigar processo de assinatura se o aviso aparecer |
| Migração exige nova rodada de onboarding para usuários já ativos (precisam reinstalar como extensão) | Rollout gradual (F4) — manter o fluxo JSON atual funcional em paralelo até confirmar estabilidade |
| CLI oficial `mcpb` ainda não é suportado via Claude Code CLI, só Claude Desktop (limitação pública conhecida) | Sem impacto — o uso alvo desta ADR é sempre Claude Desktop |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F0 — Protótipo | `mcpb init`/`mcpb pack` local empacotando o binário PyInstaller já existente; instalação manual de teste no Claude Desktop | ⬜ Não iniciada |
| F1 — Validação do bug de team sync (D5) | Instalar `.mcpb` numa máquina com `remoteToolsDeviceName` ativo; confirmar sobrevivência da config a múltiplos reinícios | ⬜ Não iniciada |
| F2 — `user_config` fim a fim | Manifest com `concilium_client_code` (sensitive) + `CONCILIUM_SERVER_URL` fixo; validar que a env var chega ao processo do proxy e completa `ativar_dispositivo` | ⬜ Não iniciada |
| F3 — Ajuste do fluxo de onboarding | `add-user`/`regenerate-code`/`migrate-legacy-codes` passam a enviar o link fixo do `.mcpb` do SO + `client_code` separado, em vez do JSON completo; atualizar README e o tutorial `concilium-usage-tutorial/SKILL.md` | ⬜ Não iniciada |
| F4 — Rollout | Migrar usuários existentes; manter fallback do fluxo JSON durante a transição | ⬜ Não iniciada |

---

## Definition of Done

### F0
- [ ] `.mcpb` gerado localmente com `mcpb pack`, instalável no Claude Desktop de teste
- [ ] Binário PyInstaller existente reaproveitado sem modificação

### F1
- [ ] Extensão sobrevive a pelo menos 3 reinícios do Claude Desktop com team sync ativo, sem perder configuração
- [ ] Resultado documentado nesta ADR mesmo se negativo — se `.mcpb` também sofrer do bug, reavaliar a decisão aqui antes de prosseguir

### F2
- [ ] Campo `concilium_client_code` aparece mascarado na UI de instalação
- [ ] Valor preenchido chega como env var ao processo do proxy e completa `ativar_dispositivo` com sucesso

### F3
- [ ] `_build_mcp_config_jsons` (ou equivalente) atualizado para apontar pro `.mcpb`
- [ ] `README.md` e `concilium-usage-tutorial/SKILL.md` atualizados

### F4
- [ ] Pelo menos um usuário real migrado com sucesso do fluxo JSON atual para o `.mcpb`
- [ ] Fallback do fluxo JSON mantido até confirmação de estabilidade em produção

---

## Relacionados

- ADR-123 — fluxo de distribuição/gestão de dispositivo que esta ADR substitui na camada de configuração local
- ADR-099 — R4 rejeitou OAuth2 completo; motivo permanece válido e é reafirmado aqui (A2)
