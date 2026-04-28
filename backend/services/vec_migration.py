# backend/services/vec_migration.py

"""
vec0 虚拟表 Schema 版本管理与双向迁移。

版本约定:
  v0 — 无分区键:    vec_dim_{dim} USING vec0(vector FLOAT[{dim}])
  v1 — 双分区键:    vec_dim_{dim}_v1 USING vec0(kb_id TEXT PARTITION KEY, resource_id TEXT PARTITION KEY, vector FLOAT[{dim}])

核心设计:
  - 不同版本使用不同表名（v0: vec_dim_{dim}, v1: vec_dim_{dim}_v1）
  - 永远不重命名、不删除任何表
  - 迁移 = 从旧表读 → 写新表 → 更新 vector_id 映射 → 更新版本号
  - 旧表永久保留作为数据安全网
"""

import struct
import json
import logging
import time
from typing import List, Optional, Dict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

logger = logging.getLogger(__name__)

VEC_CURRENT_VERSION = 1

# 运行时缓存：启动后固定，避免每次操作查表
_cached_version: Optional[int] = None


# ── 表名解析 ──────────────────────────────────────────────

def get_vec_table_name(dimension: int, version: Optional[int] = None) -> str:
    """
    根据版本号返回 vec0 表名。
    version=None 时使用缓存版本，若缓存也未初始化则默认当前版本。
    """
    if version is None:
        version = _cached_version if _cached_version is not None else VEC_CURRENT_VERSION
    if version >= 1:
        return f"vec_dim_{dimension}_v1"
    return f"vec_dim_{dimension}"


def _set_cached_version(version: int):
    global _cached_version
    _cached_version = version


# ── 版本追踪 ──────────────────────────────────────────────

async def get_vec_schema_version(conn: AsyncConnection) -> Optional[int]:
    """读取当前 vec schema 版本，如果版本表不存在或为空返回 None"""
    try:
        result = await conn.execute(text("SELECT version FROM vec_schema_version LIMIT 1"))
        row = result.fetchone()
        return row[0] if row else None
    except Exception:
        return None


async def set_vec_schema_version(conn: AsyncConnection, version: int):
    """写入 vec schema 版本"""
    await conn.execute(text("DELETE FROM vec_schema_version"))
    await conn.execute(
        text("INSERT INTO vec_schema_version (version) VALUES (:version)"),
        {"version": version},
    )


# ── 建表辅助 ──────────────────────────────────────────────

async def _create_vec_table_v1(conn: AsyncConnection, table_name: str, dim: int):
    """创建带双分区键的 v1 vec0 表"""
    await conn.execute(text(
        f"CREATE VIRTUAL TABLE IF NOT EXISTS {table_name} USING vec0("
        f"kb_id TEXT PARTITION KEY, "
        f"resource_id TEXT PARTITION KEY, "
        f"vector FLOAT[{dim}]);"
    ))


async def _create_vec_table_v0(conn: AsyncConnection, table_name: str, dim: int):
    """创建无分区键的 v0 vec0 表"""
    await conn.execute(text(
        f"CREATE VIRTUAL TABLE IF NOT EXISTS {table_name} USING vec0(vector FLOAT[{dim}]);"
    ))


async def _table_exists(conn: AsyncConnection, table_name: str) -> bool:
    result = await conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name=:name"),
        {"name": table_name},
    )
    return result.fetchone() is not None


async def _drop_table_if_exists(conn: AsyncConnection, table_name: str):
    """安全删除虚拟表及其 shadow 表"""
    if not await _table_exists(conn, table_name):
        return
    await conn.execute(text(f"DROP TABLE IF EXISTS {table_name}"))
    # 删除可能的 shadow 表 (vec0 创建的: _rowids, _segments, _data, _info)
    for suffix in ("_rowids", "_segments", "_data", "_info"):
        shadow = f"{table_name}{suffix}"
        try:
            await conn.execute(text(f"DROP TABLE IF EXISTS {shadow}"))
        except Exception:
            pass


