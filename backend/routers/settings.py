# backend/routers/settings.py

from fastapi import APIRouter, Depends, HTTPException, status, Body, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import Any, Optional

from backend.crud import setting_crud, provider_crud
from backend.services import provider_service
from backend.services.file_service import FileService
from backend.models import setting_model
from backend import schemas
from backend.database import get_db
from backend.schemas.enums import FileManagementType

router = APIRouter()


def _get_typed_setting(setting: Optional[schemas.GlobalSetting], default: Any, target_type: type) -> Any:
    """从数据库配置项安全地获取指定类型的值，如果不存在或转换失败则返回默认值"""
    if setting and setting.value is not None:
        try:
            if target_type == bool:
                return setting.value.lower() == 'true'
            return target_type(setting.value)
        except (ValueError, TypeError):
            return default
    return default


@router.get(
    "/settings/global",
    response_model=schemas.GlobalSettingsUpdate,
    summary="获取全局配置"
)
async def get_global_settings(db: AsyncSession = Depends(get_db)):
    """
    获取系统当前的全局配置。
    如果用户未设置过某些配置，则返回系统预设的默认值。
    """
    keys = [
        "default_model_id", "title_generation_model_id", "zip_history_system_prompt",
        "last_selected_provider_id", "default_max_context_messages", "default_temperature",
        "default_top_p", "default_stream", "default_enable_suggest", "default_enable_ask_user",
        "default_max_retries",
        "default_timeout",
        "proxy_enabled", "proxy_url",
        "web_search_default_mode", "web_search_use_proxy",
        "user_avatar_file_id", "ai_avatar_file_id",
        "frontend_editor", "kb_default_chunk_size", "kb_default_chunk_overlap", "send_message_shortcut",
        "language"
    ]

    result = await db.execute(
        select(setting_model.GlobalSettings).filter(setting_model.GlobalSettings.key.in_(keys))
    )
    settings_map = {s.key: s for s in result.scalars().all()}

    file_service = FileService(db)

    # --- 获取头像URL ---
    user_avatar_url = None
    user_avatar_file_id = _get_typed_setting(settings_map.get("user_avatar_file_id"), None, str)
    if user_avatar_file_id:
        file_record = await file_service.get_file(user_avatar_file_id)
        if file_record:
            user_avatar_url = file_service.get_url(file_record.storage_path)

    ai_avatar_url = None
    ai_avatar_file_id = _get_typed_setting(settings_map.get("ai_avatar_file_id"), None, str)
    if ai_avatar_file_id:
        file_record = await file_service.get_file(ai_avatar_file_id)
        if file_record:
            ai_avatar_url = file_service.get_url(file_record.storage_path)

    # --- 获取其他配置 ---
    default_model_id = _get_typed_setting(settings_map.get("default_model_id"), None, str)
    title_generation_model_id = _get_typed_setting(settings_map.get("title_generation_model_id"), None, str)
    zip_history_system_prompt = _get_typed_setting(settings_map.get("zip_history_system_prompt"), None, str)
    last_selected_provider_id = _get_typed_setting(settings_map.get("last_selected_provider_id"), None, str)
    max_context = _get_typed_setting(settings_map.get("default_max_context_messages"), 0, int)
    temperature = _get_typed_setting(settings_map.get("default_temperature"), 1.0, float)
    top_p = _get_typed_setting(settings_map.get("default_top_p"), 1.0, float)
    stream = _get_typed_setting(settings_map.get("default_stream"), True, bool)
    enable_suggest = _get_typed_setting(settings_map.get("default_enable_suggest"), False, bool)
    enable_ask_user = _get_typed_setting(settings_map.get("default_enable_ask_user"), False, bool)
    max_retries = _get_typed_setting(settings_map.get("default_max_retries"), 1, int)
    default_timeout = _get_typed_setting(settings_map.get("default_timeout"), 60, int)
    proxy_enabled = _get_typed_setting(settings_map.get("proxy_enabled"), False, bool)
    proxy_url = _get_typed_setting(settings_map.get("proxy_url"), None, str)

    web_search_default_mode = _get_typed_setting(settings_map.get("web_search_default_mode"), None, str)
    web_search_use_proxy = _get_typed_setting(settings_map.get("web_search_use_proxy"), False, bool)

    frontend_editor = _get_typed_setting(settings_map.get("frontend_editor"), "simple", str)
    kb_default_chunk_size = _get_typed_setting(settings_map.get("kb_default_chunk_size"), 500, int)
    kb_default_chunk_overlap = _get_typed_setting(settings_map.get("kb_default_chunk_overlap"), 50, int)
    send_message_shortcut = _get_typed_setting(settings_map.get("send_message_shortcut"), "enter", str)
    language = _get_typed_setting(settings_map.get("language"), "zh-CN", str)

    return schemas.GlobalSettingsUpdate(
        default_model_id=default_model_id,
        title_generation_model_id=title_generation_model_id,
        zip_history_system_prompt=zip_history_system_prompt,
        last_selected_provider_id=last_selected_provider_id,
        default_max_context_messages=max_context,
        default_temperature=temperature,
        default_top_p=top_p,
        default_stream=stream,
        default_enable_suggest=enable_suggest,
        default_enable_ask_user=enable_ask_user,
        default_max_retries=max_retries,
        default_timeout=default_timeout,
        proxy_enabled=proxy_enabled,
        proxy_url=proxy_url,
        web_search_default_mode=web_search_default_mode,
        web_search_use_proxy=web_search_use_proxy,
        user_avatar_url=user_avatar_url,
        ai_avatar_url=ai_avatar_url,
        frontend_editor=frontend_editor,
        kb_default_chunk_size=kb_default_chunk_size,
        kb_default_chunk_overlap=kb_default_chunk_overlap,
        send_message_shortcut=send_message_shortcut,
        language=language
    )


