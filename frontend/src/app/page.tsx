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
  Info,
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
    <div className="min-h-screen bg-white text-[#0a0a0a]">
      {/* Frosted Editorial Light Header */}
      <header className="sticky top-0 z-30 bg-white/85 backdrop-blur-md border-b border-neutral-200">
        <div className="max-w-[1440px] mx-auto px-4 sm:px-8 py-3.5 flex flex-col lg:flex-row lg:items-center justify-between gap-3">
          {/* Brand & Status */}
          <div className="flex items-center gap-3.5">
            <div className="w-9 h-9 rounded-xl bg-neutral-900 text-white flex items-center justify-center shadow-xs">
              <Layers className="w-4 h-4" />
            </div>
            <div>
              <div className="flex items-center gap-2.5">
                <h1 className="text-base sm:text-lg font-bold tracking-tight text-neutral-950">
                  Smart Roster
                </h1>
                <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium bg-neutral-100 text-neutral-700 border border-neutral-200">
                  <span
                    className={`w-1.5 h-1.5 rounded-full ${
                      healthStatus === "connected"
                        ? "bg-emerald-500"
                        : healthStatus === "checking"
                        ? "bg-amber-400"
                        : "bg-red-500"
                    }`}
                  />
                  {healthStatus === "connected"
                    ? "Engine Ready"
                    : healthStatus === "checking"
                    ? "Connecting"
                    : "Offline"}
                </span>
              </div>
              <p className="text-xs text-neutral-500">
                Demand-vs-supply scheduling &amp; conflict resolution for D2C CX teams
              </p>
            </div>
          </div>

          {/* Primary Controls */}
          <div className="flex flex-wrap items-center gap-2">
            {/* Month Selector */}
            <div className="flex items-center bg-neutral-50 border border-neutral-200 rounded-full px-3 py-1.5 text-xs">
              <Calendar className="w-3.5 h-3.5 text-neutral-500 mr-1.5" />
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
                className="bg-transparent text-neutral-900 font-semibold focus:outline-none tabular-nums"
              />
            </div>

            {/* Generate Roster */}
            <button
              type="button"
              onClick={handleGenerate}
              disabled={loadingRoster || resetting}
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-full bg-neutral-900 hover:bg-neutral-800 disabled:opacity-50 text-white text-xs font-semibold transition-colors"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loadingRoster ? "animate-spin" : ""}`} />
              {loadingRoster ? "Solving..." : "Generate Roster"}
            </button>

            {/* Reset Demo Data */}
            <button
              type="button"
              onClick={handleResetDemo}
              disabled={resetting || loadingRoster}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-full bg-white hover:bg-neutral-100 border border-neutral-200 text-neutral-700 text-xs font-medium transition-colors disabled:opacity-50"
            >
              <RotateCcw className={`w-3.5 h-3.5 ${resetting ? "animate-spin" : ""}`} />
              Reset Demo
            </button>

            {/* Export CSV */}
            <a
              href={getCsvExportUrl(month)}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-full bg-white hover:bg-neutral-100 border border-neutral-200 text-neutral-700 text-xs font-medium transition-colors"
            >
              <Download className="w-3.5 h-3.5" />
              Export CSV
            </a>

            {/* Conflicts Drawer Trigger */}
            <button
              type="button"
              onClick={() => openConflictsDrawer("ALL")}
              className={`inline-flex items-center gap-1.5 px-3.5 py-2 rounded-full text-xs font-semibold border transition-colors ${
                hardConflictsCount > 0
                  ? "bg-red-50 border-red-200 text-red-700 hover:bg-red-100"
                  : "bg-white border-neutral-200 text-neutral-700 hover:bg-neutral-100"
              }`}
            >
              <ShieldAlert className="w-3.5 h-3.5" />
              Conflicts ({totalConflictsCount})
            </button>
          </div>
        </div>

        {/* Clean Pill Navigation Bar */}
        <div className="max-w-[1440px] mx-auto px-4 sm:px-8 pb-3 flex flex-wrap items-center justify-between gap-3">
          <div className="inline-flex items-center p-1 rounded-full bg-neutral-100 border border-neutral-200/80">
            <button
              type="button"
              onClick={() => setMainSection("workspace")}
              className={`inline-flex items-center gap-1.5 px-4 py-1.5 rounded-full text-xs font-semibold transition-all ${
                mainSection === "workspace"
                  ? "bg-white text-neutral-950 shadow-xs"
                  : "text-neutral-600 hover:text-neutral-950"
              }`}
            >
              <LayoutGrid className="w-3.5 h-3.5" />
              Roster Workspace (5 Views)
            </button>
            <button
              type="button"
              onClick={() => setMainSection("setup")}
              className={`inline-flex items-center gap-1.5 px-4 py-1.5 rounded-full text-xs font-semibold transition-all ${
                mainSection === "setup"
                  ? "bg-white text-neutral-950 shadow-xs"
                  : "text-neutral-600 hover:text-neutral-950"
              }`}
            >
              <Settings className="w-3.5 h-3.5" />
              Operations Setup (CRUD)
            </button>
          </div>

          <div className="hidden md:flex items-center gap-2 text-[11px] text-neutral-500">
            <Info className="w-3.5 h-3.5 text-neutral-400" />
            <span>
              Tip: Click any grid cell to override status, or open{" "}
              <button
                type="button"
                onClick={() => openConflictsDrawer("HARD")}
                className="font-semibold text-neutral-800 underline underline-offset-2 hover:text-neutral-950"
              >
                Conflicts
              </button>{" "}
              for 1-click backup resolution.
            </span>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-[1440px] mx-auto px-4 sm:px-8 py-6 space-y-6">
        {errorMsg && (
          <div className="bg-red-50 border border-red-200 text-red-800 px-4 py-3 rounded-2xl text-xs font-medium flex items-center gap-2.5">
            <ShieldAlert className="w-4 h-4 text-red-600 flex-shrink-0" />
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
            <div className="bg-neutral-50 border border-neutral-200 rounded-2xl p-12 text-center">
              {loadingRoster ? (
                <div className="inline-flex items-center gap-2 text-sm font-medium text-neutral-600">
                  <Loader2 className="w-4 h-4 animate-spin text-neutral-900" />
                  Loading monthly roster for {month}...
                </div>
              ) : (
                <div className="space-y-3">
                  <p className="text-sm font-semibold text-neutral-900">
                    No roster loaded for {month}
                  </p>
                  <button
                    type="button"
                    onClick={handleGenerate}
                    className="px-5 py-2.5 rounded-full bg-neutral-900 hover:bg-neutral-800 text-white text-xs font-semibold transition-colors"
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
