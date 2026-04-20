import { useCallback, useRef, useState } from "react";

/**
 * A state-with-history hook that supports undo/redo with transaction
 * coalescing. Good for interactive editors where a drag shouldn't become
 * 40 undo steps.
 *
 * Use:
 *   const undoable = useUndoable<Hole[]>([]);
 *   undoable.set(next);             // regular state update; pushes history
 *   undoable.beginTransaction();    // e.g., on mousedown at drag start
 *   undoable.set(dragMove1);        //   ↓
 *   undoable.set(dragMove2);        //   ↓ no history push during txn
 *   undoable.endTransaction();      // e.g., on mouseup
 *   undoable.undo();                // Ctrl+Z
 *   undoable.redo();                // Ctrl+Shift+Z
 *   undoable.reset(valueFromServer) // syncing without history push
 */
export interface Undoable<T> {
  value: T;
  set: (updater: T | ((prev: T) => T)) => void;
  undo: () => void;
  redo: () => void;
  canUndo: boolean;
  canRedo: boolean;
  beginTransaction: () => void;
  endTransaction: () => void;
  /** Replace value WITHOUT pushing a history entry (e.g., server sync). */
  reset: (value: T) => void;
}

const MAX_HISTORY = 100;

export function useUndoable<T>(initial: T): Undoable<T> {
  const [value, setValueRaw] = useState<T>(initial);
  const pastRef = useRef<T[]>([]);
  const futureRef = useRef<T[]>([]);
  const inTransactionRef = useRef(false);
  // Bump to force canUndo / canRedo re-renders without duplicating state.
  const [, bump] = useState(0);
  const tick = useCallback(() => bump((n) => n + 1), []);

  const set = useCallback<Undoable<T>["set"]>((updater) => {
    setValueRaw((prev) => {
      const next =
        typeof updater === "function"
          ? (updater as (p: T) => T)(prev)
          : updater;
      // Skip history within an active transaction (the begin-transaction
      // snapshot is the single undo point for the whole drag).
      if (!inTransactionRef.current) {
        pastRef.current.push(prev);
        if (pastRef.current.length > MAX_HISTORY) pastRef.current.shift();
        futureRef.current = [];
      }
      return next;
    });
    tick();
  }, [tick]);

  const beginTransaction = useCallback(() => {
    if (inTransactionRef.current) return;
    setValueRaw((prev) => {
      pastRef.current.push(prev);
      if (pastRef.current.length > MAX_HISTORY) pastRef.current.shift();
      futureRef.current = [];
      return prev;
    });
    inTransactionRef.current = true;
    tick();
  }, [tick]);

  const endTransaction = useCallback(() => {
    inTransactionRef.current = false;
    tick();
  }, [tick]);

  const undo = useCallback(() => {
    if (pastRef.current.length === 0) return;
    setValueRaw((prev) => {
      const popped = pastRef.current.pop()!;
      futureRef.current.push(prev);
      return popped;
    });
    tick();
  }, [tick]);

  const redo = useCallback(() => {
    if (futureRef.current.length === 0) return;
    setValueRaw((prev) => {
      const popped = futureRef.current.pop()!;
      pastRef.current.push(prev);
      return popped;
    });
    tick();
  }, [tick]);

  const reset = useCallback<Undoable<T>["reset"]>((v) => {
    pastRef.current = [];
    futureRef.current = [];
    inTransactionRef.current = false;
    setValueRaw(v);
    tick();
  }, [tick]);

  return {
    value,
    set,
    undo,
    redo,
    canUndo: pastRef.current.length > 0,
    canRedo: futureRef.current.length > 0,
    beginTransaction,
    endTransaction,
    reset,
  };
}
