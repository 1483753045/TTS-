import os
import uuid
import time
import logging
import torch
from typing import List, Optional, Union, Dict, Tuple
from concurrent.futures import ThreadPoolExecutor, Future
from TTS.api import TTS  # TTS 0.20.0 核心类（直接支持 XTTS-V2）
from pathlib import Path


# ------------------------------
# 1. 自定义异常类（针对性适配 XTTS-V2）
# ------------------------------
class TTSBaseError(Exception):
    """TTS 服务基础异常"""
    pass


class TTSInitializationError(TTSBaseError):
    """XTTS-V2 初始化失败（如模型下载、GPU 适配）"""
    pass


class TTSServiceError(TTSBaseError):
    """TTS 运行时异常（如文本过长、参考音频无效）"""
    pass


class XTTSLanguageError(TTSBaseError):
    """XTTS-V2 语言参数错误（不支持的语言）"""
    pass


# ------------------------------
# 2. 工具函数（适配 XTTS-V2 路径与格式）
# ------------------------------
def ensure_directory(dir_path: str) -> None:
    """确保目录存在（支持多级目录）"""
    if not dir_path:
        raise ValueError("目录路径不能为空")
    Path(dir_path).mkdir(parents=True, exist_ok=True)
    logging.info(f"确保目录存在 | 路径: {dir_path}")


def get_xtts_default_language() -> str:
    """获取 XTTS-V2 默认语言（中文）"""
    return "zh-cn"


def validate_xtts_language(language: str) -> str:
    """验证 XTTS-V2 支持的语言（返回标准化语言码）"""
    # XTTS-V2 支持的语言码（参考 TTS 0.20.0 官方文档）
    supported_langs = {
        "en": "en", "english": "en",
        "zh": "zh-cn", "chinese": "zh-cn", "zh-cn": "zh-cn",
        "es": "es", "spanish": "es",
        "fr": "fr", "french": "fr",
        "de": "de", "german": "de",
        "it": "it", "italian": "it",
        "pt": "pt", "portuguese": "pt",
        "ru": "ru", "russian": "ru"
    }
    language = language.strip().lower()
    if language not in supported_langs:
        raise XTTSLanguageError(
            f"XTTS-V2 不支持该语言 | 输入语言: {language} \n"
            f"支持的语言：{list(supported_langs.values())}（建议使用标准化语言码，如 zh-cn）"
        )
    return supported_langs[language]


