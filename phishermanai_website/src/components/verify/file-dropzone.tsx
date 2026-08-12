"use client";

import { useCallback, useRef, useState } from "react";
import { FileText, Upload, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { MAX_UPLOAD_BYTES } from "@/lib/engine-client";
import { cn } from "@/lib/utils";

const ACCEPT = ".eml,message/rfc822,image/png,image/jpeg,image/webp,application/pdf";

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function FileDropzone({
  file,
  onSelect,
  onError,
  disabled,
}: {
  file: File | null;
  onSelect: (file: File | null) => void;
  onError: (message: string | null) => void;
  disabled?: boolean;
}) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const accept = useCallback(
    (candidate: File | undefined) => {
      if (!candidate) return;
      if (candidate.size > MAX_UPLOAD_BYTES) {
        onError(
          `${candidate.name} is ${formatBytes(candidate.size)}. The engine rejects anything over 12 MB.`,
        );
        return;
      }
      if (candidate.size === 0) {
        onError(`${candidate.name} is empty.`);
        return;
      }
      onError(null);
      onSelect(candidate);
    },
    [onError, onSelect],
  );

  if (file) {
    return (
      <div className="flex items-center gap-4 rounded-xl border border-primary/40 bg-primary/6 p-5">
        <span className="grid size-10 shrink-0 place-items-center rounded-lg border border-primary/25 bg-primary/10 text-primary">
          <FileText className="size-5" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[0.9375rem] font-medium">{file.name}</p>
          <p className="mt-1 font-mono text-xs text-foreground/45">
            {formatBytes(file.size)} · {file.type || "type not reported"}
          </p>
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="size-9 shrink-0"
          onClick={() => {
            onSelect(null);
            onError(null);
            if (inputRef.current) inputRef.current.value = "";
          }}
          disabled={disabled}
        >
          <X className="size-4" />
          <span className="sr-only">Remove {file.name}</span>
        </Button>
      </div>
    );
  }

  return (
    <div
      onDragOver={(event) => {
        event.preventDefault();
        if (!disabled) setDragging(true);
      }}
      onDragLeave={(event) => {
        event.preventDefault();
        setDragging(false);
      }}
      onDrop={(event) => {
        event.preventDefault();
        setDragging(false);
        if (disabled) return;
        accept(event.dataTransfer.files?.[0]);
      }}
      className={cn(
        "rounded-xl border-2 border-dashed transition-colors",
        dragging ? "border-primary bg-primary/8" : "border-border bg-card",
        disabled && "opacity-60",
      )}
    >
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        disabled={disabled}
        className="flex w-full flex-col items-center gap-3 px-6 py-12 text-center outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
      >
        <span
          className={cn(
            "grid size-12 place-items-center rounded-full border",
            dragging
              ? "border-primary bg-primary/15 text-primary"
              : "border-border bg-muted text-foreground/40",
          )}
        >
          <Upload className="size-5" aria-hidden />
        </span>
        <span className="text-[0.9375rem] font-medium">
          {dragging ? "Drop it here" : "Drag an email here, or click to browse"}
        </span>
        <span className="font-serif text-sm text-foreground/50">
          .eml from your mail client, or a screenshot or PDF of the message. Up to 12 MB.
        </span>
      </button>

      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT}
        className="sr-only"
        onChange={(event) => accept(event.target.files?.[0])}
        disabled={disabled}
      />
    </div>
  );
}
