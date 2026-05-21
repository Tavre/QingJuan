import { createApp } from 'vue';
import {
  fluentBadge,
  fluentButton,
  fluentCard,
  fluentCheckbox,
  fluentDesignSystemProvider,
  fluentDivider,
  fluentNumberField,
  fluentOption,
  fluentProgress,
  fluentSearch,
  fluentSelect,
  fluentSwitch,
  fluentTab,
  fluentTabPanel,
  fluentTabs,
  fluentTextArea,
  fluentTextField,
  fluentToolbar,
  fluentTooltip,
  provideFluentDesignSystem,
} from '@fluentui/web-components';
import App from '../ui/AppShell.vue';
import '../ui/style.css';

provideFluentDesignSystem().register(
  fluentBadge(),
  fluentButton(),
  fluentCard(),
  fluentCheckbox(),
  fluentDesignSystemProvider(),
  fluentDivider(),
  fluentNumberField(),
  fluentOption(),
  fluentProgress(),
  fluentSearch(),
  fluentSelect(),
  fluentSwitch(),
  fluentTab(),
  fluentTabPanel(),
  fluentTabs(),
  fluentTextArea(),
  fluentTextField(),
  fluentToolbar(),
  fluentTooltip(),
);

createApp(App).mount('#app');

if ('serviceWorker' in navigator && import.meta.env.PROD) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {
      // PWA 缓存失败不影响主应用使用。
    });
  });
}
