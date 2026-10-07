/**
 * The whole panel: connect -> setup -> progress -> preview -> apply. Hosts render
 * <AutoEditPanel controller={...} ui={spectrumPrimitives} /> and nothing else.
 */
import { useMemo, useState, type CSSProperties, type ReactNode } from 'react';

import { planStats, previewLanes, frameToTimecode } from '../plan';
import type { AutoEditController, FlowState } from '../session';
import type { ClipRole, EditPlan, PlanMethod, Preset, SessionOut } from '../types';
import { useFlow } from './hooks';
import { htmlPrimitives, type Primitives } from './primitives';
import { ToolsPanel } from './ToolsPanel';

export interface PanelProps {
  controller: AutoEditController;
  ui?: Primitives;
  /** Shown in the header ("for Premiere Pro"). */
  hostLabel?: string;
}

const PRESETS: { value: Preset; label: string }[] = [
  { value: 'calm', label: 'Calm (long shots)' },
  { value: 'balanced', label: 'Balanced' },
  { value: 'dynamic', label: 'Dynamic' },
  { value: 'punchy', label: 'Punchy (reels)' },
];
const METHODS: { value: PlanMethod; label: string }[] = [
  { value: 'stacked_enable', label: 'Stacked tracks (enable/disable)' },
  { value: 'cuts', label: 'Cuts on one track' },
  { value: 'multicam', label: 'Multicam clip' },
];
const ROLES: { value: ClipRole; label: string }[] = [
  { value: 'speaker', label: 'Speaker camera' },
  { value: 'wide', label: 'Wide / group camera' },
  { value: 'mic', label: 'Mic (sound only)' },
  { value: 'broll', label: 'B-roll (never auto)' },
];

const box: CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 8,
  padding: 10,
  fontSize: 12,
};
const actions: CSSProperties = { display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 6 };

export function AutoEditPanel({ controller, ui = htmlPrimitives, hostLabel }: PanelProps) {
  const state = useFlow(controller);
  return (
    <div style={box} data-phase={state.phase}>
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <strong>Multicam Studio{hostLabel ? ` for ${hostLabel}` : ''}</strong>
        {state.handshake && (
          <span style={{ opacity: 0.6, fontSize: 10 }}>engine {state.handshake.api_version}</span>
        )}
      </header>
      <Body state={state} controller={controller} ui={ui} />
    </div>
  );
}

function Body({
  state,
  controller,
  ui,
}: {
  state: FlowState;
  controller: AutoEditController;
  ui: Primitives;
}) {
  switch (state.phase) {
    case 'idle':
      return <ConnectView controller={controller} ui={ui} />;
    case 'connecting':
      return <p>Connecting to the engine…</p>;
    case 'setup':
      return <SetupView session={state.session!} controller={controller} ui={ui} />;
    case 'running':
    case 'applying':
      return (
        <ui.Progress
          value={state.progress?.fraction ?? 0}
          label={`${state.phase === 'applying' ? 'Applying' : 'Auto editing'} — ${state.progress?.message || state.progress?.stage || ''}`}
        />
      );
    case 'review':
      return <ReviewView state={state} controller={controller} ui={ui} />;
    case 'applied':
      return <AppliedView state={state} controller={controller} ui={ui} />;
    case 'error':
      return <ErrorView state={state} controller={controller} ui={ui} />;
  }
}

function ConnectView({ controller, ui }: { controller: AutoEditController; ui: Primitives }) {
  return (
    <section>
      <p>Select the camera clips (or a synced sequence), then connect.</p>
      <div style={actions}>
        <ui.Button variant="cta" onClick={() => void controller.connect()}>
          Connect
        </ui.Button>
        <ui.Button onClick={() => void controller.connect(true)}>Start engine</ui.Button>
      </div>
    </section>
  );
}

