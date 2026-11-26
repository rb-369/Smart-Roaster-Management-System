"use client";

import React, { useState } from "react";
import {
  Activity,
  ArrowUpRight,
  Building2,
  ChevronDown,
  ChevronUp,
  Layers,
  Lightbulb,
} from "lucide-react";
import { BottlenecksResponse } from "@/lib/api";

interface BottleneckInsightsProps {
  data: BottlenecksResponse | null;
  onOpenConflicts?: () => void;
}

export default function BottleneckInsights({
  data,
  onOpenConflicts,
}: BottleneckInsightsProps) {
  const [collapsed, setCollapsed] = useState(false);

  if (!data || data.total_hard_conflicts === 0) {
    return null;
  }

  const topPods = (data.top_pods || []).slice(0, 3);
  const topBrands = (data.top_brands || []).slice(0, 3);
  const recommendations = data.recommendations || [];
  const maxPodCount = Math.max(1, ...topPods.map((p) => p.hard_conflicts_count));
  const maxBrandCount = Math.max(1, ...topBrands.map((b) => b.hard_conflicts_count));

  return (
    <section
      aria-label="Operational Bottleneck Insights"
      className="bg-white border border-neutral-200 rounded-2xl overflow-hidden"
    >
      {/* Header */}
      <div className="px-4 sm:px-5 py-3.5 flex flex-wrap items-center justify-between gap-3 bg-neutral-50/70 border-b border-neutral-200/80">
        <div className="flex items-center gap-3">
          <span className="p-2 rounded-xl bg-rose-50 text-rose-600 border border-rose-100">
            <Activity className="w-4 h-4" />
          </span>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-xs sm:text-sm font-bold tracking-tight text-neutral-950">
                Operational Bottleneck Insights
              </h2>
              <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-rose-50 text-rose-700 border border-rose-200 tabular-nums">
                {data.total_hard_conflicts} hard conflict{data.total_hard_conflicts !== 1 ? "s" : ""}
              </span>
            </div>
            <p className="text-[11px] text-neutral-500 mt-0.5">
              Concentration of uncovered demand across pods, brands, and recommended staffing actions
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {onOpenConflicts && (
            <button
              type="button"
              onClick={onOpenConflicts}
              className="inline-flex items-center gap-1 px-3 py-1.5 rounded-full bg-white hover:bg-neutral-100 border border-neutral-200 text-neutral-800 text-xs font-semibold transition-colors"
            >
              Inspect Hard Gaps
              <ArrowUpRight className="w-3.5 h-3.5 text-rose-600" />
            </button>
          )}
          <button
            type="button"
            onClick={() => setCollapsed((prev) => !prev)}
            aria-expanded={!collapsed}
            aria-label={collapsed ? "Expand bottleneck insights" : "Collapse bottleneck insights"}
            className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-full bg-white hover:bg-neutral-100 border border-neutral-200 text-neutral-600 text-xs font-medium transition-colors"
          >
            {collapsed ? (
              <>
                <span>Expand</span>
                <ChevronDown className="w-3.5 h-3.5" />
              </>
            ) : (
              <>
                <span>Collapse</span>
                <ChevronUp className="w-3.5 h-3.5" />
              </>
            )}
          </button>
        </div>
      </div>

      {/* Body */}
      {!collapsed && (
        <div className="p-4 sm:p-5 grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Top 3 Bottleneck Pods */}
          <div className="bg-neutral-50/60 border border-neutral-200/80 rounded-xl p-3.5 space-y-2.5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-neutral-600">
                <Layers className="w-3.5 h-3.5 text-neutral-500" />
                Top Bottleneck Pods
              </div>
              <span className="text-[10px] font-medium text-neutral-400">Top {topPods.length}</span>
            </div>

            {topPods.length === 0 ? (
              <p className="text-xs text-neutral-500 py-2">No pod bottlenecks reported.</p>
            ) : (
              <div className="space-y-2.5">
                {topPods.map((pod, idx) => {
                  const pct = Math.round((pod.hard_conflicts_count / maxPodCount) * 100);
                  return (
                    <div key={pod.pod_id} className="space-y-1">
                      <div className="flex items-center justify-between gap-2 text-xs">
                        <div className="flex items-center gap-1.5 min-w-0">
                          <span className="w-4 h-4 rounded-full bg-white border border-neutral-200 text-[10px] font-bold text-neutral-600 flex items-center justify-center flex-shrink-0 tabular-nums">
                            {idx + 1}
                          </span>
                          <span className="font-semibold text-neutral-900 truncate">
                            {pod.pod_name}
                          </span>
                        </div>
                        <span className="px-2 py-0.5 rounded-full bg-rose-50 border border-rose-200 text-rose-700 text-[11px] font-semibold tabular-nums flex-shrink-0">
                          {pod.hard_conflicts_count}
                        </span>
                      </div>
                      <div className="w-full h-1.5 bg-neutral-200/70 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-rose-500 rounded-full"
                          style={{ width: `${Math.max(8, pct)}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Top 3 Bottleneck Brands */}
          <div className="bg-neutral-50/60 border border-neutral-200/80 rounded-xl p-3.5 space-y-2.5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-neutral-600">
                <Building2 className="w-3.5 h-3.5 text-neutral-500" />
                Top Bottleneck Brands
              </div>
              <span className="text-[10px] font-medium text-neutral-400">Top {topBrands.length}</span>
            </div>

            {topBrands.length === 0 ? (
              <p className="text-xs text-neutral-500 py-2">No brand bottlenecks reported.</p>
            ) : (
              <div className="space-y-2.5">
                {topBrands.map((brand, idx) => {
                  const pct = Math.round((brand.hard_conflicts_count / maxBrandCount) * 100);
                  return (
                    <div key={brand.brand_id} className="space-y-1">
                      <div className="flex items-center justify-between gap-2 text-xs">
                        <div className="flex items-center gap-1.5 min-w-0">
                          <span className="w-4 h-4 rounded-full bg-white border border-neutral-200 text-[10px] font-bold text-neutral-600 flex items-center justify-center flex-shrink-0 tabular-nums">
                            {idx + 1}
                          </span>
                          <span className="font-semibold text-neutral-900 truncate">
                            {brand.brand_name}
                          </span>
                          <span className="text-[10px] font-mono text-neutral-400 flex-shrink-0">
                            {brand.pod_id}
                          </span>
                        </div>
                        <span className="px-2 py-0.5 rounded-full bg-amber-50 border border-amber-200 text-amber-800 text-[11px] font-semibold tabular-nums flex-shrink-0">
                          {brand.hard_conflicts_count}
                        </span>
                      </div>
                      <div className="w-full h-1.5 bg-neutral-200/70 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-amber-500 rounded-full"
                          style={{ width: `${Math.max(8, pct)}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Hiring & Cross-Training Recommendations */}
          <div className="bg-blue-50/40 border border-blue-200/70 rounded-xl p-3.5 space-y-2.5">
            <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-blue-900">
              <Lightbulb className="w-3.5 h-3.5 text-blue-600" />
              Staffing Recommendations
            </div>

            {recommendations.length === 0 ? (
              <p className="text-xs text-neutral-600 py-2">
                No specific hiring or cross-training recommendations generated.
              </p>
            ) : (
              <ul className="space-y-2">
                {recommendations.map((rec, idx) => (
                  <li
                    key={idx}
                    className="flex items-start gap-2 text-xs text-neutral-700 leading-relaxed"
                  >
                    <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-blue-600 flex-shrink-0" />
                    <span>{rec}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
