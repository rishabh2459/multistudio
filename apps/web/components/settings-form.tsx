'use client';

import { CheckCircle2, FolderOpen, RotateCcw } from 'lucide-react';
import type { ReactNode } from 'react';

import { ErrorAlert } from '@/components/error-alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select } from '@/components/ui/select';
import { desktop } from '@/lib/desktop';
import { useHealth, useSystemInfo } from '@/lib/queries';
import { useSettings, type Preset, type Theme } from '@/lib/settings-store';

import { RENDER_PRESET_LABELS } from './project/result-panel';

function Field({
  id,
  label,
  hint,
  children,
}: {
  id: string;
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      {children}
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

function EngineInfo() {
  const health = useHealth();
  const info = useSystemInfo(false);
  if (health.isError) return <ErrorAlert error={health.error} />;
  if (!info.data) return <p className="text-sm text-muted-foreground">Checking the engine…</p>;
  const d = info.data;
  return (
    <dl className="grid grid-cols-[10rem_1fr] gap-x-4 gap-y-1 text-sm">
      <dt className="text-muted-foreground">Engine</dt>
      <dd className="flex items-center gap-1">
        <CheckCircle2 className="size-4 text-success" aria-hidden /> {d.engine_version} (API{' '}
        {d.api_version})
      </dd>
      <dt className="text-muted-foreground">FFmpeg</dt>
      <dd>{d.ffmpeg_version ?? 'not found'}</dd>
      <dt className="text-muted-foreground">AI speech model</dt>
      <dd>{d.vad_model_available ? 'installed' : 'missing (loudness detection is used)'}</dd>
      <dt className="text-muted-foreground">Data folder</dt>
      <dd className="truncate font-mono text-xs" title={d.data_dir}>
        {d.data_dir}
      </dd>
    </dl>
  );
}

export function SettingsForm() {
  const s = useSettings();
  const bridge = desktop();

  async function pickFolder() {
    const picked = await bridge?.pickFolder?.({ title: 'Default folder for videos' });
    if (picked) s.update({ outputFolder: picked });
  }

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle>Export defaults</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <Field id="s-render" label="Quality">
            <Select
              id="s-render"
              value={s.renderPreset}
              onChange={(e) => s.update({ renderPreset: e.target.value })}
            >
              {Object.entries(RENDER_PRESET_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
          </Field>
          <Field id="s-encoder" label="Encoder" hint="'auto' picks the fastest one that works.">
            <Input
              id="s-encoder"
              value={s.encoder}
              onChange={(e) => s.update({ encoder: e.target.value || 'auto' })}
            />
          </Field>
          <Field
            id="s-folder"
            label="Save videos in"
            hint="Empty: inside the project's data folder."
          >
            <div className="flex gap-2">
              <Input
                id="s-folder"
                value={s.outputFolder}
                onChange={(e) => s.update({ outputFolder: e.target.value })}
              />
              {bridge?.pickFolder && (
                <Button
                  variant="outline"
                  size="icon"
                  aria-label="Choose folder"
                  onClick={() => void pickFolder()}
                >
                  <FolderOpen />
                </Button>
              )}
            </div>
          </Field>
          <Field id="s-preset" label="Editing style for new projects">
            <Select
              id="s-preset"
              value={s.editPreset}
              onChange={(e) => s.update({ editPreset: e.target.value as Preset })}
            >
              <option value="calm">Calm</option>
              <option value="balanced">Balanced</option>
              <option value="dynamic">Dynamic</option>
            </Select>
          </Field>
          <Field id="s-theme" label="Appearance">
            <Select
              id="s-theme"
              value={s.theme}
              onChange={(e) => s.update({ theme: e.target.value as Theme })}
            >
              <option value="system">Match the system</option>
              <option value="light">Light</option>
              <option value="dark">Dark</option>
            </Select>
          </Field>
        </CardContent>
      </Card>

      {!bridge?.apiBase && (
        <Card>
          <CardHeader>
            <CardTitle>Engine connection</CardTitle>
            <CardDescription>
              Only needed in a browser; the desktop app connects by itself.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            <Field id="s-api" label="Address">
              <Input
                id="s-api"
                value={s.apiUrl}
                onChange={(e) => s.update({ apiUrl: e.target.value })}
              />
            </Field>
            <Field id="s-token" label="Token" hint="Only if the engine was started with a token.">
              <Input
                id="s-token"
                type="password"
                value={s.apiToken}
                onChange={(e) => s.update({ apiToken: e.target.value })}
              />
            </Field>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>About this computer</CardTitle>
        </CardHeader>
        <CardContent>
          <EngineInfo />
        </CardContent>
      </Card>

      <Button variant="ghost" className="self-start" onClick={s.reset}>
        <RotateCcw /> Reset settings
      </Button>
    </div>
  );
}