function SetupView({
  session,
  controller,
  ui,
}: {
  session: SessionOut;
  controller: AutoEditController;
  ui: Primitives;
}) {
  const [names, setNames] = useState<Record<string, string>>({});
  const sw = session.switch;
  const save = (patch: Parameters<AutoEditController['updateSetup']>[0]) =>
    void controller.updateSetup(patch);
  return (
    <section>
      <p style={{ margin: 0 }}>
        <strong>{session.name}</strong> — {session.clips.length} clips
        {session.already_synced ? ' (already synced)' : ' (will be synced)'}
      </p>
      {session.warnings.map((w) => (
        <p key={w} role="alert" style={{ color: '#c9252d', margin: 0 }}>
          {w}
        </p>
      ))}
      <ul style={{ listStyle: 'none', padding: 0, margin: 0 }} aria-label="clips">
        {session.clips.map((c) => (
          <li
            key={c.clip_id}
            style={{ borderBottom: '1px solid rgba(128,128,128,.3)', padding: '4px 0' }}
          >
            <div style={{ fontWeight: 600 }}>{c.name}</div>
            <ui.Select
              label={`Role of ${c.name}`}
              value={c.role}
              options={c.kind === 'audio' ? ROLES.filter((r) => r.value === 'mic') : ROLES}
              onChange={(role) =>
                save({
                  roles: [{ clip_id: c.clip_id, role: role as ClipRole, speaker_label: c.label }],
                })
              }
            />
            {c.role === 'speaker' && (
              <ui.TextField
                label={`Speaker on ${c.name}`}
                value={names[c.clip_id] ?? c.label ?? ''}
                onChange={(v) => {
                  setNames({ ...names, [c.clip_id]: v });
                }}
              />
            )}
          </li>
        ))}
      </ul>
      <ui.Select
        label="Editing style"
        value={session.preset}
        options={PRESETS}
        onChange={(p) => save({ preset: p as Preset })}
      />
      <ui.Slider
        label="Shortest shot"
        min={0.5}
        max={6}
        step={0.1}
        value={sw.min_shot_s}
        format={(v) => `${v.toFixed(1)} s`}
        onChange={(v) => save({ switch: { ...sw, min_shot_s: v } })}
      />
      <ui.Slider
        label="Wide shots"
        min={0}
        max={1}
        step={0.05}
        value={sw.wide_frequency ?? 0.3}
        format={(v) => (v < 0.2 ? 'only when needed' : v > 0.7 ? 'often' : 'sometimes')}
        onChange={(v) => save({ switch: { ...sw, wide_frequency: v } })}
      />
      <ui.Slider
        label="Reaction speed"
        min={0.1}
        max={2}
        step={0.05}
        value={sw.switch_delay_s}
        format={(v) => `${v.toFixed(2)} s`}
        onChange={(v) => save({ switch: { ...sw, switch_delay_s: v } })}
      />
      <ui.Select
        label="Result as"
        value={session.method}
        options={METHODS}
        onChange={(m) => save({ method: m as PlanMethod })}
      />
      <div style={actions}>
        <ui.Button
          variant="cta"
          onClick={async () => {
            const roles = Object.entries(names).map(([clip_id, speaker_label]) => ({
              clip_id,
              role: 'speaker' as const,
              speaker_label,
            }));
            if (roles.length) await controller.updateSetup({ roles });
            await controller.run();
          }}
        >
          Auto Edit
        </ui.Button>
        <ui.Button onClick={() => void controller.loadSelection()}>Use current selection</ui.Button>
      </div>
    </section>
  );
}

function ReviewView({
  state,
  controller,
  ui,
}: {
  state: FlowState;
  controller: AutoEditController;
  ui: Primitives;
}) {
  const plan = state.plan!;
  const session = state.session!;
  return (
    <section>
      <PlanPreview plan={plan} />
      <ui.Select
        label="Result as"
        value={plan.method ?? 'stacked_enable'}
        options={METHODS}
        onChange={(m) => void controller.previewMethod(m as PlanMethod)}
      />
      <ui.Select
        label="Try another style"
        value={session.preset}
        options={PRESETS}
        onChange={(p) => void controller.recut(p as Preset)}
      />
      <div style={actions}>
        <ui.Button
          variant="cta"
          onClick={() => void controller.apply({ method: plan.method ?? 'stacked_enable' })}
        >
          Apply to timeline
        </ui.Button>
        <ui.Button onClick={() => controller.backToSetup()}>Back to setup</ui.Button>
      </div>
      <ToolsPanel state={state} controller={controller} ui={ui} />
    </section>
  );
}

