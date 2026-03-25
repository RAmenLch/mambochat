// frontend/mambo/src/api/types/logTypes.ts
export interface LogQueryRequest {
  skip?: number;
  limit?: number;
  chat_id?: string | null;
  message_id?: string | null;
}

export interface LogItem {
  id: string;
  createdAt: string;
  chatId: string;
  messageId: string;
  managerName: string;
  agentName: string;
  configMetaData: Record<string, any>;
  rawPayload: Record<string, any>;
}

export interface LogQueryResponse {
  total: number;
  items: LogItem[];
}
