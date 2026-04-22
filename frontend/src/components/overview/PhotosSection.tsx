import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createPortal } from "react-dom";
import { api, type Photo } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";

interface Props {
  slug: string;
}

export function PhotosSection({ slug }: Props) {
  const qc = useQueryClient();
  const photosQuery = useQuery({
    queryKey: ["projects", slug, "photos"],
    queryFn: () => api.photos.list(slug),
  });

  const [dragOver, setDragOver] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [pendingCount, setPendingCount] = useState(0);
  const [lightbox, setLightbox] = useState<Photo | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const uploadMutation = useMutation({
    mutationFn: (file: File) => api.photos.upload(slug, file),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects", slug, "photos"] });
    },
  });

  async function handleFiles(list: FileList | File[]) {
    const files = Array.from(list).filter((f) => f.type.startsWith("image/"));
    if (!files.length) {
      setUploadError("No image files found in that drop.");
      return;
    }
    setUploadError(null);
    setPendingCount(files.length);
    for (const f of files) {
      try {
        await uploadMutation.mutateAsync(f);
      } catch (err) {
        setUploadError(`${f.name}: ${(err as Error).message}`);
      } finally {
        setPendingCount((n) => Math.max(0, n - 1));
      }
    }
  }

  const photos = photosQuery.data ?? [];

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="font-semibold">Photos</div>
          <div className="text-xs text-zinc-500">
            {photos.length} {photos.length === 1 ? "photo" : "photos"}
          </div>
        </div>
      </CardHeader>
      <CardBody className="space-y-4">
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            if (e.dataTransfer.files?.length) void handleFiles(e.dataTransfer.files);
          }}
          className={`rounded-md border-2 border-dashed p-4 text-center text-sm transition ${
            dragOver
              ? "border-emerald-500 bg-emerald-50 dark:bg-emerald-900/20"
              : "border-zinc-300 text-zinc-600 dark:border-zinc-700 dark:text-zinc-400"
          }`}
        >
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept="image/jpeg,image/png,image/webp"
            className="sr-only"
            onChange={(e) => {
              if (e.target.files?.length) void handleFiles(e.target.files);
              e.target.value = "";
            }}
          />
          <div className="mb-2">
            {pendingCount > 0
              ? `Uploading ${pendingCount}…`
              : "Drop build shots, gut shots, and debug photos here."}
          </div>
          <Button
            variant="primary"
            size="sm"
            onClick={() => fileInputRef.current?.click()}
            disabled={pendingCount > 0}
          >
            Add photos
          </Button>
        </div>

        {uploadError && (
          <div className="rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/30 dark:text-red-300">
            {uploadError}
          </div>
        )}

        {photos.length === 0 ? (
          <div className="text-center text-sm text-zinc-500">
            No photos yet.
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {photos.map((photo) => (
              <PhotoCard
                key={photo.filename}
                slug={slug}
                photo={photo}
                onOpen={() => setLightbox(photo)}
              />
            ))}
          </div>
        )}
      </CardBody>

      {lightbox && (
        <Lightbox photo={lightbox} onClose={() => setLightbox(null)} />
      )}
    </Card>
  );
}

function PhotoCard({
  slug,
  photo,
  onOpen,
}: {
  slug: string;
  photo: Photo;
  onOpen: () => void;
}) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(photo.caption);

  useEffect(() => {
    setDraft(photo.caption);
  }, [photo.caption]);

  const captionMutation = useMutation({
    mutationFn: (next: string) => api.photos.updateCaption(slug, photo.filename, next),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects", slug, "photos"] });
      setEditing(false);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => api.photos.delete(slug, photo.filename),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects", slug, "photos"] });
    },
  });

  const date = new Date(photo.uploaded_at);
  const dateLabel = isNaN(date.valueOf())
    ? photo.uploaded_at
    : date.toLocaleString();

  return (
    <div className="group overflow-hidden rounded-md border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
      <div className="relative">
        <button
          type="button"
          onClick={onOpen}
          className="block aspect-square w-full overflow-hidden bg-zinc-100 dark:bg-zinc-800"
        >
          <img
            src={photo.url}
            alt={photo.caption || photo.filename}
            loading="lazy"
            className="h-full w-full object-cover transition group-hover:opacity-90"
          />
        </button>
        <button
          type="button"
          onClick={() => {
            if (confirm("Delete this photo?")) deleteMutation.mutate();
          }}
          disabled={deleteMutation.isPending}
          aria-label="Delete photo"
          className="absolute right-2 top-2 rounded-full bg-black/50 px-2 py-0.5 text-xs text-white opacity-0 transition hover:bg-red-600 group-hover:opacity-100 focus:opacity-100"
        >
          ×
        </button>
      </div>
      <div className="space-y-1 p-2 text-xs">
        <div className="text-zinc-500">{dateLabel}</div>
        {editing ? (
          <div className="flex gap-1">
            <input
              autoFocus
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") captionMutation.mutate(draft);
                if (e.key === "Escape") {
                  setDraft(photo.caption);
                  setEditing(false);
                }
              }}
              onBlur={() => captionMutation.mutate(draft)}
              placeholder="Caption…"
              className="min-w-0 flex-1 rounded border border-zinc-300 bg-white px-1.5 py-0.5 focus:border-emerald-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900"
            />
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setEditing(true)}
            className="w-full text-left text-zinc-700 hover:text-emerald-600 dark:text-zinc-300"
          >
            {photo.caption || (
              <span className="italic text-zinc-400">add caption…</span>
            )}
          </button>
        )}
      </div>
    </div>
  );
}

function Lightbox({ photo, onClose }: { photo: Photo; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [onClose]);

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-black/90 p-4"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <img
        src={photo.url}
        alt={photo.caption || photo.filename}
        className="max-h-[90vh] max-w-full object-contain"
      />
      {photo.caption && (
        <div className="mt-3 max-w-2xl text-center text-sm text-zinc-200">
          {photo.caption}
        </div>
      )}
      <button
        type="button"
        onClick={onClose}
        aria-label="Close"
        className="absolute right-4 top-4 rounded-full bg-white/10 px-3 py-1 text-sm text-white hover:bg-white/20"
      >
        Close
      </button>
    </div>,
    document.body,
  );
}
