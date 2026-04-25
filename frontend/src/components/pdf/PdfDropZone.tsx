import { useCallback, useRef, useState } from "react";

interface Props {
  onFile: (file: File) => void;
  /** Optional handler for .diy files (DIYLC). If absent, .diy is rejected. */
  onDiyFile?: (file: File) => void;
  disabled?: boolean;
}

/** Big friendly drop zone + click-to-browse. */
export function PdfDropZone({ onFile, onDiyFile, disabled = false }: Props) {
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      if (disabled) return;
      const files = [...(e.dataTransfer.files ?? [])];
      const pdf = files.find((f) => f.name.toLowerCase().endsWith(".pdf"));
      if (pdf) {
        onFile(pdf);
        return;
      }
      const diy = files.find((f) => f.name.toLowerCase().endsWith(".diy"));
      if (diy && onDiyFile) onDiyFile(diy);
    },
    [onFile, onDiyFile, disabled],
  );

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
      onClick={() => !disabled && inputRef.current?.click()}
      className={[
        "group relative cursor-pointer rounded-lg border-2 border-dashed p-10 text-center transition",
        dragOver
          ? "border-emerald-500 bg-emerald-50 dark:bg-emerald-900/20"
          : "border-zinc-300 bg-zinc-50 hover:border-emerald-400 hover:bg-emerald-50/50 dark:border-zinc-700 dark:bg-zinc-900 dark:hover:border-emerald-500 dark:hover:bg-emerald-900/10",
        disabled ? "pointer-events-none opacity-60" : "",
      ].join(" ")}
    >
      <input
        ref={inputRef}
        type="file"
        accept={onDiyFile ? ".pdf,application/pdf,.diy" : ".pdf,application/pdf"}
        className="sr-only"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) {
            const lower = f.name.toLowerCase();
            if (lower.endsWith(".diy") && onDiyFile) onDiyFile(f);
            else onFile(f);
          }
          e.target.value = "";
        }}
      />
      <div className="text-lg font-semibold">
        Drop a PedalPCB PDF{onDiyFile ? " or DIYLC .diy file" : ""} here
      </div>
      <div className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
        or click to browse. We'll auto-extract the pedal name, enclosure, and BOM.
      </div>
    </div>
  );
}
