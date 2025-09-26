#!/bin/bash

# 激活conda环境
source $(conda info --base)/etc/profile.d/conda.sh
conda activate tts_system

# 设置AMD GPU环境变量
export HSA_OVERRIDE_GFX_VERSION=10.3.0  # 根据您的AMD GPU型号调整
export PYTORCH_HIP_ALLOC_CONF=garbage_collection_threshold:0.8

# 安装依赖
pip install -r requirements.txt

# 创建必要的目录
mkdir -p temp
mkdir -p output/tts
mkdir -p output/cloned
mkdir -p temp/samples

# 启动FastAPI服务
uvicorn app.main:app --host 0.0.0.0 --port 8000