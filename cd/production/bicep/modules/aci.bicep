// Módulo: Azure Container Instances
// Dois containers no mesmo grupo: API (8000) + MCP HTTP (8080).

@description('Região Azure')
param location string

@description('Nome do Container Group')
param containerGroupName string

@description('Login server do ACR (ex: conciliumacr.azurecr.io)')
param acrLoginServer string

@description('Tag da imagem a deployar')
param imageTag string

@description('Resource ID completo da Managed Identity')
param identityId string

@description('Nome da Storage Account Azure Blob')
param storageAccountName string

@description('Nome do container blob')
param blobContainerName string

@description('Endpoint OTLP para Azure Monitor')
param otlpEndpoint string

@description('URL do Azure Key Vault para chaves JWT (ADR-094 Fase 1)')
param keyVaultUrl string

@description('Azure Storage Account Key')
@secure()
param azureStorageKey string

var imageFull = '${acrLoginServer}/concilium:${imageTag}'

resource containerGroup 'Microsoft.ContainerInstance/containerGroups@2023-05-01' = {
  name: containerGroupName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identityId}': {}
    }
  }
  properties: {
    imageRegistryCredentials: [
      {
        server: acrLoginServer
        identity: identityId
      }
    ]

    containers: [
      // ── Container 1: FastAPI REST ──────────────────────────────────────────
      {
        name: 'concilium-api'
        properties: {
          image: imageFull
          command: ['concilium-api']
          ports: [
            { port: 8000, protocol: 'TCP' }
          ]
          resources: {
            requests: { cpu: 2, memoryInGB: 4 }
          }
          environmentVariables: [
            { name: 'CONCILIUM__API_HOST', value: '0.0.0.0' }
            { name: 'CONCILIUM__API_PORT', value: '8000' }
            { name: 'CONCILIUM__STORE_BACKEND', value: 'azure_blob' }
            { name: 'CONCILIUM__AZURE_ACCOUNT', value: storageAccountName }
            { name: 'CONCILIUM__AZURE_CONTAINER', value: blobContainerName }
            { name: 'OTEL_SERVICE_NAME', value: 'concilium-api' }
            { name: 'OTEL_EXPORTER_OTLP_ENDPOINT', value: otlpEndpoint }
            { name: 'CONCILIUM__JWT_KEY_VAULT_URL', value: keyVaultUrl }
            { name: 'CONCILIUM__AZURE_KEY', secureValue: azureStorageKey }
          ]
          livenessProbe: {
            httpGet: { path: '/health', port: 8000, scheme: 'HTTP' }
            initialDelaySeconds: 15
            periodSeconds: 30
            failureThreshold: 3
          }
          readinessProbe: {
            httpGet: { path: '/health', port: 8000, scheme: 'HTTP' }
            initialDelaySeconds: 10
            periodSeconds: 10
          }
        }
      }

      // ── Container 2: MCP Server HTTP ──────────────────────────────────────
      {
        name: 'concilium-mcp'
        properties: {
          image: imageFull
          command: ['concilium-mcp']
          ports: [
            { port: 8080, protocol: 'TCP' }
          ]
          resources: {
            requests: { cpu: 2, memoryInGB: 4 }
          }
          environmentVariables: [
            { name: 'CONCILIUM__MCP_TRANSPORT', value: 'streamable-http' }
            { name: 'CONCILIUM__MCP_HOST', value: '0.0.0.0' }
            { name: 'CONCILIUM__MCP_PORT', value: '8080' }
            { name: 'CONCILIUM__STORE_BACKEND', value: 'azure_blob' }
            { name: 'CONCILIUM__AZURE_ACCOUNT', value: storageAccountName }
            { name: 'CONCILIUM__AZURE_CONTAINER', value: blobContainerName }
            { name: 'OTEL_SERVICE_NAME', value: 'concilium-mcp' }
            { name: 'OTEL_EXPORTER_OTLP_ENDPOINT', value: otlpEndpoint }
            { name: 'CONCILIUM__AZURE_KEY', secureValue: azureStorageKey }
          ]
        }
      }
    ]

    ipAddress: {
      type: 'Public'
      dnsNameLabel: containerGroupName
      ports: [
        { port: 8000, protocol: 'TCP' }
        { port: 8080, protocol: 'TCP' }
      ]
    }

    osType: 'Linux'
    restartPolicy: 'Always'
  }
}

output publicIp string = containerGroup.properties.ipAddress.ip
output fqdn string = containerGroup.properties.ipAddress.fqdn
