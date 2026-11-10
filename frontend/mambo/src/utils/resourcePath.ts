// frontend/mambo/src/utils/resourcePath.ts

import type { Resource } from '@/api/types';

/**
 * 拼接资源的层级路径（形如：系统提示词 / 子目录 / 资源名）。
 * lookup 用于根据 parentId 取回父节点，取不到时停止向上追溯。
 */
export function buildResourcePath(
  resource: Resource,
  lookup: (id: string) => Resource | undefined,
  separator = ' / '
): string {
  const segments: string[] = [];
  const visited = new Set<string>();
  let current: Resource | undefined = resource;

  while (current && !visited.has(current.id)) {
    visited.add(current.id);
    segments.unshift(current.name);

    const parentId = current.parentId;
    if (!parentId || parentId === 'root') break;
    current = lookup(parentId);
  }

  return segments.join(separator);
}
