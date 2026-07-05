// frontend/mambo/src/api/versionControlService.ts
import apiClient from './index';

export interface VersionSnapshotItem {
  checkpoint_id: string;
  timestamp: string;
  file_count: number;
  changed_files: string[];
}

export interface VersionHistoryData {
  thread_id: string;
  snapshots: VersionSnapshotItem[];
}

export interface VersionFileContent {
  path: string;
  checkpoint_id: string;
  content: string | null;
  sha256: string | null;
}

/** 获取会话的所有版本快照 */
export async function getSnapshots(chatId: string): Promise<VersionHistoryData> {
  return apiClient.get(`/versions/${chatId}/snapshots`);
}

/** 获取最新快照 */
export async function getLatestSnapshot(chatId: string): Promise<VersionSnapshotItem> {
  return apiClient.get(`/versions/${chatId}/snapshots/latest`);
}

/** 获取指定快照的文件内容 */
export async function getFileVersion(
  chatId: string,
  path: string,
  checkpointId: string,
): Promise<VersionFileContent> {
  // strip leading '/' — backend prepends it back to reconstruct the full path
  const cleanPath = path.startsWith('/') ? path.substring(1) : path;
  return apiClient.get(
    `/versions/${chatId}/files/${cleanPath}`,
    { params: { checkpoint_id: checkpointId } },
  );
}

export interface RestoreResponse {
  success: boolean
  restored: string[]
  errors: string[]
}

/** 将指定文件恢复到历史版本 */
export async function restoreFiles(
  chatId: string,
  checkpointId: string,
  files: string[],
): Promise<RestoreResponse> {
  return apiClient.post(`/versions/${chatId}/restore`, {
    checkpoint_id: checkpointId,
    files,
  });
}

/** 从快照回滚文件并触发重新生成 */
export async function regenerateFromSnapshot(
  chatId: string,
  checkpointId: string,
  files: string[],
): Promise<RestoreResponse> {
  return apiClient.post(`/versions/${chatId}/regenerate-from-snapshot`, {
    checkpoint_id: checkpointId,
    files,
  });
}
