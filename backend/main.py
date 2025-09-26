# main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 导入我们的数据库模块和路由模块
from backend import database
from backend.routers import providers_models, chats

# 1. 创建 FastAPI 应用实例
app = FastAPI(
    title="LLM-API Client System",
    description="一个使用 FastAPI 和 Vue 构建的 LLM 客户端系统",
    version="1.0.0",
)

# 2. 配置 CORS (跨源资源共享) 中间件
#    这是至关重要的，因为它允许我们的 Vue 前端 (运行在不同端口) 与后端 API 通信
origins = [
    "http://localhost:5173",  # Vue 开发服务器的默认地址
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有 HTTP 方法
    allow_headers=["*"],  # 允许所有 HTTP 头
)

# 3. 添加应用启动事件处理器
@app.on_event("startup")
async def startup_event():
    """
    应用启动时执行的函数。
    这里我们调用 create_db_and_tables 来确保数据库和表已创建。
    """
    print("应用启动... 正在初始化数据库...")
    await database.create_db_and_tables()
    print("数据库初始化完成。")

# 4. 包含 (注册) 我们的 API 路由
#    使用 prefix="/api" 为所有相关路由添加统一的前缀
#    使用 tags 为 API 文档中的路由进行分组
app.include_router(providers_models.router, prefix="/api", tags=["Providers & Models"])
app.include_router(chats.router, prefix="/api", tags=["Chats & Messages"])


# 5. (可选) 添加一个根路径用于健康检查
@app.get("/", tags=["Root"])
async def read_root():
    return {"message": "欢迎来到 LLM-API 客户端系统后端！请访问 /docs 查看 API 文档。"}

