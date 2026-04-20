import sys
import os
import sqlite_vec
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool
from sqlalchemy import event
from sqlalchemy.engine.url import make_url

from alembic import context

# ==========================================
# 1. 路径配置与模型导入
# ==========================================

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from backend.models.base_model import Base
# 确保导入了所有模型
from backend.models import (file_model, chat_model, kb_model, mcp_model,
                            provider_model, resource_model, setting_model,agent_model,log_model,backend_model)

from backend.database import DATABASE_URL

# ==========================================
# 2. Alembic 配置
# ==========================================

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


# ==========================================
# 3. 辅助函数
# ==========================================

def get_sync_url():
    sync_url = DATABASE_URL.replace("+aiosqlite", "")
    return sync_url


def include_object(object, name, type_, reflected, compare_to):
    """
    核心安全过滤器：
    告诉 Alembic 忽略由应用层手动创建的虚拟表和影子表。
    如果返回 False，Alembic 既不会创建它，也不会删除它，完全忽略它。
    """
    # 1. 忽略向量虚拟表 (vec_dim_*)
    if type_ == "table" and name and name.startswith("vec_dim_"):
        return False

    # 2. 忽略全文检索虚拟表及其影子表 (kb_chunk_fts*)
    # FTS5 会创建主表和多个影子表(如 kb_chunk_fts_data, kb_chunk_fts_idx 等)
    # 使用 startswith 匹配前缀是最安全的做法
    if type_ == "table" and name and name.startswith("kb_chunk_fts"):
        return False

    return True


# ==========================================
# 4. 迁移运行逻辑
# ==========================================

def run_migrations_offline() -> None:
    url = get_sync_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        transaction_per_migration=True,
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_sync_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    @event.listens_for(connectable, "connect")
    def load_sqlite_extension(dbapi_connection, connection_record):
        try:
            dbapi_connection.enable_load_extension(True)
            sqlite_vec.load(dbapi_connection)
            dbapi_connection.enable_load_extension(False)
        except Exception as e:
            print(f"Warning: Failed to load sqlite-vec extension for Alembic: {e}")

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            transaction_per_migration=True,
            compare_type=True,
            compare_server_default=True,
            include_object=include_object,  # 应用安全过滤
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
