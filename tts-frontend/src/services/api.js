// @/services/api.js（删除重复定义，统一用axios实例）
import axios from 'axios';

// 1. 创建axios实例（统一配置基础路径、超时等，便于维护）
const axiosInstance = axios.create({
    baseURL: process.env.VUE_APP_API_URL || 'http://localhost:8000', // 统一基础路径
    timeout: 30000, // 超时时间（语音生成可能耗时，设30秒）
    headers: {
        'Content-Type': 'application/json'
    }
});

// 2. 统一封装API方法（避免重复定义）
export default {
    // TTS相关
    generateTTS(data) {
        return axiosInstance.post('/api/tts/generate', data); // 用实例调用，避免报错
    },
    getSpeakers() {
        return axiosInstance.get('/api/tts/speakers');
    },
    getModels() {
        return axiosInstance.get('/api/tts/models');
    },

    // 语音克隆相关
    cloneVoice(data) {
        return axiosInstance.post('/api/voice-clone/generate', data);
    },
    uploadSample(file) {
        const formData = new FormData();
        formData.append('file', file);
        return axiosInstance.post('/api/voice-clone/upload-sample', formData, {
            headers: { 'Content-Type': 'multipart/form-data' } // 覆盖默认Content-Type
        });
    }
};
