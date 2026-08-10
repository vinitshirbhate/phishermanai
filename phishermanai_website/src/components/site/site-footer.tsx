import Link from "next/link";

import { LogoMark } from "@/components/site/logo";
import { footerNav, site } from "@/lib/site";

export function SiteFooter() {
  return (
    <footer className="dark bg-navy text-cream">
      <div className="container-page py-16 sm:py-20">
        <div className="grid gap-12 lg:grid-cols-[1.4fr_repeat(3,1fr)]">
          <div className="max-w-sm">
            <Link href="/" className="flex items-center gap-2.5">
              <LogoMark className="size-9" />
              <span className="text-[1.0625rem] font-medium tracking-[-0.02em]">
                Phisherman<span className="text-primary">AI</span>
              </span>
            </Link>
            <p className="copy mt-5 text-cream/60">
              A verification engine for Indian retail investors. It asks whether what a message
              says is true — not merely where it came from.
            </p>
            <p className="mono-label mt-6 text-cream/40">{site.hackathon}</p>
          </div>

          {footerNav.map((group) => (
            <div key={group.title}>
              <h3 className="mono-label text-cream/45">{group.title}</h3>
              <ul className="mt-5 space-y-3">
                {group.links.map((link) => (
                  <li key={`${group.title}-${link.label}`}>
                    <Link
                      href={link.href}
                      className="text-[0.9375rem] text-cream/70 transition-colors hover:text-primary"
                    >
                      {link.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="mt-16 border-t border-cream/12 pt-8">
          <p className="font-serif text-[0.9375rem] leading-relaxed text-cream/60">
            The system warns — it never acts for you. Nothing is blocked, sent or reported
            without your click, and on the default path nothing you paste in ever leaves your
            device.
          </p>
          <div className="mt-6 flex flex-col gap-3 text-xs text-cream/40 sm:flex-row sm:items-center sm:justify-between">
            <p>
              © {new Date().getFullYear()} {site.name}. Register data as of 2026-08-06 · threat
              feeds as of 2026-03-23.
            </p>
            <p className="font-mono">Not investment advice. Not affiliated with SEBI, BSE or NSE.</p>
          </div>
        </div>
      </div>
    </footer>
  );
}
