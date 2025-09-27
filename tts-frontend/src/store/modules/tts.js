// store/modules/tts.js
import api from '@/services/api';

export default {
    namespaced: true,
    state: {
        speakers: [],
        models: [], // 显式初始化 models
        isLoading: false,
        error: ''
    },
    mutations: {
        SET_SPEAKERS(state, speakers) {
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
        },
        // 核心修复：添加清除错误的 mutation（统一命名风格）
        CLEAR_ERROR(state) {
            state.error = '';
        }
    },
    actions: {
        async fetchSpeakers({ commit }) {
            commit('SET_LOADING', true);
            commit('CLEAR_ERROR'); // 用新 mutation 清空错误
            try {
                const response = await api.getSpeakers();
                // 适配你的接口返回结构（根据实际情况调整）
                const speakers = response.data || [];
                commit('SET_SPEAKERS', Array.isArray(speakers) ? speakers : [speakers]);
            } catch (error) {
                console.error('获取说话人失败:', error);
                commit('SET_SPEAKERS', []);
                // 更友好的错误提示
                const errorMsg = error.response
                    ? `获取说话人失败: ${error.response.data?.message || '服务器错误'}`
                    : '网络异常，请检查连接';
                commit('SET_ERROR', errorMsg);
            } finally {
                commit('SET_LOADING', false);
            }
        },
        async fetchModels({ commit }) {
            commit('SET_LOADING', true);
            commit('CLEAR_ERROR'); // 新增：请求前清空错误

            try {
                const response = await api.getModels();

                if (response.data && response.data.success) {
                    const models = response.data.models;
                    commit('SET_MODELS', Array.isArray(models) ? models : []);
                } else {
                    throw new Error(response.data?.message || '获取模型失败');
                }
            } catch (error) {
                console.error('获取模型失败:', error);
                commit('SET_ERROR', error.message);
                commit('SET_MODELS', []); // 错误时置空更合理
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
