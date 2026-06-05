// ADR-096 — Deploy Azure: ACR → ACI → Application Gateway → DNS
// Orquestrador principal: implanta todos os módulos em sequência.
//
// Deploy:
//   az deployment group create \
//     --resource-group concilium-rg \
//     --template-file deploy/bicep/main.bicep \
//     --parameters @deploy/bicep/main.bicepparam

@description('Região Azure para todos os recursos')
param location string = 'brazilsouth'

@description('Nome do Azure Container Registry')
param acrName string = 'conciliumacr'

@description('Tag da imagem a ser deployada')
param imageTag string = 'latest'

@description('Nome da Managed Identity para pull de imagem do ACR')
param identityName string = 'concilium-identity'

@description('Nome da Storage Account para projetos (Azure Blob)')
param storageAccountName string = 'conciliumstorage'

@description('Nome do container blob para projetos')
param blobContainerName string = 'concilium-projetos'

@description('Endpoint OTLP para Azure Monitor (ADR-095)')
param otlpEndpoint string = ''

@description('Nome do Key Vault para segredos JWT e certificado TLS (ADR-094 Fase 1)')
param keyVaultName string = 'concilium-kv'

@description('Principal ID do service principal de ops/CI para gravar segredos no Key Vault')
param opsIdentityPrincipalId string

@description('Azure Storage Account Key — usar Managed Identity em produção')
@secure()
param azureStorageKey string

@description('Zona DNS (domínio da MendesLobo)')
param dnsZoneName string = 'mendesloboconstrucao.com.br'

@description('Nome do container group ACI')
param containerGroupName string = 'concilium-cg'

@description('Nome do Application Gateway')
param appGatewayName string = 'concilium-agw'

// ── Managed Identity ─────────────────────────────────────────────────────────

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: identityName
  location: location
}

// ── Key Vault (ADR-094 Fase 1) ────────────────────────────────────────────────

module keyVault 'modules/key-vault.bicep' = {
  name: 'keyvault-deploy'
  params: {
    location: location
    keyVaultName: keyVaultName
    aciIdentityPrincipalId: identity.properties.principalId
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

// ── ACI ──────────────────────────────────────────────────────────────────────

module aci 'modules/aci.bicep' = {
  name: 'aci-deploy'
  dependsOn: [acr]
  params: {
    location: location
    containerGroupName: containerGroupName
    acrLoginServer: acr.outputs.loginServer
    imageTag: imageTag
    identityId: identity.id
    storageAccountName: storageAccountName
    blobContainerName: blobContainerName
    otlpEndpoint: otlpEndpoint
    keyVaultUrl: keyVault.outputs.keyVaultUrl
    azureStorageKey: azureStorageKey
  }
}

// ── Application Gateway ───────────────────────────────────────────────────────

module appGateway 'modules/app-gateway.bicep' = {
  name: 'appgw-deploy'
  dependsOn: [aci]
  params: {
    location: location
    appGatewayName: appGatewayName
    aciApiHost: aci.outputs.fqdn
    aciMcpHost: aci.outputs.fqdn
  }
}

// ── DNS Zone ──────────────────────────────────────────────────────────────────

module dns 'modules/dns.bicep' = {
  name: 'dns-deploy'
  dependsOn: [appGateway]
  params: {
    dnsZoneName: dnsZoneName
    appGatewayPublicIp: appGateway.outputs.publicIp
  }
}

// ── Outputs ───────────────────────────────────────────────────────────────────

output acrLoginServer string = acr.outputs.loginServer
output aciPublicIp string = aci.outputs.publicIp
output aciPublicFqdn string = aci.outputs.fqdn
output appGatewayPublicIp string = appGateway.outputs.publicIp
output apiUrl string = 'https://api.${dnsZoneName}'
output mcpUrl string = 'https://mcp.${dnsZoneName}'
