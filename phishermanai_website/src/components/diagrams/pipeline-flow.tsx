import { cn } from "@/lib/utils";

interface PipelineFlowProps {
  className?: string;
}

export function PipelineFlow({ className }: PipelineFlowProps) {
  return (
    <div className={cn("rounded-3xl border border-border bg-card p-8 shadow-lg", className)}>
      <div className="mb-6">
        <p className="text-sm uppercase tracking-[0.3em] text-foreground/50">Pipeline</p>
        <h2 className="mt-2 text-2xl font-semibold">Message processing</h2>
      </div>
      <div className="grid gap-4">
        <div className="rounded-2xl border border-border bg-background px-5 py-5">
          <p className="font-medium">Ingest</p>
          <p className="mt-2 text-sm text-foreground/70">Route the input to the correct detectors based on channel.</p>
        </div>
        <div className="rounded-2xl border border-border bg-background px-5 py-5">
          <p className="font-medium">Detect</p>
          <p className="mt-2 text-sm text-foreground/70">Run the text, voice, video and web checks independently.</p>
        </div>
        <div className="rounded-2xl border border-border bg-background px-5 py-5">
          <p className="font-medium">Fuse</p>
          <p className="mt-2 text-sm text-foreground/70">Combine available detector findings into one verdict.</p>
        </div>
      </div>
    </div>
  );
}
