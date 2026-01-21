# backend/services/kb_service.py

import json
from typing import List, Tuple
from fastapi import UploadFile, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from langchain_openai import OpenAIEmbeddings

from backend import schemas
from backend.crud import kb_crud, resource_crud, file_crud, provider_crud
from backend.models import resource_model  # 导入 ResourceModel 以便手动创建版本
from backend.schemas import kb as kb_schemas
from backend.schemas.enums import FileManagementType, ModelType, ResourceItemType, ResourceType, ProviderWorkerType
from backend.services.storage_service import storage_service

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


class SimpleTextSplitter:
    """
    简单的文本切分器，优先按换行符切分，再按字符数切分。
    """

    def __init__(self, chunk_size: int = 800, chunk_overlap: int = 100):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

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
                # 在 end 附近寻找换行符，避免截断单词
                # 简单起见，这里只向前查找换行符
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


class KnowledgeBaseService:

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

        # 解析元配置获取维度
        meta_config = json.loads(model.meta_config) if model.meta_config else {}
        dimension = meta_config.get("embedding_dimension")

        if not dimension:
            raise ValueError(f"Model {model_id} configuration is missing 'embedding_dimension'.")

        # 检查维度是否在支持的列表中
        supported_dims = [384, 768, 1024, 1536, 2560, 3072, 4096]
        if dimension not in supported_dims:
            raise ValueError(f"Dimension {dimension} is not supported. Supported: {supported_dims}")

        provider = model.provider

        # --- 修正逻辑: 根据 Worker Type 选择客户端 ---

        # 1. OpenAI 和 DeepSeek (兼容 OpenAI 协议)
        if provider.worker_type in [ProviderWorkerType.OPENAI.value, ProviderWorkerType.DEEPSEEK.value]:
            client = OpenAIEmbeddings(
                model=model.modelId,
                api_key=provider.apiKey,
                base_url=provider.apiHost,
                check_embedding_ctx_length=False
            )
            return client, dimension

        # 2. Google (不兼容 OpenAI 协议)
        elif provider.worker_type == ProviderWorkerType.GOOGLE.value:
            # 目前未引入 langchain-google-genai，明确抛出不支持异常
            raise ValueError("Google Embeddings are not currently supported. Please use an OpenAI-compatible provider.")

        # 3. 其他未知类型
        else:
            raise ValueError(f"Unsupported provider worker type for embeddings: {provider.worker_type}")

    async def create_knowledge_base(self, kb_data: kb_schemas.KBCreate) -> schemas.Resource:
        """
        创建知识库资源。
        关键逻辑：
        1. 验证模型是否存在且合法。
        2. 创建 Resource (Folder 类型)。
        3. 【关键修复】手动创建初始 ResourceVersion 并绑定，确保 attributes (模型配置) 被保存。
        """
        # 1. 校验模型并获取维度
        try:
            # 复用 _get_embedding_client 的校验逻辑，但只需要维度
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
            "dimension": dimension
        }

        # 3. 创建 Resource (ItemType='folder', ResourceType='knowledge_base')
        # 注意：resource_crud.create_resource 对于 Folder 类型不会自动创建 Version
        resource_create = schemas.ResourceCreate(
            name=kb_data.name,
            description=kb_data.description,
            itemType=ResourceItemType.FOLDER,  # 使用枚举
            resourceType=ResourceType.KNOWLEDGE_BASE,  # 使用枚举
            parentId=kb_data.parent_id,
            # 这里的 initial_attributes 传给 create_resource 会被忽略，因为是 Folder
            initial_attributes=attributes,
            initial_content=""
        )

        new_resource = await resource_crud.create_resource(self.db, resource_create)

        # 4. 【修复】手动创建初始版本并关联
        # 知识库虽然是 Folder，但必须拥有 Version 来存储 embedding 配置
        initial_version = resource_model.ResourceVersion(
            resourceId=new_resource.id,
            name="初始配置",
            content="",
            attributes=attributes
        )
        self.db.add(initial_version)
        await self.db.flush()

        # 更新 Resource 的 latestVersionId
        new_resource.latestVersionId = initial_version.id
        await self.db.commit()

        # 刷新以加载关联关系
        await self.db.refresh(new_resource)
        await self.db.refresh(new_resource, ['latest_version'])

        return new_resource

    async def ingest_file(self, kb_id: str, file: UploadFile) -> schemas.Resource:
        """
        处理文件上传、切分并入库。
        流程: 校验文件类型 -> 保存物理文件 -> 创建 File 记录 -> 创建 Resource (KB File) -> 切分 -> 批量保存 Chunks。
        """
        # 1. 校验文件类型 (MIME Type 白名单)
        if file.content_type not in SUPPORTED_KB_MIME_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {file.content_type}. Only plain text formats are currently supported."
            )

        # 2. 验证知识库是否存在
        kb_resource = await resource_crud.get_resource(self.db, kb_id)

        # 使用枚举值进行判断 (DB中存储的是字符串)
        if not kb_resource or kb_resource.resourceType != ResourceType.KNOWLEDGE_BASE.value:
            raise HTTPException(status_code=400, detail="Invalid Knowledge Base ID.")

        # 3. 保存物理文件
        try:
            storage_path = await storage_service.save(file, sub_path="kb_documents")
            # 读取内容用于切分
            content_bytes = await storage_service.read_bytes(storage_path)
            try:
                text_content = content_bytes.decode('utf-8')
            except UnicodeDecodeError:
                # 简单回退策略
                text_content = content_bytes.decode('latin-1')
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"File storage failed: {e}")

        # 4. 创建 File 记录
        db_file = await file_crud.create_file(
            self.db,
            filename=file.filename,
            storage_path=storage_path,
            mime_type=file.content_type or "text/plain",
            size=file.size,
            management_type=FileManagementType.GLOBAL_SETTING.value  # 暂用，表示长期存储
        )

        # 5. 创建 Resource (KB File)
        # ResourceVersion.content 存储 file_id
        resource_create = schemas.ResourceCreate(
            name=file.filename,
            itemType=ResourceItemType.RESOURCE,  # 使用枚举
            resourceType=ResourceType.KB_FILE,
            parentId=kb_id,
            initial_content=db_file.id,
            initial_attributes={"source_file_id": db_file.id}
        )
        new_resource = await resource_crud.create_resource(self.db, resource_create)

        # 6. 切分文本
        splitter = SimpleTextSplitter()
        text_chunks = splitter.split_text(text_content)

        # 7. 批量创建 Chunks (事务内)
        chunk_schemas = []
        for idx, chunk_text in enumerate(text_chunks):
            chunk_schemas.append(kb_schemas.KBChunkCreate(
                resource_id=new_resource.id,
                content=chunk_text,
                chunk_index=idx,
                byte_size=len(chunk_text.encode('utf-8'))
            ))

        await kb_crud.batch_create_chunks(self.db, chunk_schemas)

        return new_resource

    async def run_embedding_task(self, resource_id: str):
        """
        执行指定文件的向量化任务。
        1. 查找父知识库获取模型配置。
        2. 获取 PENDING Chunks。
        3. 调用 Embedding API。
        4. 存入向量表并更新业务表。
        """
        # 1. 获取资源及其父节点 (KB)
        resource = await resource_crud.get_resource(self.db, resource_id)
        if not resource or not resource.parentId:
            return

        kb_resource = await resource_crud.get_resource(self.db, resource.parentId)
        if not kb_resource or not kb_resource.latest_version:
            return

        # 2. 解析 KB 配置
        kb_attrs = kb_resource.latest_version.attributes or {}
        embedding_model_id = kb_attrs.get("embedding_model_id")

        if not embedding_model_id:
            # 记录错误或跳过
            print(f"KB {kb_resource.id} missing embedding_model_id configuration.")
            return

        try:
            client, dimension = await self._get_embedding_client(embedding_model_id)
        except ValueError as e:
            print(f"Embedding client init failed: {e}")
            return

        # 3. 获取待处理 Chunks
        pending_chunks = await kb_crud.get_pending_chunks(self.db, resource_id)
        if not pending_chunks:
            return

        # 4. 批量处理 (简单循环，可优化为并发)
        # LangChain 的 embed_documents 支持批量，但为了方便关联 ID，这里分批或逐个处理
        batch_size = 10
        for i in range(0, len(pending_chunks), batch_size):
            batch = pending_chunks[i:i + batch_size]
            texts = [c.content for c in batch]

            try:
                vectors = await client.aembed_documents(texts)

                for chunk, vector in zip(batch, vectors):
                    if len(vector) != dimension:
                        await kb_crud.update_chunk_vector_id_and_status(
                            self.db, chunk.id, None, kb_schemas.KBChunkStatus.FAILED
                        )
                        continue

                    # 写入向量表
                    rowid = await kb_crud.insert_vector(self.db, dimension, vector)

                    # 更新 Chunk 状态
                    await kb_crud.update_chunk_vector_id_and_status(
                        self.db, chunk.id, rowid, kb_schemas.KBChunkStatus.COMPLETED
                    )
            except Exception as e:
                print(f"Embedding batch failed: {e}")
                for chunk in batch:
                    await kb_crud.update_chunk_vector_id_and_status(
                        self.db, chunk.id, None, kb_schemas.KBChunkStatus.FAILED
                    )

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

        # 如果未指定 KB 或 KB 未配置模型，尝试使用全局默认 Embedding 模型 (需 Setting 支持，此处暂略，若无则报错)
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
        # 返回 [(rowid, distance), ...]
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
            chunk = row[0]  # ResourceKBChunk object
            file_id = row[1]
            file_name = row[2]
            kb_id = row[3]
            kb_name = row[4]

            # 过滤掉不在 rowids 中的结果 (理论上 SQL 已经过滤，但为了顺序对应)
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

        # 按分数排序
        items.sort(key=lambda x: x.score)

        return kb_schemas.KBSearchResponse(total=len(items), items=items)
