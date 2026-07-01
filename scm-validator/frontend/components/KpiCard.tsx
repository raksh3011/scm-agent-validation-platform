"use client";

import { motion } from "framer-motion";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";
import { KpiRecord } from "../lib/types";

export default function KpiCard({ kpi, index = 0 }: { kpi: KpiRecord; index?: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: index * 0.04 }}
    >
      <Card className="h-full">
        <CardHeader className="pb-1">
          <CardTitle className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {kpi.name.replace(/_/g, " ")}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-semibold tabular-nums">
            {kpi.value}
            <span className="ml-1 text-sm font-normal text-muted-foreground">{kpi.unit}</span>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">{kpi.description}</p>
        </CardContent>
      </Card>
    </motion.div>
  );
}
