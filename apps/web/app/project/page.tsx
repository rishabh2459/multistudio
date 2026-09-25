'use client';

import { useSearchParams } from 'next/navigation';
import { Suspense } from 'react';

import { ProjectView } from '@/components/project/project-view';

// Static export has no dynamic routes, so the project id travels as ?id=...
function ProjectFromQuery() {
  const id = useSearchParams().get('id') ?? '';
  return <ProjectView key={id} id={id} />;
}

export default function ProjectPage() {
  return (
    <Suspense fallback={<p className="text-muted-foreground">Loading project…</p>}>
      <ProjectFromQuery />
    </Suspense>
  );
}
