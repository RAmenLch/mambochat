// frontend/mambo/src/utils/treeHelper.ts

/**
 * 定义一个通用的、可被构造成树形结构的基础类型。
 */
interface TreeItem {
  id: string;
  name: string;
  parentId: string | null;
  sortOrder: number;
  itemType: string;
  createdAt?: string;
  lastOpenedAt?: string | null;
}

/**
 * 定义一个通用的、带有子节点层级的树节点类型。
 */
export type TreeNode<T> = T & { children?: TreeNode<T>[] };

export type ChatSortMode = 'manual' | 'folder-top-time';

/**
 * 将扁平列表构建成树。
 * 策略：始终确保文件夹拥有子节点（真实节点或隐藏的 Stub 节点），以强行维持 UI 的一致性。
 */
export function buildChatTree<T extends TreeItem>(
  flatList: readonly T[],
  loadedIds?: Set<string>,
  sortMode: ChatSortMode = 'manual'
): TreeNode<T>[] {
  // 深拷贝防止由于对象引用导致的副作用
  const list: TreeNode<T>[] = JSON.parse(JSON.stringify(flatList));
  const map: Record<string, TreeNode<T>> = {};
  list.forEach(item => (map[item.id] = item));

  const tree: TreeNode<T>[] = [];

  // 1. 构建物理树结构
  list.forEach(item => {
    if (item.parentId && map[item.parentId]) {
      (map[item.parentId].children = map[item.parentId].children || []).push(item);
    } else {
      tree.push(item);
    }
  });

  // 2. 注入占位符 (Stub)
  list.forEach(item => {
    if (item.itemType === 'folder') {
      if (!item.children || item.children.length === 0) {
        const stubNode = {
          id: `stub_${item.id}`,
          name: '',
          parentId: item.id,
          sortOrder: 0,
          itemType: 'stub',
          children: []
        } as unknown as TreeNode<T>;

        item.children = [stubNode];
      }
    }
  });

  // 排序
  const sortNodes = (nodes: TreeNode<T>[], isRoot: boolean = false) => {
    if (sortMode === 'folder-top-time' && isRoot) {
      // 文件夹置顶（按 sortOrder），根目录会话按时间降序（最新在上）
      const folders = nodes.filter(n => n.itemType === 'folder');
      const chats = nodes.filter(n => n.itemType !== 'folder' && n.itemType !== 'stub');
      folders.sort((a, b) => a.sortOrder - b.sortOrder);
      chats.sort((a, b) => {
        const timeA = a.createdAt || '';
        const timeB = b.createdAt || '';
        return timeB.localeCompare(timeA);
      });
      nodes.length = 0;
      nodes.push(...folders, ...chats);
    } else {
      nodes.sort((a, b) => a.sortOrder - b.sortOrder);
    }
    nodes.forEach(node => {
      if (node.children) {
        sortNodes(node.children, false);
      }
    });
  };

  sortNodes(tree, true);

  return tree;
}
