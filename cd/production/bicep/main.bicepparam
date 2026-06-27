// Parâmetros para o deploy de produção.
// NUNCA commite valores de segredos — use CI/CD secrets.

using 'main.bicep'

param location = 'brazilsouth'
param acrName = 'conciliumacr'
param identityName = 'concilium-identity'
param keyVaultName = 'concilium-kv'
param acaEnvName = 'concilium-env'

// Injetado pelo CI/CD (deploy.sh bootstrap) — NÃO commitar aqui
// param opsIdentityPrincipalId = '...'
