---
name: 09-relatorio-e-artefatos
description: Use when rendering the final canonical model into the auditable .xlsm output format with formulas, formatting, and macros per profile template.
---

# Skill 10 — Adapter de Saída

Renderiza o canônico final no formato `.xlsm` — planilha de referência auditável com fórmulas, formatação e macros pré-estruturadas segundo o template de cada perfil. É o estágio terminal do pipeline.

## Quando ativar

Após `consolidar-resultado`. Esta skill assume que o canônico está completo e validado — não recalcula nada, apenas renderiza.

## Inputs

| Nome | Tipo | Origem | Obrigatório |
|------|------|--------|-------------|
| `canonical` | object completo | Canônico final | sim |
| `template_spec` | config | `config/templates/planilha_planejamento.json` | sim |
| `template_xlsm` | path | Referenciado em `perfil.adapter_saida.template_path` | sim |
| `output_path` | string | `projetos/{uuid}/outputs/` | sim |
| `perfil.adapter_saida` | config | `perfis/{perfil_id}.json` | sim |

**Sobre `template_spec`**: arquivo JSON que mapeia canônico -> estrutura de abas/células. Agnóstico a construtora.  
**Sobre `template_xlsm`**: planilha Excel de referência (fornecida por perfil), com fórmulas, formatação e macros já estruturadas. O adapter NÃO recria — apenas popula células de entrada conforme mapa em `template_spec`.

## Depende de

**Skills predecessoras**:
- [`06-resultado-financeiro/_consolidacao`](../06-resultado-financeiro/_consolidacao/SKILL.md) — fornece canônico completo

**Recursos consumidos**:
- `config/templates/planilha_planejamento.json` — especificação genérica de mapeamento canônico -> células
- `perfis/{perfil_id}/template_planejamento.xlsm` — template Excel de referência do perfil (preservado read-only)
- Snapshot do canônico final do projeto

**Dependências externas**:
- `openpyxl` (Python) — manipulação de .xlsx/.xlsm preservando fórmulas e formatação
- Atenção: `openpyxl` preserva macros mas não as executa; valores das células com fórmula precisam ser calculados pelo adapter ou pelo Excel ao abrir

## Produz

**Saída do pipeline**: arquivo `.xlsm` em `projetos/{uuid}/outputs/orçamento_{nome}_{revisao}.xlsm`.

**Não produz seção do canônico** — esta é a única skill que tem efeito colateral externo (escrita de arquivo) em vez de extensão do canônico.

**Validações executadas**:
- `VAL-ADAPTER-01` (ERRO): template_spec e template_xlsm existem e são legíveis
- `VAL-ADAPTER-02` (ERRO): canônico passou em todas as validações estruturais (VAL-CRON-*, VAL-EQUIP-*, VAL-EAP-*, VAL-PRAT-*); recusa renderizar canônico inconsistente
- `VAL-ADAPTER-03` (AVISO): canônico tem validações de política em status diferente de OK (renderiza mesmo assim, mas marca a planilha de saída)

## Lógica de renderização

```
1. Validar pré-condições:
   - canonical.resultado.validacoes não tem nenhum ERRO estrutural
   - template_spec existe e é legível (JSON)
   - template_xlsm existe e é legível
   - output_path é gravável

2. Carregar template_spec (mapa de células):
   spec = json.load('config/templates/planilha_planejamento.json')

3. Copiar template para output:
   shutil.copy(template_xlsm, output_path)
   workbook = openpyxl.load_workbook(output_path, keep_vba=True)

4. Iterar abas conforme template_spec.abas:
   Para cada aba em spec:
     - Extrair seções (mapa de linhas, colunas, origem_canonico)
     - Usar JMESPath para extrair valores do canônico
     - Popular células conforme mapeamento
   
   Exemplo (aba PLANEJAMENTO):
     Para cada item em canonical.planejamento:
       - Extrair cpu_id, quantitativo, precos, BDI
       - Popular linhas 55+ conforme colunas B:S
       - Deixar fórmulas existentes calcularem subtotais

5. Salvar:
   workbook.save(output_path)

6. Pós-validação:
   - Reabrir o arquivo gerado, verificar que abas críticas têm valores não-nulos
   - Conferir delta ponto de equilíbrio entre canônico e o calculado pela planilha (autovalidação)
```

## Notas de implementação

- **Template como código-vivo**: `planilha_planejamento.json` é a fonte de verdade para estrutura. Se Excel mudar (nova aba, linha realocada), atualizar apenas o JSON, não a skill Python.

- **Agnóstico a perfil**: a skill 10 não conhece AGIS, MendesLobo, ou qualquer construtora específica. Todos os detalhes vêm via `template_spec` (genérico) + `template_xlsm` (fornecido pelo perfil).

- **Macros (.xlsm vs .xlsx)**: `openpyxl` preserva macros (`keep_vba=True`) mas não as executa. Se o template contém macro para inicialização ao abrir, isso "funciona" — Excel executa quando o usuário abre.

- **Fórmulas existentes**: o template é fortemente formulado (~51k fórmulas). O adapter deve preencher apenas os valores de entrada (preços unitários, quantidades, número de equipes, etc.) e deixar as fórmulas existentes calcularem o resto ao abrir no Excel. Isso é desejável — mantém a auditabilidade.

- **Verificação de consistência**: após renderizar, considere abrir a planilha em modo headless e comparar valores calculados pelas fórmulas com o canônico. Diferenças indicam que a fórmula do template não bate com a lógica das skills — sinal de erro.

- **DEC-12** (canônico inline): o adapter NÃO acessa `catalogo/` ou `perfis/`. Tudo que precisa está no canônico. Se algo faltar, é bug no canônico ou no schema, não no adapter.

- **Múltiplos perfis no futuro**: quando uma segunda construtora entrar, ela ganha seu próprio `perfis/{construtora_id}/template_planejamento.json` (configuração) + `perfis/{construtora_id}/template_planejamento.xlsm` (binário). A skill 10 continua idêntica.

## Saída esperada

Arquivo `.xlsm` em `projetos/{uuid}/outputs/orcamento_{nome}_{revisao}.xlsm` (ou caminho equivalente), preservando estrutura e fórmulas do template, com células de entrada preenchidas a partir do canônico.

```json
{
  "adapter_output": {
    "formato": "xlsm",
    "template_usado": "config/templates/planilha_planejamento.json",
    "caminho": "projetos/abc-123/outputs/orcamento_lote09_10_CE_v1.xlsm",
    "tamanho_bytes": 1900000,
    "celulas_populadas": 8421,
    "validacoes": [
      { "codigo": "VAL-ADAPTER-01", "status": "OK" },
      { "codigo": "VAL-ADAPTER-02", "status": "OK" },
      { "codigo": "VAL-ADAPTER-03", "status": "AVISO", "mensagem": "1 validação de política em estado AVISO (margem amarela)" }
    ]
  }
}
```

## Fim do pipeline

Esta é a última skill. O arquivo gerado é o entregável final do orçamento Concilium para o perfil solicitado.

← Volta para o índice de skills
