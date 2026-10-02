"use client";

import { useEffect } from "react";
import {
  AlertCircle,
  FileArchive,
  File as FileIcon,
  FileSpreadsheet,
  FileText,
  Headphones,
  ImageIcon,
  Trash2,
  Upload,
  Video,
  X,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  formatBytes,
  useFileUpload,
  type FileMetadata,
  type FileWithPreview,
} from "@/hooks/use-file-upload";
import { cn } from "@/lib/utils";

const ICON_MAP = [
  {
    icon: FileText,
    test: (type: string, name: string) =>
      type.includes("pdf") ||
      type.includes("word") ||
      /\.(pdf|docx?)$/i.test(name),
  },
  {
    icon: FileArchive,
    test: (type: string, name: string) =>
      type.includes("zip") || type.includes("archive") || /\.(zip|rar)$/i.test(name),
  },
  {
    icon: FileSpreadsheet,
    test: (type: string, name: string) =>
      type.includes("excel") || /\.xlsx?$/i.test(name),
  },
  { icon: Video, test: (type: string) => type.startsWith("video/") },
  { icon: Headphones, test: (type: string) => type.startsWith("audio/") },
  { icon: ImageIcon, test: (type: string) => type.startsWith("image/") },
];

function getFileIcon(entry: FileWithPreview) {
  const { type, name } =
    entry.file instanceof File
      ? { type: entry.file.type, name: entry.file.name }
      : (entry.file as FileMetadata);

  return ICON_MAP.find((item) => item.test(type ?? "", name))?.icon ?? FileIcon;
}

export type FileUploadProps = {
  /** Comma-separated accept list, e.g. ".mp4,.wav" or "image/*". */
  accept?: string;
  multiple?: boolean;
  maxFiles?: number;
  maxSizeMB?: number;
  disabled?: boolean;
  className?: string;
  /** Headline shown in the empty state. */
  title?: string;
  /** Caption under the headline; defaults to the max-files/size summary. */
  hint?: string;
  /** Label for the empty-state select button. */
  selectLabel?: string;
  /** Real 0–100 upload percentage; `null` hides the progress bars. */
  uploadProgress?: number | null;
  onFilesChange?: (files: File[]) => void;
};

export function FileUpload({
  accept = "*",
  multiple = false,
  maxFiles = 1,
  maxSizeMB = 25,
  disabled = false,
  className,
  title = "Drop your files here",
  hint,
  selectLabel = "Select files",
  uploadProgress = null,
  onFilesChange,
}: FileUploadProps) {
  const maxSize = maxSizeMB * 1024 * 1024;

  const [{ files, isDragging, errors }, actions] = useFileUpload({
    accept,
    multiple,
    maxFiles: multiple ? maxFiles : 1,
    maxSize,
  });

  // Hand the parent plain File objects whenever the selection changes.
  useEffect(() => {
    onFilesChange?.(
      files
        .map((entry) => entry.file)
        .filter((file): file is File => file instanceof File),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [files]);

  const isUploading = uploadProgress !== null && uploadProgress < 100;
  const inputProps = actions.getInputProps({ disabled });

  return (
    <div className={cn("flex flex-col gap-2", className)}>
      <div
        data-dragging={isDragging || undefined}
        data-files={files.length > 0 || undefined}
        onDragEnter={actions.handleDragEnter}
        onDragLeave={actions.handleDragLeave}
        onDragOver={actions.handleDragOver}
        onDrop={actions.handleDrop}
        className={cn(
          "relative flex min-h-52 flex-col items-center overflow-hidden rounded-2xl border border-dashed border-border p-4 transition-colors",
          "not-data-[files]:justify-center data-[dragging=true]:border-primary/60 data-[dragging=true]:bg-primary/5",
          "has-[input:focus]:border-ring has-[input:focus]:ring-[3px] has-[input:focus]:ring-ring/50",
          disabled && "pointer-events-none opacity-60",
        )}
      >
        <input {...inputProps} className="sr-only" aria-label="Upload file" />

        {files.length > 0 ? (
          <div className="flex w-full flex-col gap-3">
            <div className="flex items-center justify-between gap-2">
              <h3 className="truncate text-sm font-medium">
                Files ({files.length})
              </h3>
              <div className="flex gap-2">
                {multiple && files.length < maxFiles ? (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={actions.openFileDialog}
                  >
                    <Upload className="-ms-0.5 size-3.5 opacity-60" aria-hidden />
                    Add files
                  </Button>
                ) : null}
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={actions.clearFiles}
                >
                  <Trash2 className="-ms-0.5 size-3.5 opacity-60" aria-hidden />
                  Remove all
                </Button>
              </div>
            </div>

            <div className="w-full space-y-2">
              {files.map((entry) => {
                const Icon = getFileIcon(entry);
                const name = entry.file.name;
                const size = entry.file.size;

                return (
                  <div
                    key={entry.id}
                    data-uploading={isUploading || undefined}
                    className="flex flex-col gap-1 rounded-xl border border-border bg-background p-2 pe-3 transition-opacity duration-300"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-3 overflow-hidden in-data-[uploading=true]:opacity-50">
                        <div className="flex aspect-square size-10 shrink-0 items-center justify-center rounded-lg border border-border">
                          <Icon className="size-4" aria-hidden />
                        </div>
                        <div className="flex min-w-0 flex-col gap-0.5">
                          <p className="truncate text-[13px] font-medium">
                            {name}
                          </p>
                          <p className="text-xs text-muted-foreground">
                            {formatBytes(size)}
                          </p>
                        </div>
                      </div>
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        aria-label={`Remove ${name}`}
                        onClick={() => actions.removeFile(entry.id)}
                        className="-me-2 size-8 text-muted-foreground hover:bg-transparent hover:text-foreground"
                      >
                        <X className="size-4" aria-hidden />
                      </Button>
                    </div>

                    {isUploading ? (
                      <div className="mt-1 flex items-center gap-2">
                        <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
                          <div
                            className="h-full bg-primary transition-all duration-300 ease-out"
                            style={{ width: `${uploadProgress ?? 0}%` }}
                          />
                        </div>
                        <span className="w-10 text-xs tabular-nums text-muted-foreground">
                          {uploadProgress ?? 0}%
                        </span>
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </div>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center px-4 py-3 text-center">
            <div
              className="mb-2 flex size-11 shrink-0 items-center justify-center rounded-full border border-border bg-background"
              aria-hidden
            >
              <ImageIcon className="size-4 opacity-60" />
            </div>
            <p className="mb-1.5 text-sm font-medium">{title}</p>
            <p className="text-xs text-muted-foreground">
              {hint ??
                `Max ${multiple ? `${maxFiles} files` : "1 file"} ∙ Up to ${maxSizeMB}MB`}
            </p>
            <Button
              type="button"
              variant="outline"
              className="mt-4"
              onClick={actions.openFileDialog}
            >
              <Upload className="-ms-1 opacity-60" aria-hidden />
              {selectLabel}
            </Button>
          </div>
        )}
      </div>

      {errors.length > 0 ? (
        <div
          className="flex items-center gap-1 text-xs text-destructive"
          role="alert"
        >
          <AlertCircle className="size-3 shrink-0" aria-hidden />
          <span>{errors[0]}</span>
        </div>
      ) : null}
    </div>
  );
}
