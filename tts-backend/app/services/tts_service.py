import os
import uuid
import time
import logging
import torch
from typing import List, Optional, Union, Dict, Tuple
from concurrent.futures import ThreadPoolExecutor, Future
from TTS.api import TTS  # 确保安装的是 TTS==0.20.0
from pathlib import Path
from TTS.tts.models.xtts import Xtts
from TTS.config import load_config

from TTS import __version__

print(f"=== 实际加载的 TTS 版本: {__version__} ===")  # 关键：确认版本是否为 0.22.0


# ------------------------------
# 1. 自定义异常类（针对性适配 XTTS-V2）
# ------------------------------
class TTSBaseError(Exception):
    """TTS 服务基础异常"""
    pass


class TTSInitializationError(TTSBaseError):
    """XTTS-V2 初始化失败（如模型下载、GPU/ROCM 适配）"""
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
    # 此处用 root logger（调用时自定义 logger 可能未初始化）
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
        "ru": "ru", "russian": "ru",
        "tr": "tr", "turkish": "tr",  # 添加土耳其语支持
        "ja": "ja", "japanese": "ja"   # 添加日语支持
    }
    language = language.strip().lower()
    if language not in supported_langs:
        raise XTTSLanguageError(
            f"XTTS-V2 不支持该语言 | 输入语言: {language} \n"
            f"支持的语言：{list(set(supported_langs.values()))}（建议使用标准化语言码，如 zh-cn）"
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
    - 多语言语音生成（支持 8 种语言）
    - 高质量语音克隆（仅需 3-10 秒参考音频）
    - ROCM/GPU/CPU 自动适配
    - 异步任务处理（线程池）
    """
    _instance: Optional["XTTS2Service"] = None  # 单例实例

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, settings: Optional[Dict] = None):
        """
        初始化 XTTS-V2 服务（单例模式，仅首次调用生效）
        :param settings: 配置字典（支持的配置项见下方说明）
        配置项说明：
        - XTTS_MODEL_NAME: XTTS 模型名（0.20.0 固定为 "tts_models/multilingual/multi-dataset/xtts-v2"）
        - USE_GPU: 是否使用 GPU/ROCM（默认：自动检测 torch.cuda.is_available() 或 torch.backends.rocm.is_available()）
        - TTS_MAX_WORKERS: 线程池最大线程数（默认：4，建议 ≤ CPU 核心数）
        - TTS_MAX_TEXT_LENGTH: 单段文本最大长度（默认：1000 字符）
        - LOG_DIR: 日志目录（默认："./logs/xtts2"）
        - OUTPUT_DIR: 音频输出目录（默认："./output/xtts2"）
        - REFERENCE_VOICE_DIR: 参考音频缓存目录（默认："./data/reference_voices"）
        """
        # 防止重复初始化（单例模式关键：已初始化则直接返回）
        if hasattr(self, "is_initialized"):
            return

        # 1. 初始化配置（补全默认值）
        self.settings = self._init_default_settings(settings)

        # 2. 核心属性初始化
        self.tts: Optional[TTS] = None  # TTS 0.20.0 实例
        self.is_initialized: bool = False  # 服务初始化状态
        self.supported_languages: List[str] = ["en", "zh-cn", "es", "fr", "de", "it", "pt", "ru", "tr", "ja"]  # 扩展支持语言

        # ------------------------------
        # 关键修改1：根据图片中的文件名修正 speaker_voice_map
        # ------------------------------
        self.speaker_voice_map = {
            "zh_cn_0": os.path.join(self.settings["REFERENCE_VOICE_DIR"], "zh-cn-sample.wav"),
            "en_us_0": os.path.join(self.settings["REFERENCE_VOICE_DIR"], "en_sample.wav"),
            "es_0": os.path.join(self.settings["REFERENCE_VOICE_DIR"], "es_sample.wav"),
            "fr_0": os.path.join(self.settings["REFERENCE_VOICE_DIR"], "fr_sample.wav"),
            "de_0": os.path.join(self.settings["REFERENCE_VOICE_DIR"], "de_sample.wav"),
            "pt_0": os.path.join(self.settings["REFERENCE_VOICE_DIR"], "pt_sample.wav"),
            "tr_0": os.path.join(self.settings["REFERENCE_VOICE_DIR"], "tr_sample.wav"),  # 土耳其语
            "ja_0": os.path.join(self.settings["REFERENCE_VOICE_DIR"], "ja-sample.wav")    # 日语
        }

        # 3. 初始化日志（确保目录存在）
        ensure_directory(self.settings["LOG_DIR"])
        self.logger = self._init_logger()

        # 4. 初始化线程池（异步处理语音任务）
        self.executor: ThreadPoolExecutor = self._init_thread_pool()

        # 5. 初始化 XTTS-V2（自动下载模型+处理 PyTorch 安全限制）
        self._init_xtts_service()

        # ------------------------------
        # 关键修改2：初始化时验证所有参考音频是否存在
        # ------------------------------
        self._validate_speaker_voices()

    def _init_default_settings(self, user_settings: Optional[Dict]) -> Dict:
        """初始化默认配置（适配 TTS 0.22.0 设备指定）"""
        # 自动检测设备：优先 GPU（cuda），其次 ROCM（仍用 cuda 接口），最后 CPU
        if torch.cuda.is_available() or torch.backends.rocm.is_available():
            default_device = "cuda:0"  # 默认用第 1 个 GPU/ROCM 设备
        else:
            default_device = "cpu"

        """初始化默认配置（TTS 0.20.0 适配：无 ROCM_DEVICE）"""
        default_settings = {
            # 关键修正：将 xtts-v2（横杠）改为 xtts_v2（下划线）
            "XTTS_MODEL_NAME": "tts_models/multilingual/multi-dataset/xtts_v2",
            "USE_GPU": torch.cuda.is_available() or torch.backends.rocm.is_available(),
            "TTS_MAX_WORKERS": 4,
            "TTS_MAX_TEXT_LENGTH": 1000,
            "LOG_DIR": "./logs/xtts2",
            "OUTPUT_DIR": "./output/xtts2",
            "REFERENCE_VOICE_DIR": "./data/reference_voices"
        }

        # 合并用户配置（用户可指定 device，如 "cuda:1"）
        if isinstance(user_settings, Dict):
            for key, value in user_settings.items():
                if key in default_settings and value is not None:
                    default_settings[key] = value

        ensure_directory(default_settings["REFERENCE_VOICE_DIR"])
        return default_settings

    def _init_logger(self) -> logging.Logger:
        """初始化日志系统（控制台+文件双输出，避免重复添加处理器）"""
        logger = logging.getLogger("XTTS2Service")
        logger.setLevel(logging.INFO)
        logger.propagate = False  # 禁止日志向上传播到 root logger

        # 若已存在处理器，直接返回（避免重复初始化）
        if logger.handlers:
            return logger

        # 1. 控制台日志处理器（实时查看）
        console_handler = logging.StreamHandler()
        console_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        console_handler.setFormatter(console_formatter)

        # 2. 文件日志处理器（持久化记录，含行号）
        log_file = os.path.join(self.settings["LOG_DIR"], "xtts2_service.log")
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s"
        )
        file_handler.setFormatter(file_formatter)

        # 添加处理器并返回
        logger.addHandler(console_handler)
        logger.addHandler(file_handler)
        logger.info(f"日志系统初始化完成 | 日志文件路径: {log_file}")
        return logger

    def _init_thread_pool(self) -> ThreadPoolExecutor:
        """初始化线程池（支持异步任务，子线程继承日志配置）"""
        try:
            executor = ThreadPoolExecutor(
                max_workers=self.settings["TTS_MAX_WORKERS"],
                thread_name_prefix="XTTS2-Worker-",
                initializer=self._thread_init_callback,  # 子线程初始化回调
                initargs=(self.logger,)  # 传递 logger 到子线程
            )
            self.logger.info(f"线程池初始化成功 | 最大线程数: {self.settings['TTS_MAX_WORKERS']}")
            return executor
        except Exception as e:
            self.logger.error(f"线程池初始化失败 | 错误信息: {str(e)}", exc_info=True)
            raise TTSInitializationError(f"线程池初始化失败: {str(e)}") from e

    def _thread_init_callback(self, logger: logging.Logger) -> None:
        """子线程初始化回调：确保子线程日志与主线程一致"""
        local_logger = logging.getLogger("XTTS2-Worker")
        local_logger.setLevel(logging.INFO)
        local_logger.propagate = False
        # 继承主线程的日志处理器（控制台+文件）
        for handler in logger.handlers:
            local_logger.addHandler(handler)

    def _fix_pytorch_weights_only_limit(self) -> None:
        """修复 PyTorch 安全限制（补充 BaseDatasetConfig，适配 TTS 0.20.0 + PyTorch 2.6+）"""
        try:
            # 1. 新增导入：BaseDatasetConfig（解决 weights_only 报错的关键）
            from TTS.config.shared_configs import BaseDatasetConfig
            from TTS.tts.configs.xtts_config import XttsConfig
            from TTS.tts.models.xtts import XttsAudioConfig, XttsArgs

            # 2. 将 BaseDatasetConfig 加入安全类列表
            safe_classes = [
                BaseDatasetConfig,  # 新增：解决 Unsupported global: BaseDatasetConfig 报错
                XttsConfig,
                XttsAudioConfig,
                XttsArgs
            ]
            torch.serialization.add_safe_globals(safe_classes)
            self.logger.debug(
                f"PyTorch 安全类添加成功 | 类列表: {[cls.__name__ for cls in safe_classes]}"
            )
        except ImportError as e:
            self.logger.warning(f"导入 XTTS 安全类失败（非致命）| 错误: {str(e)}")
        except Exception as e:
            self.logger.error(f"处理 PyTorch 安全限制失败 | 错误: {str(e)}", exc_info=True)
            raise TTSInitializationError(f"PyTorch 安全限制处理失败: {str(e)}") from e

    def _init_xtts_service(self) -> None:
        try:
            self._fix_pytorch_weights_only_limit()

            # 关键修改：使用 TTS.api.TTS 封装类（而非直接初始化 Xtts 底层模型）
            model_name = self.settings["XTTS_MODEL_NAME"]  # 即 "tts_models/multilingual/multi-dataset/xtts_v2"
            use_gpu = self.settings["USE_GPU"]
            device = "cuda" if use_gpu else "cpu"
            self.logger.info(
                f"初始化 XTTS-V2 | TTS版本: {__import__('TTS').__version__} | 设备: {device} | 模型名: {model_name}"
            )

            # 正确初始化：使用 TTS.api.TTS 类（该类包含 tts_to_file 方法）
            self.tts = TTS(
                model_name=model_name,
                progress_bar=False,
                gpu=use_gpu  # 自动处理设备分配
            )

            self.is_initialized = True
            self.logger.info("XTTS-V2 初始化成功！核心功能（生成/克隆）已就绪")
        except Exception as e:
            self.logger.critical(f"XTTS-V2 初始化失败 | 错误: {str(e)}", exc_info=True)
            raise TTSInitializationError(f"XTTS-V2 初始化失败: {str(e)}") from e

    # ------------------------------
    # 关键新增方法：验证说话人参考音频是否存在
    # ------------------------------
    def _validate_speaker_voices(self) -> None:
        """初始化时验证所有说话人对应的参考音频是否存在，提前暴露路径问题"""
        missing_files = []
        for speaker_name, voice_path in self.speaker_voice_map.items():
            if not os.path.exists(voice_path):
                missing_files.append(f"说话人[{speaker_name}]: {voice_path}")

        if missing_files:
            error_msg = (
                    "以下说话人的参考音频文件不存在，请检查路径或补充文件：\n" +
                    "\n".join(missing_files) +
                    f"\n参考音频根目录：{self.settings['REFERENCE_VOICE_DIR']}\n"
                    "提示：请将对应音频文件放入上述目录，文件名与映射一致（如 zh-cn-sample.wav）"
            )
            self.logger.error(error_msg)
            raise TTSInitializationError(error_msg)  # 终止初始化，避免后续报错
        self.logger.info("所有说话人参考音频验证通过，可正常使用语音生成功能")

    def get_speakers(self) -> list:
        """根据图片中的文件名修正说话人列表，确保一一对应"""
        try:
            if not self.is_initialized:
                self.logger.warning("服务未初始化，返回默认说话人列表")

            # 根据图片中的文件名生成说话人列表
            default_speakers = [
                {"name": "zh_cn_0", "language": "zh-cn", "desc": "中文女声（默认）", "source": "system"},
                {"name": "en_us_0", "language": "en", "desc": "英语女声（默认）", "source": "system"},
                {"name": "es_0", "language": "es", "desc": "西班牙语（默认）", "source": "system"},
                {"name": "fr_0", "language": "fr", "desc": "法语（默认）", "source": "system"},
                {"name": "de_0", "language": "de", "desc": "德语（默认）", "source": "system"},
                {"name": "pt_0", "language": "pt", "desc": "葡萄牙语（默认）", "source": "system"},
                {"name": "tr_0", "language": "tr", "desc": "土耳其语（默认）", "source": "system"},
                {"name": "ja_0", "language": "ja", "desc": "日语（默认）", "source": "system"}
            ]
            self.logger.info(f"返回默认说话人列表（共 {len(default_speakers)} 个）")
            return default_speakers
        except Exception as e:
            self.logger.error(f"获取说话人列表异常: {str(e)}", exc_info=True)
            return [{"name": "zh_cn_0", "language": "zh-cn", "desc": "中文默认说话人", "source": "fallback"}]

    # ------------------------------
    # 新增：get_models() 方法（解决 AttributeError）
    # ------------------------------
    def get_models(self) -> list:
        """返回 XTTS-V2 支持的模型列表（适配路由 validate_model 依赖的校验逻辑）"""
        try:
            # 从配置中获取支持的模型（当前服务仅加载 XTTS-V2 一个模型，与 settings 保持一致）
            supported_models = [self.settings["XTTS_MODEL_NAME"]]
            self.logger.info(
                f"获取支持的模型列表成功 | 模型数量: {len(supported_models)} | 模型列表: {supported_models}"
            )
            return supported_models
        except Exception as e:
            # 异常时返回默认模型列表，避免服务中断（与配置的默认模型一致）
            self.logger.error(f"获取模型列表异常 | 错误信息: {str(e)}", exc_info=True)
            return ["tts_models/multilingual/multi-dataset/xtts_v2"]

    # ------------------------------
    # 核心功能1：多语言语音生成（异步）
    # ------------------------------
    def generate_speech(self, text: str, language: str = "zh-cn", speaker_wav: Optional[str] = None) -> Future[str]:
        """
        异步生成语音（支持多语言+自定义音色）
        :param text: 待转换文本（长度 ≤ TTS_MAX_TEXT_LENGTH）
        :param language: 语言码（如 "zh-cn" 中文、"en" 英文）
        :param speaker_wav: 参考音频路径（可选，wav/mp3 格式，用于自定义音色）
        :return: Future 对象（结果为音频文件绝对路径）
        """
        try:
            # 输入校验
            self._check_service_status()
            text = self._validate_text(text)
            language = validate_xtts_language(language)
            speaker_wav = self._validate_reference_wav(speaker_wav) if speaker_wav else None

            # 提交异步任务（线程池执行）
            future = self.executor.submit(
                self._generate_speech_sync,
                text=text,
                language=language,
                speaker_wav=speaker_wav
            )

            # 日志记录任务信息
            speaker_info = os.path.basename(speaker_wav) if speaker_wav else "无"
            self.logger.info(
                f"语音生成任务提交成功 | 任务ID: {id(future)} | 语言: {language} | "
                f"文本长度: {len(text)} | 参考音频: {speaker_info}"
            )
            return future
        except Exception as e:
            self.logger.error(f"提交语音生成任务失败 | 错误: {str(e)}", exc_info=True)
            raise TTSServiceError(f"提交任务失败: {str(e)}") from e

    def _generate_speech_sync(self, text: str, language: str, speaker_wav: Optional[str]) -> str:
        """同步生成语音（内部实现，由线程池调用）"""
        try:
            # 生成按日期分类的输出路径
            output_dir = os.path.join(
                self.settings["OUTPUT_DIR"], "generated", language, time.strftime("%Y%m%d")
            )
            ensure_directory(output_dir)

            # 生成唯一文件名（避免冲突）
            file_name = f"xtts2_gen_{language}_{time.strftime('%H%M%S')}_{uuid.uuid4().hex[:8]}.wav"
            output_path = os.path.join(output_dir, file_name)

            # 调用 XTTS-V2 生成语音（TTS 0.20.0 tts_to_file 接口）
            self.logger.info(f"开始生成语音 | 输出路径: {output_path} | 语言: {language}")
            start_time = time.time()

            self.tts.tts_to_file(
                text=text,
                file_path=output_path,
                language=language,
                speaker_wav=speaker_wav,  # 可选：参考音频（自定义音色）
                speed=1.0  # 语速（0.5=慢，1.0=正常，2.0=快）
            )

            # 验证音频生成结果
            self._validate_audio(output_path)

            # 记录生成耗时与大小
            cost_time = round(time.time() - start_time, 2)
            file_size = round(os.path.getsize(output_path) / 1024, 2)  # 转 KB
            self.logger.info(
                f"语音生成成功 | 路径: {output_path} | 耗时: {cost_time}秒 | "
                f"大小: {file_size}KB | 语言: {language}"
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
        异步克隆语音（XTTS-V2 高质量克隆，需 3-10 秒参考音频）
        :param text: 待转换文本
        :param speaker_wav: 参考音频路径（必需，wav/mp3 格式）
        :param language: 生成语音的语言（默认中文 "zh-cn"）
        :return: Future 对象（结果为克隆音频文件路径）
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
                f"语音克隆任务提交成功 | 任务ID: {id(future)} | 参考音频: {os.path.basename(speaker_wav)} | 语言: {language}"
            )
            return future
        except Exception as e:
            self.logger.error(f"提交语音克隆任务失败 | 错误: {str(e)}", exc_info=True)
            raise TTSServiceError(f"提交克隆任务失败: {str(e)}") from e

    def _clone_voice_sync(self, text: str, speaker_wav: str, language: str) -> str:
        """同步克隆语音（内部实现）"""
        try:
            # 生成克隆音频输出路径（单独目录区分）
            output_dir = os.path.join(
                self.settings["OUTPUT_DIR"], "cloned", time.strftime("%Y%m%d")
            )
            ensure_directory(output_dir)

            # 生成唯一文件名
            file_name = f"xtts2_clone_{language}_{time.strftime('%H%M%S')}_{uuid.uuid4().hex[:8]}.wav"
            output_path = os.path.join(output_dir, file_name)

            # 调用 XTTS-V2 克隆语音（temperature 控制音色相似度：0.0=极相似，1.0=灵活）
            self.logger.info(
                f"开始克隆语音 | 参考音频: {os.path.basename(speaker_wav)} | 输出路径: {output_path}"
            )
            start_time = time.time()

            self.tts.tts_to_file(
                text=text,
                file_path=output_path,
                language=language,
                speaker_wav=speaker_wav,
                speed=1.0,
                temperature=0.7  # 平衡相似度与自然度（建议 0.5-0.8）
            )

            # 验证结果
            self._validate_audio(output_path)

            # 日志记录
            cost_time = round(time.time() - start_time, 2)
            file_size = round(os.path.getsize(output_path) / 1024, 2)
            self.logger.info(
                f"语音克隆成功 | 路径: {output_path} | 耗时: {cost_time}秒 | "
                f"大小: {file_size}KB | 参考音频: {os.path.basename(speaker_wav)}"
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
            raise TTSServiceError("XTTS-V2 服务未初始化，无法执行任务（请先创建服务实例）")

    def _validate_text(self, text: str) -> str:
        """验证文本有效性（非空+长度限制）"""
        text = text.strip() if text else ""
        if not text:
            raise ValueError("生成语音的文本不能为空（或仅包含空格）")
        max_len = self.settings["TTS_MAX_TEXT_LENGTH"]
        if len(text) > max_len:
            raise ValueError(
                f"文本长度超过限制 | 当前长度: {len(text)} | 最大限制: {max_len} 字符 \n"
                f"建议：将文本拆分为多个片段（每段 ≤ {max_len} 字符）"
            )
        return text

    def _validate_reference_wav(self, wav_path: str, required: bool = False) -> str:
        """验证参考音频有效性（路径+格式+大小+时长）"""
        # 非必需且为空时直接返回
        if not required and not wav_path:
            return ""

        # 1. 路径存在性
        if not os.path.exists(wav_path):
            raise FileNotFoundError(f"参考音频不存在 | 路径: {wav_path}")

        # 2. 格式校验（仅支持 wav/mp3）
        if not wav_path.lower().endswith((".wav", ".mp3")):
            raise ValueError(f"参考音频格式不支持 | 路径: {wav_path} | 仅支持 wav/mp3")

        # 3. 大小校验（10KB ~ 10MB，避免过小损坏或过大耗时）
        file_size = os.path.getsize(wav_path)
        if file_size < 10 * 1024:  # 10KB
            raise ValueError(f"参考音频过小（可能损坏）| 路径: {wav_path} | 大小: {file_size / 1024:.2f}KB")
        if file_size > 10 * 1024 * 1024:  # 10MB
            raise ValueError(f"参考音频过大 | 路径: {wav_path} | 大小: {file_size / (1024 * 1024):.2f}MB | 建议≤10MB")

        # 4. 时长校验（XTTS-V2 最佳 3-10 秒，需 torchaudio）
        try:
            import torchaudio
            info = torchaudio.info(wav_path)
            duration = info.num_frames / info.sample_rate  # 时长（秒）
            if duration < 3:
                self.logger.warning(
                    f"参考音频时长过短（{duration:.2f}秒）| 克隆效果可能不佳 | 建议 3-10 秒"
                )
            elif duration > 10:
                self.logger.warning(
                    f"参考音频时长过长（{duration:.2f}秒）| 克隆耗时可能增加 | 建议 3-10 秒"
                )
        except ImportError:
            self.logger.warning("未安装 torchaudio，无法检测参考音频时长（建议安装：pip install torchaudio==2.1.0）")
        except Exception as e:
            self.logger.warning(f"检测参考音频时长失败 | 错误: {str(e)} | 路径: {wav_path}")

        return wav_path

    def _validate_audio(self, audio_path: str) -> None:
        """验证生成的音频是否有效（存在+大小）"""
        if not os.path.exists(audio_path):
            raise RuntimeError(f"音频生成失败（文件不存在）| 路径: {audio_path}")
        if os.path.getsize(audio_path) < 100:  # 小于 100 字节视为无效
            raise RuntimeError(f"音频文件异常（体积过小）| 路径: {audio_path} | 大小: {os.path.getsize(audio_path)}字节")

    # ------------------------------
    # 辅助功能：服务信息查询
    # ------------------------------
    def get_service_info(self) -> Dict:
        """获取服务状态信息（用于监控或调试）"""
        return {
            "initialized": self.is_initialized,
            "model_name": self.settings["XTTS_MODEL_NAME"],
            "device_type": "GPU/ROCM" if self.settings["USE_GPU"] else "CPU",
            "supported_languages": self.get_supported_languages(),
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
            "pt": "葡萄牙语", "ru": "俄语", "tr": "土耳其语", "ja": "日语"
        }
        return [(lang, lang_map[lang]) for lang in self.supported_languages]

    # ------------------------------
    # 资源释放（析构函数）
    # ------------------------------
    def __del__(self):
        """安全释放线程池+GPU/ROCM缓存（避免资源泄漏）"""
        # 安全获取 logger（防止实例未初始化时属性不存在）
        logger = self.logger if (hasattr(self, "logger") and self.logger) else logging.getLogger("XTTS2Service")

        # 1. 关闭线程池（等待未完成任务）
        if hasattr(self, "executor"):
            try:
                logger.info("开始释放线程池资源 | 等待未完成任务...")
                self.executor.shutdown(wait=True, cancel_futures=False)
                logger.info("线程池资源释放完成")
            except Exception as e:
                logger.error(f"线程池释放失败 | 错误: {str(e)}", exc_info=True)

        # 2. 清空 GPU/ROCM 缓存（仅当启用 GPU/ROCM 时）
        if hasattr(self, "settings") and self.settings.get("USE_GPU"):
            try:
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                    logger.info("GPU 缓存清空完成")
                elif torch.backends.rocm.is_available():
                    torch.cuda.empty_cache()  # ROCM 兼容 CUDA 接口
                    logger.info("ROCM 缓存清空完成")
            except Exception as e:
                logger.error(f"GPU/ROCM 缓存清空失败 | 错误: {str(e)}", exc_info=True)

        logger.info("XTTS2 服务资源已全部释放")


# ------------------------------
# 4. 全局单例实例创建函数
# ------------------------------
def create_xtts2_service(settings: Optional[Dict] = None) -> XTTS2Service:
    """创建 XTTS-V2 服务实例（单例模式，全局唯一）"""
    if XTTS2Service._instance is None:
        XTTS2Service(settings=settings)
    return XTTS2Service._instance


# ------------------------------
# 自动创建全局实例（应用启动时执行）
# ------------------------------
try:
    # 可根据实际需求修改自定义配置（如线程数、输出目录）
    custom_settings = {
        # "USE_GPU": False,  # 强制使用 CPU（调试时用）
        # "TTS_MAX_WORKERS": 6,  # 根据 CPU 核心数调整（建议 ≤ CPU 核心数）
        # "OUTPUT_DIR": "./data/xtts2_output",  # 自定义音频输出目录
        # "LOG_DIR": "./data/xtts2_logs"  # 自定义日志目录
    }

    # 创建全局服务实例
    tts_service = create_xtts2_service(settings=custom_settings)
    logger = logging.getLogger("XTTS2Service")
    logger.info("XTTS-V2 全局服务实例创建成功！可开始调用语音生成/克隆接口")
except Exception as e:
    # 用自定义 logger 记录异常（避免 root logger 问题）
    error_logger = logging.getLogger("XTTS2Service")
    error_logger.critical(f"XTTS-V2 全局实例创建失败 | 错误: {str(e)}", exc_info=True)
    raise  # 抛出异常，终止应用启动（服务初始化失败需处理）