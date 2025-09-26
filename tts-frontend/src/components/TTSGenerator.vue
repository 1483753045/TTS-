<template>
  <div class="tts-generator">
    <h2>文字转语音生成器</h2>

    <!-- 加载状态提示 -->
    <div v-if="isLoading" class="loading-message">
      加载说话人列表中...
    </div>

    <div class="input-section">
      <textarea
          v-model="inputText"
          placeholder="输入要转换的文字..."
          rows="5"
          class="text-input"
      ></textarea>

      <div class="controls">
        <!-- 说话人选择器 -->
        <div class="speaker-select" v-if="speakers && speakers.length > 0">
          <label>说话人:</label>
          <select v-model="selectedSpeaker">
            <option v-for="speaker in speakers" :key="speaker" :value="speaker">
              {{ speaker }}
            </option>
          </select>
        </div>

        <!-- 无说话人时的提示 -->
        <div v-else-if="!isLoading" class="no-speakers">
          无可用说话人
        </div>

        <!-- 生成按钮 -->
        <button
            @click="generateSpeech"
            :disabled="isGenerating || isLoading"
            class="generate-btn"
        >
          <span v-if="isGenerating">生成中...</span>
          <span v-else>生成语音</span>
        </button>
      </div>
    </div>

    <!-- 音频播放区域 -->
    <div class="audio-section" v-if="audioUrl">
      <audio :src="audioUrl" controls class="audio-player"></audio>
      <div class="audio-actions">
        <a :href="audioUrl" download="generated_speech.wav" class="download-btn">
          下载音频
        </a>
        <button @click="copyShareLink" class="share-btn">
          复制分享链接
        </button>
      </div>
    </div>

    <!-- 错误信息显示 -->
    <div v-if="error" class="error-message">
      {{ error }}
    </div>

    <!-- Vuex 错误信息显示 -->
    <div v-if="ttsError" class="error-message">
      {{ ttsError }}
    </div>
  </div>
</template>

<script>
import { mapState } from 'vuex';

export default {
  name: 'TTSGenerator',
  data() {
    return {
      inputText: '',
      selectedSpeaker: '',
      audioUrl: '',
      isGenerating: false,
      error: ''
    };
  },
  watch: {
    speakers(newSpeakers) {
      if (newSpeakers && newSpeakers.length > 0) {
        this.selectedSpeaker = newSpeakers[0];
      } else {
        this.selectedSpeaker = '';
      }
    }
  },
  computed: {
    ...mapState('tts', {
      speakers: state => state.speakers,
      isLoading: state => state.isLoading,
      ttsError: state => state.error
    })
  },
  mounted() {
    // 加载说话人列表
    this.$store.dispatch('tts/fetchSpeakers');
  },
  methods: {
    async generateSpeech() {
      // 1. 先校验输入（新增：避免空文本请求）
      if (!this.inputText.trim()) {
        this.error = '请输入要转换的文字';
        return;
      }
      if (!this.selectedSpeaker) {
        this.error = '请选择说话人';
        return;
      }

      this.isGenerating = true;
      this.error = '';
      this.audioUrl = '';

      try {
        // 2. 传入关键参数（inputText + selectedSpeaker）
        const response = await this.$api.generateTTS({
          text: this.inputText.trim(),
          speaker: this.selectedSpeaker
        });

        if (response.data?.result === "success" && response.data?.file_path) {
          // 3. 用API返回的绝对路径（避免相对路径部署问题）
          this.audioUrl = `${process.env.VUE_APP_API_URL}/${response.data.file_path}`;
          // 4. 实现音频可用性检测（监听audio错误）
          await this.testAudioAvailability(this.audioUrl);
        } else {
          throw new Error('语音生成成功，但未返回音频路径');
        }
      } catch (error) {
        console.error('生成语音失败:', error);
        this.error = `生成失败：${error.message || '未知错误'}`;
      } finally {
        this.isGenerating = false; // 无论成功失败，都关闭加载状态
      }
    },

// 5. 实现音频检测方法（新增）
    async testAudioAvailability(audioUrl) {
      return new Promise((resolve, reject) => {
        const audio = new Audio(audioUrl);
        audio.onloadeddata = () => resolve(); // 加载成功
        audio.onerror = (err) => {
          this.error = '音频加载失败，请重试';
          reject(err);
        };
      });
    },

    copyShareLink() {
      if (!this.audioUrl) return;

      // 用完整URL（基于环境变量，确保部署后可用）
      const fullShareUrl = window.location.origin + this.audioUrl;
      navigator.clipboard.writeText(fullShareUrl)
          .then(() => alert('分享链接已复制到剪贴板'))
          .catch(err => {
            console.error('复制失败:', err);
            alert('复制失败，请手动复制：' + fullShareUrl); // 新增：显示手动复制链接
          });
    },
  },
};
</script>

<style scoped>
.tts-generator {
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

.input-section {
  margin-bottom: 25px;
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
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 15px;
}

.speaker-select {
  display: flex;
  align-items: center;
}

.speaker-select label {
  margin-right: 10px;
  color: #555;
  font-weight: 500;
}

.speaker-select select {
  padding: 10px 15px;
  border: 1px solid #e0e0e0;
  border-radius: 6px;
  background-color: #f9f9f9;
  font-size: 16px;
}

.no-speakers {
  color: #777;
  font-style: italic;
}

.generate-btn {
  background-color: #3498db;
  color: white;
  border: none;
  padding: 12px 25px;
  border-radius: 6px;
  font-size: 16px;
  font-weight: 500;
  cursor: pointer;
  transition: background-color 0.3s;
}

.generate-btn:hover:not(:disabled) {
  background-color: #2980b9;
}

.generate-btn:disabled {
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
  display: flex;
  gap: 15px;
}

.download-btn, .share-btn {
  flex: 1;
  text-align: center;
  padding: 12px;
  border-radius: 6px;
  font-weight: 500;
  text-decoration: none;
  transition: all 0.3s;
}

.download-btn {
  background-color: #2ecc71;
  color: white;
}

.download-btn:hover {
  background-color: #27ae60;
}

.share-btn {
  background-color: #9b59b6;
  color: white;
  border: none;
  cursor: pointer;
}

.share-btn:hover {
  background-color: #8e44ad;
}

.error-message {
  margin-top: 20px;
  padding: 15px;
  background-color: #ffebee;
  color: #c62828;
  border-radius: 8px;
  text-align: center;
}

.loading-message {
  margin-top: 10px;
  padding: 10px;
  background-color: #e3f2fd;
  color: #1976d2;
  border-radius: 6px;
  text-align: center;
}
</style>