import Vue from 'vue'
import App from './App.vue'
import router from './router'
import store from './store'
import api from './services/api'

Vue.config.productionTip = false

// 将 API 服务挂载到 Vue 原型
Vue.prototype.$api = api

new Vue({
    router,
    store,
    render: h => h(App)
}).$mount('#app')