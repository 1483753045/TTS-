import Vue from 'vue';
import Router from 'vue-router';
import HomeView from '@/views/HomeView.vue';
import SettingsView from '@/views/SettingsView.vue';

Vue.use(Router);

export default new Router({
    mode: 'history',
    routes: [
        {
            path: '/',
            name: 'home',
            component: HomeView
        },
        {
            path: '/settings',
            name: 'settings',
            component: SettingsView
        }
    ]
});