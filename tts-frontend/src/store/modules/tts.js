// store/modules/tts.js
import api from '@/services/api';

export default {
    namespaced: true,
    state: {
        speakers: [],
        models: [],
        isLoading: false,
        error: null
    },
    mutations: {
        SET_SPEAKERS(state, speakers) {
            // 确保始终设置为数组
            state.speakers = Array.isArray(speakers) ? speakers : [];
        },
        SET_MODELS(state, models) {
            state.models = Array.isArray(models) ? models : [];
        },
        SET_LOADING(state, isLoading) {
            state.isLoading = isLoading;
        },
        SET_ERROR(state, error) {
            state.error = error;
        }
    },
    actions: {
        // 在Vuex的fetchSpeakers action中添加
        async fetchSpeakers({ commit }) {
            commit('SET_LOADING', true); // 新增：开始加载
            commit('SET_ERROR', null); // 清空之前的错误
            try {
                const response = await api.getSpeakers();
                let speakers = response.data || [];
                if (!Array.isArray(speakers)) speakers = [speakers];
                commit('SET_SPEAKERS', speakers);
            } catch (error) {
                console.error('获取说话人失败:', error);
                commit('SET_SPEAKERS', []);
                commit('SET_ERROR', '获取说话人列表失败，请刷新重试'); // 新增：明确错误提示
            } finally {
                commit('SET_LOADING', false); // 新增：结束加载
            }
        },
        async fetchModels({ commit }) {
            commit('SET_LOADING', true);
            commit('SET_ERROR', null);

            try {
                const response = await api.getModels();

                if (response.data && response.data.success) {
                    const models = response.data.models;

                    if (Array.isArray(models)) {
                        commit('SET_MODELS', models);
                    } else {
                        console.warn('API返回的models不是数组，尝试转换:', models);
                        commit('SET_MODELS', models ? [models] : ['default']);
                    }
                } else {
                    throw new Error(response.data?.message || 'API响应格式错误');
                }
            } catch (error) {
                console.error('获取模型失败:', error);
                commit('SET_ERROR', error.message);
                commit('SET_MODELS', ['default']);
            } finally {
                commit('SET_LOADING', false);
            }
        }
    },
    getters: {
        speakers: state => state.speakers,
        models: state => state.models,
        isLoading: state => state.isLoading,
        error: state => state.error
    }
};