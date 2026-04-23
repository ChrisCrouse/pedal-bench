/**
 * Browser-stored Tayda Kits API token (BYOK, second axis).
 *
 * Mirrors lib/apiKey.ts exactly in shape — separate storage key so the
 * Tayda token is independent of the Anthropic one. Sent only on the
 * Tayda push call (not on every request) so it doesn't leak to endpoints
 * that don't need it.
 *
 * Never persisted server-side; our backend forwards to Tayda and drops.
 */

const STORAGE_KEY = "pedalBench_taydaToken";
const CHANGE_EVENT = "pedalbench-tayda-token-change";

export function getTaydaToken(): string | null {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    return v && v.trim() ? v.trim() : null;
  } catch {
    return null;
  }
}

export function setTaydaToken(token: string | null): void {
  try {
    if (token && token.trim()) {
      localStorage.setItem(STORAGE_KEY, token.trim());
    } else {
      localStorage.removeItem(STORAGE_KEY);
    }
    window.dispatchEvent(new CustomEvent(CHANGE_EVENT));
  } catch {
    // localStorage unavailable — fail silently.
  }
}

export function subscribeToTaydaToken(cb: () => void): () => void {
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
