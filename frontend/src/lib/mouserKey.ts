/**
 * Browser-stored Mouser Search API key (BYOK).
 *
 * Mouser's Search API ToS forbids shared keys, so each user must register
 * their own at mouser.com/api-hub/. The key lives in localStorage and
 * rides on Mouser-related fetches as the `X-Mouser-Key` header.
 */

const STORAGE_KEY = "pedalBench_mouserKey";
const CHANGE_EVENT = "pedalbench-mouser-key-change";

export function getMouserKey(): string | null {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    return v && v.trim() ? v.trim() : null;
  } catch {
    return null;
  }
}

export function setMouserKey(key: string | null): void {
  try {
    if (key && key.trim()) {
      localStorage.setItem(STORAGE_KEY, key.trim());
    } else {
      localStorage.removeItem(STORAGE_KEY);
    }
    window.dispatchEvent(new CustomEvent(CHANGE_EVENT));
  } catch {
    /* localStorage disabled — degrade quietly */
  }
}

export function subscribeToMouserKey(cb: () => void): () => void {
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
