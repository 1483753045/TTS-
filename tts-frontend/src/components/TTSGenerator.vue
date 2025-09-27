<template>
  <div class="tts-generator">
    <h2>文字转语音生成器</h2>

    <!-- 加载状态提示 -->
    <div v-if="isLoading" class="status-message loading">
      <i class="fas fa-circle-notch fa-spin"></i>
      <span>加载说话人/模型列表中...</span>
    </div>

    <div class="input-section">
      <textarea
          v-model="inputText"
          placeholder="输入要转换的文字..."
          rows="5"
          class="text-input"
          :class="{ 'has-error': error && !inputText.trim() }"
          @input="clearError"
      ></textarea>

      <div class="controls">
        <!-- 说话人选择器 -->
        <div class="speaker-select" v-if="parsedSpeakers && parsedSpeakers.length > 0">
          <label>说话人:</label>
          <select
              v-model="selectedSpeaker"
              :class="{ 'has-error': error && !selectedSpeaker }"
          >
            <option
                v-for="(speaker, index) in parsedSpeakers"
                :key="index"
                :value="speaker"
            >
              {{ speaker.desc }}
            </option>
          </select>
        </div>

        <!-- 模型选择器 -->
        <div class="model-select" v-if="parsedModels && parsedModels.length > 0">
          <label>模型:</label>
          <select
              v-model="selectedModel"
              :class="{ 'has-error': error && !selectedModel }"
          >
            <option
                v-for="(model, index) in parsedModels"
                :key="index"
                :value="model.value"
            >
              {{ model.label }}
            </option>
          </select>
        </div>

        <!-- 无数据时的提示 -->
        <div v-else-if="!isLoading" class="status-message no-speakers">
          <i class="fas fa-info-circle"></i>
          <span>无可用说话人/模型</span>
        </div>

        <!-- 生成按钮 -->
        <button
            @click="generateSpeech"
            :disabled="isGenerating || isLoading || !selectedModel"
            class="generate-btn"
        >
          <i v-if="isGenerating" class="fas fa-spinner fa-spin mr-2"></i>
          <span v-if="isGenerating">生成中...</span>
          <span v-else>生成语音</span>
        </button>
      </div>
    </div>

    <!-- 音频播放区域 -->
    <div class="audio-section" v-if="audioUrl" :class="{ 'fade-in': audioUrl }">
      <h3>生成结果</h3>
      <audio
          :src="audioUrl"
          controls
          class="audio-player"
          @error="handleAudioError"
      >
      </audio>
      <div class="audio-actions">
        <button
            @click="downloadAudio"
            class="btn download-btn"
            :disabled="!audioUrl"
        >
          <i class="fas fa-download mr-2"></i>下载音频
        </button>
      </div>
    </div>

    <!-- 错误信息显示 -->
    <div v-if="error || ttsError" class="status-message error">
      <i class="fas fa-exclamation-circle"></i>
      <span>{{ error || ttsError }}</span>
      <button class="close-btn" @click="clearError">
        <i class="fas fa-times"></i>
      </button>
    </div>
  </div>
</template>

<script>
import { mapState } from 'vuex';
import axios from 'axios';

