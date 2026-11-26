"use client";

import React, { useCallback, useEffect, useState } from "react";
import {
  BookOpen,
  Calendar,
  Download,
  FileSpreadsheet,
  RefreshCw,
  RotateCcw,
  Settings,
  ShieldAlert,
  LayoutGrid,
  Loader2,
  Info,
  Bell,
  CheckCircle2,
  Sliders,
  Send,
  UserCheck,
  AlertTriangle,
  X,
} from "lucide-react";
import RosterCopilot from "@/components/RosterCopilot";
import {
  Allocation,
  BottlenecksResponse,
  Brand,
  BrandProcessRule,
  Employee,
  LeaveAndCompOff,
  MonthlyRosterResponse,
  NotificationItem,
  Pod,
  Process,
  PublicHoliday,
  approvePodRoster,
  fetchAllocations,
  fetchBottlenecks,
  fetchBrands,
  fetchEmployees,
  fetchHealth,
  fetchHolidays,
  fetchLeaves,
  fetchMonthlyRoster,
  fetchNotifications,
  fetchPods,
  fetchProcesses,
  fetchRules,
  generateMonthlyRoster,
  getCsvExportUrl,
  getExcelExportUrl,
  markNotificationsRead,
  publishRoster,
  resetSeedData,
} from "@/lib/api";
import KpiBar from "@/components/KpiBar";
import PendingLeavesBanner from "@/components/PendingLeavesBanner";
import BottleneckInsights from "@/components/BottleneckInsights";
import RosterViews from "@/components/RosterViews";
import ConflictDrawer from "@/components/ConflictDrawer";
import ManagementTabs, { ManagementSubTab } from "@/components/ManagementTabs";
import PlanComparisonModal from "@/components/PlanComparisonModal";
import EvaluatorGuideModal from "@/components/EvaluatorGuideModal";
import SmartRosterLogo from "@/components/SmartRosterLogo";

function formatNotificationTime(iso: string): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  try {
    return new Intl.DateTimeFormat(undefined, {
      day: "numeric",
      month: "short",
      hour: "numeric",
      minute: "2-digit",
    }).format(date);
  } catch {
    return iso;
  }
}

