import { Plus } from 'lucide-react';
import Link from 'next/link';

import { ProjectList } from '@/components/project-list';
import { buttonVariants } from '@/components/ui/button';

export default function DashboardPage() {
  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Projects</h1>
        <Link href="/new/" className={buttonVariants()}>
          <Plus /> New project
        </Link>
      </div>
      <ProjectList />
    </div>
  );
}
