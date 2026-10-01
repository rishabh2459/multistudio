import { AutoEditController } from '@multicam/plugin-core';
import { AutoEditPanel } from '@multicam/plugin-core/ui';
import { createRoot } from 'react-dom/client';

import { BridgeAdapter, BridgeEngineHost, type Invoke } from './bridge';

declare global {
  interface Window {
    multicam: { invoke: Invoke };
  }
}

const invoke: Invoke = (target, method, args) => window.multicam.invoke(target, method, args);
const controller = new AutoEditController(new BridgeAdapter(invoke), new BridgeEngineHost(invoke));
createRoot(document.getElementById('root')!).render(
  <AutoEditPanel controller={controller} hostLabel="DaVinci Resolve" />,
);
