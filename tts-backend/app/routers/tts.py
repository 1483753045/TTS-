import asyncio
import logging
import os
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import FileResponse  # 用于返回音频文件
from fastapi.middleware.cors import CORSMiddleware  # 跨域中间件
from app.services.tts_service import tts_service
from app.models.tts import TTSRequest
from app.utils.file_utils import get_relative_path

router = APIRouter()
logger = logging.getLogger(__name__)

# -------------------------- 1. 全局跨域配置（关键：解决前端跨域+方法限制） --------------------------
# 注意：此配置需在 FastAPI 应用实例创建后添加（如 main.py 中），此处仅展示配置逻辑
def add_cors_middleware(app):
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:8080"],  # 前端域名（必改：匹配你的前端实际地址）
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],  # 允许前端使用的HTTP方法
        allow_headers=["*"],  # 允许的请求头
    )

# -------------------------- 2. 新增：音频文件获取接口（解决405核心） --------------------------
def validate_audio_path(file_path: str = Query(...)):
    """
    安全校验：确保音频路径在允许的目录内，防止路径遍历攻击
    """
    # 1. 定义允许的根目录（必须与你生成音频的实际目录一致）
    allowed_root = Path("output/xtts2/generated")
    # 2. 拼接绝对路径（防止相对路径越权，如 ../etc/passwd）
    absolute_path = Path(file_path).resolve()
    # 3. 校验路径是否在允许的根目录下
    if allowed_root.resolve() not in absolute_path.parents and absolute_path.parent != allowed_root.resolve():
        raise HTTPException(
            status_code=403,
            detail="非法的音频文件路径，禁止访问"
        )
    # 4. 校验文件是否存在
    if not absolute_path.exists() or not absolute_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"音频文件不存在：{file_path}"
        )
    # 5. 校验文件类型（仅允许wav）
    if absolute_path.suffix.lower() != ".wav":
        raise HTTPException(
            status_code=400,
            detail="仅支持获取WAV格式的音频文件"
        )
    return absolute_path

@router.get("/get-audio", summary="获取音频文件（解决405错误）")
async def get_audio(
    audio_path: Path = Depends(validate_audio_path)  # 依赖路径校验
):
    try:
        # 返回音频文件（自动设置Content-Type为audio/wav）
        return FileResponse(
            path=audio_path,
            filename=audio_path.name,  # 下载时的默认文件名
            media_type="audio/wav"     # 明确指定音频MIME类型
        )
    except Exception as e:
        logger.error(f"获取音频文件失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取音频文件失败，请重试")

# -------------------------- 3. 原有接口优化（保持功能+修复潜在问题） --------------------------
def validate_model(model: str = None):
    if model == "default":
        model = "tts_models/multilingual/multi-dataset/xtts_v2"
    if model is None:
        model = "tts_models/multilingual/multi-dataset/xtts_v2"
    if model not in tts_service.get_models():
        raise HTTPException(
            status_code=400,
            detail=f"无效的模型名: {model}，可用模型: {tts_service.get_models()}"
        )
    return model

def validate_speaker(request: TTSRequest):
    speaker = request.speaker.strip()
    if not speaker:
        raise HTTPException(
            status_code=400,
            detail="说话人参数不能为空（可选值：zh_cn_0、zh_cn_1、en_us_0、en_us_1 等）"
        )
    valid_speaker_names = [sp["name"] for sp in tts_service.get_speakers()]
    # 移除临时兼容逻辑（若已确认说话人格式正确）
    if speaker not in valid_speaker_names:
        raise HTTPException(
            status_code=400,
            detail=f"无效的说话人: {speaker}，可用说话人：{valid_speaker_names}"
        )
    return speaker

@router.post("/generate", summary="生成语音")
async def generate_tts(
        request: TTSRequest,
        valid_model: str = Depends(validate_model),
        valid_speaker: str = Depends(validate_speaker)
):
    try:
        logger.info(
            f"收到语音生成请求: "
            f"文本长度={len(request.text)}, "
            f"说话人={valid_speaker}, "
            f"模型={valid_model}"
        )

        # 1. 获取说话人参考音频路径
        speaker_wav = tts_service.speaker_voice_map.get(valid_speaker)
        if not speaker_wav or not Path(speaker_wav).exists():
            raise ValueError(f"说话人 {valid_speaker} 的参考音频不存在：{speaker_wav}")


        # 1. 获取所有说话人列表（从 tts_service 中获取，与前端展示的一致）
        all_speakers = tts_service.get_speakers()  # 假设该方法返回你提供的完整说话人列表

        # 2. 根据当前选中的说话人名称（valid_speaker）匹配对应的语言代码
        matched_speaker = next(
            (speaker for speaker in all_speakers if speaker["name"] == valid_speaker),
            None
        )

        if not matched_speaker:
            # 如果未匹配到说话人（理论上不会发生，因为已通过 validate_speaker 校验）
            raise ValueError(f"未找到说话人 {valid_speaker} 的语言配置")

        # 3. 直接使用说话人数据中预设的 language 字段（绝对准确）
        language = matched_speaker["language"]
        logger.debug(f"使用说话人预设的语言代码: {language}")

        # 4. 额外校验：确保语言代码在模型支持的列表中（可选，增加容错性）
        supported_languages = ['ja', 'zh-cn', 'es', 'de', 'pt', 'fr', 'it', 'ru', 'en', 'tr']
        if language not in supported_languages:
            raise ValueError(
                f"XTTS-V2 不支持该语言 | 说话人预设语言: {language}\n"
                f"支持的语言：{supported_languages}（请检查说话人配置）"
            )

        # 3. 生成语音
        output_file = await asyncio.wrap_future(
            tts_service.generate_speech(
                text=request.text,
                speaker_wav=speaker_wav,
                language=language
            )
        )

        # 4. 返回相对路径（供前端拼接/get-audio接口URL）
        relative_path = get_relative_path(output_file)
        return {
            "success": True,
            "data": {
                "file_path": relative_path,  # 前端需用此路径调用/get-audio
                "file_name": Path(output_file).name,
                "audio_url": f"/get-audio?file_path={relative_path}"  # 直接返回完整音频接口URL（前端可直接用）
            },
            "message": "语音生成成功"
        }
    except ValueError as e:
        logger.warning(f"参数错误: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"语音生成失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="语音生成失败，请稍后重试")

# -------------------------- 4. 原有说话人/模型列表接口（保持不变） --------------------------
@router.get("/speakers", summary="获取说话人列表")
async def get_speakers():
    try:
        speakers = tts_service.get_speakers()
        speaker_names = [sp["name"] for sp in speakers]
        return {
            "success": True,
            "data": {
                "speakers": speakers,
                "speaker_names": speaker_names
            },
            "message": "获取说话人列表成功"
        }
    except Exception as e:
        logger.error(f"获取说话人列表失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取说话人列表失败")

@router.get("/models", summary="获取模型列表")
async def get_models():
    try:
        models = tts_service.get_models()
        return {
            "success": True,
            "data": {"models": models},
            "message": "获取模型列表成功"
        }
    except Exception as e:
        logger.error(f"获取模型列表失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取模型列表失败")
