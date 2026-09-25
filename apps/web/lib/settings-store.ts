import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

export type Theme = 'system' | 'light' | 'dark';
export type Preset = 'calm' | 'balanced' | 'dynamic';

export interface Settings {
  /** Only used in a plain browser; the desktop app provides these itself. */
  apiUrl: string;
  apiToken: string;
  /** Folder for rendered videos ('' = the project's folder in the app data). */
  outputFolder: string;
  encoder: string; // 'auto' or an ffmpeg encoder name
  renderPreset: string; // youtube-1080p, youtube-4k, master, draft
  editPreset: Preset; // default for new projects
  theme: Theme;
}

export const DEFAULT_SETTINGS: Settings = {
  apiUrl: process.env.NEXT_PUBLIC_API_URL ?? 'http://127.0.0.1:8765',
  apiToken: '',
  outputFolder: '',
  encoder: 'auto',
  renderPreset: 'youtube-1080p',
  editPreset: 'balanced',
  theme: 'system',
};

interface SettingsState extends Settings {
  update: (patch: Partial<Settings>) => void;
  reset: () => void;
}

/** User preferences, kept in localStorage (per machine, never sent anywhere). */
export const useSettings = create<SettingsState>()(
  persist(
    (set) => ({
      ...DEFAULT_SETTINGS,
      update: (patch) => set(patch),
      reset: () => set(DEFAULT_SETTINGS),
    }),
    {
      name: 'multicam-settings',
      version: 1,
      storage: createJSONStorage(() => localStorage),
      // Pages are pre-rendered with the defaults; <Providers> loads the saved
      // values after mount so the first client render matches the HTML.
      skipHydration: true,
      // Store only the settings, not the functions.
      partialize: (state): Settings =>
        Object.fromEntries(
          (Object.keys(DEFAULT_SETTINGS) as (keyof Settings)[]).map((key) => [key, state[key]]),
        ) as unknown as Settings,
    },
  ),
);
