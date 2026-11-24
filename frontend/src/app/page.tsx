"use client";

import React, { useState, useEffect } from "react";
import {
  generateMonthlyRoster,
  fetchHealth,
  MonthlyRosterResponse,
  Conflict,
  RosterEntry,
} from "@/lib/api";
import {
  AlertTriangle,
  CheckCircle2,
  Calendar,
  Users,
  ShieldAlert,
  Sparkles,
  RefreshCw,
  Clock,
  Layers,
} from "lucide-react";

export default function HomePage() {
  const [month, setMonth] = useState("2026-12");
  const [loading, setLoading] = useState(false);
  const [healthStatus, setHealthStatus] = useState<"checking" | "connected" | "error">("checking");
  const [rosterData, setRosterData] = useState<MonthlyRosterResponse | null>(null);
  const [activeTab, setActiveTab] = useState<"conflicts" | "entries" | "coverage">("conflicts");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    checkBackendHealth();
  }, []);

  const checkBackendHealth = async () => {
    try {
      setHealthStatus("checking");
      await fetchHealth();
      setHealthStatus("connected");
    } catch {
      setHealthStatus("error");
    }
  };

  const handleGenerate = async () => {
    try {
      setLoading(true);
      setErrorMsg(null);
      const data = await generateMonthlyRoster(month);
      setRosterData(data);
    } catch (err: any) {
      setErrorMsg(err.message || "Failed to generate monthly roster.");
    } finally {
      setLoading(false);
    }
  };

  const kpis = rosterData?.kpis;
  const hardConflicts = rosterData?.conflicts.filter((c) => c.severity === "HARD") || [];
  const softConflicts = rosterData?.conflicts.filter((c) => c.severity === "SOFT") || [];

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 p-6 md:p-10 font-sans">
      <div className="max-w-7xl mx-auto space-y-8">
        {/* Top Header */}
        <header className="flex flex-col md:flex-row md:items-center justify-between pb-6 border-b border-slate-800 gap-4">
          <div>
            <div className="flex items-center gap-3">
              <span className="p-2 bg-indigo-600/20 text-indigo-400 rounded-lg border border-indigo-500/30">
                <Layers className="w-6 h-6" />
              </span>
              <h1 className="text-2xl font-bold tracking-tight text-white">
                Smart Roster Management System
              </h1>
            </div>
            <p className="text-slate-400 text-sm mt-1">
              Deterministic Demand-vs-Supply Scheduling & Real-Time Conflict Detection
            </p>
          </div>

          <div className="flex items-center gap-3">
            {/* Backend Health Badge */}
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium bg-slate-900 border border-slate-800">
              <span
                className={`w-2 h-2 rounded-full ${
                  healthStatus === "connected"
                    ? "bg-emerald-400 animate-pulse"
                    : healthStatus === "checking"
                    ? "bg-amber-400"
                    : "bg-rose-500"
                }`}
              />
              <span className="text-slate-300">
                {healthStatus === "connected"
                  ? "FastAPI Engine Online"
                  : healthStatus === "checking"
                  ? "Checking Backend..."
                  : "Backend Offline (Port 8000)"}
              </span>
            </div>

            {/* Month Picker */}
            <div className="flex items-center bg-slate-900 border border-slate-800 rounded-lg px-3 py-1.5 text-sm">
              <Calendar className="w-4 h-4 text-slate-400 mr-2" />
              <input
                type="text"
                value={month}
                onChange={(e) => setMonth(e.target.value)}
                className="bg-transparent text-white font-medium focus:outline-none w-20"
                placeholder="YYYY-MM"
              />
            </div>

            {/* Generate Button */}
            <button
              onClick={handleGenerate}
              disabled={loading}
              className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:bg-indigo-900 text-white font-medium text-sm rounded-lg transition-colors shadow-lg shadow-indigo-600/20"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
              {loading ? "Solving..." : "Generate Roster"}
            </button>
          </div>
        </header>

        {errorMsg && (
          <div className="p-4 bg-rose-950/40 border border-rose-800/50 rounded-xl text-rose-300 text-sm flex items-center gap-3">
            <ShieldAlert className="w-5 h-5 flex-shrink-0 text-rose-400" />
            <div>
              <p className="font-semibold">Generation Error</p>
              <p>{errorMsg}</p>
            </div>
          </div>
        )}

        {/* KPI Cards Bar */}
        {kpis ? (
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <div className="bg-slate-900/80 border border-slate-800 p-4 rounded-xl">
              <div className="flex items-center justify-between text-slate-400 mb-1">
                <span className="text-xs uppercase font-medium">Team Members</span>
                <Users className="w-4 h-4 text-indigo-400" />
              </div>
              <div className="text-2xl font-bold text-white">{kpis.total_employees}</div>
              <div className="text-xs text-slate-400 mt-1">4 Pods (32 Employees)</div>
            </div>

            <div className="bg-slate-900/80 border border-slate-800 p-4 rounded-xl">
              <div className="flex items-center justify-between text-slate-400 mb-1">
                <span className="text-xs uppercase font-medium">Coverage Rate</span>
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
              </div>
              <div className="text-2xl font-bold text-emerald-400">
                {kpis.coverage_percentage}%
              </div>
              <div className="text-xs text-slate-400 mt-1">
                {kpis.covered_slots} / {kpis.total_operating_slots} Operating Slots
              </div>
            </div>

            <div className="bg-slate-900/80 border border-slate-800 p-4 rounded-xl">
              <div className="flex items-center justify-between text-slate-400 mb-1">
                <span className="text-xs uppercase font-medium">Hard Conflicts</span>
                <ShieldAlert className="w-4 h-4 text-rose-400" />
              </div>
              <div className="text-2xl font-bold text-rose-400">{kpis.hard_conflicts_count}</div>
              <div className="text-xs text-rose-400/80 mt-1">Gaps / Understaffed Days</div>
            </div>

            <div className="bg-slate-900/80 border border-slate-800 p-4 rounded-xl">
              <div className="flex items-center justify-between text-slate-400 mb-1">
                <span className="text-xs uppercase font-medium">Soft Warnings</span>
                <AlertTriangle className="w-4 h-4 text-amber-400" />
              </div>
              <div className="text-2xl font-bold text-amber-400">{kpis.soft_conflicts_count}</div>
              <div className="text-xs text-amber-400/80 mt-1">Preference Overrides</div>
            </div>

            <div className="bg-slate-900/80 border border-slate-800 p-4 rounded-xl">
              <div className="flex items-center justify-between text-slate-400 mb-1">
                <span className="text-xs uppercase font-medium">Solver Speed</span>
                <Clock className="w-4 h-4 text-sky-400" />
              </div>
              <div className="text-2xl font-bold text-sky-400">&lt; 50 ms</div>
              <div className="text-xs text-slate-400 mt-1">Pure Deterministic Python</div>
            </div>
          </div>
        ) : (
          <div className="bg-slate-900/50 border border-dashed border-slate-800 p-8 rounded-2xl text-center">
            <Sparkles className="w-8 h-8 text-indigo-400 mx-auto mb-3" />
            <h2 className="text-lg font-semibold text-white">Ready to Generate December 2026 Roster</h2>
            <p className="text-slate-400 text-sm max-w-md mx-auto mt-1 mb-4">
              Click &quot;Generate Roster&quot; above to solve client operating requirements against 32 employees,
              detect coverage gaps, and rank backup candidates.
            </p>
            <button
              onClick={handleGenerate}
              className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-sm font-medium transition-colors"
            >
              Generate Roster ({month})
            </button>
          </div>
        )}

        {/* Tab Controls & Content */}
        {rosterData && (
          <div className="space-y-4">
            <div className="flex items-center gap-2 border-b border-slate-800 pb-2">
              <button
                onClick={() => setActiveTab("conflicts")}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                  activeTab === "conflicts"
                    ? "bg-slate-800 text-white"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                Conflict Detection ({rosterData.conflicts.length})
              </button>
              <button
                onClick={() => setActiveTab("entries")}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                  activeTab === "entries"
                    ? "bg-slate-800 text-white"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                Employee Entries ({rosterData.entries.length})
              </button>
              <button
                onClick={() => setActiveTab("coverage")}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                  activeTab === "coverage"
                    ? "bg-slate-800 text-white"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                Demand Coverage Matrix ({rosterData.coverage_matrix.length})
              </button>
            </div>

            {/* Conflicts Tab */}
            {activeTab === "conflicts" && (
              <div className="space-y-3">
                <div className="text-sm text-slate-400">
                  Showing {hardConflicts.length} Hard Conflicts and {softConflicts.length} Soft Warnings:
                </div>
                <div className="grid grid-cols-1 gap-3">
                  {rosterData.conflicts.map((conf, idx) => (
                    <div
                      key={idx}
                      className={`p-4 rounded-xl border ${
                        conf.severity === "HARD"
                          ? "bg-rose-950/20 border-rose-900/40 text-rose-200"
                          : "bg-amber-950/20 border-amber-900/40 text-amber-200"
                      }`}
                    >
                      <div className="flex flex-col md:flex-row md:items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <span
                            className={`px-2 py-0.5 text-xs font-bold rounded ${
                              conf.severity === "HARD"
                                ? "bg-rose-900/60 text-rose-300"
                                : "bg-amber-900/60 text-amber-300"
                            }`}
                          >
                            {conf.severity}
                          </span>
                          <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                            {conf.conflict_type.replace(/_/g, " ")}
                          </span>
                          <span className="text-xs bg-slate-900 px-2 py-0.5 rounded text-slate-300">
                            {conf.date}
                          </span>
                        </div>
                      </div>

                      <p className="mt-2 text-sm text-slate-200 font-medium">{conf.message}</p>

                      {/* Suggested Backup Recommendations */}
                      {conf.suggested_resolutions && conf.suggested_resolutions.length > 0 && (
                        <div className="mt-3 pt-3 border-t border-slate-800/80">
                          <span className="text-xs font-semibold text-indigo-400 block mb-2">
                            Top Ranked Backup Candidates:
                          </span>
                          <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
                            {conf.suggested_resolutions.map((res, rIdx) => (
                              <div
                                key={rIdx}
                                className="bg-slate-900/80 border border-slate-800 p-2.5 rounded-lg text-xs"
                              >
                                <div className="flex items-center justify-between font-semibold text-slate-200">
                                  <span>{res.name}</span>
                                  <span className="px-1.5 py-0.2 bg-indigo-950 text-indigo-300 rounded text-[10px]">
                                    Score: {res.score}
                                  </span>
                                </div>
                                <div className="text-[11px] text-slate-400 mt-1 line-clamp-2">
                                  {res.reason}
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Entries Tab */}
            {activeTab === "entries" && (
              <div className="bg-slate-900/80 border border-slate-800 rounded-xl overflow-hidden">
                <div className="max-h-[500px] overflow-y-auto">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-slate-950 text-slate-400 sticky top-0 border-b border-slate-800">
                      <tr>
                        <th className="p-3">Employee</th>
                        <th className="p-3">Date</th>
                        <th className="p-3">Status</th>
                        <th className="p-3">Assigned Brand</th>
                        <th className="p-3">Override?</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60 text-slate-300">
                      {rosterData.entries.slice(0, 100).map((e, idx) => (
                        <tr key={idx} className="hover:bg-slate-800/30">
                          <td className="p-3 font-medium text-white">{e.employee_id}</td>
                          <td className="p-3">{e.date}</td>
                          <td className="p-3">
                            <span
                              className={`px-2 py-0.5 rounded text-[11px] font-semibold ${
                                e.status === "WORKING"
                                  ? "bg-emerald-950 text-emerald-400"
                                  : e.status === "WEEKLY_OFF"
                                  ? "bg-slate-800 text-slate-400"
                                  : e.status === "PUBLIC_HOLIDAY"
                                  ? "bg-sky-950 text-sky-400"
                                  : e.status === "PLANNED_LEAVE"
                                  ? "bg-amber-950 text-amber-400"
                                  : e.status === "BACKUP_COVERAGE"
                                  ? "bg-teal-950 text-teal-400"
                                  : "bg-purple-950 text-purple-400"
                              }`}
                            >
                              {e.status}
                            </span>
                          </td>
                          <td className="p-3 text-slate-400">{e.assigned_brand_id || "—"}</td>
                          <td className="p-3">{e.is_manual_override ? "Yes" : "No"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="p-3 bg-slate-950 text-center text-xs text-slate-500 border-t border-slate-800">
                  Showing first 100 of {rosterData.entries.length} daily employee entries
                </div>
              </div>
            )}

            {/* Coverage Matrix Tab */}
            {activeTab === "coverage" && (
              <div className="bg-slate-900/80 border border-slate-800 rounded-xl overflow-hidden">
                <div className="max-h-[500px] overflow-y-auto">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-slate-950 text-slate-400 sticky top-0 border-b border-slate-800">
                      <tr>
                        <th className="p-3">Brand</th>
                        <th className="p-3">Process</th>
                        <th className="p-3">Date</th>
                        <th className="p-3">Required</th>
                        <th className="p-3">Working</th>
                        <th className="p-3">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60 text-slate-300">
                      {rosterData.coverage_matrix.slice(0, 100).map((c, idx) => (
                        <tr key={idx} className="hover:bg-slate-800/30">
                          <td className="p-3 font-medium text-white">{c.brand_name}</td>
                          <td className="p-3 text-indigo-400 font-semibold">{c.process_code}</td>
                          <td className="p-3">{c.date}</td>
                          <td className="p-3">{c.required_staffing}</td>
                          <td className="p-3">{c.working_count}</td>
                          <td className="p-3">
                            <span
                              className={`px-2 py-0.5 rounded text-[11px] font-semibold ${
                                c.status === "COVERED"
                                  ? "bg-emerald-950 text-emerald-400"
                                  : c.status === "BACKUP_COVERED"
                                  ? "bg-teal-950 text-teal-400"
                                  : c.status === "UNDERSTAFFED"
                                  ? "bg-amber-950 text-amber-400"
                                  : c.status === "UNCOVERED"
                                  ? "bg-rose-950 text-rose-400"
                                  : "bg-slate-800 text-slate-500"
                              }`}
                            >
                              {c.status}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="p-3 bg-slate-950 text-center text-xs text-slate-500 border-t border-slate-800">
                  Showing first 100 of {rosterData.coverage_matrix.length} daily operating slots
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
