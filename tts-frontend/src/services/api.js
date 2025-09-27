// @/services/api.js（修改路径，添加 /v1 版本前缀）
import axios from 'axios';

// @/services/api.js
const axiosInstance = axios.create({
    baseURL: process.env.VUE_APP_API_URL || 'http://localhost:8000', // 无多余路径
    timeout: 30000,
    withCredentials: true, // 必须启用（与后端 allow_credentials=True 对应）
    headers: { 'Content-Type': 'application/json' }
});


export default {
    // TTS相关（路径添加 /v1）
    generateTTS(data, config = {}) {
        // axios.post 的第三个参数是 config，支持 params（query 参数）
        return axiosInstance.post('/api/v1/tts/generate', data, config);
    },
    getSpeakers() {
        return axiosInstance.get('/api/v1/tts/speakers'); // 正确路径
    },
    getModels() {
        return axiosInstance.get('/api/v1/tts/models'); // 新增 /v1
    },

    // 语音克隆相关（路径添加 /v1）
    cloneVoice(data) {
        return axiosInstance.post('/api/v1/voice-clone/generate', data); // 新增 /v1
    },
    uploadSample(file) {
        const formData = new FormData();
        formData.append('file', file);
        return axiosInstance.post('/api/v1/voice-clone/upload-sample', formData, { // 新增 /v1
            headers: { 'Content-Type': 'multipart/form-data' }
        });
    }
};
