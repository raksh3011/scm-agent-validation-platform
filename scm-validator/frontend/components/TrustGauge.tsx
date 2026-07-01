"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { RadialBar, RadialBarChart, PolarAngleAxis } from "recharts";
import { cn } from "../lib/utils";

function colorFor(score: number) {
  if (score >= 85) return "var(--color-success)";
  if (score >= 65) return "var(--color-warning)";
  return "var(--color-destructive)";
}

export default function TrustGauge({ score, label }: { score: number | null; label: string }) {
  const [display, setDisplay] = useState(0);
  const numericScore = score ?? 0;
  const color = score === null ? "var(--color-muted-foreground)" : colorFor(score);

  useEffect(() => {
    if (score === null) return;
    const targetScore = score;
    setDisplay(targetScore);
    const start = performance.now();
    const duration = 800;
    let frame: number;
    let cancelled = false;
    function tick(now: number) {
      if (cancelled) return;
      const t = Math.min(1, (now - start) / duration);
      setDisplay(Math.round(targetScore * (1 - Math.pow(1 - t, 3))));
      if (t < 1) frame = requestAnimationFrame(tick);
    }
    frame = requestAnimationFrame(tick);
    // Safety net: if rAF never progresses (e.g. backgrounded tab), the score is
    // still shown immediately above, so the gauge never gets stuck at 0.
    return () => {
      cancelled = true;
      cancelAnimationFrame(frame);
    };
  }, [score]);

  const data = [{ value: numericScore, fill: color }];

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.4 }}
      className="relative flex h-44 w-44 items-center justify-center"
    >
      <RadialBarChart
        width={176}
        height={176}
        cx={88}
        cy={88}
        innerRadius={70}
        outerRadius={88}
        barSize={14}
        data={data}
        startAngle={90}
        endAngle={-270}
      >
        <PolarAngleAxis type="number" domain={[0, 100]} angleAxisId={0} tick={false} />
        <RadialBar dataKey="value" cornerRadius={8} background={{ fill: "var(--color-muted)" }} isAnimationActive />
      </RadialBarChart>
      <div className="absolute flex flex-col items-center">
        <span className={cn("text-4xl font-bold tabular-nums")} style={{ color }}>
          {score === null ? "—" : display}
        </span>
        <span className="text-xs text-muted-foreground">{label}</span>
      </div>
    </motion.div>
  );
}
