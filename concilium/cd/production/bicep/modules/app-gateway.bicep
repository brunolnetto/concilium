// Módulo: Azure Application Gateway Standard_v2
// TLS termination + roteamento por hostname para API e MCP.
// Certificados TLS devem estar em um Key Vault acessível via Managed Identity.

@description('Região Azure')
param location string

@description('Nome do Application Gateway')
param appGatewayName string

@description('FQDN do ACI para backend API (porta 8000)')
param aciApiHost string

@description('FQDN do ACI para backend MCP (porta 8080)')
param aciMcpHost string

@description('Secret ID do certificado TLS no Key Vault (ADR-094 Fase 3). Ex: https://kv.vault.azure.net/secrets/tls-cert')
param tlsCertKeyVaultSecretId string = ''

@description('Domínio raiz para listeners HTTPS (ex: mendesloboconstrucao.com.br)')
param domainName string = 'mendesloboconstrucao.com.br'

@description('Resource ID da Managed Identity com acesso ao Key Vault Certificate User')
param managedIdentityId string = ''

// ── IP Público ────────────────────────────────────────────────────────────────

resource publicIp 'Microsoft.Network/publicIPAddresses@2023-09-01' = {
  name: '${appGatewayName}-pip'
  location: location
  sku: { name: 'Standard' }
  properties: {
    publicIPAllocationMethod: 'Static'
    dnsSettings: {
      domainNameLabel: appGatewayName
    }
  }
}

// ── VNet + Subnet ─────────────────────────────────────────────────────────────

resource vnet 'Microsoft.Network/virtualNetworks@2023-09-01' = {
  name: '${appGatewayName}-vnet'
  location: location
  properties: {
    addressSpace: { addressPrefixes: ['10.0.0.0/16'] }
    subnets: [
      {
        name: 'appgw-subnet'
        properties: { addressPrefix: '10.0.0.0/24' }
      }
    ]
  }
}

// ── Application Gateway ───────────────────────────────────────────────────────

