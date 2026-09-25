import { SettingsForm } from '@/components/settings-form';

export default function SettingsPage() {
  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold">Settings</h1>
      <SettingsForm />
    </div>
  );
}
