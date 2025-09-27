import logging
from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import JSONResponse
from app.routers import tts, voice_clone
from app.settings import settings
from app.services.tts_service import TTSInitializationError  # 导入自定义异常

app = FastAPI()

app.mount(
    "/output",  # 前端请求的 URL 前缀（必须与音频路径中的 /output 对应）
    StaticFiles(directory="output"),  # 本地音频文件所在的文件夹
    name="output"
)

# ------------------------------
# 1. 日志配置（增强 CORS 相关日志）
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

logging.basicConfig(**logging_config)
logger = logging.getLogger(__name__)

# ------------------------------
# 2. FastAPI 应用初始化（不变）
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


# ------------------------------
# 3. CORS 核心配置（解决头缺失问题）
# ------------------------------
# 3.1 处理 CORS 允许源（禁止通配符与 credentials 冲突）
def get_allowed_origins() -> list:
    # 从配置读取，若无则用默认前端端口（Vue:8080, React:3000）
    if settings.CORS_ALLOW_ORIGINS:
        # 禁止通配符 "*" 与 allow_credentials=True 同时使用（浏览器会拦截）
        if "*" in settings.CORS_ALLOW_ORIGINS and settings.DEBUG is False:
            logger.warning("❌ 生产环境禁止 CORS_ALLOW_ORIGINS 使用通配符，已替换为默认域名")
            return ["http://localhost:8080", "http://localhost:3000"]
        return settings.CORS_ALLOW_ORIGINS
    # 开发环境默认允许常见前端端口
    return ["http://localhost:8080", "http://localhost:3000", "http://127.0.0.1:8080"]


ALLOWED_ORIGINS = get_allowed_origins()
logger.info(f"🌐 最终 CORS 允许源: {ALLOWED_ORIGINS}")

# 3.2 优先添加 CORS 中间件（确保是第一个中间件，避免被覆盖）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080"],  # 前端运行的域名+端口（比如 Vue 本地是 8080）
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],  # 必须包含 GET（加载音频用）和 POST（生成用）
    allow_headers=["*"],
)


# 3.3 新增：全局 HTTP 中间件（强制添加 CORS 头，兜底方案）
# 解决 CORS 中间件失效时的头缺失问题（覆盖所有响应，包括 200/404/500）
@app.middleware("http")
async def force_cors_response_headers(request: Request, call_next):
    response = await call_next(request)

    # 修复：正确匹配请求 Origin
    request_origin = request.headers.get("Origin")  # 获取前端实际请求的 Origin
    if request_origin and request_origin in ALLOWED_ORIGINS:
        # 若请求 Origin 在允许列表内，返回该 Origin（避免浏览器拦截）
        allow_origin = request_origin
    else:
        # 否则返回第一个默认允许源（开发环境通常是 localhost:8080）
        allow_origin = ALLOWED_ORIGINS[0] if ALLOWED_ORIGINS else "*"

    # 强制设置正确的 CORS 头
    response.headers["Access-Control-Allow-Origin"] = allow_origin
    response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With"
    response.headers["Access-Control-Expose-Headers"] = "Content-Length, X-TTS-Request-ID"  # 允许前端读取的头

    # 日志：打印实际的请求 Origin 和返回的 Allow-Origin（便于排查）
    logger.debug(
        f"🔍 CORS 头 | 请求Origin: {request_origin} | 返回AllowOrigin: {allow_origin} | 允许列表: {ALLOWED_ORIGINS}"
    )

    return response


# ------------------------------
# 6. 路由挂载（不变）
# ------------------------------
app.include_router(tts.router, prefix="/api/v1/tts", tags=["语音合成"])
app.include_router(voice_clone.router, prefix="/api/v1/voice-clone", tags=["语音克隆"])