resource appGateway 'Microsoft.Network/applicationGateways@2023-09-01' = {
  name: appGatewayName
  location: location
  // Managed Identity necessária para leitura do certificado TLS no Key Vault
  identity: managedIdentityId != '' ? {
    type: 'UserAssigned'
    userAssignedIdentities: { '${managedIdentityId}': {} }
  } : null
  properties: {
    sku: {
      name: 'Standard_v2'
      tier: 'Standard_v2'
    }
    autoscaleConfiguration: {
      minCapacity: 1
      maxCapacity: 3
    }

    gatewayIPConfigurations: [
      {
        name: 'appgw-ip-config'
        properties: {
          subnet: { id: vnet.properties.subnets[0].id }
        }
      }
    ]

    frontendIPConfigurations: [
      {
        name: 'appgw-frontend-ip'
        properties: { publicIPAddress: { id: publicIp.id } }
      }
    ]

    frontendPorts: [
      { name: 'port-80',  properties: { port: 80 } }
      { name: 'port-443', properties: { port: 443 } }
    ]

    // ── Backend pools ────────────────────────────────────────────────────────

    backendAddressPools: [
      {
        name: 'api-pool'
        properties: {
          backendAddresses: [{ fqdn: aciApiHost }]
        }
      }
      {
        name: 'mcp-pool'
        properties: {
          backendAddresses: [{ fqdn: aciMcpHost }]
        }
      }
    ]

    backendHttpSettingsCollection: [
      {
        name: 'api-settings'
        properties: {
          port: 8000
          protocol: 'Http'
          cookieBasedAffinity: 'Disabled'
          pickHostNameFromBackendAddress: true
          requestTimeout: 120   // pipeline pode demorar — timeout generoso
          probe: { id: resourceId('Microsoft.Network/applicationGateways/probes', appGatewayName, 'api-probe') }
        }
      }
      {
        name: 'mcp-settings'
        properties: {
          port: 8080
          protocol: 'Http'
          cookieBasedAffinity: 'Disabled'
          pickHostNameFromBackendAddress: true
          requestTimeout: 300   // MCP pode ter SSE/streaming — timeout alto
        }
      }
    ]

    // ── Probes ───────────────────────────────────────────────────────────────

    probes: [
      {
        name: 'api-probe'
        properties: {
          protocol: 'Http'
          host: aciApiHost
          path: '/health'
          interval: 30
          timeout: 10
          unhealthyThreshold: 3
          pickHostNameFromBackendHttpSettings: false
          match: {
            statusCodes: ['200-399']
          }
        }
      }
    ]

    // ── Certificado TLS (Key Vault) ───────────────────────────────────────────

    sslCertificates: tlsCertKeyVaultSecretId != '' ? [
      {
        name: 'tls-cert'
        properties: {
          keyVaultSecretId: tlsCertKeyVaultSecretId
        }
      }
    ] : []

    // ── Listeners ────────────────────────────────────────────────────────────

    httpListeners: concat(
      // HTTP → redirect para HTTPS
      [
        {
          name: 'http-listener'
          properties: {
            frontendIPConfiguration: { id: resourceId('Microsoft.Network/applicationGateways/frontendIPConfigurations', appGatewayName, 'appgw-frontend-ip') }
            frontendPort: { id: resourceId('Microsoft.Network/applicationGateways/frontendPorts', appGatewayName, 'port-80') }
            protocol: 'Http'
          }
        }
      ],
      // HTTPS listeners — só criados quando o certificado está disponível
      tlsCertKeyVaultSecretId != '' ? [
        {
          name: 'api-https-listener'
          properties: {
            frontendIPConfiguration: { id: resourceId('Microsoft.Network/applicationGateways/frontendIPConfigurations', appGatewayName, 'appgw-frontend-ip') }
            frontendPort: { id: resourceId('Microsoft.Network/applicationGateways/frontendPorts', appGatewayName, 'port-443') }
            protocol: 'Https'
            hostName: 'api.${domainName}'
            sslCertificate: { id: resourceId('Microsoft.Network/applicationGateways/sslCertificates', appGatewayName, 'tls-cert') }
          }
        }
        {
          name: 'mcp-https-listener'
          properties: {
            frontendIPConfiguration: { id: resourceId('Microsoft.Network/applicationGateways/frontendIPConfigurations', appGatewayName, 'appgw-frontend-ip') }
            frontendPort: { id: resourceId('Microsoft.Network/applicationGateways/frontendPorts', appGatewayName, 'port-443') }
            protocol: 'Https'
            hostName: 'mcp.${domainName}'
            sslCertificate: { id: resourceId('Microsoft.Network/applicationGateways/sslCertificates', appGatewayName, 'tls-cert') }
          }
        }
      ] : []
    )

    // ── Redirect HTTP → HTTPS ─────────────────────────────────────────────────

    redirectConfigurations: [
      {
        name: 'http-to-https'
        properties: {
          redirectType: 'Permanent'
          includePath: true
          includeQueryString: true
          targetUrl: 'https://api.${domainName}'
        }
      }
    ]

    // ── Routing rules ────────────────────────────────────────────────────────

    requestRoutingRules: concat(
      [
        {
          name: 'http-redirect-rule'
          properties: {
            ruleType: 'Basic'
            priority: 100
            httpListener: { id: resourceId('Microsoft.Network/applicationGateways/httpListeners', appGatewayName, 'http-listener') }
            redirectConfiguration: { id: resourceId('Microsoft.Network/applicationGateways/redirectConfigurations', appGatewayName, 'http-to-https') }
          }
        }
      ],
      tlsCertKeyVaultSecretId != '' ? [
        {
          name: 'api-https-rule'
          properties: {
            ruleType: 'Basic'
            priority: 200
            httpListener: { id: resourceId('Microsoft.Network/applicationGateways/httpListeners', appGatewayName, 'api-https-listener') }
            backendAddressPool: { id: resourceId('Microsoft.Network/applicationGateways/backendAddressPools', appGatewayName, 'api-pool') }
            backendHttpSettings: { id: resourceId('Microsoft.Network/applicationGateways/backendHttpSettingsCollection', appGatewayName, 'api-settings') }
          }
        }
        {
          name: 'mcp-https-rule'
          properties: {
            ruleType: 'Basic'
            priority: 300
            httpListener: { id: resourceId('Microsoft.Network/applicationGateways/httpListeners', appGatewayName, 'mcp-https-listener') }
            backendAddressPool: { id: resourceId('Microsoft.Network/applicationGateways/backendAddressPools', appGatewayName, 'mcp-pool') }
            backendHttpSettings: { id: resourceId('Microsoft.Network/applicationGateways/backendHttpSettingsCollection', appGatewayName, 'mcp-settings') }
          }
        }
      ] : []
    )
  }
}

output publicIp string = publicIp.properties.ipAddress
output appGatewayId string = appGateway.id
