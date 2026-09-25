'use client';

import { useRouter } from 'next/navigation';
import { useState, type FormEvent } from 'react';

import { ErrorAlert } from '@/components/error-alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select } from '@/components/ui/select';
import { useCreateProject } from '@/lib/queries';
import { useSettings, type Preset } from '@/lib/settings-store';

export const PRESET_HELP: Record<Preset, string> = {
  calm: 'Few, long shots. Good for interviews and lectures.',
  balanced: 'A natural rhythm for most podcasts.',
  dynamic: 'Quicker cuts and more reactions.',
};

export function NewProjectForm() {
  const router = useRouter();
  const defaultPreset = useSettings((s) => s.editPreset);
  const [name, setName] = useState('');
  const [preset, setPreset] = useState<Preset>(defaultPreset);
  const create = useCreateProject();

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    create.mutate(
      { name: name.trim(), preset },
      { onSuccess: (project) => router.push(`/project/?id=${project.id}`) },
    );
  }

  return (
    <Card className="mx-auto max-w-lg">
      <CardHeader>
        <CardTitle>New project</CardTitle>
        <CardDescription>Give it a name; you add the camera files next.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="project-name">Name</Label>
            <Input
              id="project-name"
              value={name}
              maxLength={200}
              placeholder="Episode 12 – Guest name"
              autoFocus
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="project-preset">Editing style</Label>
            <Select
              id="project-preset"
              value={preset}
              onChange={(e) => setPreset(e.target.value as Preset)}
            >
              <option value="calm">Calm</option>
              <option value="balanced">Balanced</option>
              <option value="dynamic">Dynamic</option>
            </Select>
            <p className="text-xs text-muted-foreground">{PRESET_HELP[preset]}</p>
          </div>
          <ErrorAlert error={create.error} />
          <Button type="submit" disabled={!name.trim() || create.isPending}>
            {create.isPending ? 'Creating…' : 'Create project'}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
