/**
 * The extra tools under a finished edit: Jump Cuts (AutoPod's jump cut editor:
 * find pauses, review them, ripple them out as a new sequence) and Social Clips
 * (one sequence per aspect ratio for the In/Out range, watermark, end page,
 * batch export).
 */
import { useState, type CSSProperties } from 'react';

import type { Corner, JumpCutMode, SocialAspect } from '../extras';
import { frameToTimecode } from '../plan';
import type { AutoEditController, FlowState } from '../session';
import type { Primitives } from './primitives';

const section: CSSProperties = {
  borderTop: '1px solid rgba(128,128,128,.3)',
  marginTop: 8,
  paddingTop: 6,
};
const actions: CSSProperties = { display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 6 };
const MAX_LISTED = 40;

const ASPECTS: { value: SocialAspect; label: string }[] = [
  { value: '9:16', label: '9:16 (Reels, Shorts, TikTok)' },
  { value: '4:5', label: '4:5 (Instagram feed)' },
  { value: '1:1', label: '1:1 (square)' },
  { value: '16:9', label: '16:9 (YouTube)' },
];
const CORNERS: { value: Corner; label: string }[] = [
  { value: 'top_left', label: 'Top left' },
  { value: 'top_right', label: 'Top right' },
  { value: 'bottom_left', label: 'Bottom left' },
  { value: 'bottom_right', label: 'Bottom right' },
  { value: 'center', label: 'Centre' },
];
const MODES: { value: JumpCutMode; label: string }[] = [
  { value: 'db', label: 'Loudness cutoff (dB)' },
  { value: 'vad', label: 'Speech detection (noisy rooms)' },
];

export interface ToolsProps {
  state: FlowState;
  controller: AutoEditController;
  ui: Primitives;
}

export function ToolsPanel(props: ToolsProps) {
  return (
    <>
      {props.state.busy && (
        <props.ui.Progress value={props.state.busy.fraction} label={props.state.busy.message} />
      )}
      <JumpCutsView {...props} />
      {props.controller.adapter.importSocial && <SocialView {...props} />}
    </>
  );
}

function JumpCutsView({ state, controller, ui }: ToolsProps) {
  const [mode, setMode] = useState<JumpCutMode>('db');
  const [threshold, setThreshold] = useState(-40);
  const [minSilence, setMinSilence] = useState(0.6);
  const [pad, setPad] = useState(0.15);
  const removals = state.removals;
  const fps = state.plan?.sequence.fps;
  const approved = removals?.removals.filter((r) => r.approved) ?? [];
  const seconds = approved.reduce((acc, r) => acc + r.seconds, 0);
  return (
    <section style={section} aria-label="jump cuts">
      <strong>Jump cuts</strong>
      <ui.Select
        label="Find pauses by"
        value={mode}
        options={MODES}
        onChange={(v) => setMode(v as JumpCutMode)}
      />
      {mode === 'db' && (
        <ui.Slider
          label="Silence below"
          min={-70}
          max={-15}
          step={1}
          value={threshold}
          format={(v) => `${v} dB`}
          onChange={setThreshold}
        />
      )}
      <ui.Slider
        label="Shortest pause to cut"
        min={0.2}
        max={3}
        step={0.05}
        value={minSilence}
        format={(v) => `${v.toFixed(2)} s`}
        onChange={setMinSilence}
      />
      <ui.Slider
        label="Keep around speech"
        min={0}
        max={0.6}
        step={0.01}
        value={pad}
        format={(v) => `${v.toFixed(2)} s`}
        onChange={setPad}
      />
      <div style={actions}>
        <ui.Button
          onClick={() =>
            void controller.findJumpCuts({
              mode,
              threshold_db: threshold,
              min_silence_s: minSilence,
              pad_s: pad,
            })
          }
        >
          Find pauses
        </ui.Button>
      </div>
      {removals && (
        <div>
          <p style={{ margin: '4px 0' }}>
            {approved.length} of {removals.removals.length} pauses approved · {seconds.toFixed(1)} s
            shorter
          </p>
          <ul
            style={{ listStyle: 'none', padding: 0, margin: 0, maxHeight: 160, overflow: 'auto' }}
          >
            {removals.removals.slice(0, MAX_LISTED).map((r) => (
              <li key={r.index}>
                <ui.Checkbox
                  label={`${fps ? frameToTimecode(r.start, fps) : r.start} · ${r.seconds.toFixed(2)} s ${r.kind}`}
                  value={r.approved}
                  onChange={(on) =>
                    void controller.setRemovals(on ? { approve: [r.index] } : { reject: [r.index] })
                  }
                />
              </li>
            ))}
          </ul>
          {removals.removals.length > MAX_LISTED && (
            <p style={{ margin: 0, opacity: 0.7 }}>
              … and {removals.removals.length - MAX_LISTED} more
            </p>
          )}
          <div style={actions}>
            <ui.Button onClick={() => void controller.setRemovals({ all: true })}>
              Approve all
            </ui.Button>
            <ui.Button onClick={() => void controller.setRemovals({ all: false })}>
              Reject all
            </ui.Button>
            <ui.Button
              variant="cta"
              disabled={!approved.length}
              onClick={() => void controller.applyJumpCuts()}
            >
              Apply jump cuts (new sequence)
            </ui.Button>
          </div>
        </div>
      )}
    </section>
  );
}