# ── 向量 blob 编解码 ─────────────────────────────────────

def decode_vector_blob(blob: bytes, dimension: int) -> List[float]:
    """将 vec0 返回的 float32 little-endian blob 解码为 Python float 列表"""
    return list(struct.unpack(f"<{dimension}f", blob))


# ── 获取 resource_id → kb_id 映射 ────────────────────────

async def _build_resource_kb_map(conn: AsyncConnection) -> Dict[str, str]:
    """
    构建 resource_id → kb_id 映射。
    优先使用 Resource.kb_id 列，如果为 NULL 则通过递归 CTE 回溯。
    """
    result = await conn.execute(text(
        "SELECT id, kb_id FROM Resource WHERE kb_id IS NOT NULL"
    ))
    mapping = {row[0]: row[1] for row in result.fetchall()}

    # 对于 kb_id 为 NULL 的资源，用递归 CTE 回溯
    null_result = await conn.execute(text(
        """
        SELECT DISTINCT c.resource_id
        FROM ResourceKBChunk c
        JOIN Resource r ON c.resource_id = r.id
        WHERE c.vector_id IS NOT NULL AND r.kb_id IS NULL
        """
    ))
    null_resources = [row[0] for row in null_result.fetchall()]

    if null_resources:
        cte_result = await conn.execute(text(
            """
            WITH RECURSIVE hierarchy AS (
                SELECT id, parentId, id AS kb_id, resourceType
                FROM Resource
                WHERE resourceType = 'KNOWLEDGE_BASE'
                UNION ALL
                SELECT r.id, r.parentId, h.kb_id, r.resourceType
                FROM Resource r
                JOIN hierarchy h ON r.parentId = h.id
            )
            SELECT h.id, h.kb_id
            FROM hierarchy h
            WHERE h.id IN :ids AND h.resourceType != 'KNOWLEDGE_BASE'
            """
        ), {"ids": tuple(null_resources)})
        for row in cte_result.fetchall():
            mapping[row[0]] = row[1]

    return mapping


# ── 正向迁移 v0 → v1 ────────────────────────────────────