@router.put(
    "/settings/global",
    response_model=schemas.GlobalSettingsUpdate,
    summary="更新全局配置"
)
async def update_global_settings(
        settings_update: schemas.GlobalSettingsUpdate,
        db: AsyncSession = Depends(get_db)
):
    """
    更新系统的全局配置。
    """
    update_data = settings_update.model_dump(exclude_unset=True)
    settings_to_update = []

    if "default_model_id" in update_data:
        model_id = update_data["default_model_id"]
        if model_id:
            db_model = await provider_crud.get_model(db, model_id=model_id)
            if not db_model:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"模型ID '{model_id}' 不存在。"
                )
        settings_to_update.append(schemas.GlobalSetting(key="default_model_id", value=model_id))

    if "title_generation_model_id" in update_data:
        model_id = update_data["title_generation_model_id"]
        if model_id:
            db_model = await provider_crud.get_model(db, model_id=model_id)
            if not db_model:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"标题生成模型ID '{model_id}' 不存在。"
                )
        settings_to_update.append(schemas.GlobalSetting(key="title_generation_model_id", value=model_id))

    if "last_selected_provider_id" in update_data:
        provider_id = update_data["last_selected_provider_id"]
        if provider_id:
            db_provider = await provider_crud.get_provider(db, provider_id=provider_id)
            if not db_provider:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"服务商ID '{provider_id}' 不存在。"
                )
        settings_to_update.append(schemas.GlobalSetting(key="last_selected_provider_id", value=provider_id))

    param_keys = [
        "default_max_context_messages", "default_temperature", "default_top_p",
        "default_stream", "default_enable_suggest", "default_enable_ask_user",
        "default_max_retries",
        "default_timeout",
        "proxy_enabled", "proxy_url",
        "web_search_default_mode", "web_search_use_proxy",
        "zip_history_system_prompt",
        "frontend_editor", "kb_default_chunk_size", "kb_default_chunk_overlap", "send_message_shortcut",
        "language"
    ]
    for key in param_keys:
        if key in update_data:
            value = update_data[key]
            if key == "default_max_retries" and value is not None and int(value) < 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="default_max_retries 必须 >= 1"
                )
            settings_to_update.append(schemas.GlobalSetting(key=key, value=str(value) if value is not None else None))

    for setting in settings_to_update:
        await setting_crud.update_setting(db, setting=setting)

    return await get_global_settings(db)


async def _validate_avatar_file(file: UploadFile):
    """辅助函数，用于校验上传的头像文件"""
    ALLOWED_MIME_TYPES = ["image/jpeg", "image/png", "image/gif", "image/webp"]
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type. Allowed types are: {', '.join(ALLOWED_MIME_TYPES)}"
        )

    MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
    if file.size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File is too large. Maximum size is {MAX_FILE_SIZE / 1024 / 1024:.0f} MB."
        )


async def _update_avatar(db: AsyncSession, file: UploadFile, avatar_key: str):
    """辅助函数，用于处理用户和AI头像的上传和更新逻辑"""
    await _validate_avatar_file(file)

    old_setting = await setting_crud.get_setting(db, avatar_key)
    old_file_id = old_setting.value if old_setting else None

    file_service = FileService(db)

    new_file_record = await file_service.save_file(
        file=file,
        management_type=[FileManagementType.GLOBAL_SETTING.value],
        sub_path="avatars"
    )

    await setting_crud.update_setting(
        db,
        schemas.GlobalSetting(key=avatar_key, value=new_file_record.id)
    )

    if old_file_id:
        await file_service.delete_file(old_file_id)

    return file_service.convert_to_schema(new_file_record)


async def _delete_avatar(db: AsyncSession, avatar_key: str):
    """辅助函数，用于处理用户和AI头像的删除逻辑"""
    setting = await setting_crud.get_setting(db, avatar_key)
    if not setting or not setting.value:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Avatar not found.")

    file_id = setting.value
    file_service = FileService(db)

    await file_service.delete_file(file_id)

    await setting_crud.update_setting(db, schemas.GlobalSetting(key=avatar_key, value=None))


@router.put("/settings/avatar/user", response_model=schemas.File, summary="上传用户头像")
async def upload_user_avatar(
        db: AsyncSession = Depends(get_db),
        file: UploadFile = File(...)
):
    return await _update_avatar(db, file, "user_avatar_file_id")


@router.put("/settings/avatar/ai", response_model=schemas.File, summary="上传AI助手头像")
async def upload_ai_avatar(
        db: AsyncSession = Depends(get_db),
        file: UploadFile = File(...)
):
    return await _update_avatar(db, file, "ai_avatar_file_id")


@router.delete("/settings/avatar/user", status_code=status.HTTP_204_NO_CONTENT, summary="删除用户头像")
async def delete_user_avatar(db: AsyncSession = Depends(get_db)):
    await _delete_avatar(db, "user_avatar_file_id")
    return None


@router.delete("/settings/avatar/ai", status_code=status.HTTP_204_NO_CONTENT, summary="删除AI助手头像")
async def delete_ai_avatar(db: AsyncSession = Depends(get_db)):
    await _delete_avatar(db, "ai_avatar_file_id")
    return None


@router.post(
    "/settings/test-proxy",
    response_model=schemas.ConnectionTestResponse,
    summary="测试代理连接"
)
async def test_proxy(
        proxy_url: str = Body(..., embed=True),
        test_url: str = Body(..., embed=True)
):
    """
    通过指定的代理服务器访问一个测试URL，以验证代理的连通性。
    """
    if not proxy_url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Proxy URL cannot be empty.")
    if not test_url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Test URL cannot be empty.")

    return await provider_service.test_proxy_connection(proxy_url, test_url)
