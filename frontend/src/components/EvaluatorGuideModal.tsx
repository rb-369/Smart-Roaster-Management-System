"use client";

import React from "react";
import { BookOpen, Calendar, Layers, Lightbulb, ShieldAlert, Users, X } from "lucide-react";

interface EvaluatorGuideModalProps {
  open: boolean;
  onClose: () => void;
}

const SCENARIOS = [
  {
    num: 1,
    title: "Different Brand Calendars (Dec 25 & Sundays)",
    badge: "Demand Rules",
    icon: Calendar,
    description:
      "Open Brand-wise View and compare BRD-01 (Mon–Sat only, closed Sundays & Dec 25), BRD-07 (open daily except Public Holidays), and BRD-02 (CS runs 365_DAYS while ACC runs MON_SAT_EXCEPT_PH).",
  },
  {
    num: 2,
    title: "Multi-Brand Cascade (DEMO-2)",
    badge: "Cascade Impact",
    icon: ShieldAlert,
    description:
      "Open Conflicts and search Kabir (EMP-08) to see how his Dec 10–11 planned leave creates gaps across both BRD-04 and BRD-05 at the same time.",
  },
  {
    num: 3,
    title: "3-Person Brand Peak Coverage (DEMO-3)",
    badge: "Smart Backup",
    icon: Users,
    description:
      "Check BRD-18 (StrideCraft Footwear) during EMP-16's leave: Tue Dec 15 (min=1) stays covered 1/1, while busy Mon Dec 14 (min=2) automatically activates backup EMP-18 (2/2 BC).",
  },
  {
    num: 4,
    title: "Live Post-Gen Change + Auto-Resolve (DEMO-4)",
    badge: "Live Re-validation",
    icon: Layers,
    description:
      "Click Preview Impact then Approve on Arjun Malhotra's pending leave (LV-07, Dec 16–17), then open Conflicts and click Auto-Resolve Solvable Gaps (Score ≥ 70) to watch coverage jump from 94.5% → 99.0%.",
  },
];

export default function EvaluatorGuideModal({ open, onClose }: EvaluatorGuideModalProps) {
  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-neutral-950/35 backdrop-blur-[2px]"
      onClick={onClose}
    >
      <div
        className="bg-white border border-neutral-200 rounded-2xl shadow-2xl w-full max-w-2xl max-h-[88vh] flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-6 py-4 border-b border-neutral-200 flex items-center justify-between bg-neutral-50/80">
          <div className="flex items-center gap-2.5">
            <span className="p-2 rounded-xl bg-blue-50 text-blue-600 border border-blue-100">
              <BookOpen className="w-4 h-4" />
            </span>
            <div>
              <h2 className="text-sm font-bold text-neutral-950">Quick Guide</h2>
              <p className="text-xs text-neutral-500">
                Simple walkthrough of how Smart Roster works &amp; what to test
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg text-neutral-400 hover:text-neutral-700 hover:bg-neutral-200/60 transition-colors"
            aria-label="Close Quick Guide"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="p-6 overflow-y-auto space-y-5">
          {/* 1. 30-Second Overview */}
          <section className="bg-blue-50/60 border border-blue-100 rounded-xl p-4 space-y-1.5">
            <h3 className="text-xs font-bold uppercase tracking-wider text-blue-900">
              30-Second Overview
            </h3>
            <p className="text-xs text-neutral-700 leading-relaxed">
              Smart Roster separates <strong>Demand</strong> (when each brand needs coverage) from{" "}
              <strong>Supply</strong> (when each employee works, takes weekly offs, or goes on leave)
              across <strong>32 employees</strong>, <strong>4 pods</strong>, and{" "}
              <strong>20 brands</strong> (80% single-owner, 20% multi-person teams). Whenever demand
              cannot be met, the engine never hides it — it flags the exact conflict and ranks the best
              available backups.
            </p>
          </section>

          {/* 2. 4 Guided Test Scenarios */}
          <section className="space-y-2.5">
            <h3 className="text-xs font-bold uppercase tracking-wider text-neutral-500">
              4 Guided Test Scenarios
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {SCENARIOS.map((sc) => {
                const Icon = sc.icon;
                return (
                  <div
                    key={sc.num}
                    className="bg-white border border-neutral-200 rounded-xl p-3.5 space-y-1.5 hover:border-neutral-300 transition-colors"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="inline-flex items-center gap-1.5 text-xs font-bold text-neutral-900">
                        <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-neutral-900 text-white text-[10px] font-bold">
                          {sc.num}
                        </span>
                        <Icon className="w-3.5 h-3.5 text-blue-600" />
                      </span>
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-neutral-100 text-neutral-600">
                        {sc.badge}
                      </span>
                    </div>
                    <h4 className="text-xs font-bold text-neutral-900">{sc.title}</h4>
                    <p className="text-[11px] text-neutral-600 leading-relaxed">
                      {sc.description}
                    </p>
                  </div>
                );
              })}
            </div>
          </section>

          {/* 3. Quick Legend & Tip */}
          <section className="bg-neutral-50 border border-neutral-200 rounded-xl p-3.5 flex items-start gap-2.5">
            <Lightbulb className="w-4 h-4 text-amber-500 flex-shrink-0 mt-0.5" />
            <p className="text-[11px] text-neutral-700 leading-relaxed">
              <strong>Legend &amp; Tips:</strong>{" "}
              <span className="font-mono font-semibold">W</span> Working ·{" "}
              <span className="font-mono font-semibold">WO</span> Weekly Off ·{" "}
              <span className="font-mono font-semibold">PH</span> Public Holiday ·{" "}
              <span className="font-mono font-semibold">LV</span> Leave ·{" "}
              <span className="font-mono font-semibold">CO</span> Comp-Off ·{" "}
              <span className="font-mono font-semibold">BC</span> Backup Coverage. Click any matrix cell to
              test live manual overrides, try <strong>Compare Plans</strong> or{" "}
              <strong>Roster Copilot</strong>, and click <strong>Reset Demo</strong> anytime to
              restore clean seed data.
            </p>
          </section>
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-neutral-200 bg-neutral-50/70 flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-1.5 rounded-full bg-neutral-900 hover:bg-neutral-800 text-white text-xs font-semibold transition-colors"
          >
            Got it
          </button>
        </div>
      </div>
    </div>
  );
}
