import asyncio
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends, Query, File, UploadFile
from fastapi.responses import FileResponse
from app.services.tts_service import tts_service  # 导入tts_service
from app.models.tts import TTSRequest, CloneTTSRequest
from app.utils.file_utils import get_relative_path
import shutil
from uuid import uuid4

# -------------------------- 1. 全局配置（统一、无冗余） --------------------------
# 语音素材保存目录（只定义1次，确保权限）
VOICE_MATERIAL_DIR = Path("data/voice_materials")
VOICE_MATERIAL_DIR.mkdir(exist_ok=True, parents=True)  # 确保目录存在

# 初始化路由（加前缀，匹配前端请求路径）
router = APIRouter(prefix="/api/v1/tts", tags=["TTS语音合成"])

# 复用tts_service的日志实例（确保日志写入 xtts2_service.log）
logger = tts_service.logger


# -------------------------- 2. 音频文件获取接口（不变，确保前端能拉取音频） --------------------------
def validate_audio_path(file_path: str = Query(...)):
    allowed_root = Path("output/xtts2/generated").resolve()  # 允许的根目录
    absolute_path = Path(file_path).resolve()

    # 关键修改：检查文件是否在 allowed_root 及其子目录下
    if not absolute_path.is_relative_to(allowed_root):
        raise HTTPException(
            status_code=403,
            detail="非法的音频文件路径，禁止访问"
        )

    # 原有校验逻辑保持不变
    if not absolute_path.exists() or not absolute_path.is_file():
        raise HTTPException(status_code=404, detail=f"音频文件不存在：{file_path}")
    if absolute_path.suffix.lower() != ".wav":
        raise HTTPException(status_code=400, detail="仅支持获取WAV格式的音频文件")
    return absolute_path


@router.get("/get-audio", summary="获取音频文件")
async def get_audio(audio_path: Path = Depends(validate_audio_path)):
    try:
        return FileResponse(
            path=audio_path,
            filename=audio_path.name,
            media_type="audio/wav"
        )
    except Exception as e:
        logger.error(f"获取音频文件失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取音频文件失败，请重试")


# -------------------------- 3. 语音生成接口（不变，修复日志实例后正常输出） --------------------------
def validate_model(model: str = None):
    if model in [None, "default"]:
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
        raise HTTPException(status_code=400, detail="说话人参数不能为空（可选值：zh_cn_0、zh_cn_1 等）")
    valid_speaker_names = [sp["name"] for sp in tts_service.get_speakers()]
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
        logger.info(f"收到语音生成请求: 文本长度={len(request.text)}, 说话人={valid_speaker}, 模型={valid_model}")
        # 获取说话人参考音频
        speaker_wav = tts_service.speaker_voice_map.get(valid_speaker)
        if not speaker_wav or not Path(speaker_wav).exists():
            raise ValueError(f"说话人 {valid_speaker} 的参考音频不存在：{speaker_wav}")
        # 匹配说话人语言
        matched_speaker = next((sp for sp in tts_service.get_speakers() if sp["name"] == valid_speaker), None)
        if not matched_speaker:
            raise ValueError(f"未找到说话人 {valid_speaker} 的语言配置")
        language = matched_speaker["language"]
        supported_languages = ['ja', 'zh-cn', 'es', 'de', 'pt', 'fr', 'it', 'ru', 'en', 'tr']
        if language not in supported_languages:
            raise ValueError(f"XTTS-V2 不支持该语言：{language}，支持列表：{supported_languages}")
        # 生成语音
        output_file = await asyncio.wrap_future(
            tts_service.generate_speech(text=request.text, speaker_wav=speaker_wav, language=language)
        )
        # 返回结果
        relative_path = get_relative_path(output_file)
        return {
            "success": True,
            "data": {
                "file_path": relative_path,
                "file_name": Path(output_file).name,
                "audio_url": f"/get-audio?file_path={relative_path}"
            },
            "message": "语音生成成功"
        }
    except ValueError as e:
        logger.warning(f"参数错误: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"语音生成失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="语音生成失败，请稍后重试")


# -------------------------- 4. 说话人/模型列表接口（不变） --------------------------
@router.get("/speakers", summary="获取说话人列表")
async def get_speakers():
    try:
        speakers = tts_service.get_speakers()
        speaker_names = [sp["name"] for sp in speakers]
        return {
            "success": True,
            "data": {"speakers": speakers, "speaker_names": speaker_names},
            "message": "获取说话人列表成功"
        }
    except Exception as e:
        logger.error(f"获取说话人列表失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取说话人列表失败")


@router.get("/models", summary="获取模型列表")
async def get_models():
    try:
        models = tts_service.get_models()
        return {"success": True, "data": {"models": models}, "message": "获取模型列表成功"}
    except Exception as e:
        logger.error(f"获取模型列表失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取模型列表失败")