# ------------------------------
# 3. XTTS-V2 核心服务类（单例模式）
# ------------------------------
class XTTS2Service:
    """
    TTS 0.20.0 + XTTS-V2 专属服务类
    核心功能：
    - XTTS-V2 模型自动下载与加载
    - 多语言语音生成（支持 10+ 语言）
    - 高质量语音克隆（仅需 3-10 秒参考音频）
    - ROCm/GPU/CPU 自动适配
    - 异步任务处理（线程池）
    """
    _instance: Optional["XTTS2Service"] = None  # 单例实例

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, settings: Optional[Dict] = None):
        """
        初始化 XTTS-V2 服务
        :param settings: 配置字典（支持的配置项见下方说明）
        配置项说明：
        - XTTS_MODEL_NAME: XTTS 模型名（0.20.0 固定为 "tts_models/multilingual/multi-dataset/xtts-v2"）
        - USE_GPU: 是否使用 GPU（默认：自动检测 torch.cuda.is_available()）
        - ROCM_DEVICE: ROCm 设备ID（如 "cuda:0"，默认自动检测）
        - TTS_MAX_WORKERS: 线程池最大线程数（默认：4）
        - TTS_MAX_TEXT_LENGTH: 单段文本最大长度（默认：1000 字符，XTTS-V2 支持更长文本）
        - LOG_DIR: 日志目录（默认："./logs/xtts2"）
        - OUTPUT_DIR: 音频输出目录（默认："./output/xtts2"）
        - REFERENCE_VOICE_DIR: 参考音频缓存目录（默认："./data/reference_voices"）
        """
        # 1. 初始化配置（补全默认值）
        self.settings = self._init_default_settings(settings)

        # 2. 核心属性初始化
        self.tts: Optional[TTS] = None  # TTS 0.20.0 实例（直接支持 XTTS-V2）
        self.is_initialized: bool = False  # 服务初始化状态
        self.supported_languages: List[str] = ["en", "zh-cn", "es", "fr", "de", "it", "pt", "ru"]  # XTTS-V2 支持语言

        # 3. 初始化日志（确保目录存在）
        ensure_directory(self.settings["LOG_DIR"])
        self.logger = self._init_logger()

        # 4. 初始化线程池（异步处理语音任务）
        self.executor: ThreadPoolExecutor = self._init_thread_pool()

        # 5. 初始化 XTTS-V2（自动下载模型+处理 PyTorch 安全限制）
        self._init_xtts_service()

    def _init_default_settings(self, user_settings: Optional[Dict]) -> Dict:
        """初始化默认配置（用户配置覆盖默认值）"""
        default_settings = {
            "XTTS_MODEL_NAME": "tts_models/multilingual/multi-dataset/xtts-v2",  # 0.20.0 XTTS-V2 固定模型名
            "USE_GPU": torch.cuda.is_available() or torch.backends.rocm.is_available(),  # 支持 ROCM/GPU
            "ROCM_DEVICE": "cuda:0" if (torch.cuda.is_available() or torch.backends.rocm.is_available()) else "cpu",
            "TTS_MAX_WORKERS": 4,
            "TTS_MAX_TEXT_LENGTH": 1000,  # XTTS-V2 支持更长文本
            "LOG_DIR": "./logs/xtts2",
            "OUTPUT_DIR": "./output/xtts2",
            "REFERENCE_VOICE_DIR": "./data/reference_voices"
        }

        # 合并用户配置
        if isinstance(user_settings, Dict):
            for key, value in user_settings.items():
                if key in default_settings and value is not None:
                    default_settings[key] = value

        # 确保参考音频目录存在
        ensure_directory(default_settings["REFERENCE_VOICE_DIR"])
        return default_settings

    def _init_logger(self) -> logging.Logger:
        """初始化日志系统（控制台+文件双输出）"""
        logger = logging.getLogger("XTTS2Service")
        logger.setLevel(logging.INFO)
        logger.propagate = False  # 禁止日志向上传播

        # 避免重复添加处理器
        if logger.handlers:
            return logger

        # 1. 控制台处理器
        console_handler = logging.StreamHandler()
        console_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        console_handler.setFormatter(console_formatter)

        # 2. 文件处理器（按日期滚动）
        log_file = os.path.join(self.settings["LOG_DIR"], "xtts2_service.log")
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s"
        )
        file_handler.setFormatter(file_formatter)

        # 添加处理器
        logger.addHandler(console_handler)
        logger.addHandler(file_handler)
        self.logger.info(f"日志系统初始化完成 | 日志文件: {log_file}")
        return logger

    def _init_thread_pool(self) -> ThreadPoolExecutor:
        """初始化线程池（支持异步任务）"""
        try:
            executor = ThreadPoolExecutor(
                max_workers=self.settings["TTS_MAX_WORKERS"],
                thread_name_prefix="XTTS2-Worker-",
                initializer=self._thread_init_callback,
                initargs=(self.logger,)
            )
            self.logger.info(f"线程池初始化成功 | 最大线程数: {self.settings['TTS_MAX_WORKERS']}")
            return executor
        except Exception as e:
            self.logger.error(f"线程池初始化失败 | 错误: {str(e)}", exc_info=True)
            raise TTSInitializationError(f"线程池初始化失败: {str(e)}") from e

    def _thread_init_callback(self, logger: logging.Logger) -> None:
        """线程初始化回调：确保子线程日志生效"""
        local_logger = logging.getLogger("XTTS2-Worker")
        local_logger.setLevel(logging.INFO)
        local_logger.propagate = False
        for handler in logger.handlers:
            local_logger.addHandler(handler)

    def _init_xtts_service(self) -> None:
        """初始化 XTTS-V2 服务（核心步骤）"""
        try:
            # 1. 处理 PyTorch 2.0+ 安全限制（允许 XTTS-V2 自定义类）
            self._fix_pytorch_weights_only_limit()

            # 2. 初始化 XTTS-V2（TTS 0.20.0 简化了模型加载）
            self.logger.info(
                f"开始初始化 XTTS-V2 | 模型名: {self.settings['XTTS_MODEL_NAME']} | 设备: {self.settings['ROCM_DEVICE']}")
            self.tts = TTS(
                model_name=self.settings["XTTS_MODEL_NAME"],
                device=self.settings["ROCM_DEVICE"],  # 支持 ROCM/GPU/CPU
                progress_bar=True,  # 模型下载时显示进度条
                gpu=self.settings["USE_GPU"]  # 兼容旧参数（0.20.0 仍支持）
            )

            # 3. 验证模型加载成功
            if not hasattr(self.tts, "synthesizer") or not self.tts.synthesizer:
                raise RuntimeError("XTTS-V2 合成器初始化失败（synthesizer 为空）")

            self.is_initialized = True
            self.logger.info("XTTS-V2 服务初始化成功，可支持多语言生成与语音克隆")
        except Exception as e:
            self.logger.critical(f"XTTS-V2 初始化失败 | 错误: {str(e)}", exc_info=True)
            raise TTSInitializationError(f"XTTS-V2 初始化失败: {str(e)}") from e

    def _fix_pytorch_weights_only_limit(self) -> None:
        """修复 PyTorch 2.0+ weights_only 限制（XTTS-V2 必需）"""
        try:
            # 导入 XTTS-V2 依赖的自定义类（TTS 0.20.0 路径）
            from TTS.tts.configs.xtts_config import XttsConfig
            from TTS.tts.models.xtts import XttsAudioConfig, XttsModelConfig, XttsArgs

            # 将类添加到 PyTorch 安全全局（避免 UnpicklingError）
            safe_classes = [XttsConfig, XttsAudioConfig, XttsModelConfig, XttsArgs]
            torch.serialization.add_safe_globals(safe_classes)
            self.logger.debug(f"已添加 XTTS-V2 安全类 | 类列表: {[cls.__name__ for cls in safe_classes]}")
        except ImportError as e:
            self.logger.warning(f"导入 XTTS-V2 安全类失败（非致命，0.20.0 可能已修复）| 错误: {str(e)}")
        except Exception as e:
            self.logger.error(f"处理 PyTorch 安全限制失败 | 错误: {str(e)}", exc_info=True)
            raise TTSInitializationError(f"PyTorch 安全限制处理失败: {str(e)}") from e

    # ------------------------------
    # 核心功能1：多语言语音生成（异步）
    # ------------------------------
    def generate_speech(self, text: str, language: str = "zh-cn", speaker_wav: Optional[str] = None) -> Future[str]:
        """
        异步生成语音（支持多语言+自定义音色）
        :param text: 待转换文本（长度≤TTS_MAX_TEXT_LENGTH）
        :param language: 语言码（如 "zh-cn" 中文、"en" 英文，需在 supported_languages 中）
        :param speaker_wav: 参考音频路径（可选，用于自定义音色，支持 wav/mp3）
        :return: Future 对象（结果为音频文件绝对路径）
        """
        try:
            # 输入校验
            self._check_service_status()
            text = self._validate_text(text)
            language = validate_xtts_language(language)
            speaker_wav = self._validate_reference_wav(speaker_wav) if speaker_wav else None

            # 提交异步任务
            future = self.executor.submit(
                self._generate_speech_sync,
                text=text,
                language=language,
                speaker_wav=speaker_wav
            )
            self.logger.info(
                f"已提交语音生成任务 | 任务ID: {id(future)} | 语言: {language} | "
                f"文本长度: {len(text)} | 参考音频: {os.path.basename(speaker_wav) if speaker_wav else '无'}"
            )
            return future
        except Exception as e:
            self.logger.error(f"提交语音生成任务失败 | 错误: {str(e)}", exc_info=True)
            raise TTSServiceError(f"提交任务失败: {str(e)}") from e

    def _generate_speech_sync(self, text: str, language: str, speaker_wav: Optional[str]) -> str:
        """同步生成语音（内部实现）"""
        try:
            # 生成输出路径（按语言+时间戳命名）
            output_dir = os.path.join(self.settings["OUTPUT_DIR"], "generated", language, time.strftime("%Y%m%d"))
            ensure_directory(output_dir)
            file_name = f"xtts2_{language}_{time.strftime('%H%M%S')}_{uuid.uuid4().hex[:8]}.wav"
            output_path = os.path.join(output_dir, file_name)

            # 调用 XTTS-V2 生成语音（TTS 0.20.0 简化了 API）
            self.logger.info(f"开始生成语音 | 输出路径: {output_path} | 语言: {language}")
            start_time = time.time()

            # 核心参数：text（文本）、language（语言）、speaker_wav（参考音频，可选）
            self.tts.tts_to_file(
                text=text,
                file_path=output_path,
                language=language,
                speaker_wav=speaker_wav,
                speed=1.0  # 语速（0.5-2.0，默认1.0）
            )

            # 验证生成结果
            self._validate_audio(output_path)

            # 日志记录
            cost_time = time.time() - start_time
            file_size = os.path.getsize(output_path) / 1024  # KB
            self.logger.info(
                f"语音生成成功 | 路径: {output_path} | 耗时: {cost_time:.2f}秒 | "
                f"大小: {file_size:.2f}KB | 语言: {language}"
            )
            return output_path
        except Exception as e:
            self.logger.error(f"语音生成失败 | 错误: {str(e)}", exc_info=True)
            raise TTSServiceError(f"生成失败: {str(e)}") from e

    # ------------------------------
    # 核心功能2：语音克隆（异步）
    # ------------------------------
    def clone_voice(self, text: str, speaker_wav: str, language: str = "zh-cn") -> Future[str]:
        """
        异步克隆语音（XTTS-V2 高质量克隆，仅需 3-10 秒参考音频）
        :param text: 待转换文本
        :param speaker_wav: 参考音频路径（必需，wav/mp3 格式，时长 3-10 秒最佳）
        :param language: 生成语音的语言（默认中文 "zh-cn"）
        :return: Future 对象（结果为克隆音频路径）
        """
        try:
            # 输入校验（参考音频必需）
            self._check_service_status()
            text = self._validate_text(text)
            language = validate_xtts_language(language)
            speaker_wav = self._validate_reference_wav(speaker_wav, required=True)

            # 提交异步任务
            future = self.executor.submit(
                self._clone_voice_sync,
                text=text,
                speaker_wav=speaker_wav,
                language=language
            )
            self.logger.info(
                f"已提交语音克隆任务 | 任务ID: {id(future)} | 参考音频: {os.path.basename(speaker_wav)} | 语言: {language}"
            )
            return future
        except Exception as e:
            self.logger.error(f"提交语音克隆任务失败 | 错误: {str(e)}", exc_info=True)
            raise TTSServiceError(f"提交克隆任务失败: {str(e)}") from e

    def _clone_voice_sync(self, text: str, speaker_wav: str, language: str) -> str:
        """同步克隆语音（内部实现）"""
        try:
            # 生成输出路径（单独目录区分克隆音频）
            output_dir = os.path.join(self.settings["OUTPUT_DIR"], "cloned", time.strftime("%Y%m%d"))
            ensure_directory(output_dir)
            file_name = f"xtts2_cloned_{language}_{time.strftime('%H%M%S')}_{uuid.uuid4().hex[:8]}.wav"
            output_path = os.path.join(output_dir, file_name)

            # 调用 XTTS-V2 克隆语音（核心：speaker_wav 参考音频）
            self.logger.info(f"开始克隆语音 | 参考音频: {os.path.basename(speaker_wav)} | 输出路径: {output_path}")
            start_time = time.time()

            self.tts.tts_to_file(
                text=text,
                file_path=output_path,
                language=language,
                speaker_wav=speaker_wav,
                speed=1.0,
                # XTTS-V2 克隆增强参数（可选）
                temperature=0.7  # 音色相似度（0.0-1.0，值越小越接近参考音频）
            )

            # 验证结果
            self._validate_audio(output_path)

            # 日志记录
            cost_time = time.time() - start_time
            file_size = os.path.getsize(output_path) / 1024
            self.logger.info(
                f"语音克隆成功 | 路径: {output_path} | 耗时: {cost_time:.2f}秒 | "
                f"大小: {file_size:.2f}KB | 参考音频: {os.path.basename(speaker_wav)}"
            )
            return output_path
        except Exception as e:
            self.logger.error(f"语音克隆失败 | 错误: {str(e)}", exc_info=True)
            raise TTSServiceError(f"克隆失败: {str(e)}") from e

    # ------------------------------
    # 辅助功能：输入校验
    # ------------------------------
    def _check_service_status(self) -> None:
        """检查服务是否已初始化"""
        if not self.is_initialized or not self.tts:
            raise TTSServiceError("XTTS-V2 服务未初始化，无法执行任务")

    def _validate_text(self, text: str) -> str:
        """验证文本有效性（非空+长度限制）"""
        text = text.strip() if text else ""
        if not text:
            raise ValueError("生成语音的文本不能为空（或仅包含空格）")
        max_len = self.settings["TTS_MAX_TEXT_LENGTH"]
        if len(text) > max_len:
            raise ValueError(
                f"文本长度超过限制 | 当前长度: {len(text)} | 最大限制: {max_len} 字符 \n"
                f"建议：将文本拆分为多个片段（每段≤{max_len}字符）"
            )
        return text

    def _validate_reference_wav(self, wav_path: str, required: bool = False) -> str:
        """验证参考音频有效性（XTTS-V2 克隆必需）"""
        # 非必需且为空时直接返回
        if not required and not wav_path:
            return ""

        # 路径存在性校验
        if not os.path.exists(wav_path):
            raise FileNotFoundError(f"参考音频不存在 | 路径: {wav_path}")

        # 格式校验（XTTS-V2 支持 wav/mp3）
        if not wav_path.endswith((".wav", ".mp3")):
            raise ValueError(f"参考音频格式不支持 | 路径: {wav_path} | 仅支持 wav/mp3")

        # 大小校验（避免过小/损坏文件，最小 10KB，最大 10MB）
        file_size = os.path.getsize(wav_path)
        if file_size < 10 * 1024:  # 10KB
            raise ValueError(f"参考音频过小（可能损坏）| 路径: {wav_path} | 大小: {file_size / 1024:.2f}KB")
        if file_size > 10 * 1024 * 1024:  # 10MB
            raise ValueError(f"参考音频过大 | 路径: {wav_path} | 大小: {file_size / (1024 * 1024):.2f}MB | 建议≤10MB")

        # 时长校验（XTTS-V2 最佳参考时长 3-10 秒，需 torchaudio 辅助）
        try:
            import torchaudio
            info = torchaudio.info(wav_path)
            duration = info.num_frames / info.sample_rate
            if duration < 3:
                self.logger.warning(
                    f"参考音频时长过短（<3秒），克隆效果可能不佳 | 路径: {wav_path} | 时长: {duration:.2f}秒")
            elif duration > 10:
                self.logger.warning(
                    f"参考音频时长过长（>10秒），可能增加克隆耗时 | 路径: {wav_path} | 时长: {duration:.2f}秒")
        except Exception as e:
            self.logger.warning(f"无法检测参考音频时长 | 错误: {str(e)} | 路径: {wav_path}")

        return wav_path

    def _validate_audio(self, audio_path: str) -> None:
        """验证生成的音频有效性"""
        if not os.path.exists(audio_path):
            raise RuntimeError(f"音频生成失败（文件不存在）| 路径: {audio_path}")
        if os.path.getsize(audio_path) < 100:  # 小于 100 字节视为无效
            raise RuntimeError(f"音频文件异常（体积过小）| 路径: {audio_path} | 大小: {os.path.getsize(audio_path)}字节")

    # ------------------------------
    # 辅助功能：服务信息查询
    # ------------------------------
    def get_service_info(self) -> Dict:
        """获取服务状态信息（用于监控）"""
        return {
            "initialized": self.is_initialized,
            "model_name": self.settings["XTTS_MODEL_NAME"],
            "device": self.settings["ROCM_DEVICE"],
            "supported_languages": self.supported_languages,
            "max_workers": self.settings["TTS_MAX_WORKERS"],
            "max_text_length": self.settings["TTS_MAX_TEXT_LENGTH"],
            "output_dir": self.settings["OUTPUT_DIR"],
            "current_time": time.strftime("%Y-%m-%d %H:%M:%S")
        }

    def get_supported_languages(self) -> List[Tuple[str, str]]:
        """获取支持的语言列表（含中文说明）"""
        lang_map = {
            "en": "英语", "zh-cn": "中文（简体）", "es": "西班牙语",
            "fr": "法语", "de": "德语", "it": "意大利语",
            "pt": "葡萄牙语", "ru": "俄语"
        }
        return [(lang, lang_map.get(lang, lang)) for lang in self.supported_languages]

    # ------------------------------
    # 资源释放（析构函数）
    # ------------------------------
    def __del__(self):
        """释放线程池+GPU缓存"""
        # 1. 关闭线程池
        if hasattr(self, "executor"):
            self.logger.info("关闭 XTTS2 线程池 | 等待未完成任务...")
            self.executor.shutdown(wait=True, cancel_futures=False)
            self.logger.info("XTTS2 线程池已关闭")

        # 2. 清空 GPU/ROCM 缓存
        if self.settings["USE_GPU"]:
            torch.cuda.empty_cache() if torch.cuda.is_available() else None
            self.logger.info("已清空 GPU/ROCM 缓存")

        self.logger.info("XTTS2 服务已销毁，所有资源已释放")


# ------------------------------
# 4. 全局 XTTS-V2 服务实例（单例）
# ------------------------------
def create_xtts2_service(settings: Optional[Dict] = None) -> XTTS2Service:
    """创建 XTTS-V2 服务实例（单例模式）"""
    if XTTS2Service._instance is None:
        XTTS2Service(settings=settings)
    return XTTS2Service._instance


# 自动创建全局实例（应用启动时执行）
try:
    # 可根据实际需求修改配置（如 ROCM 设备、输出目录）
    custom_settings = {
        # "ROCM_DEVICE": "cuda:1",  # 若有多个 GPU/ROCM 设备，指定设备ID
        # "OUTPUT_DIR": "./data/xtts2_output",  # 自定义音频输出目录
        # "TTS_MAX_WORKERS": 6  # 增加线程数（根据 CPU 核心数调整）
    }
    xtts2_service = create_xtts2_service(settings=custom_settings)
except Exception as e:
    logging.critical(f"XTTS-V2 全局实例创建失败 | 错误: {str(e)}", exc_info=True)
    raise
