import { Check } from 'lucide-react';

import { cn } from '@/lib/utils';

export type StepId = 'setup' | 'process' | 'result';

export interface Step {
  id: StepId;
  label: string;
  done: boolean;
  enabled: boolean;
}

export function Stepper({
  steps,
  current,
  onSelect,
}: {
  steps: Step[];
  current: StepId;
  onSelect: (id: StepId) => void;
}) {
  return (
    <nav aria-label="Steps">
      <ol className="flex flex-wrap items-center gap-2">
        {steps.map((step, i) => {
          const active = step.id === current;
          return (
            <li key={step.id} className="flex items-center gap-2">
              {i > 0 && <span className="h-px w-6 bg-border" aria-hidden />}
              <button
                type="button"
                disabled={!step.enabled}
                aria-current={active ? 'step' : undefined}
                onClick={() => onSelect(step.id)}
                className={cn(
                  'flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-50',
                  active ? 'border-primary bg-primary text-primary-foreground' : 'hover:bg-accent',
                )}
              >
                <span
                  className={cn(
                    'flex size-5 items-center justify-center rounded-full text-xs',
                    active ? 'bg-primary-foreground/20' : 'bg-muted',
                  )}
                >
                  {step.done ? <Check className="size-3" aria-label="done" /> : i + 1}
                </span>
                {step.label}
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

/** Which step to open first for a project in this state. */
export function initialStep(clipCount: number, hasCutlist: boolean): StepId {
  if (hasCutlist) return 'result';
  return clipCount >= 2 ? 'process' : 'setup';
}
