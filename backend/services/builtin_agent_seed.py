"""内置 mambo_agent 首次启动自动导入（A+B 幂等方案）。

A: GlobalSettings 标志位（builtin_mambo_agents_imported，JSON 数组，按包粒度）判断是否已导入；
B: 标志缺失时（老库升级场景），通过 compute_rename_plan 探测主 Agent 是否同名冲突，
   冲突即视为已导入，避免重复导入产生 "xxx (1)"。

失败处理：单个包导入失败时回滚该包已创建的实体（cleanup_import_session），
本次启动中止后续导入且不写标志，下次启动重试；整体异常仅记录日志，不阻塞服务启动。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Set

from sqlalchemy.ext.asyncio import AsyncSession

from backend.crud import setting_crud
from backend.schemas.setting import GlobalSetting
from backend.services.agent_package_service import AgentPackageImporter

logger = logging.getLogger(__name__)

# 内置 Agent 包目录（随 backend 打包，Docker 与 desktop 均包含）
BUILTIN_AGENT_DIR = Path(__file__).resolve().parent.parent / "builtin_agents"
BUILTIN_AGENT_FILES = [
    "mambo.mamboagent",
    "mambo_code.mamboagent",
    "mambo_role.mamboagent",
]
SETTING_KEY = "builtin_mambo_agents_imported"


async def seed_builtin_agents(db: AsyncSession) -> None:
    """首次启动导入内置 Agent 包；已导入则跳过。失败不阻塞服务启动。"""
    try:
        imported = await _read_imported(db)
        pending = [f for f in BUILTIN_AGENT_FILES if f not in imported]
        if not pending:
            return
        logger.info(f"首次启动，开始导入内置 Agent: {pending}")
        importer = AgentPackageImporter(db)
        for filename in pending:
            if await _import_one(importer, filename):
                imported.add(filename)
            else:
                break
        await _write_imported(db, imported)
    except Exception:
        logger.exception("内置 Agent 初始化失败（下次启动将重试）")


async def _import_one(importer: AgentPackageImporter, filename: str) -> bool:
    """导入单个包；返回是否应标记为已导入。"""
    pkg_path = BUILTIN_AGENT_DIR / filename
    if not pkg_path.is_file():
        logger.warning(f"内置 Agent 包缺失: {pkg_path}（部署不完整，已跳过）")
        return True
    try:
        raw = pkg_path.read_bytes()
        pkg = importer.load_package(raw)
        blob_index = importer.build_blob_index(pkg)
        errors = importer.check_references(pkg)
        if errors:
            logger.error(f"内置 Agent 包完整性检查失败 [{filename}]: {errors[:5]}")
            return False
        importer.validate_all_names(pkg)
        plan = await importer.compute_rename_plan(pkg, None, None)

        if _main_agent_conflicted(plan):
            # B 兜底：库中已存在同名主 Agent（老库升级），视为已导入
            logger.info(f"已检测到同名 Agent '{plan.main_agent_name}'，跳过内置包 {filename}")
            return True

        report = await importer.do_import(pkg, blob_index, None, plan)
        if report.success:
            logger.info(f"内置 Agent 导入成功 [{filename}]: 主 Agent {report.main_agent_id}")
            return True

        try:
            await importer.cleanup_import_session(report.import_session_id)
        except Exception:
            logger.exception(f"回滚内置 Agent 导入残留失败 [{filename}]")
        logger.error(f"内置 Agent 导入失败 [{filename}] 阶段 {report.failed_phase}: {report.error}")
        return False
    except Exception:
        logger.exception(f"内置 Agent 导入异常 [{filename}]")
        return False


def _main_agent_conflicted(plan) -> bool:
    return any(
        s.entity_type == "agent" and s.source_id == plan.main_source_id
        for s in plan.suggestions
    )


async def _read_imported(db: AsyncSession) -> Set[str]:
    setting = await setting_crud.get_setting(db, SETTING_KEY)
    if not setting or not setting.value:
        return set()
    try:
        data = json.loads(setting.value)
        return set(data) if isinstance(data, list) else set()
    except (ValueError, TypeError):
        return set()


async def _write_imported(db: AsyncSession, names: Set[str]) -> None:
    await setting_crud.update_setting(
        db, GlobalSetting(key=SETTING_KEY, value=json.dumps(sorted(names)))
    )
