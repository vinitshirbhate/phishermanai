"use client";

import { ShieldAlert, ShieldCheck, ShieldX } from "lucide-react";
import { motion } from "framer-motion";

import { cn } from "@/lib/utils";

export type AuthCheckState = "pass" | "fail" | "warn";

export interface AuthCheckItem {
  code: string;
  detail: string;
  state: AuthCheckState;
}

const stateMeta: Record<
  AuthCheckState,
  { icon: typeof ShieldCheck; text: string; bg: string; border: string; word: string }
> = {
  pass: {
    icon: ShieldCheck,
    text: "text-verdict-verified",
    bg: "bg-verdict-verified/10",
    border: "border-verdict-verified/35",
    word: "PASS",
  },
  fail: {
    icon: ShieldX,
    text: "text-verdict-fraud",
    bg: "bg-verdict-fraud/10",
    border: "border-verdict-fraud/35",
    word: "FAIL",
  },
  warn: {
    icon: ShieldAlert,
    text: "text-verdict-tampered",
    bg: "bg-verdict-tampered/10",
    border: "border-verdict-tampered/35",
    word: "WARN",
  },
};

/** Official-looking SPF / DKIM / DMARC style pass-fail banner row. */
export function AuthBadgeRow({ items, className }: { items: AuthCheckItem[]; className?: string }) {
  return (
    <div
      className={cn(
        "grid grid-cols-2 gap-px overflow-hidden border border-border bg-border sm:grid-cols-4",
        className,
      )}
    >
      {items.map((item, i) => {
        const meta = stateMeta[item.state];
        const Icon = meta.icon;
        return (
          <motion.div
            key={item.code}
            initial={{ opacity: 0, y: 8 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ delay: i * 0.08, duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
            className="flex flex-col gap-2.5 bg-card px-3.5 py-3.5"
            title={item.detail}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="font-mono text-[0.6875rem] tracking-[0.1em] text-muted-foreground uppercase">
                {item.code}
              </span>
              <Icon className={cn("size-3.5", meta.text)} aria-hidden />
            </div>
            <span
              className={cn(
                "inline-flex w-fit items-center border px-1.5 py-0.5 font-mono text-[0.6875rem] font-semibold tracking-[0.08em]",
                meta.text,
                meta.bg,
                meta.border,
              )}
            >
              {meta.word}
            </span>
          </motion.div>
        );
      })}
    </div>
  );
}
