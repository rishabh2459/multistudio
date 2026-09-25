'use client';

import { Film, Plus, Trash2 } from 'lucide-react';
import Link from 'next/link';
import { useState } from 'react';

import { ErrorAlert } from '@/components/error-alert';
import { Badge } from '@/components/ui/badge';
import { Button, buttonVariants } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import type { ProjectSummary } from '@/lib/api';
import { formatRelative } from '@/lib/format';
import { useDeleteProject, useProjects } from '@/lib/queries';

function ProjectCard({ project }: { project: ProjectSummary }) {
  const remove = useDeleteProject();
  const [confirming, setConfirming] = useState(false);
  return (
    <Card data-testid="project-card" className="flex flex-col">
      <CardHeader className="pb-3">
        <CardTitle className="truncate">
          <Link href={`/project/?id=${project.id}`} className="hover:underline">
            {project.name}
          </Link>
        </CardTitle>
        <CardDescription>Edited {formatRelative(project.updated_at)}</CardDescription>
      </CardHeader>
      <CardContent className="mt-auto flex items-center gap-2">
        <Badge variant="secondary">
          {project.clip_count} {project.clip_count === 1 ? 'camera' : 'cameras'}
        </Badge>
        {project.cutlist_version !== null ? (
          <Badge variant="success">Edited</Badge>
        ) : (
          <Badge variant="outline">Not edited yet</Badge>
        )}
        <div className="ml-auto flex gap-1">
          {confirming ? (
            <>
              <Button
                size="sm"
                variant="destructive"
                disabled={remove.isPending}
                onClick={() => remove.mutate(project.id)}
              >
                Delete
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setConfirming(false)}>
                Keep
              </Button>
            </>
          ) : (
            <Button
              size="icon"
              variant="ghost"
              aria-label={`Delete ${project.name}`}
              onClick={() => setConfirming(true)}
            >
              <Trash2 />
            </Button>
          )}
        </div>
      </CardContent>
      {remove.error && (
        <div className="px-5 pb-4">
          <ErrorAlert error={remove.error} />
        </div>
      )}
    </Card>
  );
}

export function ProjectList() {
  const projects = useProjects();
  if (projects.isPending) return <p className="text-muted-foreground">Loading projects…</p>;
  if (projects.isError) return <ErrorAlert error={projects.error} />;
  if (projects.data.length === 0) {
    return (
      <Card className="flex flex-col items-center gap-3 p-10 text-center">
        <Film className="size-10 text-muted-foreground" aria-hidden />
        <h2 className="text-lg font-semibold">No projects yet</h2>
        <p className="max-w-md text-sm text-muted-foreground">
          Add the recordings from each camera. Multicam Studio lines them up by sound and cuts to
          whoever is talking.
        </p>
        <Link href="/new/" className={buttonVariants()}>
          <Plus /> New project
        </Link>
      </Card>
    );
  }
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {projects.data.map((p) => (
        <ProjectCard key={p.id} project={p} />
      ))}
    </div>
  );
}
