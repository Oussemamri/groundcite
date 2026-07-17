"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  LabelList,
} from "recharts";
import type { LabelProps } from "recharts";

export interface SuiteBaseline {
  suite: string;
  git_sha: string;
  recall_at_5: number | null;
  mean_citation_precision: number | null;
  abstention_accuracy: number | null;
}

// Chart-only series colors (not the app's grounded/abstained status accents --
// those are reserved for ask-outcome status elsewhere, e.g. StatusChip; a
// generic 3-series comparison chart gets its own identity, not a borrowed
// status color). Validated CVD-safe on the app's dark surface (#131822) via
// the dataviz skill's validator: all 3 checks PASS (worst adjacent ΔE 8.4
// protan / 19.8 normal-vision).
const COLOR_RECALL = "#3987e5"; // blue
const COLOR_CITATION_PRECISION = "#199e70"; // aqua/green
const COLOR_ABSTENTION_ACCURACY = "#c98500"; // amber

function pct(v: number | null): number | null {
  return v === null ? null : Math.round(v * 1000) / 10;
}

function PctLabel(props: LabelProps) {
  const x = Number(props.x ?? 0);
  const y = Number(props.y ?? 0);
  const width = Number(props.width ?? 0);
  const value =
    props.value === undefined || props.value === null || typeof props.value === "boolean"
      ? undefined
      : Number(props.value);
  if (value === undefined || Number.isNaN(value)) return null;
  return (
    <text
      x={x + width / 2}
      y={y - 6}
      textAnchor="middle"
      className="fill-text/70 font-mono"
      fontSize={10}
    >
      {value.toFixed(1)}%
    </text>
  );
}

interface TooltipPayloadItem {
  name: string;
  value: number;
  color: string;
  payload: SuiteBaseline;
}

function ChartTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: TooltipPayloadItem[];
  label?: string;
}) {
  if (!active || !payload || payload.length === 0) return null;
  const sha = payload[0]?.payload.git_sha;
  return (
    <div className="rounded border border-border bg-surface p-3 text-xs shadow-lg">
      <div className="font-medium text-text">{label}</div>
      {sha && <div className="mt-0.5 font-mono text-text/50">git {sha}</div>}
      <div className="mt-2 flex flex-col gap-1">
        {payload.map((p) => (
          <div key={p.name} className="flex items-center gap-2">
            <span aria-hidden className="h-2 w-2 rounded-full" style={{ backgroundColor: p.color }} />
            <span className="text-text/70">{p.name}</span>
            <span className="ml-auto font-mono text-text">{p.value.toFixed(1)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * Per-suite grouped bar of the three headline metrics for each suite's
 * latest FULL-pipeline run (Week 5 AD-4). Deliberately NOT a cross-config
 * time series -- the tracked git_shas span τ=0.35→0.70 and model swaps, so a
 * line connecting those points would imply a comparability that isn't there.
 * A grouped bar per suite, each bar's git_sha named in the tooltip, is the
 * honest read of a small, mixed-config dataset.
 */
export function EvalsChart({ data }: { data: SuiteBaseline[] }) {
  const rows = data.map((d) => ({
    ...d,
    recall_at_5_pct: pct(d.recall_at_5),
    citation_precision_pct: pct(d.mean_citation_precision),
    abstention_accuracy_pct: pct(d.abstention_accuracy),
  }));

  return (
    <div className="h-80 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} margin={{ top: 24, right: 8, left: 0, bottom: 8 }} barGap={4}>
          <CartesianGrid strokeDasharray="3 3" stroke="#232B3A" vertical={false} />
          <XAxis
            dataKey="suite"
            tick={{ fill: "#E6EAF2", fontFamily: "var(--font-jetbrains-mono)", fontSize: 12 }}
            axisLine={{ stroke: "#232B3A" }}
            tickLine={false}
          />
          <YAxis
            domain={[0, 100]}
            tickFormatter={(v: number) => `${v}%`}
            tick={{ fill: "#E6EAF2AA", fontFamily: "var(--font-jetbrains-mono)", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            width={44}
          />
          <Tooltip
            cursor={{ fill: "#232B3A55" }}
            content={(props) => (
              <ChartTooltip
                active={props.active}
                label={props.label as string | undefined}
                payload={props.payload as unknown as TooltipPayloadItem[] | undefined}
              />
            )}
          />
          <Legend
            wrapperStyle={{ fontSize: 11, color: "#E6EAF2" }}
            formatter={(value: string) => <span style={{ color: "#E6EAF2" }}>{value}</span>}
          />
          <Bar
            dataKey="recall_at_5_pct"
            name="Recall@5"
            fill={COLOR_RECALL}
            radius={[4, 4, 0, 0]}
            maxBarSize={40}
            isAnimationActive={false}
          >
            <LabelList content={PctLabel} />
          </Bar>
          <Bar
            dataKey="citation_precision_pct"
            name="Citation precision"
            fill={COLOR_CITATION_PRECISION}
            radius={[4, 4, 0, 0]}
            maxBarSize={40}
            isAnimationActive={false}
          >
            <LabelList content={PctLabel} />
          </Bar>
          <Bar
            dataKey="abstention_accuracy_pct"
            name="Abstention accuracy"
            fill={COLOR_ABSTENTION_ACCURACY}
            radius={[4, 4, 0, 0]}
            maxBarSize={40}
            isAnimationActive={false}
          >
            <LabelList content={PctLabel} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
