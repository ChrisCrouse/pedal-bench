/**
 * Browser-stored Anthropic API key (BYOK).
 *
 * The key lives in `localStorage` and rides on every API call as a
 * `X-Anthropic-Key` header (see api/client.ts). Never sent anywhere
 * except the pedal-bench backend, which forwards it directly to
 * Anthropic without persisting.
 *
 * Self-host users with `ANTHROPIC_API_KEY` in `backend/.env` don't
 * need to set anything here — the backend falls back to env when no
 * header is sent.
 */

const STORAGE_KEY = "pedalBench_anthropicKey";
const CHANGE_EVENT = "pedalbench-api-key-change";

export function getApiKey(): string | null {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    return v && v.trim() ? v.trim() : null;
  } catch {
    // localStorage can be disabled (private browsing, etc.) — degrade quietly.
    return null;
  }
}

export function setApiKey(key: string | null): void {
  try {
    if (key && key.trim()) {
      localStorage.setItem(STORAGE_KEY, key.trim());
    } else {
      localStorage.removeItem(STORAGE_KEY);
    }
    window.dispatchEvent(new CustomEvent(CHANGE_EVENT));
  } catch {
    // Same as above — fail silently.
  }
}

/** Returns an unsubscribe function. Fires on same-tab changes (custom event)
 *  and cross-tab changes (storage event). */
export function subscribeToApiKey(cb: () => void): () => void {
  const onCustom = () => cb();
  const onStorage = (e: StorageEvent) => {
    if (e.key === STORAGE_KEY) cb();
  };
  window.addEventListener(CHANGE_EVENT, onCustom);
  window.addEventListener("storage", onStorage);
  return () => {
    window.removeEventListener(CHANGE_EVENT, onCustom);
    window.removeEventListener("storage", onStorage);
  };
}
