#!/bin/bash

# 启动后端服务
echo "启动后端服务..."
cd tts-backend
./start.sh &

# 等待后端启动
echo "等待后端启动..."
sleep 10

# 启动前端服务
echo "启动前端服务..."
cd ../tts-frontend
./start.sh
