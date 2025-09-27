from app.services.tts_service import xtts2_service
from concurrent.futures import wait

# 测试 1：基础语音生成（中文）
future1 = xtts2_service.generate_speech(text="你好，这是 XTTS-V2 生成的中文语音", language="zh-cn")

# 测试 2：语音克隆（需提前准备参考音频 reference.wav）
future2 = xtts2_service.clone_voice(
    text="你好，这是克隆后的语音",
    speaker_wav="./data/reference_voices/reference.wav",  # 替换为你的参考音频路径
    language="zh-cn"
)

# 等待任务完成
wait([future1, future2])
print(f"测试 1 音频路径: {future1.result()}")
print(f"测试 2 音频路径: {future2.result()}")