/** Stats + a mini multi-lane timeline; yellow ticks = cuts to check. */
export function PlanPreview({ plan }: { plan: EditPlan }) {
  const stats = useMemo(() => planStats(plan), [plan]);
  const lanes = useMemo(() => previewLanes(plan), [plan]);
  const total = plan.sequence.duration_frames;
  return (
    <div aria-label="plan preview">
      <p style={{ margin: '0 0 4px' }}>
        {stats.cuts} cuts · {stats.averageShotS.toFixed(1)} s average shot ·{' '}
        {frameToTimecode(total, plan.sequence.fps)}
        {stats.lowConfidence > 0 && ` · ${stats.lowConfidence} to check`}
      </p>
      {lanes.map((lane) => (
        <div
          key={lane.clipId}
          style={{ display: 'flex', alignItems: 'center', gap: 6, margin: '2px 0' }}
        >
          <span
            style={{
              width: 70,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
            title={lane.label}
          >
            {lane.label}
          </span>
          <div
            role="img"
            aria-label={`${lane.label}: ${Math.round(lane.share * 100)}% of the edit`}
            style={{
              position: 'relative',
              flex: 1,
              height: 10,
              background: 'rgba(128,128,128,.2)',
            }}
          >
            {lane.live.map((p, i) => (
              <div
                key={i}
                style={{
                  position: 'absolute',
                  left: `${p.from * 100}%`,
                  width: `${Math.max(0.2, (p.to - p.from) * 100)}%`,
                  top: 0,
                  bottom: 0,
                  background: p.confidence !== null && p.confidence < 0.6 ? '#e8a317' : '#2680eb',
                }}
              />
            ))}
          </div>
        </div>
      ))}
      {plan.warnings.map((w) => (
        <p key={w} style={{ margin: 0, opacity: 0.8 }}>
          ⚠ {w}
        </p>
      ))}
    </div>
  );
}

function AppliedView({
  state,
  controller,
  ui,
}: {
  state: FlowState;
  controller: AutoEditController;
  ui: Primitives;
}) {
  const r = state.applied!;
  return (
    <section>
      <p>
        Created <strong>{r.sequenceName}</strong> ({r.via === 'xml' ? 'imported' : 'built'}
        {r.markers ? `, ${r.markers} markers to check` : ''}). Undo removes it in one step.
      </p>
      {r.warnings.map((w) => (
        <p key={w} style={{ margin: 0 }}>
          ⚠ {w}
        </p>
      ))}
      <div style={actions}>
        <ui.Button onClick={() => void controller.recut()}>Re-cut</ui.Button>
        <ui.Button onClick={() => controller.backToSetup()}>Change setup</ui.Button>
        {controller.adapter.readTimeline && (
          <ui.Button onClick={() => void controller.sendFeedback()}>Send my corrections</ui.Button>
        )}
      </div>
      <ToolsPanel state={state} controller={controller} ui={ui} />
    </section>
  );
}

function ErrorView({
  state,
  controller,
  ui,
}: {
  state: FlowState;
  controller: AutoEditController;
  ui: Primitives;
}) {
  const e = state.error!;
  const startable = e.code === 'engine_unreachable';
  return (
    <section role="alert">
      <p style={{ color: '#c9252d', margin: 0 }}>
        <strong>{e.message}</strong>
      </p>
      {e.hint && <p style={{ margin: '4px 0' }}>{e.hint}</p>}
      <div style={actions}>
        {startable ? (
          <ui.Button variant="cta" onClick={() => void controller.connect(true)}>
            Start engine
          </ui.Button>
        ) : (
          <ui.Button variant="cta" onClick={() => void controller.retry()}>
            Try again
          </ui.Button>
        )}
        <ui.Button onClick={() => controller.dismissError()}>Dismiss</ui.Button>
      </div>
    </section>
  );
}

export type { ReactNode };
