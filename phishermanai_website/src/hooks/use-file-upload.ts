"use client";

import { useCallback, useRef, useState } from "react";

export type FileMetadata = {
  name: string;
  size: number;
  type: string;
  url: string;
  id: string;
};

export type FileWithPreview = {
  file: File | FileMetadata;
  id: string;
  preview?: string;
};

export type FileUploadOptions = {
  maxFiles?: number;
  maxSize?: number;
  accept?: string;
  multiple?: boolean;
  initialFiles?: FileMetadata[];
  onFilesChange?: (files: FileWithPreview[]) => void;
  onFilesAdded?: (addedFiles: FileWithPreview[]) => void;
};

export type FileUploadState = {
  files: FileWithPreview[];
  isDragging: boolean;
  errors: string[];
};

export type FileUploadActions = {
  addFiles: (files: FileList | File[]) => void;
  removeFile: (id: string) => void;
  clearFiles: () => void;
  clearErrors: () => void;
  handleDragEnter: (event: React.DragEvent<HTMLElement>) => void;
  handleDragLeave: (event: React.DragEvent<HTMLElement>) => void;
  handleDragOver: (event: React.DragEvent<HTMLElement>) => void;
  handleDrop: (event: React.DragEvent<HTMLElement>) => void;
  handleFileChange: (event: React.ChangeEvent<HTMLInputElement>) => void;
  openFileDialog: () => void;
  getInputProps: (
    props?: React.InputHTMLAttributes<HTMLInputElement>,
  ) => React.InputHTMLAttributes<HTMLInputElement> & {
    ref: React.RefObject<HTMLInputElement | null>;
  };
};

export function formatBytes(bytes: number, decimals = 2) {
  if (bytes === 0) return "0 B";

  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));

  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`;
}

function generateUniqueId(file: File | FileMetadata) {
  return `${file.name}-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

