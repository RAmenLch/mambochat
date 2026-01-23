# backend/services/kb_service.py

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from typing import List, Tuple, Optional, Set

from fastapi import UploadFile, HTTPException
from langchain_openai import OpenAIEmbeddings
from sqlalchemy.ext.asyncio import AsyncSession

from backend import schemas
from backend.crud import kb_crud, resource_crud, file_crud, provider_crud
from backend.models import resource_model
from backend.schemas import kb as kb_schemas
from backend.schemas.enums import (
    FileManagementType,
    ModelType,
    ResourceItemType,
    ResourceType,
    ProviderWorkerType,
    KBFileStatus
)
from backend.services.storage_service import storage_service
from backend.services.stream_manager_service import stream_manager

# 定义支持的知识库文件 MIME 类型白名单
SUPPORTED_KB_MIME_TYPES = {
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/json",
    "text/xml",
    "application/xml",
    "text/yaml",
    "application/x-yaml"
}

logger = logging.getLogger(__name__)


# --- Text Splitters ---

class AbstractTextSplitter(ABC):
    def __init__(self, chunk_size: int, chunk_overlap: int):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    @abstractmethod
    def split_text(self, text: str) -> List[str]:
        pass


class SimpleTextSplitter(AbstractTextSplitter):
    """
    简单的文本切分器，优先按换行符切分，再按字符数切分。
    """

    def split_text(self, text: str) -> List[str]:
        if not text:
            return []

        chunks = []
        start = 0
        text_len = len(text)

        while start < text_len:
            end = start + self.chunk_size

            # 如果不是最后一段，尝试寻找最近的换行符作为切分点
            if end < text_len:
                lookback = text.rfind('\n', start, end)
                if lookback != -1 and lookback > start + (self.chunk_size // 2):
                    end = lookback + 1  # 包含换行符

            chunk = text[start:end]
            if chunk.strip():
                chunks.append(chunk)

            # 计算下一次的起始位置，考虑重叠
            start = end - self.chunk_overlap if end < text_len else end

            # 防止死循环（如果 overlap >= size）
            if start >= end:
                start = end

        return chunks


class SepTextSplitter(AbstractTextSplitter):
    """
    基于特定分隔符的切分器。
    如果切分后的段落超过 chunk_size，则回退到 SimpleTextSplitter 进行二次切分。
    """

    def __init__(self, chunk_size: int, chunk_overlap: int, separator: str):
        super().__init__(chunk_size, chunk_overlap)
        self.separator = separator or "\n\n"
        self._fallback_splitter = SimpleTextSplitter(chunk_size, chunk_overlap)

    def split_text(self, text: str) -> List[str]:
        if not text:
            return []

        raw_chunks = text.split(self.separator)
        final_chunks = []

        for raw in raw_chunks:
            if not raw.strip():
                continue

            # 如果单段长度超过限制，使用 fallback 切分
            if len(raw) > self.chunk_size:
                sub_chunks = self._fallback_splitter.split_text(raw)
                final_chunks.extend(sub_chunks)
            else:
                final_chunks.append(raw)

        return final_chunks


class SplitterFactory:
    @staticmethod
    def create(config: kb_schemas.KBTextSplitterConfig) -> AbstractTextSplitter:
        if config.splitter_type == kb_schemas.KBSplitterType.SEPARATOR:
            return SepTextSplitter(
                chunk_size=config.chunk_size,
                chunk_overlap=config.chunk_overlap,
                separator=config.separator
            )
        else:
            return SimpleTextSplitter(
                chunk_size=config.chunk_size,
                chunk_overlap=config.chunk_overlap
            )


# --- Service ---

class KnowledgeBaseService:
    # 类级别集合，用于记录当前正在运行的任务ID (resource_id)，实现简单的互斥锁
    _running_tasks: Set[str] = set()

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_embedding_client(self, model_id: str) -> Tuple[OpenAIEmbeddings, int]:
        """
        根据 model_id 获取配置好的 LangChain Embedding 客户端和维度。
        """
        model = await provider_crud.get_model(self.db, model_id)
        if not model or not model.provider:
            raise ValueError(f"Model {model_id} not found or provider missing.")

        if model.model_type != ModelType.EMBEDDING.value:
            raise ValueError(f"Model {model_id} is not an embedding model.")

        meta_config = json.loads(model.meta_config) if model.meta_config else {}
        dimension = meta_config.get("embedding_dimension")

        if not dimension:
            raise ValueError(f"Model {model_id} configuration is missing 'embedding_dimension'.")

        supported_dims = [384, 768, 1024, 1536, 2560, 3072, 4096]
        if dimension not in supported_dims:
            raise ValueError(f"Dimension {dimension} is not supported. Supported: {supported_dims}")

        provider = model.provider

        if provider.worker_type in [ProviderWorkerType.OPENAI.value, ProviderWorkerType.DEEPSEEK.value]:
            client = OpenAIEmbeddings(
                model=model.modelId,
                api_key=provider.apiKey,
                base_url=provider.apiHost,
                check_embedding_ctx_length=False
            )
            return client, dimension
        elif provider.worker_type == ProviderWorkerType.GOOGLE.value:
            raise ValueError("Google Embeddings are not currently supported. Please use an OpenAI-compatible provider.")
        else:
            raise ValueError(f"Unsupported provider worker type for embeddings: {provider.worker_type}")

    async def _validate_kb_hierarchy(self, parent_id: str) -> schemas.Resource:
        """
        验证层级约束：
        1. KB_FILE 的祖先链中必须有且仅有一个 KNOWLEDGE_BASE 类型节点。
        2. 返回该 KB 节点资源对象。
        """
        if not parent_id:
            raise HTTPException(status_code=400, detail="Parent ID is required for KB files.")

        # 获取所有祖先节点
        ancestors = await resource_crud.get_batch_resource_ancestors(self.db, [parent_id])

        kb_nodes = [
            res for res in ancestors
            if res.resourceType == ResourceType.KNOWLEDGE_BASE.value
        ]

        if len(kb_nodes) == 0:
            raise HTTPException(status_code=400, detail="File must be uploaded within a Knowledge Base.")

        if len(kb_nodes) > 1:
            raise HTTPException(status_code=400, detail="Nested Knowledge Bases are not allowed.")

        return kb_nodes[0]

    async def _cleanup_vectors(self, resource_id: str, dimension: int):
        """清理指定资源在指定维度下的所有向量数据"""
        vector_ids = await kb_crud.get_vector_ids_by_resource(self.db, resource_id)
        if vector_ids:
            await kb_crud.delete_vectors(self.db, dimension, vector_ids)

    async def create_knowledge_base(self, kb_data: kb_schemas.KBCreate) -> schemas.Resource:
        """
        创建知识库资源。
        """
        # 1. 校验模型
        try:
            model = await provider_crud.get_model(self.db, kb_data.embedding_model_id)
            if not model or not model.provider:
                raise ValueError(f"Model {kb_data.embedding_model_id} not found.")

            if model.model_type != ModelType.EMBEDDING.value:
                raise ValueError("Selected model is not an embedding model.")

            meta_config = json.loads(model.meta_config) if model.meta_config else {}
            dimension = meta_config.get("embedding_dimension")

            supported_dims = [384, 768, 1024, 1536, 2560, 3072, 4096]
            if dimension not in supported_dims:
                raise ValueError(f"Model dimension {dimension} is not supported. Supported: {supported_dims}")

        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        # 2. 准备 Attributes
        attributes = {
            "embedding_model_id": kb_data.embedding_model_id,
            "dimension": dimension,
            "embedding_rate_limit": kb_data.embedding_rate_limit
        }

        # 3. 创建 Resource
        resource_create = schemas.ResourceCreate(
            name=kb_data.name,
            description=kb_data.description,
            itemType=ResourceItemType.FOLDER,
            resourceType=ResourceType.KNOWLEDGE_BASE,
            parentId=kb_data.parent_id,
            initial_attributes=attributes,
            initial_content=""
        )

        new_resource = await resource_crud.create_resource(self.db, resource_create)

        # 4. 手动创建初始版本并关联
        initial_version = resource_model.ResourceVersion(
            resourceId=new_resource.id,
            name="初始配置",
            content="",
            attributes=attributes
        )
        self.db.add(initial_version)
        await self.db.flush()

        new_resource.latestVersionId = initial_version.id
        await self.db.commit()
        await self.db.refresh(new_resource)
        await self.db.refresh(new_resource, ['latest_version'])

        return new_resource

    async def upload_file(self, kb_id: str, file: UploadFile) -> schemas.Resource:
        """
        仅上传文件并创建元数据，不执行切分和嵌入。
        """
        # 1. 校验文件类型
        if file.content_type not in SUPPORTED_KB_MIME_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {file.content_type}. Only plain text formats are currently supported."
            )

        # 2. 验证层级约束 (KB_FILE 必须在 KB 内，且不能嵌套)
        # kb_id 可能是 KB 本身，也可能是 KB 下的文件夹
        await self._validate_kb_hierarchy(kb_id)

        # 3. 保存物理文件
        try:
            storage_path = await storage_service.save(file, sub_path="kb_documents")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"File storage failed: {e}")

        # 4. 创建 File 记录
        db_file = await file_crud.create_file(
            self.db,
            filename=file.filename,
            storage_path=storage_path,
            mime_type=file.content_type or "text/plain",
            size=file.size,
            management_type=FileManagementType.GLOBAL_SETTING.value
        )

        # 5. 准备默认切分配置
        default_config = kb_schemas.KBTextSplitterConfig(
            splitter_type=kb_schemas.KBSplitterType.SIMPLE,
            chunk_size=500,
            chunk_overlap=50
        )

        # 6. 创建 Resource (KB File)
        # initial_content 存储 file_id
        # initial_attributes 存储默认配置，不存储 source_file_id
        resource_create = schemas.ResourceCreate(
            name=file.filename,
            itemType=ResourceItemType.RESOURCE,
            resourceType=ResourceType.KB_FILE,
            parentId=kb_id,
            initial_content=db_file.id,
            initial_attributes={
                "splitter_config": default_config.model_dump()
            }
        )
        new_resource = await resource_crud.create_resource(self.db, resource_create)

        return new_resource

    async def update_kb_file_config(self, resource_id: str,
                                    config_data: kb_schemas.KBUpdateConfigRequest) -> schemas.Resource:
        """
        更新知识库文件的切分配置。
        同时清理冗余的 source_file_id 属性。
        """
        resource = await resource_crud.get_resource_with_versions(self.db, resource_id)
        if not resource:
            raise HTTPException(status_code=404, detail="Resource not found")

        if resource.resourceType != ResourceType.KB_FILE.value:
            raise HTTPException(status_code=400, detail="Resource is not a knowledge base file.")

        # 创建副本以确保 SQLAlchemy 检测到变更
        current_attributes = dict(resource.latest_version.attributes) if resource.latest_version.attributes else {}

        # 数据清洗：移除 source_file_id
        if "source_file_id" in current_attributes:
            del current_attributes["source_file_id"]

        # 写入新配置
        current_attributes["splitter_config"] = config_data.splitter_config.model_dump()

        # 持久化更新
        await resource_crud.update_resource_version(
            self.db,
            resource.latestVersionId,
            schemas.ResourceVersionUpdate(attributes=current_attributes)
        )

        await self.db.refresh(resource)
        await self.db.refresh(resource, ['latest_version'])
        return resource

    async def delete_kb_file(self, resource_id: str) -> schemas.Resource:
        """
        删除 KB 文件资源：先清理向量数据，再删除资源记录。
        """
        resource = await resource_crud.get_resource(self.db, resource_id)
        if not resource:
            raise HTTPException(status_code=404, detail="Resource not found")

        # 尝试获取父 KB 以确定维度，以便清理向量
        # 即使找不到父 KB (例如数据不一致)，也应尝试删除资源
        try:
            if resource.parentId:
                kb_resource = await self._validate_kb_hierarchy(resource.parentId)
                if kb_resource and kb_resource.latest_version and kb_resource.latest_version.attributes:
                    dimension = kb_resource.latest_version.attributes.get("dimension")
                    if dimension:
                        await self._cleanup_vectors(resource_id, dimension)
        except Exception:
            # 忽略清理过程中的错误，确保资源能被删除
            pass

        # 删除 Chunks (级联删除可能不彻底，手动清理更安全)
        await kb_crud.delete_chunks_by_resource(self.db, resource_id)

        # 删除资源
        return await resource_crud.delete_resource(self.db, resource_id)

    async def get_comprehensive_file_status(self, resource_id: str) -> kb_schemas.KBProcessingStatus:
        """
        获取文件的综合处理状态。
        结合内存中的任务运行状态和数据库中的切片状态进行判定。
        如果 DB 显示有 Pending 但内存无任务，视为 Failed (僵尸任务)。
        """
        # 1. 获取数据库统计信息
        stats = await kb_crud.get_chunk_stats_by_resource(self.db, resource_id)

        # 2. 检查内存任务状态
        is_running = resource_id in KnowledgeBaseService._running_tasks

        # 3. 状态修正逻辑
        if is_running:
            # 正在运行，强制状态为 EMBEDDING (覆盖数据库可能滞后的状态)
            stats.file_status = KBFileStatus.EMBEDDING
        elif stats.pending_chunks > 0:
            # 未运行，但有 Pending -> 视为异常中断 (Crash/Restart)
            # 将 Pending 归入 Failed，清零 Pending
            stats.file_status = KBFileStatus.FAILED
            stats.failed_chunks += stats.pending_chunks
            stats.pending_chunks = 0

        # 其他情况 (Completed, Stopped, Failed, Initial) 直接使用 DB 统计即可
        return stats

    async def _publish_status(self, resource_id: str, status: KBFileStatus,
                              total: int, completed: int, failed: int, stopped: int):
        """
        辅助方法：构建统一的 KBProcessingStatus 并推送。
        """
        # 计算 pending
        pending = max(0, total - completed - failed - stopped)

        data = kb_schemas.KBProcessingStatus(
            resource_id=resource_id,
            total_chunks=total,
            pending_chunks=pending,
            completed_chunks=completed,
            failed_chunks=failed,
            stopped_chunks=stopped,
            file_status=status
        )
        # 转换为 dict 推送，Router 层会处理序列化
        await stream_manager.publish(resource_id, data.model_dump())

    async def handle_task_action(self, resource_id: str, request: kb_schemas.KBRunTaskRequest):
        """
        处理任务控制动作：Start, Resume, Stop。
        """
        # 1. 停止任务
        if request.action == kb_schemas.KBTaskAction.STOP:
            if resource_id in KnowledgeBaseService._running_tasks:
                await stream_manager.request_cancellation(resource_id)
                # 同步更新数据库状态，将剩余 PENDING 切片标记为 STOPPED
                await kb_crud.mark_pending_chunks_as_stopped(self.db, resource_id)
                return {"message": "Cancellation requested."}
            else:
                return {"message": "Task is not running."}

        # 2. 检查任务是否已在运行
        if resource_id in KnowledgeBaseService._running_tasks:
            raise HTTPException(status_code=409, detail="Task is already running for this file.")

        # 3. 获取资源和父 KB 信息
        resource = await resource_crud.get_resource_with_versions(self.db, resource_id)
        if not resource:
            raise HTTPException(status_code=404, detail="Resource not found")

        kb_resource = await self._validate_kb_hierarchy(resource.parentId)
        kb_attrs = kb_resource.latest_version.attributes or {}
        embedding_model_id = kb_attrs.get("embedding_model_id")
        dimension = kb_attrs.get("dimension")
        rate_limit = kb_attrs.get("embedding_rate_limit", 0.0)

        if not embedding_model_id or not dimension:
            raise HTTPException(status_code=400, detail="Knowledge Base configuration is incomplete.")

        # 4. 准备配置和状态
        # 创建副本以确保 SQLAlchemy 检测到变更
        current_attributes = dict(resource.latest_version.attributes) if resource.latest_version.attributes else {}

        splitter_config_dict = current_attributes.get("splitter_config")
        last_config_dict = current_attributes.get("last_ingest_config")

        # 数据清洗：确保运行时移除冗余字段
        if "source_file_id" in current_attributes:
            del current_attributes["source_file_id"]

        target_splitter_config = None

        # 5. 动作分发
        if request.action == kb_schemas.KBTaskAction.RESUME:
            # Resume 校验
            if not last_config_dict:
                raise HTTPException(status_code=400, detail="No previous task found. Please use START.")

            # 检查配置一致性
            if splitter_config_dict != last_config_dict:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": "Configuration mismatch. Cannot resume task.",
                        "current_config": splitter_config_dict,
                        "last_ingest_config": last_config_dict
                    }
                )

            target_splitter_config = kb_schemas.KBTextSplitterConfig(**last_config_dict)

            # 保存可能发生的清理变更
            await resource_crud.update_resource_version(
                self.db,
                resource.latestVersionId,
                schemas.ResourceVersionUpdate(attributes=current_attributes)
            )

            # 启动后台循环 (Resume 模式)
            asyncio.create_task(self._run_embedding_loop(
                resource_id, embedding_model_id, dimension, rate_limit,
                resume=True,
                splitter_config=target_splitter_config
            ))

        elif request.action == kb_schemas.KBTaskAction.START:
            if not splitter_config_dict:
                raise HTTPException(status_code=400,
                                    detail="Splitter configuration not found. Please save configuration first.")

            # 创建配置快照
            current_attributes["last_ingest_config"] = splitter_config_dict

            # 更新版本属性 (保存快照和清理结果)
            await resource_crud.update_resource_version(
                self.db,
                resource.latestVersionId,
                schemas.ResourceVersionUpdate(attributes=current_attributes)
            )

            target_splitter_config = kb_schemas.KBTextSplitterConfig(**splitter_config_dict)

            # 启动后台循环 (Start 模式)
            asyncio.create_task(self._run_embedding_loop(
                resource_id, embedding_model_id, dimension, rate_limit,
                resume=False,
                splitter_config=target_splitter_config
            ))

        return {"message": "Task started."}

    async def _run_embedding_loop(
            self,
            resource_id: str,
            model_id: str,
            dimension: int,
            rate_limit: float,
            resume: bool,
            splitter_config: kb_schemas.KBTextSplitterConfig
    ):
        """
        核心任务循环：处理切分、嵌入、存储、状态更新和取消。
        此方法在后台任务中运行，需自行管理 DB Session 生命周期。
        """
        # 注册任务
        KnowledgeBaseService._running_tasks.add(resource_id)

        # 本地计数器，避免频繁查询 DB
        total_count = 0
        processed_count = 0
        failed_count = 0
        stopped_count = 0

        # 创建新的 DB Session
        from backend.database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            try:
                # 初始化 Embedding Client
                # 注意：这里需要重新实例化 Service 或直接调用 helper，因为 session 不同
                # 为了简单，直接复用 Service 实例的方法，但传入新的 session
                temp_service = KnowledgeBaseService(session)
                try:
                    client, _ = await temp_service._get_embedding_client(model_id)
                except Exception as e:
                    logger.error(f"Model init failed: {e}")
                    await self._publish_status(resource_id, KBFileStatus.FAILED, 0, 0, 0, 0)
                    return

                # --- 阶段 1: 准备数据 (Start 模式需切分) ---
                if not resume:
                    # 1. 获取文件 ID (从 Resource Content 中)
                    resource = await resource_crud.get_resource_with_versions(session, resource_id)
                    if not resource or not resource.latest_version or not resource.latest_version.content:
                        raise ValueError("Source file information not found in resource.")
                    file_id = resource.latest_version.content

                    # 2. 清理旧数据
                    await self._publish_status(resource_id, KBFileStatus.CLEANING, 0, 0, 0, 0)
                    await temp_service._cleanup_vectors(resource_id, dimension)
                    await kb_crud.delete_chunks_by_resource(session, resource_id)

                    # 3. 读取文件
                    await self._publish_status(resource_id, KBFileStatus.READING, 0, 0, 0, 0)
                    db_file = await file_crud.get_file(session, file_id)
                    if not db_file:
                        raise ValueError("Source file record not found.")

                    content_bytes = await storage_service.read_bytes(db_file.storage_path)
                    try:
                        text_content = content_bytes.decode('utf-8')
                    except UnicodeDecodeError:
                        text_content = content_bytes.decode('latin-1')

                    # 4. 切分
                    await self._publish_status(resource_id, KBFileStatus.SPLITTING, 0, 0, 0, 0)
                    splitter = SplitterFactory.create(splitter_config)
                    text_chunks = splitter.split_text(text_content)

                    # 5. 存储 Chunks
                    chunk_schemas = [
                        kb_schemas.KBChunkCreate(
                            resource_id=resource_id,
                            content=chunk,
                            chunk_index=idx,
                            byte_size=len(chunk.encode('utf-8'))
                        )
                        for idx, chunk in enumerate(text_chunks)
                    ]
                    await kb_crud.batch_create_chunks(session, chunk_schemas)

                    # 初始化计数器
                    total_count = len(chunk_schemas)
                else:
                    # Resume 模式：从 DB 获取当前统计
                    # 注意：Resume 时，failed 和 stopped 会被重新处理，所以在本轮循环开始时，它们视为待处理(Pending)
                    stats = await kb_crud.get_chunk_stats_by_resource(session, resource_id)
                    total_count = stats.total_chunks
                    processed_count = stats.completed_chunks
                    # 本轮开始时，failed 和 stopped 重置为 0，因为它们将变为 pending 重新跑
                    failed_count = 0
                    stopped_count = 0

                # --- 阶段 2: 嵌入循环 ---

                # 获取待处理 Chunks (Resume 模式可能包含 Failed/Stopped)
                target_statuses = [kb_schemas.KBChunkStatus.PENDING.value]
                if resume:
                    target_statuses.append(kb_schemas.KBChunkStatus.FAILED.value)
                    target_statuses.append(kb_schemas.KBChunkStatus.STOPPED.value)

                pending_chunks = await kb_crud.get_chunks_by_statuses(session, resource_id, target_statuses)

                # 如果是 Resume，重新校准 total (防止 DB 数据不一致)
                if resume:
                    stats = await kb_crud.get_chunk_stats_by_resource(session, resource_id)
                    total_count = stats.total_chunks
                    processed_count = stats.completed_chunks

                batch_size = 10

                # 初始推送：EMBEDDING 开始
                await self._publish_status(resource_id, KBFileStatus.EMBEDDING,
                                           total_count, processed_count, failed_count, stopped_count)

                for i in range(0, len(pending_chunks), batch_size):
                    # 检查取消信号
                    if await stream_manager.is_cancellation_requested(resource_id):
                        # 计算剩余未处理的都变成 stopped
                        remaining = len(pending_chunks) - i
                        stopped_count += remaining

                        # 再次确保数据库状态被更新为 STOPPED
                        await kb_crud.mark_pending_chunks_as_stopped(session, resource_id)

                        # 推送 STOPPED 状态
                        await self._publish_status(resource_id, KBFileStatus.STOPPED,
                                                   total_count, processed_count, failed_count, stopped_count)
                        # 直接返回
                        return

                    batch = pending_chunks[i:i + batch_size]
                    texts = [c.content for c in batch]

                    try:
                        # 调用 API
                        vectors = await client.aembed_documents(texts)

                        current_batch_success = 0
                        current_batch_failed = 0

                        for idx, vector in enumerate(vectors):
                            if len(vector) == dimension:
                                # 写入向量表
                                rowid = await kb_crud.insert_vector(session, dimension, vector)
                                # 更新 Chunk 状态
                                await kb_crud.update_chunk_vector_id_and_status(
                                    session, batch[idx].id, rowid, kb_schemas.KBChunkStatus.COMPLETED
                                )
                                current_batch_success += 1
                            else:
                                # 维度不匹配
                                await kb_crud.update_chunk_vector_id_and_status(
                                    session, batch[idx].id, None, kb_schemas.KBChunkStatus.FAILED
                                )
                                current_batch_failed += 1

                        # 处理 API 返回数量少于请求数量的情况（异常）
                        if len(vectors) < len(batch):
                            diff = len(batch) - len(vectors)
                            current_batch_failed += diff
                            for k in range(len(vectors), len(batch)):
                                await kb_crud.update_chunk_vector_id_and_status(
                                    session, batch[k].id, None, kb_schemas.KBChunkStatus.FAILED
                                )

                        processed_count += current_batch_success
                        failed_count += current_batch_failed

                    except Exception as e:
                        logger.error(f"Embedding batch failed: {e}")
                        # 全批次失败
                        for chunk in batch:
                            await kb_crud.update_chunk_vector_id_and_status(
                                session, chunk.id, None, kb_schemas.KBChunkStatus.FAILED
                            )
                        failed_count += len(batch)

                    # 推送进度
                    await self._publish_status(resource_id, KBFileStatus.EMBEDDING,
                                               total_count, processed_count, failed_count, stopped_count)

                    # 频率限制
                    if rate_limit > 0:
                        await asyncio.sleep(rate_limit)

                # 任务结束
                await self._publish_status(resource_id, KBFileStatus.COMPLETED,
                                           total_count, processed_count, failed_count, stopped_count)

            except Exception as e:
                logger.error(f"Task failed for resource {resource_id}: {e}")
                # 简单估算剩余的为 Failed
                failed_count = total_count - processed_count - stopped_count
                await self._publish_status(resource_id, KBFileStatus.FAILED,
                                           total_count, processed_count, failed_count, stopped_count)
            finally:
                # 清理任务注册和取消标记
                KnowledgeBaseService._running_tasks.discard(resource_id)
                await stream_manager.close_stream(resource_id)

    async def search_kb(self, request: kb_schemas.KBSearchRequest) -> kb_schemas.KBSearchResponse:
        """
        执行向量检索。
        """
        # 1. 确定搜索范围和模型
        target_kb_id = request.kb_id
        embedding_model_id = None

        if target_kb_id:
            # 如果指定了 KB，使用该 KB 的模型
            kb_resource = await resource_crud.get_resource(self.db, target_kb_id)
            if kb_resource and kb_resource.latest_version:
                embedding_model_id = (kb_resource.latest_version.attributes or {}).get("embedding_model_id")

        if not embedding_model_id:
            raise HTTPException(status_code=400,
                                detail="Embedding model not determined. Please specify a valid Knowledge Base ID.")

        # 2. 初始化客户端
        try:
            client, dimension = await self._get_embedding_client(embedding_model_id)
        except ValueError as e:
            raise HTTPException(status_code=500, detail=str(e))

        # 3. 生成查询向量
        try:
            query_vector = await client.aembed_query(request.query_text)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Embedding generation failed: {e}")

        # 4. 向量检索
        vector_results = await kb_crud.search_vectors(self.db, dimension, query_vector, request.top_k)

        if not vector_results:
            return kb_schemas.KBSearchResponse(total=0, items=[])

        rowids = [r[0] for r in vector_results]
        distance_map = {r[0]: r[1] for r in vector_results}

        # 5. 反查 Chunk 详情
        rows = await kb_crud.get_chunks_by_vector_ids(self.db, rowids, kb_id_filter=target_kb_id)

        # 6. 格式化结果
        items = []
        for row in rows:
            chunk = row[0]
            file_id = row[1]
            file_name = row[2]
            kb_id = row[3]
            kb_name = row[4]

            if chunk.vector_id not in distance_map:
                continue

            items.append(kb_schemas.KBSearchResultItem(
                chunk_id=chunk.id,
                chunk_content=chunk.content,
                score=distance_map[chunk.vector_id],
                resource_id=file_id,
                resource_name=file_name,
                kb_id=kb_id,
                kb_name=kb_name
            ))

        items.sort(key=lambda x: x.score)

        return kb_schemas.KBSearchResponse(total=len(items), items=items)
