import {
  Compass,
  FileCheck2,
  MailSearch,
  PlayCircle,
  ShieldCheck,
  SlidersHorizontal,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { channels } from "./content";

export const site = {
  name: "PhishermanAI",
  tagline: "Detect the synthetic. Verify the genuine.",
  description:
    "Detection of AI-generated threats across email, voice, video and social, plus a framework for verifying that a communication really is from SEBI, an exchange, a listed company or a registered intermediary. Built for SEBI Problem Statement 1.",
  url: "https://phishermanai.example",
  hackathon: "",
  repo: "https://github.com/phishermanai",
} as const;

export type NavLink = {
  href: string;
  label: string;
  description?: string;
  icon?: LucideIcon;
};

/** Short nav labels — the full channel names are too long for a tab. */
const shortLabel: Record<(typeof channels)[number]["id"], string> = {
  email: "Email",
  voice: "Voice",
  video: "Video",
  social: "Social",
  web: "Web",
};

/** The five channels, front and centre in the island — one tap each. */
export const channelNav: NavLink[] = channels.map((channel) => ({
  href: channel.href,
  label: shortLabel[channel.id],
  icon: channel.icon,
}));

/** Everything that isn't a channel, tucked under "More". */
export const moreNav: NavLink[] = [
  {
    href: "/verify",
    label: "Check an email",
    description: "Drop in an .eml or paste the text — checked against the real filings.",
    icon: MailSearch,
  },
  {
    href: "/how-it-works",
    label: "How it works",
    description: "One API, four possible answers.",
    icon: Compass,
  },
  {
    href: "/features",
    label: "Features",
    description: "Every capability, channel by channel.",
    icon: SlidersHorizontal,
  },
  {
    href: "/evidence",
    label: "Evidence",
    description: "The numbers, including the ones that miss.",
    icon: FileCheck2,
  },
  {
    href: "/demo",
    label: "Demo",
    description: "Paste a message, watch it get judged.",
    icon: PlayCircle,
  },
  {
    href: "/#authenticity",
    label: "Authenticity framework",
    description: "Confirming a genuine communication, not merely failing to flag it.",
    icon: ShieldCheck,
  },
];

export const footerNav: { title: string; links: NavLink[] }[] = [
  {
    title: "Detection",
    links: channels.map((channel) => ({ href: channel.href, label: channel.name })),
  },
  {
    title: "Verification",
    links: [
      { href: "/verify", label: "Check an email" },
      { href: "/#authenticity", label: "Authenticity framework" },
      { href: "/#authenticity", label: "Official-channel registry" },
      { href: "/#channel-email", label: "Filing cross-check" },
      { href: "/how-it-works#outcomes", label: "The four outcomes" },
    ],
  },
  {
    title: "Understand it",
    links: [
      { href: "/how-it-works", label: "How it works" },
      { href: "/features", label: "Everything, by channel" },
      { href: "/evidence", label: "Evidence & limitations" },
      { href: "/demo", label: "Interactive demo" },
    ],
  },
];