export default function HomePage() {
  const [month, setMonth] = useState("2026-12");
  const [mainSection, setMainSection] = useState<"workspace" | "setup">("workspace");
  const [setupInitialTab, setSetupInitialTab] = useState<ManagementSubTab>("team");

  const [healthStatus, setHealthStatus] = useState<"checking" | "connected" | "error">("checking");
  const [initializing, setInitializing] = useState(true);
  const [loadingRoster, setLoadingRoster] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const [rosterData, setRosterData] = useState<MonthlyRosterResponse | null>(null);
  const [bottlenecks, setBottlenecks] = useState<BottlenecksResponse | null>(null);
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

  const [userRole, setUserRole] = useState<"OPS_MANAGER" | "POD_LEAD">("OPS_MANAGER");
  const [compareModalOpen, setCompareModalOpen] = useState(false);
  const [guideOpen, setGuideOpen] = useState(false);
  const [approvingPod, setApprovingPod] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [publishOverrideModal, setPublishOverrideModal] = useState<{
    hardConflictsCount: number;
    detail: string;
  } | null>(null);
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [notifOpen, setNotifOpen] = useState(false);
  const [markingNotifs, setMarkingNotifs] = useState(false);

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

  const loadNotifications = useCallback(async (targetMonth: string) => {
    const list = await fetchNotifications(targetMonth).catch(() => []);
    setNotifications(list);
  }, []);

  const loadBottlenecks = useCallback(async (targetMonth: string) => {
    const data = await fetchBottlenecks(targetMonth).catch(() => null);
    setBottlenecks(data);
  }, []);

  const handleRosterUpdated = useCallback(
    (updated: MonthlyRosterResponse) => {
      setRosterData(updated);
      loadBottlenecks(updated.month);
      if (updated.status === "PUBLISHED") {
        loadNotifications(updated.month);
      }
    },
    [loadBottlenecks, loadNotifications]
  );

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
      await Promise.all([loadNotifications(targetMonth), loadBottlenecks(targetMonth)]);
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to load roster from backend.");
    } finally {
      setLoadingRoster(false);
    }
  }, [loadBottlenecks, loadNotifications]);

  useEffect(() => {
    const init = async () => {
      try {
        try {
          setHealthStatus("checking");
          await fetchHealth();
          setHealthStatus("connected");
        } catch {
          setHealthStatus("error");
        }
        await loadEntities();
        await loadOrGenerateRoster(month);
      } finally {
        setInitializing(false);
      }
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
      await Promise.all([loadEntities(), loadBottlenecks(month)]);
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
      await loadBottlenecks(month);
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to reset demo data.");
    } finally {
      setResetting(false);
    }
  };

  const openConflictsDrawer = useCallback((severity: "ALL" | "HARD" | "SOFT" = "ALL") => {
    setNotifOpen(false);
    setDrawerSeverity(severity);
    setDrawerOpen(true);
  }, []);

  const handleApprovePod = async () => {
    try {
      setApprovingPod(true);
      setErrorMsg(null);
      const updated = await approvePodRoster(month);
      setRosterData(updated);
      await loadNotifications(month);
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to approve pod roster.");
    } finally {
      setApprovingPod(false);
    }
  };

  const handlePublish = async (force: boolean = false) => {
    if (!force && hardConflictsCount > 0) {
      setPublishOverrideModal({
        hardConflictsCount,
        detail: `This roster still has ${hardConflictsCount} unresolved HARD conflict(s). Publishing now will notify stakeholders with active coverage gaps.`,
      });
      return;
    }
    try {
      setPublishing(true);
      setErrorMsg(null);
      const res = await publishRoster(month, force);
      if (res.requiresForce) {
        setPublishOverrideModal({
          hardConflictsCount: res.hardConflictsCount,
          detail: res.detail,
        });
        return;
      }
      setRosterData(res.roster);
      setPublishOverrideModal(null);
      await loadNotifications(month);
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to publish roster.");
    } finally {
      setPublishing(false);
    }
  };

  const handleMarkAllRead = async () => {
    try {
      setMarkingNotifs(true);
      await markNotificationsRead();
      setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to mark notifications read.");
    } finally {
      setMarkingNotifs(false);
    }
  };

  const unreadNotifsCount = notifications.filter((n) => !n.read).length;
  const workflowStatus = rosterData?.status || "DRAFT";
  const pendingLeavesCount = leaves.filter((l) => l.status === "PENDING").length;
  const totalConflictsCount = rosterData?.conflicts?.length ?? 0;
  const hardConflictsCount = rosterData?.kpis?.hard_conflicts_count ?? 0;

  return (
    <div className="min-h-screen bg-[#FAFAFC] text-[#0a0a0a]">
      {/* Frosted Editorial Light Header */}
      <header className="sticky top-0 z-30 bg-white/85 backdrop-blur-md border-b border-neutral-200">
        <div className="max-w-[1440px] mx-auto px-4 sm:px-8 py-3.5 flex flex-col lg:flex-row lg:items-center justify-between gap-3">
          {/* Brand & Status */}
          <div className="flex items-center gap-3.5">
            <SmartRosterLogo size={40} className="shadow-md shadow-blue-600/25 rounded-2xl" />
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
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-xs font-semibold shadow-sm shadow-blue-600/15 transition-colors"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loadingRoster ? "animate-spin" : ""}`} />
              {loadingRoster ? "Solving..." : "Generate Roster"}
            </button>

            {/* Compare Plans */}
            <button
              type="button"
              onClick={() => setCompareModalOpen(true)}
              disabled={loadingRoster || resetting}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-full bg-white hover:bg-neutral-100 border border-neutral-200 text-neutral-700 text-xs font-semibold transition-colors disabled:opacity-50"
            >
              <Sliders className="w-3.5 h-3.5 text-blue-600" />
              Compare Plans
            </button>

            {/* Reset Demo Data */}
            <button
              type="button"
              onClick={handleResetDemo}
              disabled={resetting || loadingRoster}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-full bg-white hover:bg-neutral-100 border border-neutral-200 text-neutral-700 text-xs font-medium transition-colors disabled:opacity-50"
            >
              <RotateCcw className={`w-3.5 h-3.5 ${resetting ? "animate-spin" : ""}`} />
              {resetting ? "Resetting..." : "Reset Demo"}
            </button>

            {/* Quick Guide Modal Trigger */}
            <button
              type="button"
              onClick={() => setGuideOpen(true)}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-full bg-white hover:bg-neutral-100 border border-neutral-200 text-neutral-700 text-xs font-medium transition-colors"
              title="Open Quick Guide"
            >
              <BookOpen className="w-3.5 h-3.5 text-blue-600" />
              Quick Guide
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

            {/* Export Excel (.xlsx) */}
            <a
              href={getExcelExportUrl(month)}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-full bg-white hover:bg-neutral-100 border border-neutral-200 text-neutral-700 text-xs font-medium transition-colors"
            >
              <FileSpreadsheet className="w-3.5 h-3.5 text-emerald-600" />
              Export Excel (.xlsx)
            </a>

            {/* Conflicts Drawer Trigger */}
            <button
              type="button"
              onClick={() => openConflictsDrawer("ALL")}
              className={`cursor-pointer inline-flex items-center gap-1.5 px-3.5 py-2 rounded-full text-xs font-semibold border transition-colors ${
                hardConflictsCount > 0
                  ? "bg-red-50 border-red-200 text-red-700 hover:bg-red-100"
                  : "bg-white border-neutral-200 text-neutral-700 hover:bg-neutral-100"
              }`}
            >
              <ShieldAlert className="w-3.5 h-3.5" />
              Conflicts ({totalConflictsCount})
            </button>

            {/* Notification Bell */}
            <div className="relative">
              <button
                type="button"
                onClick={() => setNotifOpen((prev) => !prev)}
                className="relative p-2 rounded-full bg-white hover:bg-neutral-100 border border-neutral-200 text-neutral-700 transition-colors"
                aria-label="Notifications"
              >
                <Bell className="w-4 h-4" />
                {unreadNotifsCount > 0 && (
                  <span className="absolute -top-1 -right-1 min-w-[18px] h-[18px] px-1 rounded-full bg-rose-600 text-white text-[10px] font-bold flex items-center justify-center tabular-nums">
                    {unreadNotifsCount}
                  </span>
                )}
              </button>

              {notifOpen && (
                <>
                  <div className="fixed inset-0 z-40" onClick={() => setNotifOpen(false)} />
                  <div className="absolute right-0 mt-2 w-80 sm:w-96 bg-white border border-neutral-200 rounded-2xl shadow-xl z-50 overflow-hidden">
                  <div className="px-4 py-3 border-b border-neutral-200 flex items-center justify-between bg-neutral-50">
                    <div>
                      <h3 className="text-xs font-bold text-neutral-950">
                        Roster Audit &amp; Notifications
                      </h3>
                      <p className="text-[11px] text-neutral-500">
                        {unreadNotifsCount} unread update(s) for {month}
                      </p>
                    </div>
                    <button
                      type="button"
                      disabled={markingNotifs || unreadNotifsCount === 0}
                      onClick={handleMarkAllRead}
                      className="text-[11px] font-semibold text-blue-600 hover:text-blue-800 disabled:opacity-40"
                    >
                      Mark all read
                    </button>
                  </div>
                  <div className="max-h-72 overflow-y-auto divide-y divide-neutral-100">
                    {notifications.length === 0 ? (
                      <div className="p-6 text-center text-xs text-neutral-500">
                        No published-roster change logs yet.
                      </div>
                    ) : (
                      notifications.map((n) => (
                        <div
                          key={n.id}
                          className={`px-4 py-3 text-xs space-y-1 ${
                            n.read ? "bg-white" : "bg-blue-50/50"
                          }`}
                        >
                          <div className="flex items-center justify-between gap-2">
                            <span className="font-semibold text-neutral-900">
                              {n.title || n.action_type || "Roster Update"}
                            </span>
                            {!n.read && (
                              <span className="w-2 h-2 rounded-full bg-blue-600 flex-shrink-0" />
                            )}
                          </div>
                          <p className="text-neutral-600 leading-relaxed">{n.message}</p>
                          <div className="text-[10px] text-neutral-400 tabular-nums">
                            {n.actor ? `${n.actor} · ` : ""}
                            {formatNotificationTime(n.created_at)}
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>
                </>
              )}
            </div>
          </div>
        </div>

        {/* Clean Pill Navigation Bar + Role Switcher + Workflow Approval Bar */}
        <div className="max-w-[1440px] mx-auto px-4 sm:px-8 pb-3 flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-3">
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

            {/* Role Switcher Pill */}
            <div
              className="inline-flex items-center p-1 rounded-full bg-neutral-100 border border-neutral-200/80"
              role="group"
              aria-label="Role Switcher"
            >
              <button
                type="button"
                onClick={() => setUserRole("OPS_MANAGER")}
                className={`px-3 py-1 rounded-full text-[11px] font-semibold transition-all ${
                  userRole === "OPS_MANAGER"
                    ? "bg-neutral-900 text-white shadow-xs"
                    : "text-neutral-600 hover:text-neutral-950"
                }`}
              >
                Ops Manager
              </button>
              <button
                type="button"
                onClick={() => setUserRole("POD_LEAD")}
                className={`px-3 py-1 rounded-full text-[11px] font-semibold transition-all ${
                  userRole === "POD_LEAD"
                    ? "bg-neutral-900 text-white shadow-xs"
                    : "text-neutral-600 hover:text-neutral-950"
                }`}
              >
                Pod Lead
              </button>
            </div>
          </div>

          {/* Roster Workflow Status & Approval Bar */}
          <div className="flex flex-wrap items-center gap-2">
            <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full border border-neutral-200 bg-neutral-50 text-[11px] font-semibold text-neutral-700">
              <span>Status:</span>
              <span
                className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                  workflowStatus === "PUBLISHED"
                    ? "bg-emerald-600 text-white"
                    : workflowStatus === "POD_APPROVED"
                    ? "bg-blue-600 text-white"
                    : "bg-slate-200 text-slate-800"
                }`}
              >
                {workflowStatus}
              </span>
            </div>

            {workflowStatus === "DRAFT" && (
              <button
                type="button"
                disabled={approvingPod || !rosterData}
                onClick={handleApprovePod}
                className={`inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-full text-xs font-semibold transition-colors disabled:opacity-50 ${
                  userRole === "POD_LEAD"
                    ? "bg-blue-600 hover:bg-blue-700 text-white shadow-xs"
                    : "bg-white hover:bg-neutral-100 border border-neutral-200 text-neutral-700"
                }`}
              >
                {approvingPod ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <UserCheck className="w-3.5 h-3.5" />
                )}
                {approvingPod ? "Approving..." : "Approve as Pod Lead"}
              </button>
            )}

            {workflowStatus !== "PUBLISHED" ? (
              <button
                type="button"
                disabled={publishing || !rosterData}
                onClick={() => handlePublish(false)}
                className={`inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-full text-xs font-semibold transition-colors disabled:opacity-50 ${
                  userRole === "OPS_MANAGER"
                    ? "bg-emerald-600 hover:bg-emerald-700 text-white shadow-xs"
                    : "bg-white hover:bg-neutral-100 border border-neutral-200 text-neutral-700"
                }`}
              >
                {publishing ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Send className="w-3.5 h-3.5" />
                )}
                {publishing ? "Publishing..." : "Publish Roster"}
              </button>
            ) : (
              <span className="inline-flex items-center gap-1 px-3 py-1.5 rounded-full bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-semibold">
                <CheckCircle2 className="w-3.5 h-3.5" />
                Published
              </span>
            )}

            <div className="hidden xl:flex items-center gap-1.5 text-[11px] text-neutral-500 pl-2 border-l border-neutral-200">
              <Info className="w-3.5 h-3.5 text-neutral-400" />
              <button
                type="button"
                onClick={() => openConflictsDrawer("HARD")}
                className="font-semibold text-neutral-700 underline underline-offset-2 hover:text-neutral-950"
              >
                1-click backup
              </button>
            </div>
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
        {initializing ? (
          <div
            className="grid grid-cols-2 lg:grid-cols-5 gap-3"
            aria-label="Loading metrics"
          >
            {Array.from({ length: 5 }).map((_, idx) => (
              <div
                key={idx}
                className="bg-white border border-neutral-200 rounded-2xl p-4 animate-pulse"
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="h-3 w-24 bg-neutral-200 rounded" />
                  <div className="w-7 h-7 rounded-lg bg-neutral-100" />
                </div>
                <div className="h-7 w-16 bg-neutral-200 rounded-md mt-1" />
                <div className="h-3 w-28 bg-neutral-100 rounded mt-2.5" />
              </div>
            ))}
          </div>
        ) : (
          <KpiBar
            kpis={rosterData?.kpis || null}
            totalEmployeesFallback={employees.length}
            pendingLeavesCount={pendingLeavesCount}
            podCount={pods.length}
            onOpenConflicts={openConflictsDrawer}
            onJumpToLeaves={() => {
              setSetupInitialTab("leaves");
              setMainSection("setup");
            }}
          />
        )}

        {/* Pending Leaves Banner (DEMO-4 Live Flow) */}
        <PendingLeavesBanner
          month={month}
          leaves={leaves}
          employees={employees}
          currentRoster={rosterData}
          onRosterUpdated={handleRosterUpdated}
          onLeavesUpdated={loadEntities}
          onOpenConflicts={openConflictsDrawer}
        />

        {/* Workspace vs Setup */}
        {mainSection === "workspace" ? (
          initializing ? (
            <div className="bg-white border border-neutral-200 rounded-2xl p-12 text-center shadow-xs">
              <div className="inline-flex flex-col items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center">
                  <Loader2 className="w-5 h-5 animate-spin" />
                </div>
                <div className="space-y-1">
                  <p className="text-sm font-semibold text-neutral-950">
                    Waking up scheduling engine...
                  </p>
                  <p className="text-xs text-neutral-500">
                    Connecting to backend and loading roster data for {month}.
                  </p>
                </div>
              </div>
            </div>
          ) : rosterData ? (
            <div className="space-y-6">
              <BottleneckInsights
                data={bottlenecks}
                onOpenConflicts={() => openConflictsDrawer("HARD")}
              />
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
                onRosterUpdated={handleRosterUpdated}
              />
            </div>
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
            onRosterUpdated={handleRosterUpdated}
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
        onRosterUpdated={handleRosterUpdated}
      />

      {/* Plan Comparison Modal */}
      <PlanComparisonModal
        open={compareModalOpen}
        onClose={() => setCompareModalOpen(false)}
        month={month}
        onRosterUpdated={handleRosterUpdated}
      />

      {/* Publish Override Warning Confirmation Modal */}
      {publishOverrideModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-neutral-950/35 backdrop-blur-[2px]">
          <div className="bg-white border border-neutral-200 rounded-2xl shadow-2xl w-full max-w-md overflow-hidden">
            <div className="px-5 py-4 border-b border-neutral-200 flex items-center justify-between bg-rose-50/70">
              <div className="flex items-center gap-2 text-rose-800">
                <AlertTriangle className="w-5 h-5 text-rose-600" />
                <h3 className="text-sm font-bold">Unresolved Hard Conflicts</h3>
              </div>
              <button
                type="button"
                onClick={() => setPublishOverrideModal(null)}
                className="p-1.5 rounded-lg text-neutral-400 hover:text-neutral-700 hover:bg-white"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="p-5 space-y-4">
              <p className="text-xs text-neutral-700 leading-relaxed">
                {publishOverrideModal.detail}
              </p>
              <div className="bg-rose-50 border border-rose-200 rounded-xl px-3.5 py-2.5 text-xs font-semibold text-rose-800">
                Hard Conflicts Remaining: {publishOverrideModal.hardConflictsCount}
              </div>
              <div className="flex items-center justify-end gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => {
                    setPublishOverrideModal(null);
                    openConflictsDrawer("HARD");
                  }}
                  className="px-3.5 py-2 rounded-lg border border-neutral-200 text-xs font-semibold text-neutral-700 hover:bg-neutral-50"
                >
                  Resolve Conflicts
                </button>
                <button
                  type="button"
                  disabled={publishing}
                  onClick={() => handlePublish(true)}
                  className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-rose-600 hover:bg-rose-700 text-white text-xs font-semibold shadow-xs disabled:opacity-50"
                >
                  {publishing && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                  Publish Anyway (Override)
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
      {/* Quick Guide Modal */}
      <EvaluatorGuideModal open={guideOpen} onClose={() => setGuideOpen(false)} />

      {/* Read-Only Roster Copilot */}
      <RosterCopilot month={month} employees={employees} brands={brands} />
    </div>
  );
}