export default {
  name: 'TTSGenerator',
  data() {
    return {
      inputText: '',
      selectedSpeaker: null,
      selectedModel: 'default',
      audioUrl: '',          // 存储带api/v1/tts前缀的完整音频URL
      audioFileName: 'generated_speech.wav',
      isGenerating: false,
      error: ''
    };
  },
  computed: {
    ...mapState('tts', {
      speakers: state => state.speakers,
      models: state => state.models,
      isLoading: state => state.isLoading,
      ttsError: state => state.error
    }),
    parsedSpeakers() {
      const speakerMap = {
        '中文女声（默认）': 'zh_cn_0',
        '英语女声（默认）': 'en_us_0',
        '西班牙语（默认）': 'es_0',
        '法语（默认）': 'fr_0',
        '德语（默认）': 'de_0',
        '意大利语（默认）': 'it_0',
        '葡萄牙语（默认）': 'pt_0',
        '俄语（默认）': 'ru_0'
      };

      let result = [];
      if (this.speakers && Array.isArray(this.speakers) && this.speakers.length > 0) {
        const firstItem = this.speakers[0];
        if (firstItem?.data?.speakers && Array.isArray(firstItem.data.speakers)) {
          result = firstItem.data.speakers.map(speaker => {
            const pureDesc = speaker.desc.trim().replace(/[\u200B-\u200D\uFEFF]/g, '');
            const correctName = speakerMap[pureDesc] || '';
            if (!correctName) {
              console.error(`说话人映射失败：未找到 desc="${pureDesc}" 对应的配置`);
              return null;
            }
            return { ...speaker, name: correctName };
          }).filter(Boolean);
        }
      }
      return result;
    },
    parsedModels() {
      let result = [];
      if (this.models && Array.isArray(this.models) && this.models.length > 0) {
        result = this.models.map(model => ({
          label: model.label || model.value,
          value: model.value || model
        }));
      } else {
        result = [{ label: '默认模型（default）', value: 'default' }];
      }
      return result;
    }
  },
  watch: {
    parsedSpeakers(newSpeakers) {
      if (newSpeakers.length > 0 && !this.selectedSpeaker) {
        this.selectedSpeaker = newSpeakers[0];
        console.log('默认选择说话人:', this.selectedSpeaker);
      } else if (newSpeakers.length === 0) {
        this.selectedSpeaker = null;
      }
    },
    parsedModels(newModels) {
      if (newModels.length > 0 && !this.selectedModel) {
        this.selectedModel = newModels[0].value;
        console.log('默认选择模型:', this.selectedModel);
      }
    }
  },
  mounted() {
    this.$store.dispatch('tts/fetchSpeakers');
    this.$store.dispatch('tts/fetchModels');
  },
  methods: {
    async generateSpeech() {
      // 1. 输入校验
      if (!this.inputText.trim()) {
        this.error = '请输入要转换的文字';
        return;
      }
      if (!this.selectedSpeaker?.name) {
        this.error = '请选择有效说话人';
        return;
      }
      if (!this.selectedModel) {
        this.error = '请选择有效模型';
        return;
      }

      // 2. 构造请求体
      const requestData = {
        text: this.inputText.trim(),
        speaker: this.selectedSpeaker.name,
        model: this.selectedModel
      };
      console.log('生成语音请求体:', requestData);

      this.isGenerating = true;
      this.error = '';
      this.audioUrl = '';

      try {
        // 3. 调用后端生成接口（带api/v1/tts前缀，与Postman一致）
        const response = await axios.post(
            `${process.env.VUE_APP_API_URL}/api/v1/tts/generate`,
            requestData,
            {
              headers: {
                "Content-Type": "application/json" // 显式指定JSON类型，确保后端解析
              }
            }
        );

        console.log('后端完整响应:', response);

        // 4. 解析后端响应
        if (!response.data?.success) {
          throw new Error(response.data?.message || '语音生成失败');
        }
        if (!response.data?.data) {
          throw new Error('后端未返回核心数据（data字段缺失）');
        }

        // 5. 提取音频URL并补充api/v1/tts前缀（关键！匹配Postman路径）
        const { audio_url, file_name } = response.data.data;
        if (!audio_url) {
          throw new Error('后端未返回有效的音频URL');
        }

        // 处理前缀拼接，避免双斜杠问题
        const apiPrefix = '/api/v1/tts';
        const fullAudioUrl = audio_url.startsWith('/')
            ? `${process.env.VUE_APP_API_URL}${apiPrefix}${audio_url}`
            : `${process.env.VUE_APP_API_URL}${apiPrefix}/${audio_url}`;

        console.log('最终音频接口URL（与Postman一致）:', fullAudioUrl);

        // 6. 赋值用于播放和下载
        this.audioUrl = fullAudioUrl;
        this.audioFileName = file_name || 'generated_speech.wav';
        this.showTemporaryMessage('语音生成成功！');
      } catch (error) {
        console.error('语音生成失败:', error);
        // 显示具体请求URL，方便排查路径问题
        this.error = error.response
            ? `生成失败: ${error.response.data?.message || error.response.statusText}`
            : `生成失败: ${error.message}（请求URL: ${error.config?.url || '未知'}）`;
      } finally {
        this.isGenerating = false;
      }
    },

    // 音频播放错误：显示具体URL方便排查
    handleAudioError() {
      this.error = `音频无法播放（当前URL: ${this.audioUrl}），请检查路径是否正确`;
    },

    // 下载音频：使用带完整前缀的URL
    downloadAudio() {
      if (!this.audioUrl) return;

      const a = document.createElement('a');
      a.href = this.audioUrl;
      a.download = this.audioFileName;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    },

    clearError() {
      this.error = '';
      this.$store.commit('tts/CLEAR_ERROR');
    },

    showTemporaryMessage(message) {
      const tempMsg = document.createElement('div');
      tempMsg.className = 'temp-message';
      tempMsg.innerHTML = `<i class="fas fa-check-circle"></i><span>${message}</span>`;
      document.body.appendChild(tempMsg);

      setTimeout(() => tempMsg.classList.add('show'), 10);
      setTimeout(() => {
        tempMsg.classList.remove('show');
        setTimeout(() => document.body.removeChild(tempMsg), 300);
      }, 3000);
    }
  },
  beforeDestroy() {
    // 无需清理Blob URL（已使用普通URL）
  }
};
</script>

