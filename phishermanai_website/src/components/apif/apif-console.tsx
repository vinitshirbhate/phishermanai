"use client";

import { Link2, Upload } from "lucide-react";

import { ApifLinkPreview } from "@/components/apif/apif-link-preview";
import { ApifVerifyForm } from "@/components/apif/apif-verify-form";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

/**
 * The two intake routes are one console with two tabs, not two stacked
 * sections. They ask for different inputs but answer the same question, and
 * side by side they made the page twice as tall as it needed to be.
 *
 * `after:hidden` drops the primitive's own underline so the active state is a
 * single vermilion rule that lines up with the list border.
 */
const triggerClass =
  "flex-none gap-2 rounded-none border-0 border-b-2 border-transparent bg-transparent px-1 pt-0 pb-3 text-[0.9375rem] after:hidden hover:text-foreground data-active:border-primary data-active:bg-transparent data-active:text-foreground data-active:shadow-none dark:data-active:border-primary dark:data-active:bg-transparent";

export function ApifConsole() {
  return (
    <Tabs defaultValue="direct" className="gap-8">
      <TabsList
        variant="line"
        className="h-auto w-full justify-start gap-8 border-b border-border bg-transparent p-0"
      >
        <TabsTrigger value="direct" className={triggerClass}>
          <Upload aria-hidden />
          Text &amp; media
        </TabsTrigger>
        <TabsTrigger value="link" className={triggerClass}>
          <Link2 aria-hidden />
          Link
        </TabsTrigger>
      </TabsList>

      <TabsContent value="direct">
        <ApifVerifyForm />
      </TabsContent>
      <TabsContent value="link">
        <ApifLinkPreview />
      </TabsContent>
    </Tabs>
  );
}
