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
