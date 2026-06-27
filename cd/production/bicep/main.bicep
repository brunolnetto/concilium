// Infraestrutura base do Concilium (ACA)
// Provisiona: Managed Identity, ACR, Key Vault, ACA Environment.
// O ciclo de vida dos Container Apps (API + MCP) é gerenciado pelo deploy.sh.
//
// Deploy:
//   az deployment group create \
//     --resource-group concilium-rg \
//     --template-file cd/production/bicep/main.bicep \
//     --parameters @cd/production/bicep/main.bicepparam \
//     --parameters opsIdentityPrincipalId=<principal-id>

@description('Região Azure para todos os recursos')
param location string = 'brazilsouth'

@description('Nome do Azure Container Registry')
param acrName string = 'conciliumacr'

@description('Nome da Managed Identity para pull de imagem do ACR')
param identityName string = 'concilium-identity'

@description('Nome do Key Vault para segredos JWT')
param keyVaultName string = 'concilium-kv'

@description('Principal ID do service principal de ops/CI para gravar segredos no Key Vault')
param opsIdentityPrincipalId string

@description('Nome do ACA Environment compartilhado')
param acaEnvName string = 'concilium-env'

// ── Managed Identity ─────────────────────────────────────────────────────────

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: identityName
  location: location
}

// ── Key Vault ─────────────────────────────────────────────────────────────────

module keyVault 'modules/key-vault.bicep' = {
  name: 'keyvault-deploy'
  params: {
    location: location
    keyVaultName: keyVaultName
    acaIdentityPrincipalId: identity.properties.principalId
    opsIdentityPrincipalId: opsIdentityPrincipalId
  }
}

// ── ACR ──────────────────────────────────────────────────────────────────────

module acr 'modules/acr.bicep' = {
  name: 'acr-deploy'
  params: {
    location: location
    acrName: acrName
    identityPrincipalId: identity.properties.principalId
  }
}

// ── ACA Environment ───────────────────────────────────────────────────────────

module acaEnv 'modules/aca-env.bicep' = {
  name: 'aca-env-deploy'
  params: {
    location: location
    envName: acaEnvName
  }
}

// ── Outputs ───────────────────────────────────────────────────────────────────

output acrLoginServer string = acr.outputs.loginServer
output keyVaultUrl string = keyVault.outputs.keyVaultUrl
output acaEnvId string = acaEnv.outputs.envId
output identityId string = identity.id
output identityPrincipalId string = identity.properties.principalId
