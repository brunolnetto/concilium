// Parâmetros para o deploy de produção.
// Copie este arquivo e preencha os valores antes do primeiro deploy.
// NUNCA commite valores de segredos — use az keyvault secret show ou CI/CD secrets.

using 'main.bicep'

param location = 'brazilsouth'
param acrName = 'conciliumacr'
param imageTag = 'latest'           // substituído pelo CI/CD com o git SHA
param identityName = 'concilium-identity'
param storageAccountName = 'conciliumstorage'
param blobContainerName = 'concilium-projetos'
param dnsZoneName = 'mendesloboconstrucao.com.br'
param containerGroupName = 'concilium-cg'
param appGatewayName = 'concilium-agw'

// Endpoint OTLP do Azure Monitor Application Insights
param otlpEndpoint = 'https://brazilsouth-1.in.applicationinsights.azure.com/v2/track'

// Segredos: injetar via CI/CD ou az keyvault — NÃO commitar aqui
// param jwtSecret       = readEnvironmentVariable('JWT_SECRET')
// param azureStorageKey = readEnvironmentVariable('CONCILIUM_AZURE_KEY')
