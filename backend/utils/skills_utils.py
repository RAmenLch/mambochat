# backend/utils/skills_utils.py

import os
import re
import yaml
from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field

# ==========================================
# 1. 规范常量定义
# ==========================================
MAX_SKILL_FILE_SIZE = 10 * 1024 * 1024  # 10MB
MAX_SKILL_NAME_LENGTH = 64
MAX_SKILL_DESCRIPTION_LENGTH = 1024
MAX_SKILL_COMPATIBILITY_LENGTH = 500


# ==========================================
# 2. 内存文件树数据结构
# ==========================================
class FileNode(BaseModel):
    """表示内存中的文件或目录节点"""
    type: Literal["file", "dir"]
    name: str
    content: Optional[str] = Field(default=None, description="文件内容，仅当 type='file' 时有效")
    children: Optional[List['FileNode']] = Field(default=None, description="子节点，仅当 type='dir' 时有效")


# 解决 Pydantic 递归类型引用
FileNode.model_rebuild()


class ValidationResult(BaseModel):
    """校验结果"""
    is_valid: bool
    errors: List[str]
    warnings: List[str]


# ==========================================
# 3. 核心校验工具类
# ==========================================
class SkillValidator:
    """
    Agent Skills 规范校验器
    接受一个内存中的文件树，检查其中所有的 SKILL.md 是否符合规范。
    """

    def __init__(self):
        self._errors: List[str] = []
        self._warnings: List[str] = []

    def validate_tree(self, root: FileNode) -> ValidationResult:
        """
        校验整个内存文件树
        """
        self._errors = []
        self._warnings = []

        # 如果根节点就是 SKILL 目录，直接从根节点开始校验
        if root.type == "dir":
            # 检查根目录下是否有 SKILL.md
            has_skill_md = any(child.type == "file" and child.name == "SKILL.md" for child in (root.children or []))
            if has_skill_md:
                skill_md_node = next(
                    child for child in root.children if child.type == "file" and child.name == "SKILL.md")
                self._validate_skill_md(dir_name=root.name, skill_md_node=skill_md_node, full_path=root.name)

            # 继续遍历子目录
            for child in (root.children or []):
                if child.type == "dir":
                    self._traverse_and_validate(child, root.name)

        return ValidationResult(
            is_valid=len(self._errors) == 0,
            errors=self._errors,
            warnings=self._warnings
        )

    def _traverse_and_validate(self, node: FileNode, current_path: str):
        """递归遍历文件树，寻找并校验包含 SKILL.md 的目录"""
        path = f"{current_path}/{node.name}".strip("/")

        if node.type == "dir" and node.children:
            # 查找当前目录下是否有 SKILL.md
            skill_md_node = next(
                (child for child in node.children if child.type == "file" and child.name == "SKILL.md"),
                None
            )

            if skill_md_node:
                self._validate_skill_md(dir_name=node.name, skill_md_node=skill_md_node, full_path=path)

            # 继续递归遍历子目录
            for child in node.children:
                if child.type == "dir":
                    self._traverse_and_validate(child, path)

    def _validate_skill_md(self, dir_name: str, skill_md_node: FileNode, full_path: str):
        """校验单个 SKILL.md 文件"""
        content = skill_md_node.content or ""
        file_path = f"{full_path}/SKILL.md"

        # 1. 校验文件大小
        if len(content.encode('utf-8')) > MAX_SKILL_FILE_SIZE:
            self._errors.append(f"[{file_path}] 文件过大，超过 {MAX_SKILL_FILE_SIZE // (1024 * 1024)} MB 限制。")
            return

        # 2. 提取并校验 YAML Frontmatter
        frontmatter_pattern = r"^---\s*\n(.*?)\n---\s*(?:\n|$)"
        match = re.match(frontmatter_pattern, content, re.DOTALL)

        if not match:
            self._errors.append(f"[{file_path}] 缺失有效的 YAML frontmatter (必须以 --- 包裹并位于文件头部)。")
            return

        frontmatter_str = match.group(1)

        try:
            frontmatter_data = yaml.safe_load(frontmatter_str)
        except yaml.YAMLError as e:
            self._errors.append(f"[{file_path}] YAML 解析失败: {e}")
            return

        if not isinstance(frontmatter_data, dict):
            self._errors.append(f"[{file_path}] YAML frontmatter 必须是一个键值对结构。")
            return

        # 3. 校验必须字段
        name = str(frontmatter_data.get("name", "")).strip()
        description = str(frontmatter_data.get("description", "")).strip()

        if not name:
            self._errors.append(f"[{file_path}] 缺少必填字段: 'name'。")
        else:
            self._validate_name(name, dir_name, file_path)

        if not description:
            self._errors.append(f"[{file_path}] 缺少必填字段: 'description'。")
        elif len(description) > MAX_SKILL_DESCRIPTION_LENGTH:
            self._warnings.append(
                f"[{file_path}] 'description' 长度({len(description)})超过建议的最大长度 {MAX_SKILL_DESCRIPTION_LENGTH}。")

        # 4. 校验可选字段
        compatibility = str(frontmatter_data.get("compatibility", "")).strip()
        if compatibility and len(compatibility) > MAX_SKILL_COMPATIBILITY_LENGTH:
            self._warnings.append(
                f"[{file_path}] 'compatibility' 长度超过建议的最大长度 {MAX_SKILL_COMPATIBILITY_LENGTH}。")

        metadata = frontmatter_data.get("metadata")
        if metadata is not None and not isinstance(metadata, dict):
            self._warnings.append(f"[{file_path}] 'metadata' 应当是一个字典，但得到了 {type(metadata).__name__}。")

        raw_tools = frontmatter_data.get("allowed-tools") or frontmatter_data.get("allowed_tools")
        if raw_tools is not None and not isinstance(raw_tools, (str, list)):
            self._warnings.append(
                f"[{file_path}] 'allowed-tools' 应当是字符串或列表，但得到了 {type(raw_tools).__name__}。")

    def _validate_name(self, name: str, dir_name: str, file_path: str):
        """校验 Skill Name 的合法性"""
        if len(name) > MAX_SKILL_NAME_LENGTH:
            self._errors.append(f"[{file_path}] 'name' 长度超过 {MAX_SKILL_NAME_LENGTH} 个字符。")

        if name.startswith("-") or name.endswith("-") or "--" in name:
            self._errors.append(
                f"[{file_path}] 'name' ({name}) 格式错误：不能以连字符开头或结尾，且不能包含连续的连字符。")
        else:
            for c in name:
                if c == "-":
                    continue
                # 校验Unicode小写字母或数字
                if not ((c.isalpha() and c.islower()) or c.isdigit()):
                    self._errors.append(f"[{file_path}] 'name' ({name}) 格式错误：只能包含小写字母、数字和单连字符。")
                    break

        if name != dir_name:
            self._errors.append(f"[{file_path}] 'name' ({name}) 必须与其所在的父目录名称 ({dir_name}) 完全一致。")


