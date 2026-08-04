// Agent 导出包（.mamboagent）API 服务
import apiClient from './index';
import type {
  AgentPackageCleanupReport,
  AgentPackageImportReport,
  AgentPackagePreview,
} from './types/agentPackageTypes';

/**
 * 导出 Agent 为 .mamboagent 包（gzip 二进制）。
 */
export const exportAgent = (agentId: string): Promise<Blob> => {
  return apiClient.get('/agents/export', {
    params: { agentId },
    responseType: 'blob',
  });
};

/**
 * 触发浏览器下载 .mamboagent 文件。
 */
export const downloadAgentPackage = (agentId: string, agentName: string): Promise<void> => {
  return exportAgent(agentId).then((blob) => {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${agentName}.mamboagent`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  });
};

const buildForm = (
  file: File,
  targetFolderId: string | null,
  nameOverrides?: Record<string, string>,
): FormData => {
  const form = new FormData();
  form.append('file', file);
  if (targetFolderId) {
    form.append('targetFolderId', targetFolderId);
  }
  if (nameOverrides && Object.keys(nameOverrides).length > 0) {
    form.append('nameOverrides', JSON.stringify(nameOverrides));
  }
  return form;
};

// 必须显式声明 multipart：apiClient 全局默认 Content-Type 为 application/json，
// axios 会把 FormData 序列化为 JSON 导致后端收不到 file 字段（422）
const MULTIPART_HEADERS = { 'Content-Type': 'multipart/form-data' };

/**
 * dry-run 预检：校验包格式 / 引用完整性 / 名称冲突，返回改名建议与目录树预览。
 */
export const importAgentPreview = (
  file: File,
  targetFolderId: string | null,
  nameOverrides?: Record<string, string>,
): Promise<AgentPackagePreview> => {
  return apiClient.post('/agents/import', buildForm(file, targetFolderId, nameOverrides), {
    params: { preview: true },
    headers: MULTIPART_HEADERS,
  });
};

/**
 * 正式导入 Agent 包。
 */
export const importAgent = (
  file: File,
  targetFolderId: string | null,
  nameOverrides?: Record<string, string>,
): Promise<AgentPackageImportReport> => {
  return apiClient.post('/agents/import', buildForm(file, targetFolderId, nameOverrides), {
    params: { preview: false },
    headers: MULTIPART_HEADERS,
  });
};

/**
 * 清理一次导入会话创建的实体（失败后「清理并重试」）。
 */
export const cleanupImportSession = (sessionId: string): Promise<AgentPackageCleanupReport> => {
  return apiClient.post(`/agents/import/${sessionId}/cleanup`);
};
