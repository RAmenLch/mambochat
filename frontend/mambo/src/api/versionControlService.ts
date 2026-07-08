// frontend/mambo/src/api/versionControlService.ts
import apiClient from './index';

export interface VersionFileContent {
  path: string;
  checkpoint_id: string;
  content: string | null;
  sha256: string | null;
}

/** 获取指定快照的文件内容（查看历史版本） */
export async function getFileVersion(
  chatId: string,
  path: string,
  checkpointId: string,
): Promise<VersionFileContent> {
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
