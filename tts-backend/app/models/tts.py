from pydantic import BaseModel, Field

# 原有 TTSRequest 保持不变
class TTSRequest(BaseModel):
    text: str = Field(..., description="目标文本")
    speaker: str = Field(..., description="预设说话人名称")
    model: str = Field(None, description="TTS模型名（默认xtts_v2）")

# 新增克隆请求模型
class CloneTTSRequest(BaseModel):
    text: str = Field(..., description="目标文本")
    material_id: str = Field(..., description="上传的语音素材ID")
    model: str = Field(None, description="TTS模型名（默认xtts_v2）")

class VoiceCloneRequest(BaseModel):
    text: str
    speaker_wav: str  # 语音样本文件路径
    model: str = None
    vocoder: str = None