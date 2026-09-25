'use client';

import { ArrowLeft, Radio } from 'lucide-react';
import Link from 'next/link';
import { useEffect, useState } from 'react';

import { ErrorAlert } from '@/components/error-alert';
import { Badge } from '@/components/ui/badge';
import { useCutlist, useLiveJobs, useProject } from '@/lib/queries';

import { ClipSetup } from './clip-setup';
import { ProcessingPanel } from './processing-panel';
import { ResultPanel } from './result-panel';
import { initialStep, Stepper, type Step, type StepId } from './stepper';

export function ProjectView({ id }: { id: string }) {
  const project = useProject(id);
  const cutlist = useCutlist(id);
  const jobs = useLiveJobs(id);
  const [chosen, setChosen] = useState<StepId | null>(null);

  // Pick the starting step once, when the project has loaded; after that the user
  // decides (finishing the auto edit must not yank them to another step).
  const loaded = project.isSuccess && cutlist.isSuccess;
  useEffect(() => {
    if (loaded && chosen === null && project.data && cutlist.data !== undefined) {
      const clips = project.data.clips;
      const ok = clips.length >= 2 && clips.some((c) => c.role === 'speaker');
      setChosen(initialStep(ok ? clips.length : 0, cutlist.data !== null));
    }
  }, [loaded, chosen, project.data, cutlist.data]);

  if (!id) return <ErrorAlert error={new Error('No project selected.')} />;
  if (project.isPending || cutlist.isPending) {
    return <p className="text-muted-foreground">Loading project…</p>;
  }
  if (project.isError) return <ErrorAlert error={project.error} />;

  const p = project.data;
  const cut = cutlist.data?.cutlist ?? null;
  const speakers = p.clips.filter((c) => c.role === 'speaker').length;
  const canProcess = p.clips.length >= 2 && speakers > 0;
  const steps: Step[] = [
    { id: 'setup', label: 'Cameras', done: canProcess, enabled: true },
    { id: 'process', label: 'Auto edit', done: cut !== null, enabled: canProcess },
    { id: 'result', label: 'Export', done: false, enabled: cut !== null },
  ];
  const wanted = chosen ?? initialStep(canProcess ? p.clips.length : 0, cut !== null);
  const step = steps.find((s) => s.id === wanted)?.enabled ? wanted : 'setup';
  const jobList = jobs.data ?? [];

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center gap-3">
        <Link
          href="/"
          className="text-muted-foreground hover:text-foreground"
          aria-label="All projects"
        >
          <ArrowLeft className="size-5" />
        </Link>
        <h1 className="text-2xl font-semibold">{p.name}</h1>
        {jobs.live && (
          <Badge variant="outline" title="Progress updates arrive live">
            <Radio className="size-3" aria-hidden /> Live
          </Badge>
        )}
      </div>
      <Stepper steps={steps} current={step} onSelect={setChosen} />
      <ErrorAlert error={cutlist.error ?? jobs.error} />
      {step === 'setup' && <ClipSetup project={p} onNext={() => setChosen('process')} />}
      {step === 'process' && (
        <ProcessingPanel
          project={p}
          jobs={jobList}
          cutlist={cut}
          onNext={() => setChosen('result')}
        />
      )}
      {step === 'result' && <ResultPanel project={p} jobs={jobList} cutlist={cut} />}
    </div>
  );
}
