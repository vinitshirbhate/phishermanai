"use client";

import { useCallback, useRef, useState } from "react";

const EXAMPLES = [
  { label: "Genuine dividend notice", file: "genuine_01.eml", tone: "emerald" },
  { label: "Tampered amount", file: "tampered_01.eml", tone: "amber" },
  { label: "Fraud: guaranteed returns", file: "fraud_02_guaranteed_returns.eml", tone: "red" },
  { label: "Real but unregistered", file: "edge_01_unregistered_but_real.eml", tone: "slate" },
];

const TONE: Record<string, string> = {
  emerald: "border-emerald-300 text-emerald-800 hover:bg-emerald-50",
  amber: "border-amber-300 text-amber-800 hover:bg-amber-50",
  red: "border-red-300 text-red-800 hover:bg-red-50",
  slate: "border-slate-300 text-slate-700 hover:bg-slate-50",
};

export default function DropZone({
  onSubmit,
  onExample,
  busy,
}: {
  onSubmit: (payload: { file?: File; text?: string }) => void;
  onExample: (fixture: string) => void;
  busy: boolean;
}) {
  const [dragging, setDragging] = useState(false);
  const [text, setText] = useState("");
  const [fileName, setFileName] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback(
    (file: File) => {
      setFileName(file.name);
      onSubmit({ file });
    },
    [onSubmit],
  );

  return (
    <section className="space-y-4">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          const file = e.dataTransfer.files?.[0];
          if (file) handleFile(file);
        }}
        onClick={() => inputRef.current?.click()}
        className={`card cursor-pointer border-2 border-dashed px-6 py-10 text-center transition-colors ${
          dragging ? "border-slate-900 bg-slate-50" : "border-slate-300 hover:border-slate-400"
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          className="hidden"
          accept=".eml,.msg,.pdf,.png,.jpg,.jpeg,.webp"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) handleFile(file);
          }}
        />
        <p className="text-base font-medium text-slate-800">
          Drop an email (.eml), screenshot, or PDF here
        </p>
        <p className="mt-1 text-sm text-slate-500">
          or click to choose a file{fileName ? ` — last: ${fileName}` : ""}
        </p>
      </div>

      <div className="card p-4">
        <label htmlFor="msg" className="mb-2 block text-sm font-medium text-slate-700">
          Or paste the message text / a link
        </label>
        <textarea
          id="msg"
          rows={5}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Paste the suspicious message here, exactly as you received it..."
          className="w-full resize-y rounded-lg border border-slate-300 px-3 py-2 text-sm
                     focus:border-slate-900 focus:outline-none focus:ring-1 focus:ring-slate-900"
        />
        <div className="mt-3 flex items-center justify-between">
          <button
            className="btn-primary"
            disabled={busy || text.trim().length === 0}
            onClick={() => onSubmit({ text })}
          >
            {busy ? "Checking…" : "Check this message"}
          </button>
          <span className="text-xs text-slate-400">
            Nothing you submit is stored — only a hash of it.
          </span>
        </div>
      </div>

      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
          Or try one of these
        </p>
        <div className="flex flex-wrap gap-2">
          {EXAMPLES.map((ex) => (
            <button
              key={ex.file}
              disabled={busy}
              onClick={() => onExample(ex.file)}
              className={`rounded-lg border bg-white px-3 py-1.5 text-sm font-medium transition-colors disabled:opacity-50 ${TONE[ex.tone]}`}
            >
              {ex.label}
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}
