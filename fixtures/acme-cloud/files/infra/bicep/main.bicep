// The reports part of Acme Tickets, owned by the analytics team.
targetScope = 'subscription'

@description('Deployment region.')
param location string = 'westeurope'

@description('Deployment environment.')
param environment string = 'prod'

resource reportsRg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-acme-reports-${environment}'
  location: location
  tags: {
    product: 'reports'
  }
}

module reports 'modules/reports.bicep' = {
  name: 'reports'
  scope: reportsRg
  params: {
    location: location
    environment: environment
  }
}
