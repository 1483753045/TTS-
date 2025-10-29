import logging
from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from app.routers import tts, voice_clone
from app.settings import settings
from app.services.tts_service import TTSInitializationError  # 导入自定义异常

# ------------------------------
# 1. 应用初始化（只创建一次，合并配置）
# ------------------------------
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="XTTS-V2语音合成与克隆服务API接口",
    debug=settings.DEBUG,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
    contact={"name": "技术支持", "email": "support@example.com"},
    license_info={"name": "MIT License", "url": "https://opensource.org/licenses/MIT"}
)

# 挂载静态文件（音频输出目录）
app.mount(
    "/output",  # 前端通过 /output/xxx.wav 访问
    StaticFiles(directory="output"),  # 对应本地 output 文件夹
    name="output"
)

# ------------------------------
# 2. 日志配置
# ------------------------------
logging_config = {
    "level": logging.DEBUG if settings.DEBUG else logging.INFO,
    "format": "%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s",
    "handlers": [logging.StreamHandler()]  # 控制台输出
}

# 生产环境添加文件日志（含轮转）
if not settings.DEBUG:
    from logging.handlers import RotatingFileHandler
    file_handler = RotatingFileHandler(
        "logs/app.log",
        maxBytes=1024 * 1024 * 5,  # 5MB 轮转
        backupCount=5,
        encoding="utf-8"
    )
    logging_config["handlers"].append(file_handler)

logging.basicConfig(** logging_config)
logger = logging.getLogger(__name__)
logger.info(f"📝 日志配置完成 | 级别: {'DEBUG' if settings.DEBUG else 'INFO'} | "
            f"输出: {'控制台+文件' if not settings.DEBUG else '控制台'}")

# ------------------------------
# 3. CORS 配置（简化，避免冲突）
# ------------------------------
def get_allowed_origins() -> list:
    if settings.CORS_ALLOW_ORIGINS:
        # 生产环境禁止通配符 "*" 与 allow_credentials=True 同时使用
        if "*" in settings.CORS_ALLOW_ORIGINS and not settings.DEBUG:
            logger.warning("❌ 生产环境禁止 CORS_ALLOW_ORIGINS 使用通配符，已替换为默认域名")
            return ["http://localhost:8080", "http://localhost:3000"]
        return settings.CORS_ALLOW_ORIGINS
    # 开发环境默认允许常见前端端口
    return ["http://localhost:8080", "http://localhost:3000", "http://127.0.0.1:8080"]

ALLOWED_ORIGINS = get_allowed_origins()
logger.info(f"🌐 CORS 允许源: {ALLOWED_ORIGINS}")

# 添加 CORS 中间件（优先于其他中间件）
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# ------------------------------
# 4. OPTIONS 预检请求处理
# ------------------------------
@app.options("/{full_path:path}")
async def handle_options_request(request: Request) -> Response:
    logger.debug(f"📩 收到 OPTIONS 预检请求 | 路径: {request.url.path}")
    origin = request.headers.get("Origin", "")
    allow_origin = origin if origin in ALLOWED_ORIGINS else ALLOWED_ORIGINS[0] if ALLOWED_ORIGINS else "*"
    return Response(
        status_code=204,
        headers={
            "Access-Control-Allow-Origin": allow_origin,
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Requested-With",
            "Access-Control-Max-Age": "86400"
        }
    )

# ------------------------------
# 5. 其他中间件（GZip 压缩）
# ------------------------------
app.add_middleware(
    GZipMiddleware,
    minimum_size=1000  # 小于1000字节不压缩
)

# ------------------------------
# 6. 路由挂载（去掉重复前缀）
# ------------------------------
app.include_router(tts.router, tags=["语音合成"])  # tts.router 已包含 /api/v1/tts 前缀
app.include_router(voice_clone.router, tags=["语音克隆"])  # 同理，路由内部已定义前缀

# ------------------------------
# 7. 全局异常处理
# ------------------------------
@app.exception_handler(TTSInitializationError)
async def tts_init_exception_handler(request: Request, exc: TTSInitializationError):
    logger.error(f"TTS服务初始化失败: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "服务初始化失败", "message": str(exc), "code": "TTS_INIT_FAILED"},
        headers={"Access-Control-Allow-Origin": request.headers.get("Origin", ALLOWED_ORIGINS[0] if ALLOWED_ORIGINS else "*")}
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"未捕获异常: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "服务器内部错误",
            "message": str(exc) if settings.DEBUG else "请联系管理员查看详情",
            "code": "INTERNAL_ERROR"
        },
        headers={"Access-Control-Allow-Origin": request.headers.get("Origin", ALLOWED_ORIGINS[0] if ALLOWED_ORIGINS else "*")}
    )

# ------------------------------
# 8. 系统接口
# ------------------------------
@app.get("/", tags=["系统信息"])
async def root(request: Request):
    return JSONResponse(
        content={
            "service": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "status": "running",
            "timestamp": logging.Formatter("%Y-%m-%d %H:%M:%S").formatTime(logging.LogRecord("", 0, "", 0, "", "", 0)),
            "debug": settings.DEBUG,
            "docs": "/docs" if settings.DEBUG else None
        }
    )

@app.get("/health", tags=["系统信息"])
async def health_check(request: Request):
    return JSONResponse(
        content={
            "status": "healthy",
            "components": {
                "tts_service": "initialized" if hasattr(tts, "tts_service") and tts.tts_service.is_initialized else "not_ready"
            }
        }
    )

# ------------------------------
# 9. 生命周期事件
# ------------------------------
@app.on_event("startup")
async def startup_event():
    logger.info(f"✅ {settings.APP_NAME} v{settings.APP_VERSION} 启动成功")
    logger.info(f"📌 服务地址: http://{settings.HOST}:{settings.PORT}")
    logger.info(f"🌐 CORS允许源: {ALLOWED_ORIGINS}")
    logger.info(f"🔧 调试模式: {'开启' if settings.DEBUG else '关闭'}")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info(f"🛑 {settings.APP_NAME} 开始关闭")
    # 清理TTS服务资源
    if hasattr(tts, "tts_service"):
        try:
            del tts.tts_service  # 释放资源
            logger.info("TTS服务资源已释放")
        except Exception as e:
            logger.warning(f"TTS服务资源释放失败: {str(e)}")
    logger.info(f"🛑 {settings.APP_NAME} 已完全关闭")