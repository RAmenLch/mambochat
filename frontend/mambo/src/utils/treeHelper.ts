// frontend/mambo/src/utils/treeHelper.ts

/**
 * 定义一个通用的、可被构造成树形结构的基础类型。
 * 任何希望被构造成树的数组元素都应至少包含这些属性。
 */
interface TreeItem {
  id: string;
  name: string;
  parentId: string | null;
  // sortOrder 仍然保留用于同级排序，但在懒加载模式下，
  // 它的值由后端返回的列表顺序决定，前端不再主动计算它。
  sortOrder: number;
  itemType: string;
}

/**
 * 定义一个通用的、带有子节点层级的树节点类型。
 */
export type TreeNode<T> = T & { children?: TreeNode<T>[] };

/**
 * 将一个扁平的、实现了 TreeItem 接口的列表构建成一个层级分明的树形结构。
 * 该函数是通用的，可用于构建会话树、资源树等。
 *
 * 在懒加载模式下，此函数处理的是“当前已加载的增量数据”。
 * 如果一个文件夹的子节点尚未加载，它将没有 children 属性（或为空数组）。
 * 为了支持 UI 上的懒加载展开效果，对于未加载且无子节点的文件夹，我们会注入一个临时的 Stub 节点。
 *
 * @param flatList - 从 Store 获取的扁平列表（包含已加载的所有节点）。
 * @param loadedIds - (可选) 已完成加载子节点的文件夹 ID 集合。
 * @returns 返回一个表示层级结构的 TreeNode 数组。
 */
export function buildChatTree<T extends TreeItem>(
  flatList: readonly T[],
  loadedIds?: Set<string>
): TreeNode<T>[] {
  // 使用深拷贝来避免对原始 store state 的副作用
  const list: TreeNode<T>[] = JSON.parse(JSON.stringify(flatList));
  const map: Record<string, TreeNode<T>> = {};
  list.forEach(item => (map[item.id] = item));

  const tree: TreeNode<T>[] = [];

  // 1. 构建树结构
  list.forEach(item => {
    if (item.parentId && map[item.parentId]) {
      // 如果存在父节点且父节点也在当前列表中，则将当前项添加到父节点的 children 数组中
      (map[item.parentId].children = map[item.parentId].children || []).push(item);
    } else {
      // 否则，该项为根节点（或者其父节点尚未加载/不存在于当前列表中）
      tree.push(item);
    }
  });

  // 2. 处理懒加载占位符 (Stub)
  // 如果是文件夹，且尚未加载过子节点，且当前没有子节点，则注入一个占位符，
  // 迫使 el-tree 渲染展开箭头。
  list.forEach(item => {
    if (item.itemType === 'folder') {
      const hasChildren = item.children && item.children.length > 0;
      const isLoaded = loadedIds ? loadedIds.has(item.id) : false;

      if (!hasChildren && !isLoaded) {
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

  // 递归函数，用于对树的每个层级进行排序
  const sortNodes = (nodes: TreeNode<T>[]) => {
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
