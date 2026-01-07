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
}

/**
 * 定义一个通用的、带有子节点层级的树节点类型。
 */
export type TreeNode<T> = T & { children?: TreeNode<T>[] };

/**
 * 将扁平列表构建成树。
 * 策略：始终确保文件夹拥有子节点（真实节点或隐藏的 Stub 节点），以强行维持 UI 的一致性。
 */
export function buildChatTree<T extends TreeItem>(
  flatList: readonly T[],
  loadedIds?: Set<string>
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
  // 解决问题 1: 只要是文件夹，如果当前没有子节点，就注入 Stub。
  // 这样做有两个好处：
  // a) 未加载时：显示箭头，点击触发加载。
  // b) 已加载但为空时：依然显示箭头（指向下），表示这是一个容器，符合“保留三角符号”的需求。
  list.forEach(item => {
    if (item.itemType === 'folder') {
      if (!item.children || item.children.length === 0) {
        const stubNode = {
          id: `stub_${item.id}`,
          name: '', // 名字为空，配合 CSS 隐藏
          parentId: item.id,
          sortOrder: 0,
          itemType: 'stub', // 特殊类型，ElementTree 中会识别并隐藏
          children: []
        } as unknown as TreeNode<T>;

        item.children = [stubNode];
      }
    }
  });

  // 排序
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
