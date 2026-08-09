import { channels } from "./content";

export const site = {
  name: "PhishermanAI",
  tagline: "Detect the synthetic. Verify the genuine.",
  description:
    "Detection of AI-generated threats across email, voice, video and social, plus a framework for verifying that a communication really is from SEBI, an exchange, a listed company or a registered intermediary. Built for SEBI Problem Statement 1.",
  url: "https://phishermanai.example",
  hackathon: "SEBI Securities Market Hackathon · PS-01",
  repo: "https://github.com/phishermanai",
} as const;

export type NavLink = {
  href: string;
  label: string;
  description?: string;
};

/** Every channel is first-class in the navigation, in the same order. */
export const productNav: NavLink[] = [
  ...channels.map((channel) => ({
    href: channel.href,
    label: channel.navLabel,
    description: channel.navDescription,
  })),
  {
    href: "/product/authenticity",
    label: "Authenticity framework",
    description: "Confirming a genuine communication, not merely failing to flag it.",
  },
];

export const mainNav: NavLink[] = [
  { href: "/how-it-works", label: "How it works" },
  { href: "/features", label: "Features" },
  { href: "/evidence", label: "Evidence" },
  { href: "/demo", label: "Demo" },
];

export const footerNav: { title: string; links: NavLink[] }[] = [
  {
    title: "Detection",
    links: channels.map((channel) => ({ href: channel.href, label: channel.name })),
  },
  {
    title: "Verification",
    links: [
      { href: "/product/authenticity", label: "Authenticity framework" },
      { href: "/product/authenticity#registry", label: "Official-channel registry" },
      { href: "/product/email#filing", label: "Filing cross-check" },
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
