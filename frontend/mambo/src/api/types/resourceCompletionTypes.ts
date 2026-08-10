// 资源补全类型（独立模块，避免污染 resourceTypes.ts）

export interface ResourceCompletePathRequest {
  agent_id: string
  prefix: string
  limit?: number
}

export interface ResourceCompletePathItem {
  name: string
  item_type: string
  resource_type: string | null
  path: string
  is_dir: boolean
}

export interface ResourceCompletePathResponse {
  enabled: boolean
  items: ResourceCompletePathItem[]
}

export interface ResourceContentCompleteRequest {
  agent_id: string
  prefix: string
  limit?: number
  max_items?: number
}

export interface ResourceContentCompleteItem {
  resource_id: string
  resource_path: string
  snippet: string
}

export interface ResourceContentCompleteResponse {
  enabled: boolean
  items: ResourceContentCompleteItem[]
}