function SocialView({ state, controller, ui }: ToolsProps) {
  const [aspects, setAspects] = useState<SocialAspect[]>(['9:16']);
  const [watermark, setWatermark] = useState('');
  const [corner, setCorner] = useState<Corner>('bottom_right');
  const [endPage, setEndPage] = useState('');
  const [endSeconds, setEndSeconds] = useState(3);
  const [jumpCuts, setJumpCuts] = useState(false);
  const [queue, setQueue] = useState(false);
  const [preset, setPreset] = useState('');
  const pick = async (purpose: 'picture' | 'preset', set: (v: string) => void) => {
    const path = await controller.adapter.pickFile?.(purpose);
    if (path) set(path);
  };
  const result = state.social;
  return (
    <section style={section} aria-label="social clips">
      <strong>Social clips</strong>
      <p style={{ margin: '2px 0', opacity: 0.8 }}>Mark In and Out on the auto-edit sequence.</p>
      {ASPECTS.map((a) => (
        <ui.Checkbox
          key={a.value}
          label={a.label}
          value={aspects.includes(a.value)}
          onChange={(on) =>
            setAspects(on ? [...aspects, a.value] : aspects.filter((x) => x !== a.value))
          }
        />
      ))}
      <ui.TextField label="Watermark (image file)" value={watermark} onChange={setWatermark} />
      {controller.adapter.pickFile && (
        <ui.Button onClick={() => void pick('picture', setWatermark)}>Choose watermark…</ui.Button>
      )}
      {watermark && (
        <ui.Select
          label="Watermark corner"
          value={corner}
          options={CORNERS}
          onChange={(v) => setCorner(v as Corner)}
        />
      )}
      <ui.TextField label="End page (image or video)" value={endPage} onChange={setEndPage} />
      {controller.adapter.pickFile && (
        <ui.Button onClick={() => void pick('picture', setEndPage)}>Choose end page…</ui.Button>
      )}
      {endPage && (
        <ui.Slider
          label="End page length"
          min={1}
          max={10}
          step={0.5}
          value={endSeconds}
          format={(v) => `${v.toFixed(1)} s`}
          onChange={setEndSeconds}
        />
      )}
      <ui.Checkbox label="Cut the approved pauses" value={jumpCuts} onChange={setJumpCuts} />
      <ui.Checkbox label="Queue renders in Media Encoder" value={queue} onChange={setQueue} />
      {queue && (
        <ui.TextField label="Export preset (.epr, optional)" value={preset} onChange={setPreset} />
      )}
      <div style={actions}>
        <ui.Button
          variant="cta"
          disabled={!aspects.length}
          onClick={() =>
            void controller.createSocial(
              {
                aspects,
                jump_cuts: jumpCuts,
                ...(watermark ? { watermark: { path: watermark, corner } } : {}),
                ...(endPage ? { end_page: { path: endPage, seconds: endSeconds } } : {}),
              },
              { queueRenders: queue, startQueue: queue, ...(preset ? { presetPath: preset } : {}) },
            )
          }
        >
          Create social clips
        </ui.Button>
      </div>
      {result && (
        <div aria-label="social result">
          <p style={{ margin: '4px 0' }}>
            {result.imported.sequences.length} clips in <strong>{result.imported.bin}</strong>
            {result.imported.queued ? ` · ${result.imported.queued} queued to render` : ''}
          </p>
          {[...result.warnings, ...result.imported.warnings].map((w) => (
            <p key={w} style={{ margin: 0 }}>
              ⚠ {w}
            </p>
          ))}
        </div>
      )}
    </section>
  );
}
