"use client";

import React, { useCallback, useEffect, useState } from "react";
import {
  Calendar,
  Download,
  Layers,
  RefreshCw,
  RotateCcw,
  Settings,
  ShieldAlert,
  LayoutGrid,
  Loader2,
} from "lucide-react";
import {
  Allocation,
  Brand,
  BrandProcessRule,
  Employee,
  LeaveAndCompOff,
  MonthlyRosterResponse,
  Pod,
  Process,
  PublicHoliday,
  fetchAllocations,
  fetchBrands,
  fetchEmployees,
  fetchHealth,
  fetchHolidays,
  fetchLeaves,
  fetchMonthlyRoster,
  fetchPods,
  fetchProcesses,
  fetchRules,
  generateMonthlyRoster,
  getCsvExportUrl,
  resetSeedData,
} from "@/lib/api";
import KpiBar from "@/components/KpiBar";
import PendingLeavesBanner from "@/components/PendingLeavesBanner";
import RosterViews from "@/components/RosterViews";
import ConflictDrawer from "@/components/ConflictDrawer";
import ManagementTabs, { ManagementSubTab } from "@/components/ManagementTabs";

export default function HomePage() {
  const [month, setMonth] = useState("2026-12");
  const [mainSection, setMainSection] = useState<"workspace" | "setup">("workspace");
  const [setupInitialTab, setSetupInitialTab] = useState<ManagementSubTab>("team");

  const [healthStatus, setHealthStatus] = useState<"checking" | "connected" | "error">("checking");
  const [loadingRoster, setLoadingRoster] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const [rosterData, setRosterData] = useState<MonthlyRosterResponse | null>(null);
  const [pods, setPods] = useState<Pod[]>([]);
  const [processes, setProcesses] = useState<Process[]>([]);
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [brands, setBrands] = useState<Brand[]>([]);
  const [rules, setRules] = useState<BrandProcessRule[]>([]);
  const [allocations, setAllocations] = useState<Allocation[]>([]);
  const [leaves, setLeaves] = useState<LeaveAndCompOff[]>([]);
  const [holidays, setHolidays] = useState<PublicHoliday[]>([]);

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerSeverity, setDrawerSeverity] = useState<"ALL" | "HARD" | "SOFT">("ALL");

  const loadEntities = useCallback(async () => {
    const [p, pr, emp, br, ru, al, lv, hl] = await Promise.all([
      fetchPods().catch(() => []),
      fetchProcesses().catch(() => []),
      fetchEmployees().catch(() => []),
      fetchBrands().catch(() => []),
      fetchRules().catch(() => []),
      fetchAllocations().catch(() => []),
      fetchLeaves().catch(() => []),
      fetchHolidays().catch(() => []),
    ]);
    setPods(p);
    setProcesses(pr);
    setEmployees(emp);
    setBrands(br);
    setRules(ru);
    setAllocations(al);
    setLeaves(lv);
    setHolidays(hl);
  }, []);

  const loadOrGenerateRoster = useCallback(async (targetMonth: string) => {
    try {
      setLoadingRoster(true);
      setErrorMsg(null);
      try {
        const existing = await fetchMonthlyRoster(targetMonth);
        setRosterData(existing);
      } catch (err: unknown) {
        const status = (err as { status?: number })?.status;
        if (status === 404) {
          const generated = await generateMonthlyRoster(targetMonth);
          setRosterData(generated);
        } else {
          throw err;
        }
      }
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to load roster from backend.");
    } finally {
      setLoadingRoster(false);
    }
  }, []);

  useEffect(() => {
    const init = async () => {
      try {
        setHealthStatus("checking");
        await fetchHealth();
        setHealthStatus("connected");
      } catch {
        setHealthStatus("error");
      }
      await loadEntities();
      await loadOrGenerateRoster(month);
    };
    init();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleGenerate = async () => {
    try {
      setLoadingRoster(true);
      setErrorMsg(null);
      const generated = await generateMonthlyRoster(month);
      setRosterData(generated);
      await loadEntities();
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to generate roster.");
    } finally {
      setLoadingRoster(false);
    }
  };

  const handleResetDemo = async () => {
    try {
      setResetting(true);
      setErrorMsg(null);
      await resetSeedData();
      await loadEntities();
      const generated = await generateMonthlyRoster(month);
      setRosterData(generated);
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to reset demo data.");
    } finally {
      setResetting(false);
    }
  };

  const openConflictsDrawer = (severity: "ALL" | "HARD" | "SOFT" = "ALL") => {
    setDrawerSeverity(severity);
    setDrawerOpen(true);
  };

  const pendingLeavesCount = leaves.filter((l) => l.status === "PENDING").length;
  const totalConflictsCount = rosterData?.conflicts?.length ?? 0;
  const hardConflictsCount = rosterData?.kpis?.hard_conflicts_count ?? 0;

  return (
    <div className="min-h-screen bg-[#F8FAFC] text-[#0F172A]">
      {/* Top Navigation Bar */}
      <header className="sticky top-0 z-30 bg-white border-b border-slate-200 shadow-sm">
        <div className="max-w-[1440px] mx-auto px-4 sm:px-6 py-3 flex flex-col lg:flex-row lg:items-center justify-between gap-3">
          {/* Brand & Status */}
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-xl bg-indigo-600 text-white shadow-sm">
                <Layers className="w-5 h-5" />
              </div>
              <div>
                <h1 className="text-base sm:text-lg font-bold tracking-tight text-slate-900">
                  Smart Roster Management System
                </h1>
                <div className="flex items-center gap-2 text-xs text-slate-500">
                  <span>Enterprise Operations Command Center</span>
                  <span>&middot;</span>
                  <span className="inline-flex items-center gap-1.5 font-medium">
                    <span
                      className={`w-2 h-2 rounded-full ${
                        healthStatus === "connected"
                          ? "bg-emerald-500"
                          : healthStatus === "checking"
                          ? "bg-amber-400"
                          : "bg-rose-500"
                      }`}
                    />
                    {healthStatus === "connected"
                      ? "Engine Online"
                      : healthStatus === "checking"
                      ? "Connecting..."
                      : "Engine Offline"}
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Controls */}
          <div className="flex flex-wrap items-center gap-2">
            {/* Month Selector */}
            <div className="flex items-center bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1.5 text-xs">
              <Calendar className="w-3.5 h-3.5 text-slate-500 mr-1.5" />
              <input
                type="month"
                value={month}
                onChange={(e) => {
                  const val = e.target.value;
                  setMonth(val);
                  if (/^\d{4}-\d{2}$/.test(val)) {
                    loadOrGenerateRoster(val);
                  }
                }}
                className="bg-transparent text-slate-900 font-semibold focus:outline-none tabular-nums"
              />
            </div>

            {/* Generate Roster */}
            <button
              type="button"
              onClick={handleGenerate}
              disabled={loadingRoster || resetting}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-xs font-semibold shadow-sm transition-colors"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loadingRoster ? "animate-spin" : ""}`} />
              {loadingRoster ? "Solving..." : "Generate Roster"}
            </button>

            {/* Reset Demo Data */}
            <button
              type="button"
              onClick={handleResetDemo}
              disabled={resetting || loadingRoster}
              className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-white hover:bg-slate-50 border border-slate-200 text-slate-700 text-xs font-semibold transition-colors disabled:opacity-50"
            >
              <RotateCcw className={`w-3.5 h-3.5 ${resetting ? "animate-spin" : ""}`} />
              Reset Demo Data
            </button>

            {/* Export CSV */}
            <a
              href={getCsvExportUrl(month)}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-white hover:bg-slate-50 border border-slate-200 text-slate-700 text-xs font-semibold transition-colors"
            >
              <Download className="w-3.5 h-3.5" />
              Export CSV
            </a>

            {/* Conflicts Drawer Trigger */}
            <button
              type="button"
              onClick={() => openConflictsDrawer("ALL")}
              className={`inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-semibold border transition-colors ${
                hardConflictsCount > 0
                  ? "bg-rose-50 border-rose-200 text-rose-700 hover:bg-rose-100"
                  : "bg-white border-slate-200 text-slate-700 hover:bg-slate-50"
              }`}
            >
              <ShieldAlert className="w-3.5 h-3.5" />
              Conflicts ({totalConflictsCount})
            </button>
          </div>
        </div>

        {/* Primary Section Navigation */}
        <div className="max-w-[1440px] mx-auto px-4 sm:px-6 flex items-center gap-4 border-t border-slate-100">
          <button
            type="button"
            onClick={() => setMainSection("workspace")}
            className={`inline-flex items-center gap-2 py-2.5 text-xs font-semibold border-b-2 transition-colors ${
              mainSection === "workspace"
                ? "border-indigo-600 text-indigo-600"
                : "border-transparent text-slate-600 hover:text-slate-900"
            }`}
          >
            <LayoutGrid className="w-3.5 h-3.5" />
            Roster Workspace (5 Views)
          </button>
          <button
            type="button"
            onClick={() => setMainSection("setup")}
            className={`inline-flex items-center gap-2 py-2.5 text-xs font-semibold border-b-2 transition-colors ${
              mainSection === "setup"
                ? "border-indigo-600 text-indigo-600"
                : "border-transparent text-slate-600 hover:text-slate-900"
            }`}
          >
            <Settings className="w-3.5 h-3.5" />
            Operations Setup (CRUD)
          </button>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-[1440px] mx-auto px-4 sm:px-6 py-6 space-y-5">
        {errorMsg && (
          <div className="bg-rose-50 border border-rose-200 text-rose-800 px-4 py-3 rounded-xl text-xs font-medium flex items-center gap-2.5">
            <ShieldAlert className="w-4 h-4 text-rose-600 flex-shrink-0" />
            <span>{errorMsg}</span>
          </div>
        )}

        {/* KPI Bar */}
        <KpiBar
          kpis={rosterData?.kpis || null}
          totalEmployeesFallback={employees.length}
          pendingLeavesCount={pendingLeavesCount}
          onOpenConflicts={openConflictsDrawer}
          onJumpToLeaves={() => {
            setSetupInitialTab("leaves");
            setMainSection("setup");
          }}
        />

        {/* Pending Leaves Banner (DEMO-4 Live Flow) */}
        <PendingLeavesBanner
          month={month}
          leaves={leaves}
          employees={employees}
          currentRoster={rosterData}
          onRosterUpdated={setRosterData}
          onLeavesUpdated={loadEntities}
          onOpenConflicts={openConflictsDrawer}
        />

        {/* Workspace vs Setup */}
        {mainSection === "workspace" ? (
          rosterData ? (
            <RosterViews
              month={month}
              roster={rosterData}
              pods={pods}
              processes={processes}
              employees={employees}
              brands={brands}
              rules={rules}
              allocations={allocations}
              holidays={holidays}
              onRosterUpdated={setRosterData}
            />
          ) : (
            <div className="bg-white border border-slate-200 rounded-xl p-12 text-center shadow-sm">
              {loadingRoster ? (
                <div className="inline-flex items-center gap-2 text-sm font-medium text-slate-600">
                  <Loader2 className="w-4 h-4 animate-spin text-indigo-600" />
                  Loading monthly roster for {month}...
                </div>
              ) : (
                <div className="space-y-3">
                  <p className="text-sm font-semibold text-slate-900">
                    No roster loaded for {month}
                  </p>
                  <button
                    type="button"
                    onClick={handleGenerate}
                    className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold"
                  >
                    Generate Roster ({month})
                  </button>
                </div>
              )}
            </div>
          )
        ) : (
          <ManagementTabs
            month={month}
            pods={pods}
            processes={processes}
            employees={employees}
            brands={brands}
            rules={rules}
            allocations={allocations}
            leaves={leaves}
            holidays={holidays}
            initialSubTab={setupInitialTab}
            onEntitiesChanged={loadEntities}
            onRosterUpdated={setRosterData}
          />
        )}
      </main>

      {/* Slide-over Conflict Drawer */}
      <ConflictDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        month={month}
        conflicts={rosterData?.conflicts || []}
        initialSeverity={drawerSeverity}
        onRosterUpdated={setRosterData}
      />
    </div>
  );
}
