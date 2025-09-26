<template>
  <div class="home-view">
    <div class="container">
      <TTSGenerator />
      <VoiceClone class="mt-5" />
    </div>
  </div>
</template>

<script>
import TTSGenerator from '@/components/TTSGenerator.vue';
import VoiceClone from '@/components/VoiceClone.vue';

export default {
  name: 'HomeView',
  components: {
    TTSGenerator,
    VoiceClone
  }
};
</script>

<style scoped>
.home-view {
  display: flex;
  justify-content: center;
  padding: 2rem;
}

.container {
  width: 100%;
  max-width: 900px;
}

.mt-5 {
  margin-top: 3rem;
}
</style>