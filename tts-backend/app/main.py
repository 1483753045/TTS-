import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from app.routers import tts, voice_clone
from app.settings import settings

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 初始化FastAPI应用
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    debug=settings.DEBUG,
    # 禁用默认文档路径，避免生产环境暴露
    docs_url=None if not settings.DEBUG else "/docs",
    redoc_url=None if not settings.DEBUG else "/redoc"
)

# 从配置读取CORS允许源（支持环境变量配置，更灵活）
ALLOWED_ORIGINS = settings.CORS_ALLOW_ORIGINS or ["http://localhost:8080", "http://localhost:3000"]

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载路由
app.include_router(tts.router)
app.include_router(voice_clone.router)

# 根路径接口（增强返回信息）
@app.get("/")
async def root():
    return {
        "message": f"{settings.APP_NAME} 服务正常运行",
        "version": settings.APP_VERSION,
        "docs": "/docs" if settings.DEBUG else "未启用（生产环境）"
    }

# 启动时打印日志
@app.on_event("startup")
async def startup_event():
    logger.info(f"✅ {settings.APP_NAME} v{settings.APP_VERSION} 启动成功")
    logger.info(f"📌 服务地址: http://{settings.HOST}:{settings.PORT}")
    logger.info(f"🌐 CORS允许源: {ALLOWED_ORIGINS}")
