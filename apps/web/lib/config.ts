import { desktop } from './desktop';
import { useSettings } from './settings-store';

export interface ApiConfig {
  base: string;
  token: string;
}

/** Where the API is: the desktop bridge wins, then the user's settings. */
export function apiConfig(): ApiConfig {
  const bridge = desktop();
  const settings = useSettings.getState();
  const base = (bridge?.apiBase ?? settings.apiUrl).replace(/\/+$/, '');
  return { base, token: bridge?.apiToken ?? settings.apiToken };
}

/** Absolute URL for a GET resource that the browser loads itself
 *  (EventSource, <video src>): the token has to travel in the query string. */
export function resourceUrl(path: string, config: ApiConfig = apiConfig()): string {
  const url = new URL(config.base + path);
  if (config.token) url.searchParams.set('token', config.token);
  return url.toString();
}
