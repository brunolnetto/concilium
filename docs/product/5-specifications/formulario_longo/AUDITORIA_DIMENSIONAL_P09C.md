# P09-C — Auditoria dimensional e de paridade do formalismo

**Rastreamento:** [epic #8](https://github.com/brunolnetto/concilium/issues/8) → [issue #9](https://github.com/brunolnetto/concilium/issues/9), Onda 0. Este documento registra a **prova disponível e os limites**; não é certificado GO/NOGO de projeto.

## Defeitos objetivos corrigidos

1. **Rampa retangular:** a afirmação anterior `μ+=μ-=0 ⇒ m(τ)=mmax` é falsa. É preciso acrescentar `m0=m1=mmax`. O contraexemplo `(m0,m1,mmax,μ+,μ-,N)=(1,1,4,0,0,3)` produz a sequência `[1,1,1]`, nunca `[4,4,4]`. A equivalência foi corrigida no LONGO e TeX e verificada em `test_normative_boundaries.py`; RESUMIDO já estava correto.
2. **Proxy MAT sem evidência física:** o antigo modelo afirmava `κ=1 [unid_g/h]` e `p_g=c_r [R$/h]`. O produto das unidades seria `(unid_g/h)×(R$/h)=R$·unid_g/h²`, incompatível com `c_r [R$/h]`. LONGO/RESUMIDO/TeX foram corrigidos: dado apenas `c_r`, o valor é proxy monetário `UNVERIFIED`, não volume/compra física ou preço certificado. Essa negativa tem teste dimensional.

## Inventário para fechamento de #9

- `EQUATION_INVENTORY_P09C.json` lista **93 equações em blocos `$$...$$` do LONGO**, por ID estável `FL-001…FL-093`, seção, expressão literal, *dimensão esperada do resultado*, fonte de entrada, saída/consumidor, dependências normativas e estado. Testes de referência exigem correspondência **exata e bijetiva**. Alterar qualquer equação sem atualizar a auditoria falha CI.
- `SYMBOL_PROVENANCE_P09C.json` registra **53 símbolos/interfaces de maior impacto** com unidades, fontes e projeções (incluindo a distinção `F(m)` [u/h], `rho_front` [u/(h·frente)], `κ_h` [good/h], `κ_out` [good/u], `p_g` [R$/good], recursos ativos/idle, K/V/IND/BDI).
- Testes independentes de tipos dimensionais cobrem capacidade física, contrato K, compra física V, armazenamento, origem de preço e a impossibilidade de substituir rate físico por proxy monetário. O fator de fechamento `φ=1/4` não deve cobrar somente 1/4 do K semanal.

## Limites e falsificabilidade

Inventário **não é prova matemática**. Os registros distinguem `NORMATIVE_CANDIDATE` e `CONDITIONAL_OR_UNCERTIFIED`; todas as 93 expressões estão anotadas `REQUIRES_INDEPENDENT_VERIFICATION`, impedindo o salto lógico de presença no catálogo para conformidade. Várias identidades dependem de **#11** (ζ/π, catálogo K/V, médias e invariância), **#13** (tarifas standby) e da reconciliação real do pool, estoque, ledger e preço **#16–#21**.

**Ainda necessário para fechar #9:** demonstrar validade dimensional de *cada fórmula efetivamente classificada como normativa*, promover apenas itens com prova inequívoca, registrar todos os símbolos restantes ou aliases com origem e saída — não apenas os 53 já auditados — e comprovar consistência **semântica**, não só textual, entre MD/RESUMIDO/TeX. O contrato de casos de erro `UNKNOWN/NOT_EVALUATED` e as tolerâncias também precisam refletir a versão do oráculo.

Não iniciar o trabalho de novas ondas sob a hipótese de que este inventário certifica suas dependências; PR e testes locais podem ser integrados com `Refs #9` mantendo a issue aberta até aceite integral.

## CI e comandos reproduzíveis

```bash
uv run pytest -q tests/reference_formalism/test_normative_boundaries.py \
  tests/reference_formalism/test_equation_inventory_p09c.py
```

Não gera outputs de produção nem modifica preços. Uma mutação do LONGO, como reintroduzir a implicação falsa ou trocar a unidade do proxy sem alterar o inventário, deve induzir teste vermelho.
