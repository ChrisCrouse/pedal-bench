import { useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api, type BOMItem } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";

interface Props {
  slug: string;
  row: BOMItem;
  onClose: () => void;
}

type Verdict = "match" | "mismatch" | "unsure" | "error";

const VERDICT_STYLE: Record<Verdict, { label: string; className: string }> = {
  match: {
    label: "Match",
    className:
      "border-emerald-300 bg-emerald-50 text-emerald-900 dark:border-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-200",
  },
  mismatch: {
    label: "Mismatch — don't solder",
    className:
      "border-red-300 bg-red-50 text-red-900 dark:border-red-700 dark:bg-red-900/30 dark:text-red-200",
  },
  unsure: {
    label: "Can't tell — retake the photo",
    className:
      "border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-700 dark:bg-amber-900/30 dark:text-amber-200",
  },
  error: {
    label: "Error",
    className:
      "border-zinc-300 bg-zinc-50 text-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200",
  },
};

export function VerifyComponentDialog({ slug, row, onClose }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);

  const verify = useMutation({
    mutationFn: (f: File) => api.verify.component(slug, row.location, f),
  });

  const onPick = (f: File | null) => {
    if (!f) return;
    setFile(f);
    if (preview) URL.revokeObjectURL(preview);
    setPreview(URL.createObjectURL(f));
    verify.reset();
  };

  const handleClose = () => {
    if (preview) URL.revokeObjectURL(preview);
    setPreview(null);
    setFile(null);
    verify.reset();
    onClose();
  };

  const result = verify.data;
  const style = result ? VERDICT_STYLE[result.verdict] : null;

  return (
    <Dialog
      open={true}
      onClose={handleClose}
      title={`Verify ${row.location}`}
      maxWidth="lg"
    >
      <div className="space-y-4">
        <div className="rounded-md border border-zinc-200 bg-zinc-50 p-3 text-sm dark:border-zinc-800 dark:bg-zinc-900">
          <div className="font-medium">BOM expects:</div>
          <div className="mt-1 text-zinc-700 dark:text-zinc-300">
            <span className="font-mono">{row.location}</span> ·{" "}
            <span className="font-semibold">{row.value || "(no value)"}</span>{" "}
            · {row.type || "(no type)"}
          </div>
        </div>

        <input
          ref={inputRef}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          className="sr-only"
          capture="environment"
          onChange={(e) => onPick(e.target.files?.[0] ?? null)}
        />

        {!preview ? (
          <div className="rounded-md border-2 border-dashed border-zinc-300 p-6 text-center dark:border-zinc-700">
            <div className="text-sm text-zinc-600 dark:text-zinc-400">
              Take or pick a photo of the component.
            </div>
            <Button
              variant="primary"
              size="sm"
              className="mt-3"
              onClick={() => inputRef.current?.click()}
            >
              Choose photo
            </Button>
          </div>
        ) : (
          <div className="space-y-3">
            <img
              src={preview}
              alt={`${row.location} candidate`}
              className="mx-auto max-h-80 rounded border border-zinc-200 object-contain dark:border-zinc-800"
            />
            <div className="flex justify-center gap-2">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => inputRef.current?.click()}
              >
                Pick different photo
              </Button>
              <Button
                variant="primary"
                size="sm"
                disabled={verify.isPending || !file}
                onClick={() => file && verify.mutate(file)}
              >
                {verify.isPending ? "Checking…" : "Verify"}
              </Button>
            </div>
          </div>
        )}

        {verify.isError && (
          <div className="rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/30 dark:text-red-300">
            {(verify.error as Error).message}
          </div>
        )}

        {result && style && (
          <div
            className={`rounded-md border p-3 text-sm ${style.className}`}
            role="status"
          >
            <div className="font-semibold">{style.label}</div>
            <div className="mt-1">{result.explanation}</div>
            {(result.guess_value || result.guess_type) && (
              <div className="mt-2 text-xs opacity-80">
                Photo looks like:{" "}
                {result.guess_value && (
                  <span className="font-mono">{result.guess_value}</span>
                )}
                {result.guess_value && result.guess_type ? " · " : ""}
                {result.guess_type}
              </div>
            )}
          </div>
        )}

        <div className="flex justify-end pt-2">
          <Button variant="ghost" onClick={handleClose}>
            Close
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
