"use client";

import type { LucideIcon } from "lucide-react";

import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";

export type SwitchFieldProps = {
  id: string;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  label: string;
  /** Muted parenthetical shown next to the label. */
  sublabel?: string;
  description?: string;
  icon?: LucideIcon;
  disabled?: boolean;
  className?: string;
};

/**
 * Bordered switch card: control on the trailing edge, icon + label + description
 * on the leading edge, and a highlighted border while enabled.
 */
export function SwitchField({
  id,
  checked,
  onCheckedChange,
  label,
  sublabel,
  description,
  icon: Icon,
  disabled = false,
  className,
}: SwitchFieldProps) {
  return (
    <div
      className={cn(
        "relative flex w-full items-start gap-2 rounded-2xl border p-4 shadow-sm shadow-black/5 transition-colors",
        checked ? "border-primary/50" : "border-border",
        disabled && "opacity-60",
        className,
      )}
    >
      <Switch
        id={id}
        checked={checked}
        onCheckedChange={onCheckedChange}
        disabled={disabled}
        aria-describedby={description ? `${id}-description` : undefined}
        className="order-1 mt-1 shrink-0"
      />

      <div className="flex grow items-center gap-3">
        {Icon ? (
          <span
            className={cn(
              "grid size-8 shrink-0 place-items-center rounded-xl transition-colors",
              checked
                ? "bg-primary/10 text-primary"
                : "bg-muted text-muted-foreground",
            )}
            aria-hidden
          >
            <Icon className="size-4" />
          </span>
        ) : null}

        <div className="grid grow gap-1">
          <Label htmlFor={id} className="font-medium">
            {label}{" "}
            {sublabel ? (
              <span className="text-xs font-normal leading-[inherit] text-muted-foreground">
                ({sublabel})
              </span>
            ) : null}
          </Label>
          {description ? (
            <p id={`${id}-description`} className="text-xs text-muted-foreground">
              {description}
            </p>
          ) : null}
        </div>
      </div>
    </div>
  );
}
