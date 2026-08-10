// frontend/mambo/src/api/types/mcpTypes.ts

export type McpTransportType = 'stdio' | 'sse' | 'streamable_http';
export type McpHealthStatus = 'healthy' | 'unhealthy' | null;

export type ToolReviewMode = 'none' | 'require_review';
export type ToolStatus = 'online' | 'offline';

export interface McpServer {
  id: string;
  name: string;
  description: string | null;
  transportType: McpTransportType;
  isEnabled: boolean;
  isSystem: boolean;

  // 状态字段
  last_status: McpHealthStatus;
  last_test_at: string | null;
  last_error: string | null;

  // STDIO 模式专属字段
  command: string | null;
  args: string[] | null;
  env: Record<string, string> | null;
  cwd: string | null;

  // SSE 模式专属字段
  url: string | null;
  headers: Record<string, string> | null;
  timeout: number | null;
  sse_read_timeout: number | null;

  // 是否启用全局代理（仅 http 传输生效）
  useProxy: boolean;
}

export interface McpCreateRequest {
  name: string;
  description?: string | null;
  transportType: McpTransportType;
  isEnabled?: boolean;

  // STDIO 模式参数
  command?: string | null;
  args?: string[] | null;
  env?: Record<string, string> | null;
  cwd?: string | null;

  // SSE 模式参数
  url?: string | null;
  headers?: Record<string, string> | null;
  timeout?: number | null;
  sse_read_timeout?: number | null;

  // 是否启用全局代理（仅 http 传输生效）
  useProxy?: boolean;
}

export interface McpUpdateRequest {
  name?: string;
  description?: string | null;
  transportType?: McpTransportType;
  isEnabled?: boolean;

  // STDIO 模式参数
  command?: string | null;
  args?: string[] | null;
  env?: Record<string, string> | null;
  cwd?: string | null;

  // SSE 模式参数
  url?: string | null;
  headers?: Record<string, string> | null;
  timeout?: number | null;
  sse_read_timeout?: number | null;

  // 是否启用全局代理（仅 http 传输生效）
  useProxy?: boolean;
}

export interface McpTestResponse {
  status: 'healthy' | 'unhealthy';
  tools_count: number;
  message: string;
  error: string | null;
}

export interface McpToolResponse {
  id: string;
  server_id: string;
  name: string;
  description: string | null;
  input_schema: Record<string, unknown> | null;
  is_enabled: boolean;
  review_mode: ToolReviewMode;
  status: ToolStatus;
  last_synced_at: string;
}

export interface McpToolUpdate {
  is_enabled?: boolean;
  review_mode?: ToolReviewMode;
}