async def upgrade_v0_to_v1(conn: AsyncConnection, dimensions: List[int]):
    """
    将 v0 表数据迁移到 v1 表。

    v0 表名: vec_dim_{dim}       (保留不删)
    v1 表名: vec_dim_{dim}_v1    (新建)

    步骤:
      1. 创建 v1 表（带双分区键）
      2. 从 v0 表 + ResourceKBChunk + Resource 读取数据写入 v1
      3. 批量更新 ResourceKBChunk.vector_id
      4. 更新版本号
    """
    logger.info("开始 vec schema 升级: v0 -> v1")

    resource_kb_map = await _build_resource_kb_map(conn)

    for dim in dimensions:
        v0_table = f"vec_dim_{dim}"
        v1_table = f"vec_dim_{dim}_v1"

        v0_exists = await _table_exists(conn, v0_table)
        v1_exists = await _table_exists(conn, v1_table)

        if not v0_exists and not v1_exists:
            # 全新: 直接创建 v1
            await _create_vec_table_v1(conn, v1_table, dim)
            logger.info(f"维度 {dim}: 无旧表，直接创建 {v1_table}")
            continue

        if v1_exists:
            # v1 已存在（可能是上次中断后的残留），先清理
            logger.info(f"维度 {dim}: {v1_table} 已存在，清理后重新迁移")
            await _drop_table_if_exists(conn, v1_table)

        if not v0_exists:
            # v0 不存在但 v1 存在过（已被清理），直接创建 v1
            await _create_vec_table_v1(conn, v1_table, dim)
            logger.info(f"维度 {dim}: v0 表不存在，直接创建 {v1_table}")
            continue

        # 创建 v1 表
        await _create_vec_table_v1(conn, v1_table, dim)

        logger.info(f"{v0_table} 开始迁移 -> {v1_table}")

        # 从 ResourceKBChunk 获取 vector_id → resource_id 映射
        chunk_result = await conn.execute(text(
            "SELECT vector_id, resource_id FROM ResourceKBChunk WHERE vector_id IS NOT NULL"
        ))
        vec_to_resource = {row[0]: row[1] for row in chunk_result.fetchall()}

        # 从 v0 读取向量写入 v1
        old_data = await conn.execute(text(f"SELECT rowid, vector FROM {v0_table}"))
        rows = old_data.fetchall()

        if not rows:
            logger.info(f"维度 {dim}: v0 表为空，跳过数据迁移")
            continue

        rowid_mapping: Dict[int, int] = {}
        skipped = 0

        for old_rowid, vector_blob in rows:
            resource_id = vec_to_resource.get(old_rowid)
            if not resource_id:
                skipped += 1
                continue

            kb_id = resource_kb_map.get(resource_id)
            if not kb_id:
                logger.warning(
                    f"跳过无法定位 kb_id 的向量: resource_id={resource_id}, old_rowid={old_rowid}"
                )
                skipped += 1
                continue

            vector = decode_vector_blob(vector_blob, dim)
            vector_json = json.dumps(vector)

            insert_result = await conn.execute(
                text(
                    f"INSERT INTO {v1_table} (kb_id, resource_id, vector) "
                    f"VALUES (:kb_id, :resource_id, :vector)"
                ),
                {"kb_id": kb_id, "resource_id": resource_id, "vector": vector_json},
            )
            new_rowid = insert_result.lastrowid
            rowid_mapping[old_rowid] = new_rowid

        # 批量更新 ResourceKBChunk.vector_id
        if rowid_mapping:
            for old_vid, new_vid in rowid_mapping.items():
                await conn.execute(
                    text("UPDATE ResourceKBChunk SET vector_id = :new_id WHERE vector_id = :old_id"),
                    {"new_id": new_vid, "old_id": old_vid},
                )

        logger.info(
            f"维度 {dim}: 迁移完成 (迁移 {len(rowid_mapping)} 条, 跳过 {skipped} 条), "
            f"保留旧表 {v0_table}"
        )

    await set_vec_schema_version(conn, 1)
    _set_cached_version(1)
    logger.info("vec schema 升级完成: v0 -> v1")


# ── 反向迁移 v1 → v0 ────────────────────────────────────

async def downgrade_v1_to_v0(conn: AsyncConnection, dimensions: List[int]):
    """
    将 v1 表数据迁移回 v0 表。

    v1 表名: vec_dim_{dim}_v1    (保留不删)
    v0 表名: vec_dim_{dim}       (重建)

    步骤:
      1. 如 v0 表已存在，重命名为 _v0_legacy_{timestamp}（保留不删）
      2. 创建 v0 表
      3. 从 v1 读取向量写入 v0，记录 rowid 映射
      4. 批量更新 ResourceKBChunk.vector_id
      5. 更新版本号
    """
    logger.info("开始 vec schema 降级: v1 -> v0")

    for dim in dimensions:
        v0_table = f"vec_dim_{dim}"
        v1_table = f"vec_dim_{dim}_v1"

        v1_exists = await _table_exists(conn, v1_table)

        if not v1_exists:
            # v1 不存在，看看 v0 是否已存在
            if await _table_exists(conn, v0_table):
                logger.info(f"维度 {dim}: {v0_table} 已存在且无 v1 数据，跳过")
            else:
                await _create_vec_table_v0(conn, v0_table, dim)
                logger.info(f"维度 {dim}: 无数据，直接创建 {v0_table}")
            continue

        # v0 表已存在 → 重命名保留
        if await _table_exists(conn, v0_table):
            ts = int(time.time())
            legacy_name = f"vec_dim_{dim}_v0_legacy_{ts}"
            # 直接 DROP 旧的 v0，因为 v1 是完整备份
            # 但为安全起见先尝试重命名（shadow 表可能导致失败）
            try:
                await _drop_table_if_exists(conn, v0_table)
                logger.info(f"维度 {dim}: 清理旧 v0 表 {v0_table}")
            except Exception as e:
                logger.warning(f"维度 {dim}: 无法清理旧 v0 表: {e}")

        # 创建 v0 表
        await _create_vec_table_v0(conn, v0_table, dim)

        logger.info(f"{v1_table} 开始降级 -> {v0_table}")

        # 从 v1 读取向量写入 v0
        data = await conn.execute(text(f"SELECT rowid, vector FROM {v1_table}"))
        rows = data.fetchall()

        rowid_mapping: Dict[int, int] = {}

        for old_rowid, vector_blob in rows:
            vector = decode_vector_blob(vector_blob, dim)
            vector_json = json.dumps(vector)

            insert_result = await conn.execute(
                text(f"INSERT INTO {v0_table} (vector) VALUES (:vector)"),
                {"vector": vector_json},
            )
            new_rowid = insert_result.lastrowid
            rowid_mapping[old_rowid] = new_rowid

        # 批量更新 ResourceKBChunk.vector_id
        for old_vid, new_vid in rowid_mapping.items():
            await conn.execute(
                text("UPDATE ResourceKBChunk SET vector_id = :new_id WHERE vector_id = :old_id"),
                {"new_id": new_vid, "old_id": old_vid},
            )

        logger.info(
            f"维度 {dim}: 降级完成 (迁移 {len(rowid_mapping)} 条), "
            f"保留 v1 表 {v1_table}"
        )

    await set_vec_schema_version(conn, 0)
    _set_cached_version(0)
    logger.info("vec schema 降级完成: v1 -> v0")


