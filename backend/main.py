# backend/main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from .database import engine, Base
from .routers import chats, providers_models, settings

# 在应用启动时创建数据库表
# 注意：在生产环境中，通常使用 Alembic 等工具进行数据库迁移管理
@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield

app = FastAPI(lifespan=lifespan,version="1.0.1")

# 配置 CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 在生产中应限制为前端应用的源
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 包含各个模块的路由
# 将所有API路由都挂载在 /api 前缀下
app.include_router(chats.router, prefix="/api", tags=["Chats & Messages"])
app.include_router(providers_models.router, prefix="/api", tags=["Providers & Models"])
app.include_router(settings.router, prefix="/api", tags=["Global Settings"])

@app.get("/")
async def root():
    return {"message": "LLM-API Client Backend is running."}

