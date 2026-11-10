// Report exports for partners and the API that serves them.
param location string
param environment string

resource reportsStorage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: 'stacmereports${environment}'
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    allowBlobPublicAccess: true
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
  }
}

resource blobServices 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  name: 'default'
  parent: reportsStorage
}

resource exportsContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  name: 'exports'
  parent: blobServices
  properties: {
    publicAccess: 'Blob'
  }
}

resource reportsEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cae-acme-reports-${environment}'
  location: location
  properties: {
    zoneRedundant: false
  }
}

resource reportsApi 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-acme-reports-${environment}'
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    environmentId: reportsEnv.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8080
      }
    }
    template: {
      containers: [
        {
          name: 'reports-api'
          image: 'acrticketsprod.azurecr.io/reports-api:latest'
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
            {
              name: 'REPORTS_STORAGE'
              value: reportsStorage.name
            }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 2
      }
    }
  }
}
