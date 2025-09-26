from pydantic import BaseModel

class TTSRequest(BaseModel):
    text: str
    speaker: str = "default"
    model: str = None
    vocoder: str = None

class VoiceCloneRequest(BaseModel):
    text: str
    speaker_wav: str  # 语音样本文件路径
    model: str = None
    vocoder: str = None