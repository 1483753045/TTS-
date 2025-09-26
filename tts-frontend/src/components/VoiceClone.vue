<template>
  <div class="voice-clone">
    <h2>语音克隆</h2>

    <div class="upload-section">
      <input type="file" @change="handleFileUpload" accept="audio/*" ref="fileInput">
      <button @click="triggerFileUpload" class="upload-btn">选择语音样本</button>
      <p v-if="sampleFile">已选择: {{ sampleFile.name }}</p>
    </div>

    <div class="input-section">
      <textarea
          v-model="inputText"
          placeholder="输入要克隆的文字..."
          rows="5"
          class="text-input"
      ></textarea>
    </div>

    <div class="controls">
      <button
          @click="cloneVoice"
          :disabled="isCloning || !sampleFile"
          class="clone-btn"
      >
        <span v-if="isCloning">克隆中...</span>
        <span v-else>克隆语音</span>
      </button>
    </div>

    <div class="audio-section" v-if="clonedAudioUrl">
      <audio :src="clonedAudioUrl" controls class="audio-player"></audio>
      <div class="audio-actions">
        <a :href="clonedAudioUrl" download="cloned_voice.wav" class="download-btn">
          下载克隆音频
        </a>
      </div>
    </div>

    <div v-if="error" class="error-message">
      {{ error }}
    </div>
  </div>
</template>

<script>
import api from '@/services/api';

export default {
  name: 'VoiceClone',
  data() {
    return {
      inputText: '',
      sampleFile: null,
      clonedAudioUrl: '',
      isCloning: false,
      error: ''
    };
  },
  methods: {
    triggerFileUpload() {
      this.$refs.fileInput.click();
    },
    handleFileUpload(event) {
      const file = event.target.files[0];
      if (!file) return;

      // 1. 校验文件类型（仅允许音频）
      const audioTypes = ['audio/wav', 'audio/mp3', 'audio/m4a'];
      if (!audioTypes.includes(file.type)) {
        this.error = '仅支持上传 WAV/MP3/M4A 格式的音频文件';
        this.sampleFile = null;
        return;
      }

      // 2. 校验文件大小（限制10MB，可调整）
      const maxSize = 10 * 1024 * 1024; // 10MB
      if (file.size > maxSize) {
        this.error = `文件过大（${(file.size/1024/1024).toFixed(1)}MB），请上传10MB以内的文件`;
        this.sampleFile = null;
        return;
      }

      // 3. 校验通过，保存文件
      this.sampleFile = file;
      this.error = '';
    },
    async cloneVoice() {
      if (!this.inputText.trim()) {
        this.error = '请输入要克隆的文字';
        return;
      }

      if (!this.sampleFile) {
        this.error = '请先上传语音样本';
        return;
      }

      this.error = '';
      this.isCloning = true;
      this.clonedAudioUrl = ''; // 重置之前的音频URL

      try {
        // 上传语音样本
        const uploadResponse = await api.uploadSample(this.sampleFile);

        // 检查上传响应
        if (!uploadResponse.data || !uploadResponse.data.success) {
          throw new Error(uploadResponse.data?.message || '样本上传失败');
        }

        // 克隆语音
        const cloneResponse = await api.cloneVoice({
          text: this.inputText,
          speaker_wav: uploadResponse.data.file_path
        });

        // 检查克隆响应
        if (cloneResponse.data && cloneResponse.data.success) {
          if (cloneResponse.data.file_path) {
            // 处理成功克隆
            // 拼接前先判断环境变量是否存在
            const baseUrl = process.env.VUE_APP_API_URL || 'http://localhost:8000';
            this.clonedAudioUrl = `${baseUrl}/${cloneResponse.data.file_path.replace(/^\/+/, '')}`;
            // replace(/^\/+/, '')：移除file_path开头的斜杠，避免重复（如http://xxx//audio.wav）

          } else {
            throw new Error('API返回的file_path为空');
          }
        } else {
          throw new Error(cloneResponse.data?.message || '语音克隆失败');
        }
      } catch (err) {
        console.error('语音克隆失败:', err);
        this.error = `语音克隆失败: ${err.message || '未知错误'}`;
      } finally {
        this.isCloning = false;
      }
    }
  }
};
</script>

<style scoped>
.voice-clone {
  max-width: 800px;
  margin: 0 auto;
  padding: 30px;
  background-color: #ffffff;
  border-radius: 12px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
}

h2 {
  text-align: center;
  color: #2c3e50;
  margin-bottom: 25px;
  font-size: 28px;
}

.upload-section {
  margin-bottom: 20px;
  text-align: center;
}

input[type="file"] {
  display: none;
}

.upload-btn {
  background-color: #e67e22;
  color: white;
  border: none;
  padding: 10px 20px;
  border-radius: 6px;
  font-size: 16px;
  cursor: pointer;
  transition: background-color 0.3s;
}

.upload-btn:hover {
  background-color: #d35400;
}

.input-section {
  margin-bottom: 20px;
}

.text-input {
  width: 100%;
  padding: 15px;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  font-size: 16px;
  line-height: 1.5;
  resize: vertical;
  transition: border-color 0.3s;
}

.text-input:focus {
  border-color: #3498db;
  outline: none;
  box-shadow: 0 0 0 2px rgba(52, 152, 219, 0.2);
}

.controls {
  text-align: center;
  margin-bottom: 20px;
}

.clone-btn {
  background-color: #9b59b6;
  color: white;
  border: none;
  padding: 12px 25px;
  border-radius: 6px;
  font-size: 16px;
  cursor: pointer;
  transition: background-color 0.3s;
}

.clone-btn:hover:not(:disabled) {
  background-color: #8e44ad;
}

.clone-btn:disabled {
  background-color: #95a5a6;
  cursor: not-allowed;
}

.audio-section {
  margin-top: 25px;
  padding: 20px;
  background-color: #f8f9fa;
  border-radius: 8px;
  animation: fadeIn 0.5s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.audio-player {
  width: 100%;
  margin-bottom: 15px;
}

.audio-actions {
  text-align: center;
}

.download-btn {
  display: inline-block;
  background-color: #2ecc71;
  color: white;
  padding: 12px 25px;
  border-radius: 6px;
  text-decoration: none;
  transition: background-color 0.3s;
}

.download-btn:hover {
  background-color: #27ae60;
}

.error-message {
  margin-top: 20px;
  padding: 15px;
  background-color: #ffebee;
  color: #c62828;
  border-radius: 8px;
  text-align: center;
}
</style>