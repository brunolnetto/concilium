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

> **Atualização (2026-07-27):** P4 tem solução completa, não só contorno — ver D3/D1. O manifest
> MCPB v0.3 suporta `platform_overrides`, permitindo um único `.mcpb` universal com os 3 binários
> embutidos, e o próprio Claude Desktop escolhe o certo em runtime. Nem admin nem usuário precisam
> discernir SO em momento nenhum do fluxo.

---

## Decisão

D1. Empacotar o proxy (`concilium-mcp-proxy`, hoje distribuído como binário PyInstaller cru, um por
SO) como uma **única Desktop Extension (`.mcpb`) universal**, usando o CLI oficial
`@anthropic-ai/mcpb` (`mcpb init` / `mcpb pack`). O `.mcpb` é um ZIP: os 3 binários (Windows/
macOS/Linux) vão embutidos juntos em `server/`, e o manifest declara `platform_overrides`
(chaveado pelos valores de `process.platform`: `win32`/`darwin`/`linux`) apontando cada um pro seu
binário. O Claude Desktop detecta o SO do host e escolhe o binário certo sozinho, na instalação —
nenhum script de detecção próprio é necessário. O proxy em si não é reescrito — o `.mcpb` só
empacota os artefatos que o `build-proxy.yml` já produz.

D2. Usar a seção `user_config` do `manifest.json` para pedir o `CONCILIUM_CLIENT_CODE` **na própria
UI de instalação** do Claude Desktop (campo `sensitive: true` — mascarado na tela, armazenado no
Keychain/Credential Manager do SO em vez de texto plano num arquivo). `CONCILIUM_SERVER_URL` é
fixo no manifest (igual pra todos os usuários) e não precisa ser pedido.

