"use client";

import { useEffect, useRef } from "react";
import type { FieldComparison, MatchedFiling } from "@/lib/types";

/**
 * THE DEMO MOMENT.
 *
 * Shows the altered field beside the value the company actually filed with the
 * exchange. When the input was an image and OCR gave us a bounding box, the
 * uploaded image is drawn to a canvas with a red rectangle around the altered
 * region. For text and email input there is no pixel to point at, so the
 * comparison panel carries the whole message.
 *
 * The panel is the part that matters. "This document says Rs 40 / Canara Bank
 * filed Rs 4 with BSE on 12 July 2026" is a claim a user can check for
 * themselves in thirty seconds, which is what makes it persuasive.
 */

function prettyField(field: string): string {
  return field.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatValue(value: string | number | null): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") {
    return Number.isInteger(value) ? `${value}` : `${value}`;
  }
  return String(value);
}

function AnnotatedImage({
  imageUrl,
  bbox,
}: {
  imageUrl: string;
  bbox: number[];
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => {
      // Cap the rendered width so a 4000px screenshot does not blow out the
      // layout, and scale the box by the same factor.
      const maxWidth = 560;
      const scale = Math.min(1, maxWidth / img.width);
      canvas.width = img.width * scale;
      canvas.height = img.height * scale;
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

      const [x1, y1, x2, y2] = bbox.map((v) => v * scale);
      ctx.strokeStyle = "#dc2626";
      ctx.lineWidth = 3;
      ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);

      // A translucent wash so the box reads even against dense text.
      ctx.fillStyle = "rgba(220, 38, 38, 0.12)";
      ctx.fillRect(x1, y1, x2 - x1, y2 - y1);

      ctx.fillStyle = "#dc2626";
      ctx.font = "600 13px ui-sans-serif, system-ui";
      const label = "altered";
      const labelY = y1 > 20 ? y1 - 6 : y2 + 16;
      ctx.fillText(label, x1, labelY);
    };
    img.src = imageUrl;
  }, [imageUrl, bbox]);

  return (
    <canvas
      ref={canvasRef}
      className="w-full rounded-lg border border-slate-200"
      aria-label="Uploaded document with the altered field outlined in red"
    />
  );
}

export default function TamperView({
  comparisons,
  filing,
  imageUrl,
}: {
  comparisons: FieldComparison[];
  filing: MatchedFiling | null;
  imageUrl?: string | null;
}) {
  const altered = comparisons.filter((c) => c.match === false);
  const matching = comparisons.filter((c) => c.match === true);
  const unreadable = comparisons.filter((c) => c.read_confidence === "UNREADABLE");

  if (altered.length === 0 && unreadable.length === 0) return null;

  const filedOn = filing?.filing_date
    ? new Date(filing.filing_date).toLocaleDateString("en-IN", {
        day: "numeric",
        month: "long",
        year: "numeric",
      })
    : null;

  const boxed = altered.find((c) => c.bbox && c.bbox.length === 4);

  return (
    <section className="card overflow-hidden">
      <header className="border-b border-amber-200 bg-amber-50 px-5 py-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-amber-900">
          Document compared against the exchange filing
        </h2>
      </header>

      <div className="grid gap-6 p-5 lg:grid-cols-2">
        {imageUrl && boxed?.bbox ? (
          <div>
            <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">
              The document you submitted
            </p>
            <AnnotatedImage imageUrl={imageUrl} bbox={boxed.bbox} />
          </div>
        ) : imageUrl ? (
          <div>
            <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">
              The document you submitted
            </p>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={imageUrl}
              alt="Submitted document"
              className="w-full rounded-lg border border-slate-200"
            />
          </div>
        ) : null}

        <div className={imageUrl ? "" : "lg:col-span-2"}>
          <div className="space-y-4">
            {altered.map((c) => (
              <div
                key={c.field}
                className="rounded-lg border-2 border-red-300 bg-red-50/60 p-4"
              >
                <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-red-700">
                  {prettyField(c.field)} does not match
                </p>

                <dl className="space-y-2.5">
                  <div className="flex items-baseline justify-between gap-4">
                    <dt className="text-sm text-slate-600">This document says</dt>
                    <dd className="tamper-highlight text-lg">
                      {formatValue(c.extracted_value)}
                    </dd>
                  </div>
                  <div className="flex items-baseline justify-between gap-4">
                    <dt className="text-sm text-slate-600">
                      {filing?.company_name ?? "The company"} filed
                    </dt>
                    <dd className="rounded bg-white px-2 py-0.5 font-mono text-lg font-semibold text-emerald-700 ring-1 ring-emerald-300">
                      {formatValue(c.filed_value)}
                    </dd>
                  </div>
                </dl>

                {(filing?.exchange || filedOn) && (
                  <p className="mt-3 border-t border-red-200 pt-2 text-xs text-slate-600">
                    Filed with {filing?.exchange ?? "the exchange"}
                    {filedOn ? ` on ${filedOn}` : ""}
                    {filing?.pdf_url && (
                      <>
                        {" · "}
                        <a
                          href={filing.pdf_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="font-medium text-slate-900 underline underline-offset-2"
                        >
                          view the original filing
                        </a>
                      </>
                    )}
                  </p>
                )}

                {c.read_confidence === "MEDIUM" && (
                  <p className="mt-2 rounded bg-amber-100 px-2 py-1 text-xs text-amber-900">
                    The document was not fully legible — please verify against the original.
                  </p>
                )}
              </div>
            ))}

            {/* Unreadable fields are shown, never treated as tampering. */}
            {unreadable.map((c) => (
              <div
                key={c.field}
                className="rounded-lg border border-slate-300 bg-slate-50 p-4"
              >
                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-600">
                  {prettyField(c.field)} could not be read
                </p>
                <p className="text-sm text-slate-700">{c.message}</p>
              </div>
            ))}

            {matching.length > 0 && (
              <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3">
                <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-emerald-800">
                  Fields that do match the filing
                </p>
                <ul className="space-y-1">
                  {matching.map((c) => (
                    <li key={c.field} className="flex justify-between text-sm">
                      <span className="text-slate-600">{prettyField(c.field)}</span>
                      <span className="font-mono text-emerald-800">
                        {formatValue(c.filed_value)}
                      </span>
                    </li>
                  ))}
                </ul>
                <p className="mt-2 text-xs text-emerald-900/80">
                  These matching fields are why we can be confident this is a real
                  document with one field altered, rather than a fabrication.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
