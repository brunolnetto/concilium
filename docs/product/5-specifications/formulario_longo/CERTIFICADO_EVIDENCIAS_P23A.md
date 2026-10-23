# P23-A — Fonte de evidência imutável (não é certificado GO)

O modelo `FormalismCertificate` nesta fase é um **envelope provisório** com
`decision=NOT_EVALUATED` (único valor permitido). Seu checksum de entrada
não substitui os testes V1–V6, reconciliação financeira, prova de margem
ou validade regulatória. Somente P23-B introduzirá um avaliador capaz
de produzir decisões, e P23-C cuidará de persistência e exposição.

`fingerprint_source` utiliza SHA-256 determinístico sobre JSON UTF-8
normalizado, com separação de domínio por fonte. Dez categorias são
sempre enumeradas: canonical, catalog, productivity, calendar, schedule,
pool, inventory, ledger, pricing e solver. Em RFI ou preview,
dados ainda não produzidos são *explicitamente None*, com estado
`UNAVAILABLE`; omitir a categoria ou fornecer estrutura vazia em seu
lugar não tem o mesmo significado. `formalism_sha256`,
`oracle_sha256` e escopo da execução compõem o checksum agregado.

O materializado é independente da hora de criação; mudar qualquer entrada
material, existência de fonte, base normativa ou escopo produz checksum
distinto. A função `matches_current_sources` compara o envelope com
fontes atuais, rejeitando diferenças. Não é assinatura criptográfica
de autorização ou armazenamento durável: P23-C deve vincular o envelope
ao snapshot persistido, project/run e à política de confiança.

Fontes em `Decimal`, conjuntos não ordenados, NaN e infinito devem ser
normalizadas *antes* do envelope de acordo com contratos tipados; o
hash nunca faz coerção silenciosa desses valores. Conformidade de um
pipeline parcial não implica uma proposta RFP certificada.
