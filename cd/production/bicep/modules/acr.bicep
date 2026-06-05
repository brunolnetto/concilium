// Módulo: Azure Container Registry
// SKU Basic — suficiente para imagem única de serviço de nicho.

@description('Região Azure')
param location string

@description('Nome do ACR (globalmente único)')
param acrName string

@description('Principal ID da Managed Identity que fará pull de imagens')
param identityPrincipalId string

resource acr 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' = {
  name: acrName
  location: location
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false   // autenticação via Managed Identity (sem admin password)
  }
}

// AcrPull para a Managed Identity — permite que ACI faça pull sem credenciais hardcoded
resource acrPullRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, identityPrincipalId, 'AcrPull')
  scope: acr
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '7f951dda-4ed3-4680-a7ca-43fe172d538d'   // AcrPull built-in role ID
    )
    principalId: identityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

output loginServer string = acr.properties.loginServer
output acrId string = acr.id
