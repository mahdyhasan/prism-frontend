"use client";

import { useMemo } from "react";
import { Clock } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import {
  overviewWidgetsApi,
  type HourlyHeatmapPoint,
} from "@/lib/api-client";
import { formatNumber } from "@/lib/format";

interface HourlyHeatmapProps {
  propertyId: number;
  start: string;
  end: string;
}

// API uses 0=Sunday..6=Saturday. We display Mon..Sun rows.
const DISPLAY_DAYS: { apiIndex: number; label: string }[] = [
  { apiIndex: 1, label: "Mon" },
  { apiIndex: 2, label: "Tue" },
  { apiIndex: 3, label: "Wed" },
  { apiIndex: 4, label: "Thu" },
  { apiIndex: 5, label: "Fri" },
  { apiIndex: 6, label: "Sat" },
  { apiIndex: 0, label: "Sun" },
];

const HOUR_LABELS: number[] = [0, 4, 8, 12, 16, 20];

export function HourlyHeatmap({ propertyId, start, end }: HourlyHeatmapProps) {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["overview-hourly", propertyId, start, end],
    queryFn: () => overviewWidgetsApi.getHourly(propertyId, { start, end }),
    enabled: !!propertyId,
    staleTime: 1000 * 60 * 5,
  });

  const { grid, peak, totalSessions } = useMemo(() => {
    const g: HourlyHeatmapPoint[][] = Array.from({ length: 7 }, () =>
      Array.from({ length: 24 }, () => ({
        day_of_week: 0,
        hour: 0,
        sessions: 0,
        users: 0,
      })),
    );
    let p = 0;
    let total = 0;
    if (data) {
      for (const point of data) {
        if (
          point.day_of_week >= 0 &&
          point.day_of_week <= 6 &&
          point.hour >= 0 &&
          point.hour <= 23
        ) {
          g[point.day_of_week][point.hour] = point;
          if (point.sessions > p) p = point.sessions;
          total += point.sessions;
        }
      }
    }
    return { grid: g, peak: p, totalSessions: total };
  }, [data]);

  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
      <div className="mb-4 flex items-center gap-3">
        <Clock className="h-4 w-4 text-slate-400" />
        <div>
          <h3 className="text-sm font-semibold text-white">When traffic happens</h3>
          <p className="text-xs text-slate-500">Sessions by day of week and hour</p>
        </div>
      </div>

      {isLoading && (
        <div
          className="animate-pulse rounded-lg border border-slate-800 bg-slate-900/40"
          style={{ height: 240 }}
          aria-hidden
        />
      )}
      {isError && (
        <div className="rounded-lg border border-red-900 bg-red-950/60 px-4 py-3 text-xs text-red-300">
          Failed to load: {(error as Error | undefined)?.message ?? "Unknown error"}
        </div>
      )}
      {data && totalSessions === 0 && (
        <div className="rounded-lg border border-dashed border-slate-800 bg-slate-900/40 px-4 py-10 text-center text-xs text-slate-500">
          No hourly traffic data for this period
        </div>
      )}
      {data && totalSessions > 0 && (
        <div className="overflow-x-auto">
          <div className="min-w-[560px]">
            {/* hour axis */}
            <div
              className="grid"
              style={{
                gridTemplateColumns: "32px repeat(24, minmax(0, 1fr))",
                columnGap: 2,
              }}
            >
              <div />
              {Array.from({ length: 24 }).map((_, h) => (
                <div
                  key={h}
                  className="text-center text-[10px] text-slate-500"
                  style={{ visibility: HOUR_LABELS.includes(h) ? "visible" : "hidden" }}
                >
                  {h}
                </div>
              ))}
            </div>
            {/* rows */}
            <div className="mt-1 flex flex-col gap-[2px]">
              {DISPLAY_DAYS.map((day) => (
                <div
                  key={day.apiIndex}
                  className="grid items-center"
                  style={{
                    gridTemplateColumns: "32px repeat(24, minmax(0, 1fr))",
                    columnGap: 2,
                  }}
                >
                  <div className="text-[10px] font-medium uppercase tracking-wider text-slate-500">
                    {day.label}
                  </div>
                  {Array.from({ length: 24 }).map((_, h) => {
                    const cell = grid[day.apiIndex][h];
                    const intensity = peak === 0 ? 0 : cell.sessions / peak;
                    return (
                      <HeatCell
                        key={h}
                        dayLabel={day.label}
                        hour={h}
                        sessions={cell.sessions}
                        users={cell.users}
                        intensity={intensity}
                      />
                    );
                  })}
                </div>
              ))}
            </div>
            {/* legend */}
            <div className="mt-4 flex items-center gap-2 text-[10px] text-slate-500">
              <span>Less</span>
              <div className="flex gap-[2px]">
                {[0.05, 0.25, 0.5, 0.75, 1].map((step) => (
                  <span
                    key={step}
                    className="h-3 w-3 rounded-sm"
                    style={{ background: heatColor(step) }}
                  />
                ))}
              </div>
              <span>More</span>
              <span className="ml-auto">
                Peak hour: {formatNumber(peak)} sessions
              </span>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

interface HeatCellProps {
  dayLabel: string;
  hour: number;
  sessions: number;
  users: number;
  intensity: number;
}

function HeatCell({ dayLabel, hour, sessions, users, intensity }: HeatCellProps) {
  const hourLabel = `${hour.toString().padStart(2, "0")}:00`;
  const tooltip = `${dayLabel} ${hourLabel} — ${formatNumber(sessions)} sessions, ${formatNumber(users)} users`;
  return (
    <div
      title={tooltip}
      aria-label={tooltip}
      className="aspect-square rounded-[3px] transition-transform hover:scale-110 hover:ring-1 hover:ring-brand-500/60"
      style={{ background: heatColor(intensity) }}
    />
  );
}

/**
 * Map intensity 0..1 to a slate-800 → brand-600 gradient using rgba.
 * slate-800 ≈ rgb(30,41,59); brand-600 ≈ rgb(79,70,229).
 * intensity=0 returns near-empty slate so the grid stays visible.
 */
function heatColor(intensity: number): string {
  const i = Math.max(0, Math.min(1, intensity));
  if (i === 0) return "rgba(30,41,59,0.55)";
  // Lerp
  const r = Math.round(30 + (79 - 30) * i);
  const g = Math.round(41 + (70 - 41) * i);
  const b = Math.round(59 + (229 - 59) * i);
  // Boost alpha with intensity for extra depth
  const a = 0.45 + 0.5 * i;
  return `rgba(${r},${g},${b},${a.toFixed(2)})`;
}
