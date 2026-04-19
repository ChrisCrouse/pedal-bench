import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api, type Hole } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";

interface Props {
  open: boolean;
  onClose: () => void;
  onImport: (holes: Hole[], mode: "replace" | "append") => void;
}

const EXAMPLE = `side,diameter,x,y,label
A,12.2,0,-45.1,FOOTSWITCH
A,7.2,-16.5,38.1,LEVEL
A,7.2,16.5,38.1,DRIVE
A,7.2,-16.5,12.7,BASS
A,7.2,16.5,12.7,TREBLE
A,4.4,0,25.4,LED
B,9.7,-15.2,5.75,INPUT
B,9.7,15.2,5.75,OUTPUT
B,8.1,0,-4.4,DC`;

export function TaydaPasteDialog({ open, onClose, onImport }: Props) {
  const [text, setText] = useState(EXAMPLE);
  const [mode, setMode] = useState<"replace" | "append">("replace");
  const [error, setError] = useState<string | null>(null);

  const parse = useMutation({
    mutationFn: (t: string) => api.tayda.parse(t),
    onSuccess: (holes) => {
      setError(null);
      onImport(holes, mode);
      onClose();
    },
    onError: (err) => setError(err instanceof Error ? err.message : String(err)),
  });

  return (
    <Dialog open={open} onClose={onClose} title="Paste Tayda coordinates" maxWidth="xl">
      <div className="space-y-4">
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          Paste CSV, TSV, or JSON from the Tayda Box Tool. Columns: <code>side</code>,{" "}
          <code>diameter</code>, <code>x</code>, <code>y</code> (label optional). Headers
          optional — positional format also works.
        </p>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={14}
          spellCheck={false}
          className="block w-full rounded-md border border-zinc-300 bg-white px-3 py-2 font-mono text-xs shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/30 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
        />
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="radio"
              name="mode"
              checked={mode === "replace"}
              onChange={() => setMode("replace")}
            />
            Replace existing holes
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="radio"
              name="mode"
              checked={mode === "append"}
              onChange={() => setMode("append")}
            />
            Append
          </label>
        </div>
        {error && (
          <div className="rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/30 dark:text-red-300">
            {error}
          </div>
        )}
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="primary"
            disabled={parse.isPending || !text.trim()}
            onClick={() => parse.mutate(text)}
          >
            {parse.isPending ? "Parsing…" : "Import"}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
