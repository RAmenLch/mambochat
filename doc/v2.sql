ALTER TABLE "AIProvider" ADD COLUMN "use_proxy" BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE "AIModel" ADD COLUMN meta_config TEXT;
ALTER TABLE "File" ADD COLUMN management_type VARCHAR(50);

-- 1. 为 AIProvider 表新增 worker_type 字段，默认值为 'openai'
ALTER TABLE AIProvider ADD COLUMN worker_type VARCHAR(50) NOT NULL DEFAULT 'openai';

-- 2. 为 AIModel 表新增 type 字段，默认值为 'chat'
ALTER TABLE AIModel ADD COLUMN model_type VARCHAR(50) NOT NULL DEFAULT 'chat';