<style scoped>
/* 模型选择器样式 */
.model-select {
  display: flex;
  align-items: center;
  flex: 1;
  min-width: 200px;
  margin-left: 1rem;
}

.model-select label {
  margin-right: 0.75rem;
  color: #555;
  font-weight: 500;
  white-space: nowrap;
}

.model-select select {
  flex: 1;
  padding: 0.75rem 1rem;
  border: 1px solid #e0e0e0;
  border-radius: 6px;
  background-color: #f9f9f9;
  font-size: 1rem;
  transition: all 0.3s ease;
}

.model-select select:focus {
  border-color: #3498db;
  outline: none;
}

.model-select select.has-error {
  border-color: #e74c3c;
  box-shadow: 0 0 0 2px rgba(231, 76, 60, 0.2);
}

/* 响应式：移动端模型选择器样式 */
@media (max-width: 600px) {
  .controls {
    flex-direction: column;
    align-items: stretch;
  }

  .model-select {
    width: 100%;
    margin-left: 0;
    margin-top: 0.5rem;
  }
}

/* 主容器样式 */
.tts-generator {
  max-width: 800px;
  margin: 2rem auto;
  padding: 2rem;
  background-color: #ffffff;
  border-radius: 12px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
}

h2 {
  text-align: center;
  color: #2c3e50;
  margin-bottom: 1.5rem;
  font-size: 1.8rem;
}

h3 {
  color: #2c3e50;
  margin-top: 0;
  margin-bottom: 1rem;
  font-size: 1.2rem;
}

/* 输入区域样式 */
.input-section {
  margin-bottom: 1.5rem;
}

.text-input {
  width: 100%;
  padding: 1rem;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  font-size: 1rem;
  line-height: 1.5;
  resize: vertical;
  transition: all 0.3s ease;
  box-sizing: border-box;
}

.text-input:focus {
  border-color: #3498db;
  outline: none;
  box-shadow: 0 0 0 2px rgba(52, 152, 219, 0.2);
}

.text-input.has-error,
select.has-error {
  border-color: #e74c3c;
  box-shadow: 0 0 0 2px rgba(231, 76, 60, 0.2);
}

/* 控制区域样式 */
.controls {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
  margin-top: 1rem;
}

.speaker-select {
  display: flex;
  align-items: center;
  flex: 1;
  min-width: 200px;
}

.speaker-select label {
  margin-right: 0.75rem;
  color: #555;
  font-weight: 500;
  white-space: nowrap;
}

.speaker-select select {
  flex: 1;
  padding: 0.75rem 1rem;
  border: 1px solid #e0e0e0;
  border-radius: 6px;
  background-color: #f9f9f9;
  font-size: 1rem;
  transition: all 0.3s ease;
}

