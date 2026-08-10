import { RevealGroup, RevealItem } from "@/components/site/motion";
import { Section, SectionHeading } from "@/components/site/section";
import { targetUsers } from "@/lib/content";

export function TargetUsers() {
  return (
    <Section id="who-its-for" tone="raised">
      <SectionHeading
        eyebrow="Target users"
        title="Named, in order of who gets hurt"
        accent="rather than who signs the cheque."
        lead="Retail investors are the primary beneficiary. Intermediaries and infrastructure institutions are both impersonation targets and the route a tool reaches investors through."
      />

      <RevealGroup
        className="mt-14 grid gap-px overflow-hidden border border-border bg-border md:grid-cols-2"
        stagger={0.08}
      >
        {targetUsers.map((user) => (
          <RevealItem key={user.name}>
            <article className="h-full bg-card p-6 sm:p-7">
              <div className="flex items-start gap-4">
                <span className="mt-0.5 grid size-10 shrink-0 place-items-center border border-primary/25 bg-primary/8 text-primary">
                  <user.icon className="size-5" aria-hidden />
                </span>
                <div className="min-w-0">
                  <h3 className="text-lg font-medium">{user.name}</h3>
                  <p className="mono-label mt-1.5 text-primary">{user.role}</p>
                </div>
              </div>
              <p className="copy mt-5">{user.needs}</p>
              <p className="mono-label mt-5 border-t border-border pt-4 text-foreground/35">
                reached through — {user.surface}
              </p>
            </article>
          </RevealItem>
        ))}
      </RevealGroup>
    </Section>
  );
}
