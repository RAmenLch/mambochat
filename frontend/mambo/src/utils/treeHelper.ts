// frontend/mambo/src/utils/treeHelper.ts

import type { Chat } from '@/api/types';

/**
 * 带有子节点层级的会话/文件夹树节点类型。
 */
export type ChatNode = Chat & { children?: ChatNode[] };

/**
 * 将扁平的会话/文件夹列表构建成一个层级分明的树形结构。
 * 该函数会进行深拷贝以避免修改原始数组，并按 sortOrder 对每个层级的节点进行排序。
 *
 * @param flatList - 从API获取的原始扁平会话/文件夹列表。
 * @returns 返回一个表示层级结构的 ChatNode 数组。
 */
export function buildChatTree(flatList: readonly Chat[]): ChatNode[] {
  // 使用深拷贝来避免对原始 store state 的副作用
  const list: ChatNode[] = JSON.parse(JSON.stringify(flatList));
  const map: Record<string, ChatNode> = {};
  list.forEach(item => (map[item.id] = item));

  const tree: ChatNode[] = [];
  list.forEach(item => {
    if (item.parentId && map[item.parentId]) {
      // 如果存在父节点，则将当前项添加到父节点的 children 数组中
      (map[item.parentId].children = map[item.parentId].children || []).push(item);
    } else {
      // 否则，该项为根节点
      tree.push(item);
    }
  });

  // 递归函数，用于对树的每个层级进行排序
  const sortNodes = (nodes: ChatNode[]) => {
    nodes.sort((a, b) => a.sortOrder - b.sortOrder);
    nodes.forEach(node => {
      if (node.children) {
        sortNodes(node.children);
      }
    });
  };

  sortNodes(tree);

  return tree;
}
