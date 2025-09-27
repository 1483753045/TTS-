import torch
from torch.serialization import add_safe_globals

# 允许加载 TTS 自定义类（解决安全限制）
try:
    from TTS.tts.configs.xtts_config import XttsConfig
    add_safe_globals([XttsConfig])
except ImportError:
    pass  # 若导入失败，直接关闭 weights_only

# 替换为你的模型路径
model_path = "/home/wxa/tts-weights/xtts_v2_0.20.0/model.pth"

# 关闭 weights_only 以兼容旧模型（仅在信任文件来源时使用）
state_dict = torch.load(model_path, map_location="cpu", weights_only=False)

# 检查关键键名
has_old_key = any("weight_g" in key for key in state_dict.keys())
has_new_key = any("parametrizations" in key for key in state_dict.keys())

print(f"旧格式键（weight_g）存在: {has_old_key}")  # 需为 True
print(f"新格式键（parametrizations）存在: {has_new_key}")  # 需为 False
