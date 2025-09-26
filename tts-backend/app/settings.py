import os
import json
import logging
from typing import List, Optional, Literal, Union
from pydantic import Field, ValidationError, HttpUrl
from pydantic.functional_validators import field_validator
from pydantic_settings import BaseSettings

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [Settings] - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """TTS 服务全局配置类（适配 TTS 0.13.3）"""
    # ========================== 基础应用配置 ==========================
    DEBUG: bool = Field(default=False, description="是否开启调试模式")
    APP_NAME: str = Field(default="Coqui TTS API Service", description="应用名称")
    APP_VERSION: str = Field(default="1.0.0", description="应用版本")
    API_PREFIX: str = Field(default="/api/v1", description="API 统一前缀")
    HOST: str = Field(default="0.0.0.0", description="服务绑定地址")
    PORT: int = Field(default=8000, description="服务监听端口")

    # ========================== 路径配置 ==========================
    ROOT_DIR: str = Field(
        default_factory=lambda: os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
        description="项目根目录（自动计算）"
    )
    LOG_DIR: str = Field(
        default_factory=lambda: os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")), "logs"),
        description="日志目录"
    )
    TEMP_DIR: str = Field(
        default_factory=lambda: os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")), "temp"),
        description="临时文件目录"
    )
    OUTPUT_DIR_TTS: str = Field(
        default_factory=lambda: os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")), "output/tts"),
        description="TTS 生成音频目录"
    )
    OUTPUT_DIR_CLONE: str = Field(
        default_factory=lambda: os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")), "output/clone"),
        description="语音克隆音频目录"
    )

    # ========================== CORS 配置 ==========================
    CORS_ALLOW_ORIGINS: List[Union[str, HttpUrl]] = Field(
        default=["http://localhost:8080", "http://localhost:3000"],
        description="允许跨域的源列表"
    )
    CORS_ALLOW_METHODS: List[str] = Field(
        default=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        description="允许跨域的 HTTP 方法"
    )
    CORS_ALLOW_HEADERS: List[str] = Field(
        default=["Content-Type", "Authorization", "X-Request-ID"],
        description="允许跨域的请求头"
    )
    CORS_ALLOW_CREDENTIALS: bool = Field(default=True, description="是否允许携带 Cookie")

    # ========================== TTS 核心配置（关键修正） ==========================
    # 修正：TTS 0.13.3 支持的中文模型名（无 _ph 后缀）
    DEFAULT_TTS_MODEL: str = Field(
        default="tts_models/multilingual/multi-dataset/xtts_v2",  # 保持模型名格式，TTS 会自动识别本地路径
        description="默认 TTS 模型（XTTS-v2 本地路径）"
    )
    DEFAULT_VOCODER_MODEL: Optional[str] = Field(
        default=None,  # 0.13.3 无需显式指定，模型自带 Vocoder
        description="默认 Vocoder 模型（None 表示使用模型自带）"
    )
    TTS_MAX_WORKERS: int = Field(default=4, ge=1, le=16, description="TTS 线程池最大工作数")
    TTS_MAX_TEXT_LENGTH: int = Field(default=500, ge=100, le=2000, description="文本最大长度限制")
    TTS_AUDIO_FORMAT: Literal["wav", "mp3"] = Field(default="wav", description="生成音频格式")

    # ========================== GPU 配置 ==========================
    USE_GPU: bool = Field(default=True, description="是否启用 GPU 加速")
    GPU_DEVICE_ID: int = Field(default=0, ge=0, description="GPU 设备 ID（多 GPU 环境）")

    # ========================== 安全配置 ==========================
    API_RATE_LIMIT: int = Field(default=60, ge=10, description="每分钟最大请求数")
    UPLOAD_FILE_MAX_SIZE: int = Field(default=10, ge=1, le=50, description="上传文件最大体积（MB）")
    ALLOWED_UPLOAD_EXTENSIONS: List[str] = Field(default=["wav", "mp3"], description="允许上传的格式")

    # ========================== 配置加载规则（移除 deprecated 项） ==========================
    class Config:
        env_prefix = "TTS_"  # 环境变量前缀
        env_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.env"))  # .env 文件路径
        extra = "forbid"  # 禁止未定义字段
        case_sensitive = False  # 环境变量不区分大小写
        # 关键：移除 json_loads = json.loads（pydantic v2 已移除该配置，会报警告）

    # ========================== 自定义验证器 ==========================
    @field_validator("CORS_ALLOW_ORIGINS", mode="before")
    def parse_cors_origins(cls, v):
        if not v:
            return ["http://localhost:8080"]
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v if isinstance(v, list) else ["http://localhost:8080"]

    @field_validator("ALLOWED_UPLOAD_EXTENSIONS")
    def lowercase_extensions(cls, v):
        return [ext.lower() for ext in v]

    # ========================== 动态属性 ==========================
    @property
    def available_gpu(self) -> bool:
        if not self.USE_GPU:
            logger.info("GPU 加速已禁用，使用 CPU 运行")
            return False
        try:
            import torch
            if torch.version.hip:
                # AMD ROCm 环境（日志显示你的环境支持 ROCm）
                gpu_available = torch.cuda.is_available()
                logger.info(f"ROCm GPU 检测结果：{'可用' if gpu_available else '不可用'} | 设备 ID: {self.GPU_DEVICE_ID}")
                return gpu_available
            elif torch.version.cuda:
                # NVIDIA CUDA 环境
                gpu_available = torch.cuda.is_available()
                logger.info(f"CUDA GPU 检测结果：{'可用' if gpu_available else '不可用'} | 设备名: {torch.cuda.get_device_name(self.GPU_DEVICE_ID) if gpu_available else 'N/A'}")
                return gpu_available
            else:
                logger.warning("Torch 未编译 GPU 支持，使用 CPU 运行")
                return False
        except ImportError:
            logger.error("未安装 torch，使用 CPU 运行")
            return False
        except Exception as e:
            logger.error(f"GPU 检测出错，使用 CPU 运行 | 错误: {str(e)}", exc_info=True)
            return False

    @property
    def upload_file_max_size_bytes(self) -> int:
        return self.UPLOAD_FILE_MAX_SIZE * 1024 * 1024

    # ========================== 初始化钩子（创建目录） ==========================
    def __init__(self, **data):
        super().__init__(**data)
        self._create_necessary_dirs()

    def _create_necessary_dirs(self):
        dirs_to_create = [self.LOG_DIR, self.TEMP_DIR, self.OUTPUT_DIR_TTS, self.OUTPUT_DIR_CLONE]
        for dir_path in dirs_to_create:
            try:
                os.makedirs(dir_path, exist_ok=True)
                logger.info(f"目录已创建/存在：{dir_path}")
            except Exception as e:
                logger.error(f"创建目录失败 | 路径: {dir_path} | 错误: {str(e)}", exc_info=True)
                raise Warning(f"目录创建失败，部分功能可能异常：{dir_path}") from e


# ========================== 全局配置实例 ==========================
try:
    settings = Settings()
    logger.info("=" * 50)
    logger.info(f"应用配置加载完成 | 应用名: {settings.APP_NAME} | 版本: {settings.APP_VERSION}")
    logger.info(f"运行模式: {'调试' if settings.DEBUG else '生产'} | API 前缀: {settings.API_PREFIX}")
    logger.info(f"服务地址: {settings.HOST}:{settings.PORT} | GPU 可用: {'是' if settings.available_gpu else '否'}")
    logger.info(f"默认 TTS 模型: {settings.DEFAULT_TTS_MODEL} | 线程池: {settings.TTS_MAX_WORKERS}")
    logger.info("=" * 50)
except ValidationError as e:
    logger.critical(f"配置验证失败，服务无法启动 | 错误: {e}", exc_info=True)
    raise
except Exception as e:
    logger.critical(f"配置加载失败，服务无法启动 | 错误: {e}", exc_info=True)
    raise
