"use client";

import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "./ui/accordion";
import { Badge } from "./ui/badge";
import { RootCauseRecord } from "../lib/types";

export default function RootCausePanel({ rootCauses }: { rootCauses: RootCauseRecord[] }) {
  if (rootCauses.length === 0) {
    return <p className="text-sm text-muted-foreground">No repeated failure signatures were detected for this run.</p>;
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        Repeated identical failures are grouped into a single root cause, instead of listing every affected
        scenario individually.
      </p>
      <Accordion type="multiple" className="space-y-2">
        {rootCauses.map((rc) => (
          <AccordionItem key={rc.id} value={rc.id} className="rounded-lg border border-destructive/30 px-4">
            <AccordionTrigger>
              <div className="flex flex-wrap items-center gap-3 text-left">
                <Badge variant="destructive">{rc.exception_type}</Badge>
                <span className="font-medium">{rc.affected_count} scenario(s) affected</span>
                <span className="text-xs text-muted-foreground">confidence {Math.round(rc.confidence * 100)}%</span>
              </div>
            </AccordionTrigger>
            <AccordionContent className="space-y-2 text-sm">
              <p className="font-mono text-xs text-muted-foreground">{rc.normalized_message}</p>
              <p><span className="font-medium">Recovery suggestion:</span> {rc.recovery_suggestion}</p>
              <p className="text-muted-foreground">
                <span className="font-medium text-foreground">Affected scenarios:</span>{" "}
                {rc.affected_scenario_ids.slice(0, 15).join(", ")}
                {rc.affected_scenario_ids.length > 15 ? ` +${rc.affected_scenario_ids.length - 15} more` : ""}
              </p>
            </AccordionContent>
          </AccordionItem>
        ))}
      </Accordion>
    </div>
  );
}