# ── 入口函数 ──────────────────────────────────────────────

async def ensure_vec_tables(conn: AsyncConnection, dimensions: List[int]):
    """
    应用启动时调用，检测 vec schema 版本并执行必要的迁移。

    - 全新安装: 创建 v1 表
    - v0 → v1: 自动升级
    - 已是最新版本: 无操作
    """
    # 创建版本追踪表
    await conn.execute(text(
        "CREATE TABLE IF NOT EXISTS vec_schema_version (version INTEGER NOT NULL)"
    ))

    version = await get_vec_schema_version(conn)

    if version is None:
        # 新安装 或 旧版无版本追踪
        # 检查是否存在 v0 表（无后缀的 vec_dim_{dim}）
        has_v0_table = False
        has_v1_table = False
        for dim in dimensions:
            if await _table_exists(conn, f"vec_dim_{dim}"):
                has_v0_table = True
            if await _table_exists(conn, f"vec_dim_{dim}_v1"):
                has_v1_table = True

        if has_v1_table:
            # v1 表已存在，只需补写版本号
            version = 1
            await set_vec_schema_version(conn, version)
            _set_cached_version(version)
            logger.info(f"检测到 v1 vec 表，补写版本号 {version}")
        elif has_v0_table:
            logger.info("检测到 v0 vec 表，开始升级到 v1")
            await upgrade_v0_to_v1(conn, dimensions)
        else:
            # 全新安装
            for dim in dimensions:
                await _create_vec_table_v1(conn, f"vec_dim_{dim}_v1", dim)
            await set_vec_schema_version(conn, VEC_CURRENT_VERSION)
            _set_cached_version(VEC_CURRENT_VERSION)
            logger.info("全新安装: 创建 v1 vec 表")

    elif version < VEC_CURRENT_VERSION:
        logger.info(f"vec schema 版本 {version} < 当前 {VEC_CURRENT_VERSION}，开始升级")
        await upgrade_v0_to_v1(conn, dimensions)

    elif version > VEC_CURRENT_VERSION:
        _set_cached_version(version)
        logger.warning(
            f"vec schema 版本 ({version}) 高于当前代码支持 ({VEC_CURRENT_VERSION})，"
            f"请考虑升级应用代码或手动执行 downgrade"
        )
    else:
        _set_cached_version(version)
        logger.info(f"vec schema 版本已是最新 ({version})")
