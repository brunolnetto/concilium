// Módulo: Azure DNS Zone
// Cria a zona DNS mendesloboconstrucao.com.br e os registros A para API e MCP.
//
// IMPORTANTE: após criar a zona, copie os Name Servers (NS records) gerados pelo Azure
// e configure-os no seu registrador de domínio (ex: Registro.br).
//
// az network dns zone show \
//   --resource-group concilium-rg \
//   --name mendesloboconstrucao.com.br \
//   --query nameServers

@description('Nome do domínio DNS (ex: mendesloboconstrucao.com.br)')
param dnsZoneName string

@description('IP público do Application Gateway')
param appGatewayPublicIp string

resource dnsZone 'Microsoft.Network/dnsZones@2018-05-01' = {
  name: dnsZoneName
  location: 'global'   // DNS zones são recursos globais no Azure
  properties: {
    zoneType: 'Public'
  }
}

// api.mendesloboconstrucao.com.br → Application Gateway
resource apiRecord 'Microsoft.Network/dnsZones/A@2018-05-01' = {
  parent: dnsZone
  name: 'api'
  properties: {
    TTL: 300
    ARecords: [
      { ipv4Address: appGatewayPublicIp }
    ]
  }
}

// mcp.mendesloboconstrucao.com.br → Application Gateway
resource mcpRecord 'Microsoft.Network/dnsZones/A@2018-05-01' = {
  parent: dnsZone
  name: 'mcp'
  properties: {
    TTL: 300
    ARecords: [
      { ipv4Address: appGatewayPublicIp }
    ]
  }
}

output dnsZoneId string = dnsZone.id
output nameServers array = dnsZone.properties.nameServers
output apiRecordFqdn string = 'api.${dnsZoneName}'
output mcpRecordFqdn string = 'mcp.${dnsZoneName}'
