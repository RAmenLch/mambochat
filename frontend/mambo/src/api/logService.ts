// frontend/mambo/src/api/logService.ts
import apiClient from './index';
import type { LogQueryRequest, LogQueryResponse } from './types/logTypes';

export const getPostPayloadLogs = (params: LogQueryRequest): Promise<LogQueryResponse> => {
  return apiClient.get('/logs/post-payloads', { params });
};
