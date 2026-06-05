// Módulo: Azure Key Vault — ADR-094 Fase 1
// Armazena chaves RS256 do JWT e certificado TLS.
// ACI acessa via Managed Identity (sem credenciais em variáveis de ambiente).

@description('Região Azure')
param location string

@description('Nome do Key Vault (globalmente único, 3-24 chars)')
param keyVaultName string

@description('Principal ID da Managed Identity do ACI (recebe Secrets User)')
param aciIdentityPrincipalId string

@description('Principal ID da Managed Identity de deploy/ops (recebe Secrets Officer)')
param opsIdentityPrincipalId string

// ── Key Vault ─────────────────────────────────────────────────────────────────

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyVaultName
  location: location
  properties: {
    sku: { family: 'A', name: 'standard' }
    tenantId: subscription().tenantId
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    enableRbacAuthorization: true   // RBAC em vez de access policies
    publicNetworkAccess: 'Enabled'  // ACI público precisa de acesso — restringir com VNet em hardening futuro
  }
}

// ── RBAC: ACI lê segredos (Managed Identity do container) ────────────────────

resource aciSecretsUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, aciIdentityPrincipalId, 'SecretsUser')
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '4633458b-17de-408a-b874-0445c86b69e6'  // Key Vault Secrets User
    )
    principalId: aciIdentityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// ── RBAC: Ops/deploy escreve segredos (CI/CD e setup inicial) ────────────────

resource opsSecretsOfficer 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, opsIdentityPrincipalId, 'SecretsOfficer')
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      'b86a8fe4-44ce-4948-aee5-eccb2c155cd7'  // Key Vault Secrets Officer
    )
    principalId: opsIdentityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// ── RBAC: App Gateway lê certificados TLS ────────────────────────────────────

resource appGwCertUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, opsIdentityPrincipalId, 'CertUser')
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      'db79e9a7-68ee-4b58-9aeb-b90e7c24fcba'  // Key Vault Certificate User
    )
    principalId: opsIdentityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

output keyVaultId string = keyVault.id
output keyVaultUrl string = keyVault.properties.vaultUri
output keyVaultName string = keyVault.name
