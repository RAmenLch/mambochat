# backend/services/kb_service.py

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from typing import List, Tuple, Optional, Set
from datetime import datetime

from fastapi import UploadFile, HTTPException
from langchain_openai import OpenAIEmbeddings
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select

from backend import schemas
from backend.crud import kb_crud, resource_crud, file_crud, provider_crud
from backend.models import resource_model, kb_model
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
    "application/x-yaml",
    "application/pdf" # 通常向量化库支持PDF，如果不支持请移除
}
# 注意：如果你的系统依赖纯文本读取，PDF等二进制格式可能需要专门的解析器(如PyPDF2)，
# 这里根据你的 FileExtractor 实现（直接 read_bytes decode），目前仅支持纯文本类型。
# 根据你的代码逻辑 (decode utf-8)，我将严格限制为文本类型。
STRICT_TEXT_MIME_TYPES = {
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/json",
    "text/xml",
    "application/xml",
    "text/yaml",
    "application/x-yaml",
    "application/javascript",
    "text/html"
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


# --- Content Extractors ---

class AbstractContentExtractor(ABC):
    @abstractmethod
    async def extract(self, resource: schemas.ResourceWithVersions, db: AsyncSession) -> str:
        """从资源中提取纯文本内容"""
        pass


class FileExtractor(AbstractContentExtractor):
    """适用于 FILE 和 KB_FILE 类型，从存储系统读取物理文件"""
    async def extract(self, resource: schemas.ResourceWithVersions, db: AsyncSession) -> str:
        if not resource.latest_version or not resource.latest_version.content:
            raise ValueError("Resource content (file_id) is empty.")

        file_id = resource.latest_version.content
        db_file = await file_crud.get_file(db, file_id)
        if not db_file:
            raise ValueError(f"Physical file record not found for ID: {file_id}")

        # --- 新增：类型校验 ---
        # 检查 MIME 类型是否在允许的文本列表中
        if db_file.mime_type not in STRICT_TEXT_MIME_TYPES:
             # 对于 text/plain 等通用类型，有时 mime检测可能不准，但这里严格执行要求
             # 如果是二进制文件（如 image/png, application/zip 等），直接报错
             raise ValueError(f"Unsupported file type for vectorization: {db_file.mime_type}. Only text files are supported.")

        try:
            content_bytes = await storage_service.read_bytes(db_file.storage_path)
            # 尝试解码
            try:
                return content_bytes.decode('utf-8')
            except UnicodeDecodeError:
                return content_bytes.decode('latin-1')
        except Exception as e:
            raise ValueError(f"Failed to read file content: {e}")


class TextExtractor(AbstractContentExtractor):
    """适用于 SYSTEM_PROMPT 和 SUBMESSAGE_TEMPLATE，直接读取版本内容"""
    async def extract(self, resource: schemas.ResourceWithVersions, db: AsyncSession) -> str:
        if not resource.latest_version:
            return ""
        return resource.latest_version.content or ""


class ExtractorFactory:
    @staticmethod
    def get_extractor(resource_type: str) -> AbstractContentExtractor:
        if resource_type in [ResourceType.FILE.value, ResourceType.KB_FILE.value]:
            return FileExtractor()
        elif resource_type in [ResourceType.SYSTEM_PROMPT.value, ResourceType.SUBMESSAGE_TEMPLATE.value]:
            return TextExtractor()
        else:
            # 默认尝试作为文本处理，或者抛出不支持的异常
            raise ValueError(f"Unsupported resource type for extraction: {resource_type}")


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
        1. 资源必须位于 KNOWLEDGE_BASE 类型节点下。
        2. 返回该 KB 节点资源对象。
        """
        if not parent_id:
            raise HTTPException(status_code=400, detail="Parent ID is required for KB resources.")

        # 获取所有祖先节点
        ancestors = await resource_crud.get_batch_resource_ancestors(self.db, [parent_id])

        kb_nodes = [
            res for res in ancestors
            if res.resourceType == ResourceType.KNOWLEDGE_BASE.value
        ]

        if len(kb_nodes) == 0:
            raise HTTPException(status_code=400, detail="Resource must be within a Knowledge Base.")

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


    async def update_kb_file_config(self, resource_id: str,
                                    config_data: kb_schemas.KBUpdateConfigRequest) -> schemas.Resource:
        """
        更新知识库文件的切分配置。
        配置现在存储在 Resource.kb_config 中，所有版本共享。
        """
        resource = await resource_crud.get_resource(self.db, resource_id)
        if not resource:
            raise HTTPException(status_code=404, detail="Resource not found")

        # 更新 Resource 表字段
        resource.kb_config = config_data.splitter_config.model_dump()

        await self.db.commit()
        await self.db.refresh(resource)
        return resource

    async def delete_kb_file(self, resource_id: str) -> schemas.Resource:
        """
        删除 KB 文件资源：先清理向量数据，再删除资源记录。
        """
        resource = await resource_crud.get_resource(self.db, resource_id)
        if not resource:
            raise HTTPException(status_code=404, detail="Resource not found")

        try:
            if resource.parentId:
                kb_resource = await self._validate_kb_hierarchy(resource.parentId)
                if kb_resource and kb_resource.latest_version and kb_resource.latest_version.attributes:
                    dimension = kb_resource.latest_version.attributes.get("dimension")
                    if dimension:
                        await self._cleanup_vectors(resource_id, dimension)
        except Exception:
            pass

        await kb_crud.delete_chunks_by_resource(self.db, resource_id)
        return await resource_crud.delete_resource(self.db, resource_id)

    async def get_comprehensive_file_status(self, resource_id: str) -> kb_schemas.KBProcessingStatus:
        """
        获取文件的综合处理状态，包含过时判定 (Staleness)。
        """
        # 1. 获取数据库统计信息
        stats = await kb_crud.get_chunk_stats_by_resource(self.db, resource_id)

        # 2. 检查内存任务状态
        is_running = resource_id in KnowledgeBaseService._running_tasks

        # 3. 状态修正
        if is_running:
            stats.file_status = KBFileStatus.EMBEDDING
        elif stats.pending_chunks > 0:
            stats.file_status = KBFileStatus.FAILED
            stats.failed_chunks += stats.pending_chunks
            stats.pending_chunks = 0

        # 4. 过时判定 (Staleness Check)
        # 获取资源最新版本时间
        resource = await resource_crud.get_resource(self.db, resource_id)
        if resource and resource.latest_version:
            latest_version_time = resource.latest_version.updatedAt

            # 获取最新的 Chunk 处理时间
            stmt = select(func.max(kb_model.ResourceKBChunk.processed_at)).where(
                kb_model.ResourceKBChunk.resource_id == resource_id
            )
            result = await self.db.execute(stmt)
            max_processed_at = result.scalar()

            # 如果版本更新时间晚于最后一次向量处理时间，标记为过时
            if max_processed_at and latest_version_time > max_processed_at:
                stats.is_stale = True
            elif not max_processed_at and stats.total_chunks == 0:
                # 如果没有处理记录且不是初始状态(通常指有内容但未处理)，也可以视为 stale
                # 但这里保持简单，仅对比时间
                pass

        return stats

    async def _publish_status(self, resource_id: str, status: KBFileStatus,
                              total: int, completed: int, failed: int, stopped: int):
        """
        辅助方法：构建统一的 KBProcessingStatus 并推送。
        """
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
        await stream_manager.publish(resource_id, data.model_dump())

    async def handle_task_action(self, resource_id: str, request: kb_schemas.KBRunTaskRequest):
        """
        处理任务控制动作：Start, Resume, Stop。
        """
        # 1. 停止任务
        if request.action == kb_schemas.KBTaskAction.STOP:
            if resource_id in KnowledgeBaseService._running_tasks:
                await stream_manager.request_cancellation(resource_id)
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

        # 4. 获取切分配置 (从 Resource 层级)
        kb_config_dict = resource.kb_config

        if not kb_config_dict and request.action == kb_schemas.KBTaskAction.START:
            raise HTTPException(status_code=400, detail="Splitter configuration not found.")

        # 获取上次运行的配置快照 (用于 Resume 校验)
        # 注意：last_ingest_config 仍然保存在 Version attributes 中，代表该版本最后一次处理时的配置
        current_attributes = dict(resource.latest_version.attributes) if resource.latest_version.attributes else {}
        last_config_dict = current_attributes.get("last_ingest_config")

        target_splitter_config = None

        # 5. 动作分发
        if request.action == kb_schemas.KBTaskAction.RESUME:
            if not last_config_dict:
                raise HTTPException(status_code=400, detail="No previous task found. Please use START.")

            # 检查配置一致性
            if kb_config_dict != last_config_dict:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": "Configuration mismatch. Cannot resume task.",
                        "current_config": kb_config_dict,
                        "last_ingest_config": last_config_dict
                    }
                )

            target_splitter_config = kb_schemas.KBTextSplitterConfig(**last_config_dict)

            asyncio.create_task(self._run_embedding_loop(
                resource_id, embedding_model_id, dimension, rate_limit,
                resume=True,
                splitter_config=target_splitter_config
            ))

        elif request.action == kb_schemas.KBTaskAction.START:
            # 更新 last_ingest_config 到当前版本
            current_attributes["last_ingest_config"] = kb_config_dict

            await resource_crud.update_resource_version(
                self.db,
                resource.latestVersionId,
                schemas.ResourceVersionUpdate(attributes=current_attributes)
            )

            target_splitter_config = kb_schemas.KBTextSplitterConfig(**kb_config_dict)

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
        """
        KnowledgeBaseService._running_tasks.add(resource_id)

        total_count = 0
        processed_count = 0
        failed_count = 0
        stopped_count = 0

        from backend.database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            try:
                temp_service = KnowledgeBaseService(session)
                try:
                    client, _ = await temp_service._get_embedding_client(model_id)
                except Exception as e:
                    logger.error(f"Model init failed: {e}")
                    await self._publish_status(resource_id, KBFileStatus.FAILED, 0, 0, 0, 0)
                    return

                # --- 阶段 1: 准备数据 (Start 模式需切分) ---
                if not resume:
                    # 1. 获取资源
                    resource = await resource_crud.get_resource_with_versions(session, resource_id)
                    if not resource:
                        raise ValueError("Resource not found.")

                    # 2. 清理旧数据
                    await self._publish_status(resource_id, KBFileStatus.CLEANING, 0, 0, 0, 0)
                    await temp_service._cleanup_vectors(resource_id, dimension)
                    await kb_crud.delete_chunks_by_resource(session, resource_id)

                    # 3. 提取文本 (使用工厂模式)
                    await self._publish_status(resource_id, KBFileStatus.READING, 0, 0, 0, 0)

                    try:
                        extractor = ExtractorFactory.get_extractor(resource.resourceType)
                        text_content = await extractor.extract(resource, session)
                    except Exception as e:
                        logger.error(f"Extraction failed: {e}")
                        raise ValueError(f"Content extraction failed: {e}")

                    # 4. 切分
                    await self._publish_status(resource_id, KBFileStatus.SPLITTING, 0, 0, 0, 0)
                    splitter = SplitterFactory.create(splitter_config)
                    text_chunks = splitter.split_text(text_content)

                    # 5. 存储 Chunks (包含 created_at)
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

                    total_count = len(chunk_schemas)
                else:
                    # Resume 模式
                    stats = await kb_crud.get_chunk_stats_by_resource(session, resource_id)
                    total_count = stats.total_chunks
                    processed_count = stats.completed_chunks
                    failed_count = 0
                    stopped_count = 0

                # --- 阶段 2: 嵌入循环 ---

                target_statuses = [kb_schemas.KBChunkStatus.PENDING.value]
                if resume:
                    target_statuses.append(kb_schemas.KBChunkStatus.FAILED.value)
                    target_statuses.append(kb_schemas.KBChunkStatus.STOPPED.value)

                pending_chunks = await kb_crud.get_chunks_by_statuses(session, resource_id, target_statuses)

                if resume:
                    stats = await kb_crud.get_chunk_stats_by_resource(session, resource_id)
                    total_count = stats.total_chunks
                    processed_count = stats.completed_chunks

                batch_size = 10

                await self._publish_status(resource_id, KBFileStatus.EMBEDDING,
                                           total_count, processed_count, failed_count, stopped_count)

                for i in range(0, len(pending_chunks), batch_size):
                    if await stream_manager.is_cancellation_requested(resource_id):
                        remaining = len(pending_chunks) - i
                        stopped_count += remaining
                        await kb_crud.mark_pending_chunks_as_stopped(session, resource_id)
                        await self._publish_status(resource_id, KBFileStatus.STOPPED,
                                                   total_count, processed_count, failed_count, stopped_count)
                        return

                    batch = pending_chunks[i:i + batch_size]
                    texts = [c.content for c in batch]

                    try:
                        vectors = await client.aembed_documents(texts)

                        current_batch_success = 0
                        current_batch_failed = 0

                        # 记录当前时间作为 processed_at
                        now = datetime.now()

                        for idx, vector in enumerate(vectors):
                            chunk = batch[idx]
                            if len(vector) == dimension:
                                rowid = await kb_crud.insert_vector(session, dimension, vector)

                                # 更新 Chunk 状态和时间
                                chunk.vector_id = rowid
                                chunk.status = kb_schemas.KBChunkStatus.COMPLETED.value
                                chunk.processed_at = now

                                # 显式提交更新 (因为 crud 方法可能只更新部分字段，这里需要更新 processed_at)
                                # 由于 kb_crud.update_chunk_vector_id_and_status 不支持 processed_at
                                # 我们这里直接操作 session 或需要扩展 crud。
                                # 鉴于不能修改 crud，我们直接在 session 中 merge 或 add
                                session.add(chunk)

                                current_batch_success += 1
                            else:
                                chunk.vector_id = None
                                chunk.status = kb_schemas.KBChunkStatus.FAILED.value
                                session.add(chunk)
                                current_batch_failed += 1

                        await session.commit()

                        if len(vectors) < len(batch):
                            diff = len(batch) - len(vectors)
                            current_batch_failed += diff
                            for k in range(len(vectors), len(batch)):
                                chunk = batch[k]
                                chunk.vector_id = None
                                chunk.status = kb_schemas.KBChunkStatus.FAILED.value
                                session.add(chunk)
                            await session.commit()

                        processed_count += current_batch_success
                        failed_count += current_batch_failed

                    except Exception as e:
                        logger.error(f"Embedding batch failed: {e}")
                        for chunk in batch:
                            chunk.vector_id = None
                            chunk.status = kb_schemas.KBChunkStatus.FAILED.value
                            session.add(chunk)
                        await session.commit()
                        failed_count += len(batch)

                    await self._publish_status(resource_id, KBFileStatus.EMBEDDING,
                                               total_count, processed_count, failed_count, stopped_count)

                    if rate_limit > 0:
                        await asyncio.sleep(rate_limit)

                await self._publish_status(resource_id, KBFileStatus.COMPLETED,
                                           total_count, processed_count, failed_count, stopped_count)

            except Exception as e:
                logger.error(f"Task failed for resource {resource_id}: {e}")
                failed_count = total_count - processed_count - stopped_count
                await self._publish_status(resource_id, KBFileStatus.FAILED,
                                           total_count, processed_count, failed_count, stopped_count)
            finally:
                KnowledgeBaseService._running_tasks.discard(resource_id)
                await stream_manager.close_stream(resource_id)

    async def search_kb(self, request: kb_schemas.KBSearchRequest) -> kb_schemas.KBSearchResponse:
        """
        执行向量检索。
        """
        target_kb_id = request.kb_id
        embedding_model_id = None

        if target_kb_id:
            kb_resource = await resource_crud.get_resource(self.db, target_kb_id)
            if kb_resource and kb_resource.latest_version:
                embedding_model_id = (kb_resource.latest_version.attributes or {}).get("embedding_model_id")

        if not embedding_model_id:
            raise HTTPException(status_code=400,
                                detail="Embedding model not determined. Please specify a valid Knowledge Base ID.")

        try:
            client, dimension = await self._get_embedding_client(embedding_model_id)
        except ValueError as e:
            raise HTTPException(status_code=500, detail=str(e))

        try:
            query_vector = await client.aembed_query(request.query_text)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Embedding generation failed: {e}")

        vector_results = await kb_crud.search_vectors(self.db, dimension, query_vector, request.top_k)

        if not vector_results:
            return kb_schemas.KBSearchResponse(total=0, items=[])

        rowids = [r[0] for r in vector_results]
        distance_map = {r[0]: r[1] for r in vector_results}

        rows = await kb_crud.get_chunks_by_vector_ids(self.db, rowids, kb_id_filter=target_kb_id)

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
