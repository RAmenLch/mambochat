"""Agent 导出包（.mamboagent）路由：导出 / 导入（dry-run 与正式）/ 清理。"""

import json
from typing import Optional, Union
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from backend.crud import agent_crud
from backend.database import get_db
from backend.schemas.agent_package import (
    CleanupReport,
    ImportPreviewResponse,
    ImportReport,
    ProviderBrief,
)
from backend.schemas.enums import AgentItemType
from backend.services.agent_package_service import (
    MAMBOCHAT_VERSION,
    AgentPackageExporter,
    AgentPackageImporter,
)

router = APIRouter(prefix="/agents", tags=["Agent Package"])


def _version_tuple(v: str):
    parts = []
    for seg in str(v).split("."):
        try:
            parts.append(int(seg))
        except ValueError:
            parts.append(0)
    return tuple(parts)


@router.get("/export", summary="导出 Agent 为 .mamboagent 包")
async def export_agent(agentId: str, db: AsyncSession = Depends(get_db)):
    exporter = AgentPackageExporter(db)
    data, name = await exporter.export(agentId)
    filename = f"{name}.mamboagent"
    return Response(
        content=data,
        media_type="application/gzip",
        headers={"Content-Disposition": f"attachment; filename*=utf-8''{quote(filename)}"},
    )


@router.post("/import", summary="导入 Agent 包（preview=true 时仅预检，不写入数据）")
async def import_agent(
        file: UploadFile = File(...),
        targetFolderId: Optional[str] = Form(None, description="目标文件夹 ID（Agent 树），不传表示根目录"),
        nameOverrides: Optional[str] = Form(None, description='JSON 对象，如 {"sourceId": "新名称"}，覆盖自动改名结果'),
        preview: bool = Query(False, description="dry-run 预检模式"),
        db: AsyncSession = Depends(get_db),
) -> Union[ImportPreviewResponse, ImportReport]:
    # 目标文件夹校验（§5.2：主 Agent 导入到目标文件夹）
    target_id = targetFolderId or None
    if target_id:
        folder = await agent_crud.get_agent(db, target_id)
        if folder is None or folder.itemType != AgentItemType.FOLDER.value:
            raise HTTPException(status_code=400, detail="目标文件夹不存在或不是文件夹")

    # nameOverrides 解析
    overrides: Optional[dict] = None
    if nameOverrides:
        try:
            overrides = json.loads(nameOverrides)
            if not isinstance(overrides, dict):
                raise ValueError
        except Exception:
            raise HTTPException(status_code=400, detail="nameOverrides 必须是 JSON 对象")

    raw = await file.read()

    importer = AgentPackageImporter(db)

    # §7.1 步 1-3：解压 / 格式校验 / blob 索引
    pkg = importer.load_package(raw)
    blob_index = importer.build_blob_index(pkg)

    # §7.1 步 4：引用完整性检查 + 名称校验 + 冲突预扫描
    errors = importer.check_references(pkg)
    if errors:
        raise HTTPException(
            status_code=400,
            detail="引用完整性检查失败: " + "; ".join(errors[:20]),
        )
    importer.validate_all_names(pkg)
    plan = await importer.compute_rename_plan(pkg, target_id, overrides)

    if preview:
        warnings: list = []
        if _version_tuple(pkg.mambochatVersion) < _version_tuple(MAMBOCHAT_VERSION):
            warnings.append(
                f"包由较低版本 {pkg.mambochatVersion} 导出（当前 {MAMBOCHAT_VERSION}），"
                f"可能存在兼容性差异"
            )
        return ImportPreviewResponse(
            importable=True,
            format_version=pkg.formatVersion,
            mambochat_version=pkg.mambochatVersion,
            exported_at=pkg.exportedAt,
            description=pkg.description,
            warnings=warnings,
            rename_suggestions=plan.suggestions,
            providers_missing_api_key=[
                ProviderBrief(source_id=p.sourceId, name=p.name) for p in pkg.providers
            ],
            resource_tree=importer.build_tree_preview(pkg),
        )

    # §7.1 步 5-6：正式导入
    return await importer.do_import(pkg, blob_index, target_id, plan)


@router.post("/import/{session_id}/cleanup", response_model=CleanupReport, summary="清理一次导入会话创建的实体")
async def cleanup_import(session_id: str, db: AsyncSession = Depends(get_db)):
    importer = AgentPackageImporter(db)
    return await importer.cleanup_import_session(session_id)
