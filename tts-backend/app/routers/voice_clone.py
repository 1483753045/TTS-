# voice_clone.py 关键修改（若有异步逻辑）
import asyncio  # 导入 asyncio
from fastapi import APIRouter, HTTPException, UploadFile, File
from app.services.tts_service import tts_service
from app.models.tts import VoiceCloneRequest
from app.utils.file_utils import ensure_directory, get_relative_path

router = APIRouter()

@router.post("/generate")
async def clone_voice(request: VoiceCloneRequest):
    try:
        # 同样需要 asyncio 包装线程池任务
        output_file = await asyncio.wrap_future(
            tts_service.clone_voice(
                text=request.text,
                speaker_wav=request.speaker_wav,
                model=request.model
            )
        )
        return {
            "success": True,
            "file_path": get_relative_path(output_file),
            "message": "语音克隆成功"
        }
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=400, detail=f"语音克隆失败: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"语音克隆失败: {str(e)}")