```json
{
  "manifest_version": "0.3",
  "name": "concilium-mcp-proxy",
  "version": "1.0.0",
  "server": {
    "type": "binary",
    "entry_point": "server/concilium-mcp-proxy",
    "mcp_config": {
      "command": "server/concilium-mcp-proxy",
      "platform_overrides": {
        "win32":  { "command": "server/concilium-mcp-proxy.exe" },
        "darwin": { "command": "server/concilium-mcp-proxy-macos" },
        "linux":  { "command": "server/concilium-mcp-proxy-linux" }
      }
    }
  },
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

D3. **Um único `.mcpb` universal substitui os dois blocos JSON e os dois links por SO** — não um
pacote por usuário, nem um pacote por SO. `add-user` / `regenerate-code` / `migrate-legacy-codes`
passam a enviar sempre o **mesmo link fixo** (reaproveitado entre cadastros, independente do SO do
usuário) + o `client_code` em separado, pra colar na tela de instalação — em vez de montar e enviar
um JSON completo (ou escolher entre dois blocos) por pessoa.

> **Atualização (2026-07-27, F3):** "link fixo" implementado como TTL de 10 anos em vez de
> renovação por cadastro (`_MCPB_LINK_TTL_SEGUNDOS`, `commands_auth.py`) — Graph `createLink` é
> idempotente por item+type+scope, então chamadas repetidas tendem a devolver o mesmo `webUrl`
> enquanto o path (`distribuicao/concilium-mcp-proxy/latest.mcpb`) não mudar, mesmo com o conteúdo
> sendo sobrescrito a cada build (mesma driveItem, nova versão SharePoint). Resolve a lacuna
> deixada em aberto nesta decisão (como o link deixava de expirar em 7 dias).

D4. O pipeline de build do proxy (`build-proxy.yml`, PyInstaller por SO) não muda — o `.mcpb`
consome o binário resultante como está.

D6. **Publicação versionada, não sobrescrita (F3).** `build-proxy.yml` ganha um job `pack-mcpb`
(após a matrix de build, via `actions/upload-artifact`/`download-artifact` — os 3 binários nunca
coexistem no mesmo runner) que empacota o `.mcpb` e publica com `concilium ops blob put-versioned`
(novo comando, `commands_blob.py`): grava `distribuicao/concilium-mcp-proxy/vN.mcpb` (imutável, N
sequencial — mesma convenção `vN` de `ConfigVersionService`/ADR-062, adaptada para blob storage) +
`distribuicao/concilium-mcp-proxy/latest.mcpb` (ponteiro estável, sobrescrito a cada publish — é
este path usado por D3). O mecanismo antigo (`_get_proxy_exe_download_urls`, os 3 binários crus
publicados direto em `distribuicao/concilium-mcp-proxy.exe`/`-linux`/`-macos`, sempre sobrescritos
sem versão) foi **removido, não mantido em paralelo** — decisão do usuário em 2026-07-27: sunset
imediato, sem fallback dual. Isso diverge do F4 original desta ADR (ver nota na seção de fases).

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
| A4 | Um `.mcpb` por SO (Windows / macOS-Linux), como no rascunho inicial desta ADR | Superada por D1/D3: `platform_overrides` permite os 3 binários num único pacote universal, sem custo de tamanho relevante (~30-105MB, sem limite técnico documentado) — não há razão pra manter a divisão por SO |

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Zero discernimento de SO | Um único `.mcpb` universal (`platform_overrides`) resolve P4 por completo — nem admin nem usuário escolhem SO em ponto nenhum do fluxo; mesmo link pra todos os cadastros |
| Menos artefato por cadastro | `add-user` só precisa gerar o `client_code` e apontar pro link fixo — não monta mais JSON nem escolhe entre blocos |
| Secret fora de texto plano | `client_code`/credencial de dispositivo saem do JSON local e vão para o Keychain/Credential Manager do SO via campo `sensitive` |
| UX de instalação | Elimina "baixar binário → salvar em caminho fixo → editar JSON à mão → reiniciar"; vira instalação nativa com formulário de configuração |
| Candidato a resolver P2 | Armazenamento em `extensions-installations.json` (separado de `mcpServers`) é indício de que escapa do bug de team sync — a confirmar em D5/F1 |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| `.mcpb` pode sofrer do mesmo bug de team sync — não confirmado oficialmente pela Anthropic | D5/F1: validar em ambiente controlado antes de qualquer rollout; se falhar, registrar aqui e reavaliar a decisão sem prosseguir |
| Assinatura do pacote não está claramente documentada — risco de aviso de "extensão não confiável" na instalação | Testar instalação local (F0) antes do rollout; investigar processo de assinatura se o aviso aparecer |
| Migração exige nova rodada de onboarding para usuários já ativos (precisam reinstalar como extensão) | **Mudou em F3:** mecanismo antigo (JSON + link por SO) foi removido, não mantido em paralelo (D6) — usuários já ativos com o fluxo antigo continuam funcionando via token em cache (`~/.concilium/tokens/`) até o token expirar/ser revogado, mas um `regenerate-code`/reativação daqui em diante só oferece o caminho `.mcpb`. Sem fallback automático se F1 revelar problema — reavaliar antes de expandir o rollout |
| CLI oficial `mcpb` ainda não é suportado via Claude Code CLI, só Claude Desktop (limitação pública conhecida) | Sem impacto — o uso alvo desta ADR é sempre Claude Desktop |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F0 — Protótipo | `mcpb init`/`mcpb pack` local empacotando os 3 binários PyInstaller já existentes num `.mcpb` universal (`platform_overrides`); instalação manual de teste em pelo menos 2 SOs distintos | 🔶 Parcial — ver nota |
| F1 — Validação do bug de team sync (D5) | Instalar `.mcpb` numa máquina com `remoteToolsDeviceName` ativo; confirmar sobrevivência da config a múltiplos reinícios | ⬜ Não iniciada |
| F2 — `user_config` fim a fim | Manifest com `concilium_client_code` (sensitive) + `CONCILIUM_SERVER_URL` fixo; validar que a env var chega ao processo do proxy e completa `ativar_dispositivo` | ⬜ Não iniciada |
| F3 — Ajuste do fluxo de onboarding | `add-user`/`regenerate-code`/`migrate-legacy-codes` passam a enviar o link fixo do `.mcpb` + `client_code` separado, em vez do JSON completo; publicação versionada (D6); atualizar README e o tutorial `concilium-usage-tutorial/SKILL.md` | ✅ Feita |
| F4 — Rollout | Migrar usuários existentes | ⬜ Não iniciada — nota: mecanismo antigo já foi removido em F3 (sem fallback dual, ver D6), diferente do plano original desta linha |

---

## Definition of Done

### F0
- [x] `.mcpb` universal gerado localmente com `mcpb pack` — `tools/mcp-proxy/mcpb/manifest.json` + `build.sh`; `mcpb validate` passa; pacote resultante tem `manifest.json` na raiz e os 3 binários em `server/`, nomes idênticos aos já usados em `blob_path` do `build-proxy.yml` (`concilium-mcp-proxy.exe`/`-macos`/`-linux`)
- [x] Binários PyInstaller existentes reaproveitados sem modificação — testado com o binário Linux real (`pyinstaller --onefile tools/mcp-proxy/proxy.py`, 9,5MB, sem alteração em `proxy.py`); Windows/macOS só têm stub vazio neste teste local (sem runner desses SOs disponível aqui)
- [ ] Instalável no Claude Desktop de teste — não verificado (sem GUI neste ambiente)
- [ ] Confirmado em pelo menos 2 SOs distintos que o Claude Desktop escolhe o binário certo sozinho — pendente, requer os 3 binários reais (via CI `build-proxy.yml`) + instalação manual

### F1
- [ ] Extensão sobrevive a pelo menos 3 reinícios do Claude Desktop com team sync ativo, sem perder configuração
- [ ] Resultado documentado nesta ADR mesmo se negativo — se `.mcpb` também sofrer do bug, reavaliar a decisão aqui antes de prosseguir

### F2
- [ ] Campo `concilium_client_code` aparece mascarado na UI de instalação
- [ ] Valor preenchido chega como env var ao processo do proxy e completa `ativar_dispositivo` com sucesso

### F3
- [x] `_build_mcp_config_jsons`/`_get_proxy_exe_download_urls`/`_print_both_configs` removidos; `_get_mcpb_download_url`/`_print_mcpb_link_and_code` implementados em `commands_auth.py`, usados por `add-user`, `regenerate-code` (flag renomeada `--link/--no-link`) e `migrate-legacy-codes`
- [x] `notifications.py` (`notify_user_created`/`notify_client_code_migrated`) e os templates `user_created.txt/html.jinja2` atualizados — anexo dos 2 JSONs removido, só o `.skill` + `client_code` em destaque
- [x] `concilium ops blob put-versioned` novo (`commands_blob.py`) — vN + ponteiro `latest`, testado (`test_commands_blob_coverage.py`)
- [x] `build-proxy.yml`: job `pack-mcpb` publica versionado via `put-versioned`; binário cru não é mais publicado direto (sunset)
- [x] `README.md` e `concilium-usage-tutorial/SKILL.md` (+ espelho em `docs/product/.../AGENT_SKILL_TUTORIAL.md`) atualizados
- [x] Testes de `commands_auth`/`notifications` reescritos para o novo mecanismo (nenhuma referência ao antigo restante fora de comentários históricos)

### F4
- [ ] Pelo menos um usuário real migrado com sucesso para o `.mcpb` — pendente, depende de F0/F1 (instalação real validada) antes de rollout
- [x] ~~Fallback do fluxo JSON mantido até confirmação de estabilidade~~ — não aplicável: mecanismo antigo já removido em F3 (D6, decisão do usuário de sunset imediato). Se F1 revelar que `.mcpb` também sofre do bug de team sync, não há fallback automático — reavaliar antes de expandir o rollout

---

## Relacionados

- ADR-123 — fluxo de distribuição/gestão de dispositivo que esta ADR substitui na camada de configuração local
- ADR-099 — R4 rejeitou OAuth2 completo; motivo permanece válido e é reafirmado aqui (A2)
