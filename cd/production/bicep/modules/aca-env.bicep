// Módulo: Azure Container Apps Environment
// Ambiente compartilhado por concilium-api e concilium-mcp.
// Os Container Apps são gerenciados pelo deploy.sh (blue-green por revisions).

@description('Região Azure')
param location string

@description('Nome do ACA Environment')
param envName string

resource acaEnv 'Microsoft.App/managedEnvironments@2023-11-02-preview' = {
  name: envName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'none'
    }
  }
}

output envId string = acaEnv.id
output envName string = acaEnv.name
