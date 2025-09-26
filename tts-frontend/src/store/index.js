import Vue from 'vue';
import Vuex from 'vuex';
import tts from './modules/tts';

Vue.use(Vuex);

export default new Vuex.Store({
    modules: {
        tts
    }
});