.speaker-select select:focus {
  border-color: #3498db;
  outline: none;
}

/* 状态提示样式 */
.status-message {
  padding: 0.75rem 1rem;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 1rem 0;
  font-size: 0.95rem;
}

.status-message i {
  margin-right: 0.5rem;
  font-size: 1.1rem;
}

.loading {
  background-color: #e3f2fd;
  color: #1976d2;
}

.no-speakers {
  background-color: #fff3e0;
  color: #f57c00;
  flex: 1;
  min-width: 200px;
}

.error {
  background-color: #ffebee;
  color: #c62828;
  position: relative;
  padding-right: 2.5rem;
}

.close-btn {
  position: absolute;
  right: 0.75rem;
  top: 50%;
  transform: translateY(-50%);
  background: none;
  border: none;
  color: #c62828;
  cursor: pointer;
  font-size: 1rem;
  width: 1.5rem;
  height: 1.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  transition: background-color 0.2s;
}

.close-btn:hover {
  background-color: rgba(255, 255, 255, 0.3);
}

/* 生成按钮样式 */
.generate-btn {
  background-color: #3498db;
  color: white;
  border: none;
  padding: 0.75rem 1.5rem;
  border-radius: 6px;
  font-size: 1rem;
  font-weight: 500;
  cursor: pointer;
  transition: background-color 0.3s;
  display: flex;
  align-items: center;
  justify-content: center;
  white-space: nowrap;
}

.generate-btn:hover:not(:disabled) {
  background-color: #2980b9;
}

.generate-btn:disabled {
  background-color: #95a5a6;
  cursor: not-allowed;
  opacity: 0.8;
}

/* 音频区域样式 */
.audio-section {
  margin-top: 1.5rem;
  padding: 1.5rem;
  background-color: #f8f9fa;
  border-radius: 8px;
  opacity: 0;
  transform: translateY(10px);
  transition: opacity 0.5s ease, transform 0.5s ease;
}

.audio-section.fade-in {
  opacity: 1;
  transform: translateY(0);
}

.audio-player {
  width: 100%;
  margin-bottom: 1rem;
  padding: 0.5rem 0;
}

.audio-actions {
  display: flex;
  gap: 1rem;
  flex-wrap: wrap;
}

/* 按钮通用样式 */
.btn {
  flex: 1;
  min-width: 150px;
  text-align: center;
  padding: 0.75rem;
  border-radius: 6px;
  font-weight: 500;
  text-decoration: none;
  transition: all 0.3s;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.95rem;
  border: none;
  cursor: pointer;
}

.btn:disabled {
  background-color: #bdc3c7;
  cursor: not-allowed;
  transform: none !important;
  box-shadow: none !important;
}

.download-btn {
  background-color: #2ecc71;
  color: white;
}

.download-btn:hover:not(:disabled) {
  background-color: #27ae60;
  transform: translateY(-2px);
  box-shadow: 0 4px 8px rgba(46, 204, 113, 0.2);
}

/* 临时提示样式 */
.temp-message {
  position: fixed;
  bottom: 2rem;
  right: 2rem;
  background-color: #27ae60;
  color: white;
  padding: 0.75rem 1.5rem;
  border-radius: 6px;
  display: flex;
  align-items: center;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  opacity: 0;
  transform: translateY(20px);
  transition: opacity 0.3s ease, transform 0.3s ease;
  z-index: 1000;
}

.temp-message.show {
  opacity: 1;
  transform: translateY(0);
}

.temp-message i {
  margin-right: 0.5rem;
}

/* 移动端响应式样式 */
@media (max-width: 600px) {
  .tts-generator {
    padding: 1.5rem 1rem;
    margin: 1rem;
  }

  .controls {
    flex-direction: column;
    align-items: stretch;
  }

  .speaker-select {
    width: 100%;
  }

  .generate-btn {
    width: 100%;
  }

  .audio-actions {
    flex-direction: column;
  }

  .btn {
    width: 100%;
  }
}
</style>