# ==========================================
# 4. 数据适配器
# ==========================================
def build_file_node_tree(resources: List[Any], file_contents: Dict[str, str], root_id: str) -> Optional[FileNode]:
    """
    将扁平的数据库 Resource 列表和文件内容字典转换为 FileNode 树状结构。

    :param resources: 数据库查询出的 Resource 对象列表 (需包含 id, name, itemType, parentId 属性)
    :param file_contents: 字典，键为 resource.id，值为该文件的文本内容
    :param root_id: 树的根节点 Resource ID
    :return: 构建好的 FileNode 根节点，如果找不到 root_id 则返回 None
    """
    if not resources:
        return None

    # 建立 ID 到 Resource 的映射
    res_map = {r.id: r for r in resources}

    # 建立 parentId 到子节点列表的映射
    children_map: Dict[str, List[Any]] = {}
    for r in resources:
        pid = r.parentId
        if pid not in children_map:
            children_map[pid] = []

        # 避免将自身作为自己的子节点（防御性编程）
        if pid != r.id:
            children_map[pid].append(r)

    def _build_node(current_id: str) -> Optional[FileNode]:
        if current_id not in res_map:
            return None

        res = res_map[current_id]

        # 判断节点类型 (ResourceItemType.FOLDER.value 通常为 'folder', ResourceItemType.RESOURCE.value 通常为 'resource')
        # 兼容处理，只要不是 folder 就视为 file
        is_folder = (getattr(res, 'itemType', '') == 'folder')
        node_type: Literal["dir", "file"] = "dir" if is_folder else "file"

        node = FileNode(
            type=node_type,
            name=res.name,
            content=file_contents.get(res.id) if node_type == "file" else None,
            children=[] if node_type == "dir" else None
        )

        # 如果是目录，递归构建子节点
        if node_type == "dir":
            child_resources = children_map.get(current_id, [])
            for child_res in child_resources:
                child_node = _build_node(child_res.id)
                if child_node:
                    node.children.append(child_node)

        return node

    return _build_node(root_id)


def identify_skill_roots(root_dir: str) -> List[str]:
    """
    扫描目录，识别所有符合规范的 Skill 根目录路径。
    逻辑：
    1. 找到所有 SKILL.md 文件。
    2. 按路径深度排序。
    3. 过滤掉作为已知 Skill 子目录的 SKILL.md（防止嵌套 Skill 被识别为独立 Skill）。

    :param root_dir: 解压后的临时目录根路径。
    :return: 有效 Skill 目录的绝对路径列表。
    """
    skill_files = []

    # 遍历目录寻找所有 SKILL.md
    for dirpath, dirnames, filenames in os.walk(root_dir):
        if "SKILL.md" in filenames:
            skill_files.append(os.path.join(dirpath, "SKILL.md"))

    # 按路径深度升序排序，确保父级 Skill 先被处理
    skill_files.sort(key=lambda x: x.count(os.sep))

    valid_skill_dirs = []

    for skill_file_path in skill_files:
        current_skill_dir = os.path.dirname(skill_file_path)

        # 检查当前 Skill 是否已被包含在已确认的 Skill 目录中
        is_nested = False
        for existing_dir in valid_skill_dirs:
            # 如果当前目录是已确认目录的子目录，则视为嵌套依赖，跳过
            if current_skill_dir.startswith(existing_dir + os.sep):
                is_nested = True
                break

        if not is_nested:
            valid_skill_dirs.append(current_skill_dir)

    return valid_skill_dirs
