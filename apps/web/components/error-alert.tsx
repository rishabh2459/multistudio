import { AlertTriangle } from 'lucide-react';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { ApiError } from '@/lib/api';

export function ErrorAlert({ error, title }: { error: unknown; title?: string }) {
  if (!error) return null;
  const offline = error instanceof ApiError && error.status === 0;
  const message = error instanceof Error ? error.message : String(error);
  return (
    <Alert variant="destructive">
      <AlertTitle className="flex items-center gap-2">
        <AlertTriangle className="size-4" aria-hidden />
        {title ?? (offline ? 'The engine is not running' : 'Something went wrong')}
      </AlertTitle>
      <AlertDescription>
        {message}
        {offline && (
          <p className="mt-1">
            Start it with <code className="font-mono">uv run multicam-api</code>, or check the
            address in Settings.
          </p>
        )}
      </AlertDescription>
    </Alert>
  );
}
