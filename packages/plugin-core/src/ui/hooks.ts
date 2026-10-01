import { useSyncExternalStore } from 'react';

import type { AutoEditController, FlowState } from '../session';

/** Re-render on every controller state change. */
export function useFlow(controller: AutoEditController): FlowState {
  return useSyncExternalStore(
    (cb) => controller.subscribe(cb),
    () => controller.getState(),
    () => controller.getState(),
  );
}