export function useFileUpload(
  options: FileUploadOptions = {},
): [FileUploadState, FileUploadActions] {
  const {
    maxFiles = Infinity,
    maxSize = Infinity,
    accept = "*",
    multiple = false,
    initialFiles = [],
    onFilesChange,
    onFilesAdded,
  } = options;

  const [state, setState] = useState<FileUploadState>({
    files: initialFiles.map((file) => ({
      file,
      id: file.id,
      preview: file.url,
    })),
    isDragging: false,
    errors: [],
  });

  const inputRef = useRef<HTMLInputElement>(null);

  const validateFile = useCallback(
    (file: File | FileMetadata): string | null => {
      if (file instanceof File) {
        if (file.size > maxSize) {
          return `File "${file.name}" exceeds the maximum size of ${formatBytes(maxSize)}.`;
        }
      } else if (file.size > maxSize) {
        return `File "${file.name}" exceeds the maximum size of ${formatBytes(maxSize)}.`;
      }

      if (accept !== "*") {
        const acceptedTypes = accept.split(",").map((type) => type.trim());
        const fileType = file instanceof File ? file.type || "" : file.type;
        const fileExtension = `.${file.name.split(".").pop()}`;

        const isAccepted = acceptedTypes.some((type) => {
          if (type.startsWith(".")) {
            return fileExtension.toLowerCase() === type.toLowerCase();
          }
          if (type.endsWith("/*")) {
            const baseType = type.split("/")[0];
            return fileType.startsWith(`${baseType}/`);
          }
          return fileType === type;
        });

        if (!isAccepted) {
          return `File "${file.name}" is not an accepted file type.`;
        }
      }

      return null;
    },
    [accept, maxSize],
  );

  const createPreview = useCallback(
    (file: File | FileMetadata): string | undefined =>
      file instanceof File ? URL.createObjectURL(file) : file.url,
    [],
  );

  const clearFiles = useCallback(() => {
    setState((prev) => {
      prev.files.forEach((file) => {
        if (file.preview && file.file instanceof File) {
          URL.revokeObjectURL(file.preview);
        }
      });

      if (inputRef.current) {
        inputRef.current.value = "";
      }

      const newState = { ...prev, files: [], errors: [] };
      onFilesChange?.(newState.files);
      return newState;
    });
  }, [onFilesChange]);

  const addFiles = useCallback(
    (newFiles: FileList | File[]) => {
      if (!newFiles || newFiles.length === 0) return;

      const newFilesArray = Array.from(newFiles);
      const errors: string[] = [];

      setState((prev) => {
        // In single-file mode the incoming file replaces whatever is there.
        if (!multiple) {
          prev.files.forEach((file) => {
            if (file.preview && file.file instanceof File) {
              URL.revokeObjectURL(file.preview);
            }
          });
        }

        if (
          multiple &&
          maxFiles !== Infinity &&
          prev.files.length + newFilesArray.length > maxFiles
        ) {
          errors.push(`You can only upload a maximum of ${maxFiles} files.`);
          return { ...prev, errors };
        }

        const validFiles: FileWithPreview[] = [];

        newFilesArray.forEach((file) => {
          const isDuplicate =
            multiple &&
            prev.files.some(
              (existing) =>
                existing.file.name === file.name &&
                existing.file.size === file.size,
            );

          if (isDuplicate) return;

          if (file.size > maxSize && maxFiles === 1) {
            errors.push(
              `The selected file exceeds the maximum size of ${formatBytes(maxSize)}.`,
            );
            return;
          }

          const error = validateFile(file);
          if (error) {
            errors.push(error);
            return;
          }

          validFiles.push({
            file,
            id: generateUniqueId(file),
            preview: createPreview(file),
          });
        });

        if (validFiles.length === 0) {
          return { ...prev, errors };
        }

        onFilesAdded?.(validFiles);

        const files = multiple ? [...prev.files, ...validFiles] : validFiles;
        onFilesChange?.(files);

        return { ...prev, files, errors };
      });

      // Reset so re-picking the same file still fires a change event.
      if (inputRef.current) {
        inputRef.current.value = "";
      }
    },
    [
      createPreview,
      maxFiles,
      maxSize,
      multiple,
      onFilesAdded,
      onFilesChange,
      validateFile,
    ],
  );

  const removeFile = useCallback(
    (id: string) => {
      setState((prev) => {
        const target = prev.files.find((file) => file.id === id);
        if (target?.preview && target.file instanceof File) {
          URL.revokeObjectURL(target.preview);
        }

        const files = prev.files.filter((file) => file.id !== id);
        onFilesChange?.(files);

        return { ...prev, files, errors: [] };
      });
    },
    [onFilesChange],
  );

  const clearErrors = useCallback(() => {
    setState((prev) => ({ ...prev, errors: [] }));
  }, []);

  const handleDragEnter = useCallback((event: React.DragEvent<HTMLElement>) => {
    event.preventDefault();
    event.stopPropagation();
    setState((prev) => ({ ...prev, isDragging: true }));
  }, []);

  const handleDragLeave = useCallback((event: React.DragEvent<HTMLElement>) => {
    event.preventDefault();
    event.stopPropagation();

    // Ignore leave events fired while moving between child nodes.
    if (
      event.currentTarget.contains(event.relatedTarget as Node | null) &&
      event.relatedTarget !== null
    ) {
      return;
    }

    setState((prev) => ({ ...prev, isDragging: false }));
  }, []);

  const handleDragOver = useCallback((event: React.DragEvent<HTMLElement>) => {
    event.preventDefault();
    event.stopPropagation();
  }, []);

  const handleDrop = useCallback(
    (event: React.DragEvent<HTMLElement>) => {
      event.preventDefault();
      event.stopPropagation();
      setState((prev) => ({ ...prev, isDragging: false }));

      if (inputRef.current?.disabled) return;

      if (event.dataTransfer.files?.length) {
        const droppedFiles = multiple
          ? Array.from(event.dataTransfer.files)
          : [event.dataTransfer.files[0]];
        addFiles(droppedFiles);
      }
    },
    [addFiles, multiple],
  );

  const handleFileChange = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      if (event.target.files?.length) {
        addFiles(event.target.files);
      }
    },
    [addFiles],
  );

  const openFileDialog = useCallback(() => {
    inputRef.current?.click();
  }, []);

  const getInputProps = useCallback(
    (props: React.InputHTMLAttributes<HTMLInputElement> = {}) => ({
      ...props,
      type: "file" as const,
      onChange: handleFileChange,
      accept: props.accept ?? accept,
      multiple: props.multiple ?? multiple,
      ref: inputRef,
    }),
    [accept, handleFileChange, multiple],
  );

  return [
    state,
    {
      addFiles,
      removeFile,
      clearFiles,
      clearErrors,
      handleDragEnter,
      handleDragLeave,
      handleDragOver,
      handleDrop,
      handleFileChange,
      openFileDialog,
      getInputProps,
    },
  ];
}