# -------------------------- 5. 语音素材上传接口（修复重复配置+日志） --------------------------
@router.post("/upload-voice-material", summary="上传自定义语音素材（用于克隆音色）")
async def upload_voice_material(
    file: UploadFile = File(..., description="克隆用的参考音频（WAV/MP3格式，5MB以内）")
):
    try:
        # 1. 校验文件格式和大小
        logger.info(f"开始处理语音素材上传：文件名={file.filename}，格式={file.content_type}，大小={file.size/1024/1024:.2f}MB")
        allowed_types = ["audio/wav", "audio/mp3", "audio/mpeg"]
        if file.content_type not in allowed_types:
            raise HTTPException(
                status_code=400,
                detail=f"仅支持 WAV/MP3 格式，当前格式：{file.content_type}"
            )
        if file.size > 5 * 1024 * 1024:
            raise HTTPException(
                status_code=400,
                detail=f"音频文件大小不能超过 5MB，当前大小：{file.size/1024/1024:.2f}MB"
            )

        # 2. 生成保存路径（用全局的 VOICE_MATERIAL_DIR）
        material_id = f"clone_{uuid4().hex[:12]}"
        file_ext = file.filename.split(".")[-1].lower()
        save_path = VOICE_MATERIAL_DIR / f"{material_id}.{file_ext}"

        # 3. 保存文件
        with open(save_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
        logger.info(f"语音素材保存成功：路径={save_path}，素材ID={material_id}")

        # 4. 返回结果
        return {
            "success": True,
            "data": {
                "material_id": material_id,
                "preview_url": f"/api/v1/tts/preview-material?material_id={material_id}",
                "file_ext": file_ext
            },
            "message": "语音素材上传成功"
        }
    except HTTPException as e:
        raise e  # 直接抛出已定义的HTTP错误
    except PermissionError:
        err_msg = f"保存文件失败：目录 {VOICE_MATERIAL_DIR} 无写入权限"
        logger.error(err_msg, exc_info=True)
        raise HTTPException(status_code=500, detail=err_msg)
    except Exception as e:
        err_msg = f"语音素材上传失败：{str(e)}"
        logger.error(err_msg, exc_info=True)
        raise HTTPException(status_code=500, detail=err_msg)
    finally:
        await file.close()  # 确保关闭文件流


# -------------------------- 6. 素材预览接口（不变） --------------------------
def validate_material_id(material_id: str = Query(...)):
    material_files = list(VOICE_MATERIAL_DIR.glob(f"{material_id}.*"))
    if not material_files:
        raise HTTPException(status_code=404, detail=f"语音素材不存在：{material_id}")
    material_path = material_files[0]
    if material_path.suffix.lower() not in [".wav", ".mp3"]:
        raise HTTPException(status_code=400, detail="仅支持预览 WAV/MP3 格式的素材")
    return material_path


@router.get("/preview-material", summary="预览上传的语音素材")
async def preview_material(material_path: Path = Depends(validate_material_id)):
    try:
        return FileResponse(
            path=material_path,
            filename=material_path.name,
            media_type=f"audio/{material_path.suffix[1:]}"
        )
    except Exception as e:
        logger.error(f"素材预览失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="素材预览失败")


# -------------------------- 7. 克隆生成接口（补充方法存在性提醒） --------------------------
@router.post("/generate-with-clone", summary="基于上传素材克隆音色并生成语音")
async def generate_tts_with_clone(
        request: CloneTTSRequest,
        valid_model: str = Depends(validate_model)
):
    try:
        # 校验参数
        if not request.material_id or not request.text:
            raise HTTPException(status_code=400, detail="material_id（素材ID）和 text（目标文本）不能为空")
        # 获取克隆素材路径
        material_files = list(VOICE_MATERIAL_DIR.glob(f"{request.material_id}.*"))
        if not material_files:
            raise ValueError(f"克隆素材不存在：{request.material_id}")
        clone_speaker_wav = str(material_files[0])
        logger.info(f"开始克隆音色生成：素材ID={request.material_id}，文本长度={len(request.text)}")

        # 关键：确保 tts_service 中已实现 generate_speech_with_clone 方法！
        # 若未实现，替换为 tts_service.generate_speech（需确认参数兼容）
        output_file = tts_service.generate_speech_with_clone(
            text=request.text,
            clone_speaker_wav=clone_speaker_wav,
            language="zh-cn"
        )

        # 返回结果
        relative_path = get_relative_path(output_file)
        return {
            "success": True,
            "data": {
                "file_path": relative_path,
                "file_name": Path(output_file).name,
                "audio_url": f"/get-audio?file_path={relative_path}"
            },
            "message": "克隆音色并生成语音成功"
        }
    except ValueError as e:
        logger.warning(f"克隆参数错误: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"克隆生成失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="克隆音色生成失败，请重试")