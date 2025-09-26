import asyncio
import logging
from fastapi import APIRouter, HTTPException, Depends
from app.services.tts_service import tts_service
from app.models.tts import TTSRequest
from app.utils.file_utils import get_relative_path

router = APIRouter(prefix="/api/tts", tags=["TTS"])
logger = logging.getLogger(__name__)

# 依赖项：校验模型是否存在
def validate_model(model: str = None):
    if model and model not in tts_service.get_models():
        raise HTTPException(
            status_code=400,
            detail=f"无效的模型名: {model}，可用模型: {tts_service.get_models()}"
        )
    return model

# 依赖项：校验说话人是否存在
def validate_speaker(speaker: str):
    if speaker not in tts_service.get_speakers():
        raise HTTPException(
            status_code=400,
            detail=f"无效的说话人: {speaker}，可用说话人: {tts_service.get_speakers()}"
        )
    return speaker

@router.post("/generate", summary="生成语音")
async def generate_tts(
    request: TTSRequest,
    valid_model: str = Depends(validate_model),
    valid_speaker: str = Depends(validate_speaker)
):
    try:
        logger.info(f"生成语音请求: 文本长度={len(request.text)}, 说话人={request.speaker}, 模型={request.model}")
        output_file = await asyncio.wrap_future(
            tts_service.generate_speech(
                text=request.text,
                speaker=valid_speaker,
                model=valid_model
            )
        )
        return {
            "success": True,
            "data": {
                "file_path": get_relative_path(output_file),
                "file_name": output_file.split("/")[-1]  # 新增：返回文件名，方便前端显示
            },
            "message": "语音生成成功"
        }
    except ValueError as e:
        logger.warning(f"客户端错误: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"服务器错误: {str(e)}", exc_info=True)  # 记录详细堆栈
        raise HTTPException(status_code=500, detail="语音生成失败，请稍后重试")

@router.get("/speakers", summary="获取说话人列表")
async def get_speakers():
    try:
        speakers = tts_service.get_speakers()
        return {
            "success": True,
            "data": {"speakers": speakers},  # 统一格式：用data包裹数据
            "message": "获取说话人列表成功"
        }
    except Exception as e:
        logger.error(f"获取说话人失败: {str(e)}", exc_info=True)
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
        logger.error(f"获取模型失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取模型列表失败")
