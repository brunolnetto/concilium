# NEP-011: Equipe de apoio nos custos indiretos sem edição completa de itens

**Status:** Concluído  
**Prioridade:** 🟠 Alto  
**Área:** Projetos  
**Tipo:** Feature  
**Esforço:** M  
**Identificado em:** 2026-05-20  

---

## Contexto

A seção "👥 Equipe de Apoio" em Custos Indiretos exibe as categorias de custo indireto (ADM, TOP, LAB, QSMS, MOB) com suas funções e verbas mensais. No entanto, o usuário não consegue:
- Adicionar ou remover funções dentro de uma categoria
- Adicionar ou remover equipamentos alocados
- Editar verbas mensais (alimentação, transporte, etc.)

As categorias são fixas no código, mas os itens dentro delas são dinâmicos por projeto.

## Categorias e Estrutura

As categorias esperadas são:
- **ADM** — Administração Central (permanência)
- **TOP** — Topografia (permanência)
- **LAB** — Laboratório (permanência)
- **QSMS** — Qualidade, Segurança, Meio Ambiente e Saúde (permanência)
- **MOB** — Mobilização / Desmobilização (one_time)

Cada categoria tem três tipos de itens editáveis:
1. **Funções** — `(funcao_id, num_pessoas, salario_base, regime: PJ|CLT)`
2. **Equipamentos** — `(equip_id, num_unidades, custo_mensal)`
3. **Verbas mensais** — `(descricao, valor_mensal)`

## Critério de Aceite

Para cada categoria de custo indireto:
- `data_editor` com `num_rows="dynamic"` para Funções (adicionar/remover operadores)
- `data_editor` com `num_rows="dynamic"` para Equipamentos
- `data_editor` com `num_rows="dynamic"` para Verbas mensais
- Botão "💾 Salvar {categoria}" persiste via override `07-custos-indiretos`
- Total calculado ao vivo: `Σ(num_pessoas × salario × (1 + encargos)) + Σ(equip × custo) + Σ(verbas)`

## Notas Técnicas

- A estrutura de override de indiretos vive em `skill_inputs["07-custos-indiretos"]["equipes_indiretas"]`
- O endpoint existente `POST /api/projects/{id}/overrides` com `skill_id: "07-custos-indiretos"` suporta isso
- Encargos por regime: PJ=0%, CLT-mensalista=92%, CLT-horista=80% (já em `ENCARGOS` em layout.py)
- Formulário deve ser idêntico em estrutura ao da equipe direta (`render_cpu_composition_override`)