# 3.4 新增：处理 OPTIONS 预检请求（避免浏览器预检失败）
# 针对所有路径的 OPTIONS 请求，直接返回 204 并携带 CORS 头
@app.options("/{full_path:path}")
async def handle_options_request(request: Request) -> Response:
    logger.debug(f"📩 收到 OPTIONS 预检请求 | 路径: {request.url.path}")
    return Response(
        status_code=204,  # 预检成功无响应体
        headers={
            "Access-Control-Allow-Origin": request.headers.get("Origin",
                                                               ALLOWED_ORIGINS[0] if ALLOWED_ORIGINS else "*"),
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Requested-With",
            "Access-Control-Max-Age": "86400"  # 预检结果缓存 24 小时（减少重复预检）
        }
    )


# ------------------------------
# 4. 其他中间件（GZip 压缩，放在 CORS 之后）
# ------------------------------
app.add_middleware(
    GZipMiddleware,
    minimum_size=1000  # 小于 1000 字节不压缩（避免小文件压缩开销）
)


# ------------------------------
# 5. 全局异常处理（不变，增强 CORS 头携带）
# ------------------------------
@app.exception_handler(TTSInitializationError)
async def tts_init_exception_handler(request: Request, exc: TTSInitializationError):
    logger.error(f"TTS服务初始化失败: {str(exc)}", exc_info=True)
    # 异常响应也需携带 CORS 头
    return JSONResponse(
        status_code=500,
        content={"error": "服务初始化失败", "message": str(exc), "code": "TTS_INIT_FAILED"},
        headers={
            "Access-Control-Allow-Origin": request.headers.get("Origin",
                                                               ALLOWED_ORIGINS[0] if ALLOWED_ORIGINS else "*"),
            "Access-Control-Allow-Credentials": "true"
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"未捕获异常: {str(exc)}", exc_info=True)
    # 异常响应也需携带 CORS 头
    return JSONResponse(
        status_code=500,
        content={
            "error": "服务器内部错误",
            "message": str(exc) if settings.DEBUG else "请联系管理员查看详情",
            "code": "INTERNAL_ERROR"
        },
        headers={
            "Access-Control-Allow-Origin": request.headers.get("Origin",
                                                               ALLOWED_ORIGINS[0] if ALLOWED_ORIGINS else "*"),
            "Access-Control-Allow-Credentials": "true"
        }
    )

# ------------------------------
# 7. 系统接口（不变，增强 CORS 头）
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
        },
        headers={
            "Access-Control-Allow-Origin": request.headers.get("Origin",
                                                               ALLOWED_ORIGINS[0] if ALLOWED_ORIGINS else "*"),
            "Access-Control-Allow-Credentials": "true"
        }
    )


@app.get("/health", tags=["系统信息"])
async def health_check(request: Request):
    return JSONResponse(
        content={
            "status": "healthy",
            "components": {
                "tts_service": "initialized" if hasattr(tts,
                                                        "tts_service") and tts.tts_service.is_initialized else "not_ready"
            }
        },
        headers={
            "Access-Control-Allow-Origin": request.headers.get("Origin",
                                                               ALLOWED_ORIGINS[0] if ALLOWED_ORIGINS else "*"),
            "Access-Control-Allow-Credentials": "true"
        }
    )


# ------------------------------
# 8. 生命周期事件（不变）
# ------------------------------
@app.on_event("startup")
async def startup_event():
    logger.info(f"✅ {settings.APP_NAME} v{settings.APP_VERSION} 启动成功")
    logger.info(f"📌 服务地址: http://{settings.HOST}:{settings.PORT}")
    logger.info(f"🌐 CORS允许源: {ALLOWED_ORIGINS}")
    logger.info(f"🔧 调试模式: {'开启' if settings.DEBUG else '关闭'}")
    logger.info(f"⚠️  CORS兜底中间件: 已启用（确保所有响应携带跨域头）")


@app.on_event("shutdown")
async def shutdown_event():
    logger.info(f"🛑 {settings.APP_NAME} 开始关闭")
    # 清理TTS服务资源
    if hasattr(tts, "tts_service"):
        try:
            del tts.tts_service  # 触发__del__方法释放资源
            logger.info("TTS服务资源已释放")
        except Exception as e:
            logger.warning(f"TTS服务资源释放失败: {str(e)}")
    logger.info(f"🛑 {settings.APP_NAME} 已完全关闭")
