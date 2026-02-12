import { Card, CardContent } from "@/components/ui/card";
import type { HitSummary as HitSummaryType } from "@/types/api";
import { INSTRUMENT_COLORS, INSTRUMENT_LABELS } from "@/lib/constants";
import type { InstrumentLabel } from "@/types/api";

interface HitSummaryProps {
  summary: HitSummaryType;
}

export function HitSummary({ summary }: HitSummaryProps) {
  const entries = Object.entries(summary) as [InstrumentLabel, number][];

  if (entries.length === 0) return null;

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
      {entries
        .sort((a, b) => b[1] - a[1])
        .map(([instrument, count]) => (
          <Card
            key={instrument}
            className="relative overflow-hidden"
            style={{
              borderLeftColor: INSTRUMENT_COLORS[instrument],
              borderLeftWidth: "3px",
            }}
          >
            <CardContent className="p-4">
              <p className="text-xs text-muted-foreground">
                {INSTRUMENT_LABELS[instrument]}
              </p>
              <p className="mt-1 text-2xl font-bold font-mono">{count}</p>
              <p className="text-xs text-muted-foreground">hits</p>
            </CardContent>
          </Card>
        ))}
    </div>
  );
}
