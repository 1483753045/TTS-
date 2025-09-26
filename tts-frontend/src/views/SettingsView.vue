<template>
  <div class="settings-view">
    <h2>系统设置</h2>

    <div class="settings-container">
      <div class="setting-item">
        <label>API 地址:</label>
        <input type="text" v-model="apiUrl">
      </div>

      <div class="setting-item">
        <label>默认模型:</label>
        <select v-model="selectedModel">
          <option v-for="model in models" :key="model.key" :value="model.key">
            {{ model.name }}
          </option>
        </select>
      </div>

      <div class="setting-item">
        <label>默认声码器:</label>
        <select v-model="selectedVocoder">
          <option v-for="vocoder in vocoders" :key="vocoder.key" :value="vocoder.key">
            {{ vocoder.name }}
          </option>
        </select>
      </div>

      <button @click="saveSettings" class="save-btn">保存设置</button>
    </div>
  </div>
</template>

<script>
import { mapState } from 'vuex';

export default {
  name: 'SettingsView',
  data() {
    return {
      apiUrl: process.env.VUE_APP_API_URL || 'http://localhost:8000',
      selectedModel: '',
      selectedVocoder: ''
    };
  },
  computed: {
    ...mapState('tts', ['models']),
    vocoders() {
      // 这里简化处理，实际应从后端获取
      return [
        { key: 'vocoder_models/en/ljspeech/hifigan_v2', name: 'HiFi-GAN V2' },
        { key: 'vocoder_models/en/ljspeech/univnet', name: 'UnivNet' }
      ];
    }
  },
  async mounted() {
    if (this.models.length === 0) {
      await this.$store.dispatch('tts/fetchModels');
    }
    if (this.models.length > 0) {
      this.selectedModel = this.models[0].key;
    }
    if (this.vocoders.length > 0) {
      this.selectedVocoder = this.vocoders[0].key;
    }
  },
  methods: {
    saveSettings() {
      // 在实际应用中，这里应该保存设置到本地存储或后端
      alert('设置已保存');
    }
  }
};
</script>

<style scoped>
.settings-view {
  max-width: 800px;
  margin: 0 auto;
  padding: 30px;
}

h2 {
  text-align: center;
  margin-bottom: 30px;
  color: #2c3e50;
}

.settings-container {
  background-color: #ffffff;
  border-radius: 12px;
  padding: 25px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
}

.setting-item {
  margin-bottom: 20px;
}

.setting-item label {
  display: block;
  margin-bottom: 8px;
  font-weight: 500;
  color: #555;
}

.setting-item input, .setting-item select {
  width: 100%;
  padding: 12px;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  font-size: 16px;
}

.save-btn {
  display: block;
  width: 100%;
  padding: 15px;
  background-color: #3498db;
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 16px;
  font-weight: 500;
  cursor: pointer;
  transition: background-color 0.3s;
  margin-top: 20px;
}

.save-btn:hover {
  background-color: #2980b9;
}
</style>