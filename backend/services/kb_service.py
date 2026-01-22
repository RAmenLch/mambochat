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
from backend.schemas.enums import FileManagementType, ModelType, ResourceItemType, ResourceType, ProviderWorkerType
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

        # 5. 创建 Resource (KB File)
        # 初始状态下没有切分配置，attributes 仅存储 source_file_id
        resource_create = schemas.ResourceCreate(
            name=file.filename,
            itemType=ResourceItemType.RESOURCE,
            resourceType=ResourceType.KB_FILE,
            parentId=kb_id,
            initial_content=db_file.id,
            initial_attributes={"source_file_id": db_file.id}
        )
        new_resource = await resource_crud.create_resource(self.db, resource_create)

        return new_resource

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
        """
        # 1. 获取数据库统计信息
        stats = await kb_crud.get_chunk_stats_by_resource(self.db, resource_id)

        # 2. 检查内存任务状态
        is_running = resource_id in KnowledgeBaseService._running_tasks

        # 3. 综合判定逻辑
        final_status = "INITIAL"

        if is_running:
            # 检查任务存在, 鉴定状态为 processing
            final_status = "PROCESSING"
        elif stats.total_chunks == 0:
            # 检查任务不存在, chunk不存在鉴定状态为 initial
            final_status = "INITIAL"
        elif stats.pending_chunks > 0:
            # 检查任务不存在, chunk存在, 但存在状态 为pending或processing 的chunk, 状态为failed
            # (注: processing 状态在 DB 中体现为 pending，因为只有 completed/failed/stopped 会落库为终态)
            final_status = "FAILED"
        elif stats.stopped_chunks > 0:
            # 检查任务不存在, 但存在chunk的状态为stop的, 则状态为stop
            final_status = "STOPPED"
        elif stats.failed_chunks > 0:
            # 补充逻辑: 如果没有 pending，但有 failed，也视为 failed
            final_status = "FAILED"
        else:
            # 检查任务不存在, 但全部chunk的状态都为completed的, 则状态为completed (INDEXED)
            final_status = "INDEXED"

        stats.file_status = final_status
        return stats

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
        current_attributes = resource.latest_version.attributes or {}
        last_config = current_attributes.get("last_ingest_config")

        # 5. 动作分发
        if request.action == kb_schemas.KBTaskAction.RESUME:
            # Resume 校验
            if not last_config:
                raise HTTPException(status_code=400, detail="No previous task found. Please use START.")

            # 检查配置一致性 (如果有传入新配置，必须与旧配置一致，否则报错)
            if request.splitter_config:
                req_config_dict = request.splitter_config.model_dump()
                # 简单比较字典
                if req_config_dict != last_config:
                    raise HTTPException(status_code=400,
                                        detail="Configuration changed. Cannot resume, please use START (Overwrite).")

            # 启动后台循环 (Resume 模式)
            asyncio.create_task(self._run_embedding_loop(
                resource_id, embedding_model_id, dimension, rate_limit, resume=True
            ))

        elif request.action == kb_schemas.KBTaskAction.START:
            if not request.splitter_config:
                raise HTTPException(status_code=400, detail="Splitter config is required for START action.")

            # 更新 Resource Attributes (保存配置)
            new_config_dict = request.splitter_config.model_dump()
            current_attributes["last_ingest_config"] = new_config_dict

            # 更新版本属性
            await resource_crud.update_resource_version(
                self.db,
                resource.latestVersionId,
                schemas.ResourceVersionUpdate(attributes=current_attributes)
            )

            # 启动后台循环 (Start 模式)
            asyncio.create_task(self._run_embedding_loop(
                resource_id, embedding_model_id, dimension, rate_limit,
                resume=False,
                splitter_config=request.splitter_config,
                file_id=current_attributes.get("source_file_id")
            ))

        return {"message": "Task started."}

    async def _run_embedding_loop(
            self,
            resource_id: str,
            model_id: str,
            dimension: int,
            rate_limit: float,
            resume: bool,
            splitter_config: Optional[kb_schemas.KBTextSplitterConfig] = None,
            file_id: Optional[str] = None
    ):
        """
        核心任务循环：处理切分、嵌入、存储、状态更新和取消。
        此方法在后台任务中运行，需自行管理 DB Session 生命周期。
        """
        # 注册任务
        KnowledgeBaseService._running_tasks.add(resource_id)

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
                    await stream_manager.publish(resource_id, {"status": "error", "message": f"Model init failed: {e}"})
                    return

                # --- 阶段 1: 准备数据 (Start 模式需切分) ---
                if not resume:
                    # 1. 清理旧数据
                    await stream_manager.publish(resource_id, {"status": "cleaning", "message": "Cleaning old data..."})
                    await temp_service._cleanup_vectors(resource_id, dimension)
                    await kb_crud.delete_chunks_by_resource(session, resource_id)

                    # 2. 读取文件
                    await stream_manager.publish(resource_id, {"status": "reading", "message": "Reading file..."})
                    db_file = await file_crud.get_file(session, file_id)
                    if not db_file:
                        raise ValueError("Source file record not found.")

                    content_bytes = await storage_service.read_bytes(db_file.storage_path)
                    try:
                        text_content = content_bytes.decode('utf-8')
                    except UnicodeDecodeError:
                        text_content = content_bytes.decode('latin-1')

                    # 3. 切分
                    await stream_manager.publish(resource_id, {"status": "splitting", "message": "Splitting text..."})
                    splitter = SplitterFactory.create(splitter_config)
                    text_chunks = splitter.split_text(text_content)

                    # 4. 存储 Chunks
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

                # --- 阶段 2: 嵌入循环 ---

                # 获取待处理 Chunks (Resume 模式可能包含 Failed/Stopped)
                target_statuses = [kb_schemas.KBChunkStatus.PENDING.value]
                if resume:
                    target_statuses.append(kb_schemas.KBChunkStatus.FAILED.value)
                    target_statuses.append(kb_schemas.KBChunkStatus.STOPPED.value)

                pending_chunks = await kb_crud.get_chunks_by_statuses(session, resource_id, target_statuses)
                total_count = len(pending_chunks)  # 注意：这只是剩余的，不是总数。前端可通过 status 接口查总数。

                batch_size = 10
                processed_count = 0

                for i in range(0, total_count, batch_size):
                    # 检查取消信号
                    if await stream_manager.is_cancellation_requested(resource_id):
                        # 再次确保数据库状态被更新为 STOPPED
                        await kb_crud.mark_pending_chunks_as_stopped(session, resource_id)
                        await stream_manager.publish(resource_id,
                                                     {"status": "cancelled", "message": "Task cancelled by user."})
                        break

                    batch = pending_chunks[i:i + batch_size]
                    texts = [c.content for c in batch]

                    try:
                        # 调用 API
                        vectors = await client.aembed_documents(texts)

                        for chunk, vector in zip(batch, vectors):
                            if len(vector) != dimension:
                                await kb_crud.update_chunk_vector_id_and_status(
                                    session, chunk.id, None, kb_schemas.KBChunkStatus.FAILED
                                )
                                continue

                            # 写入向量表
                            rowid = await kb_crud.insert_vector(session, dimension, vector)

                            # 更新 Chunk 状态
                            await kb_crud.update_chunk_vector_id_and_status(
                                session, chunk.id, rowid, kb_schemas.KBChunkStatus.COMPLETED
                            )
                    except Exception as e:
                        logger.error(f"Embedding batch failed: {e}")
                        for chunk in batch:
                            await kb_crud.update_chunk_vector_id_and_status(
                                session, chunk.id, None, kb_schemas.KBChunkStatus.FAILED
                            )

                    processed_count += len(batch)

                    # 推送进度
                    await stream_manager.publish(resource_id, {
                        "status": "processing",
                        "processed": processed_count,
                        "batch_total": total_count
                    })

                    # 频率限制
                    if rate_limit > 0:
                        await asyncio.sleep(rate_limit)

                # 任务结束
                await stream_manager.publish(resource_id, {"status": "completed", "message": "Task finished."})

            except Exception as e:
                logger.error(f"Task failed for resource {resource_id}: {e}")
                await stream_manager.publish(resource_id, {"status": "error", "message": str(e)})
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
