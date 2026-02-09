ALTER TABLE "AIProvider" ADD COLUMN "use_proxy" BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE "AIModel" ADD COLUMN meta_config TEXT;
ALTER TABLE "File" ADD COLUMN management_type VARCHAR(50);

-- 1. 为 AIProvider 表新增 worker_type 字段，默认值为 'openai'
ALTER TABLE AIProvider ADD COLUMN worker_type VARCHAR(50) NOT NULL DEFAULT 'openai';

-- 2. 为 AIModel 表新增 type 字段，默认值为 'chat'
ALTER TABLE AIModel ADD COLUMN model_type VARCHAR(50) NOT NULL DEFAULT 'chat';


ALTER TABLE Resource ADD COLUMN kb_id VARCHAR(36);

-- 为 kb_id 创建索引以优化查询
CREATE INDEX ix_Resource_kb_id ON Resource (kb_id);

-- 新增 kb_config 字段，用于存储切分配置 (JSON 序列化存储为 TEXT)
ALTER TABLE Resource ADD COLUMN kb_config TEXT;

-- 2. ResourceKBChunk 表变更
-- 新增 created_at 字段，记录切分创建时间，默认值为当前时间
ALTER TABLE ResourceKBChunk ADD COLUMN created_at DATETIME NOT NULL DEFAULT '1970-01-01 00:00:00';

-- 新增 processed_at 字段，记录向量化完成时间，用于过时判定
ALTER TABLE ResourceKBChunk ADD COLUMN processed_at DATETIME;


-- SQLite 迁移脚本
-- 1. 创建新表
CREATE TABLE File_new (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    storage_path TEXT NOT NULL UNIQUE,
    mime_type TEXT NOT NULL,
    size INTEGER NOT NULL,
    management_type JSON NOT NULL DEFAULT '[]',
    created_at DATETIME NOT NULL
);

-- 2. 复制数据，将字符串转换为 JSON 数组
INSERT INTO File_new (id, filename, storage_path, mime_type, size, management_type, created_at)
SELECT id, filename, storage_path, mime_type, size,
       json_array(management_type) as management_type,
       created_at
FROM File;

-- 3. 删除旧表
DROP TABLE File;

-- 4. 重命名新表
ALTER TABLE File_new RENAME TO File;

ALTER TABLE ResourceKBChunk ADD COLUMN fts_id INTEGER;

-- 2. 为 fts_id 创建索引以提高查询性能
CREATE INDEX IF NOT EXISTS ix_ResourceKBChunk_fts_id ON ResourceKBChunk (fts_id);

ALTER TABLE Chat ADD COLUMN resource_prompt_list TEXT;

ALTER TABLE McpServer ADD COLUMN last_status VARCHAR(50);
ALTER TABLE McpServer ADD COLUMN last_test_at DATETIME;
ALTER TABLE McpServer ADD COLUMN last_error TEXT;
