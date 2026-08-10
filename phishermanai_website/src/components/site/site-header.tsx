"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronDown, Menu } from "lucide-react";
import { motion } from "framer-motion";

import { LogoMark } from "@/components/site/logo";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { channelNav, moreNav } from "@/lib/site";
import { cn } from "@/lib/utils";

/**
 * The nav is a floating island, deliberately rounded against the spec-sheet
 * sharp-corner system below it. The five channels ride in the bar itself —
 * one tap each — everything else collapses under "More". The mark rides
 * outside the island, to its left, as the way back home.
 */
export function SiteHeader() {
  const pathname = usePathname();
  const [scrolled, setScrolled] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 12);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const isActive = (href: string) => pathname === href || pathname.startsWith(`${href}/`);

  return (
    <header className="sticky top-0 z-50 w-full">
      <div
        className="pointer-events-none absolute inset-0 -z-10 backdrop-blur-[3px] [-webkit-mask-image:linear-gradient(to_bottom,black,black_80%,transparent)] [mask-image:linear-gradient(to_bottom,black,black_80%,transparent)]"
        aria-hidden
      />

      <motion.div
        initial={{ opacity: 0, y: -16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
        className="container-page relative flex items-center gap-3 pt-4 pb-3 sm:pt-5"
      >
        <Link
          href="/"
          aria-label="PhishermanAI — home"
          className="shrink-0 outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
        >
          <LogoMark className="size-11" />
        </Link>

        <div
          className={cn(
            "mx-auto flex h-14 max-w-4xl items-center gap-1 rounded-full border px-2 backdrop-blur-sm transition-colors duration-300",
            scrolled
              ? "border-border bg-background/65 shadow-[0_16px_40px_-24px_rgba(16,27,40,0.3)]"
              : "border-border/60 bg-background/45",
          )}
        >
          <nav className="hidden flex-1 items-center gap-0.5 pl-1.5 lg:flex">
            {channelNav.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="flex items-center gap-1.5 rounded-full px-3 py-2 text-[0.875rem] text-foreground/65 transition-colors hover:bg-foreground/5 hover:text-foreground"
              >
                {item.icon ? <item.icon className="size-3.5 text-primary" aria-hidden /> : null}
                {item.label}
              </Link>
            ))}

            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  className="h-9 rounded-full px-3.5 text-[0.875rem] font-normal text-foreground/65 hover:bg-foreground/5 hover:text-foreground"
                >
                  More
                  <ChevronDown className="size-3.5 opacity-60" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent
                align="end"
                sideOffset={10}
                className="w-[19rem] rounded-2xl border-border/80 bg-popover/95 p-1.5 shadow-[0_24px_48px_-24px_rgba(16,27,40,0.35)] backdrop-blur-xl"
              >
                {moreNav.map((item, i) => (
                  <div key={item.href}>
                    <DropdownMenuItem asChild className="items-start gap-3 rounded-xl p-2.5">
                      <Link href={item.href}>
                        {item.icon ? (
                          <span className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-full bg-primary/8 text-primary">
                            <item.icon className="size-4" aria-hidden />
                          </span>
                        ) : null}
                        <span className="min-w-0">
                          <span className="block text-sm font-medium">{item.label}</span>
                          <span className="block text-xs leading-relaxed text-muted-foreground">
                            {item.description}
                          </span>
                        </span>
                      </Link>
                    </DropdownMenuItem>
                    {i === moreNav.length - 2 ? (
                      <div className="my-1.5 h-px bg-border" aria-hidden />
                    ) : null}
                  </div>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          </nav>

          <div className="ml-auto flex items-center gap-1.5 lg:ml-0">
            <Button asChild className="h-9 rounded-full px-4 text-[0.875rem]">
              <Link href="/demo">Run the demo</Link>
            </Button>

            <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
              <SheetTrigger asChild>
                <Button variant="outline" size="icon" className="size-9 rounded-full lg:hidden">
                  <Menu />
                  <span className="sr-only">Open menu</span>
                </Button>
              </SheetTrigger>
              <SheetContent side="right" className="w-[19rem] rounded-none">
                <SheetHeader>
                  <SheetTitle className="text-left">Menu</SheetTitle>
                </SheetHeader>
                <nav className="flex flex-col gap-1 px-4 pb-8">
                  <p className="mono-label mt-2 mb-2 text-foreground/45">Channels</p>
                  {channelNav.map((item) => (
                    <Link
                      key={item.href}
                      href={item.href}
                      onClick={() => setMobileOpen(false)}
                      className="flex items-center gap-2.5 rounded-xl px-3 py-2.5 text-[0.9375rem] hover:bg-muted"
                    >
                      {item.icon ? (
                        <span className="grid size-7 shrink-0 place-items-center rounded-full bg-primary/8 text-primary">
                          <item.icon className="size-3.5" aria-hidden />
                        </span>
                      ) : null}
                      {item.label}
                    </Link>
                  ))}
                  <p className="mono-label mt-5 mb-2 text-foreground/45">More</p>
                  {moreNav.map((item) => (
                    <Link
                      key={item.href}
                      href={item.href}
                      onClick={() => setMobileOpen(false)}
                      className={cn(
                        "rounded-none px-3 py-2.5 text-[0.9375rem] hover:bg-muted",
                        isActive(item.href) && "text-primary",
                      )}
                    >
                      {item.label}
                    </Link>
                  ))}
                </nav>
              </SheetContent>
            </Sheet>
          </div>
        </div>
      </motion.div>
    </header>
  );
}
