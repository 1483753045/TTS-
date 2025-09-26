<template>
  <div id="app">
    <header class="app-header">
      <h1>Coqui TTS 文字转语音系统</h1>
      <nav>
        <router-link to="/">首页</router-link>
        <router-link to="/settings">设置</router-link>
      </nav>
    </header>

    <main class="app-main">
      <router-view />
    </main>

    <footer class="app-footer">
      <p>© 2023 Coqui TTS 文字转语音系统 | 使用 AMD GPU 加速</p>
    </footer>
  </div>
</template>

<script>
export default {
  name: 'App'
};
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
  line-height: 1.6;
  color: #333;
  background-color: #f5f7fa;
}

#app {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}

.app-header {
  background-color: #2c3e50;
  color: white;
  padding: 1.5rem 2rem;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
}

.app-header h1 {
  font-size: 1.8rem;
  margin-bottom: 0.5rem;
}

.app-header nav {
  display: flex;
  gap: 1.5rem;
}

.app-header nav a {
  color: #ecf0f1;
  text-decoration: none;
  font-weight: 500;
  padding: 0.5rem 0;
  position: relative;
}

.app-header nav a.router-link-exact-active {
  color: #3498db;
}

.app-header nav a.router-link-exact-active::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 0;
  width: 100%;
  height: 3px;
  background-color: #3498db;
}

.app-main {
  flex: 1;
  padding: 2rem;
}

.app-footer {
  background-color: #2c3e50;
  color: white;
  text-align: center;
  padding: 1.5rem;
  margin-top: auto;
}
</style>