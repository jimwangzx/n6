// The Vue build version to load with the `import` command
// (runtime-only or standalone) has been set in webpack.base.conf with an alias.
import Vue from 'vue';
import { VTooltip } from 'v-tooltip';
import App from './App';
import router from './router';
import store from './store';
import Notifications from 'vue-notification';

Vue.use(Notifications);

Vue.config.productionTip = false;

// v-tooltip
VTooltip.options.defaultPlacement = 'bottom';
VTooltip.options.defaultDelay = 500;

/* eslint-disable-next-line no-new */
new Vue({
  el: '#app',
  components: {
    App,
  },
  template: '<App />',
  router,
  store,
});
