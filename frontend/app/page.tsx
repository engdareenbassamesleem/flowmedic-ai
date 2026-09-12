"use client";

import Link from "next/link";

import { IncidentTable } from "@/components/incident-table";
import { MetricCard } from "@/components/metric-card";
import { PageHeader } from "@/components/page-header";
import { StatePanel } from "@/components/state-panel";
import { api } from "@/lib/api";
import { useApi } from "@/lib/use-api";

export default function OverviewPage() {
  const incidents = useApi(() => api.incidents(50, 0));
  const workflows = useApi(() => api.workflows(100));
  const system = useApi(() => api.systemStatus());

  const incidentRows = incidents.data?.data ?? [];
  const openIncidents = incidentRows.filter((incident) => incident.status === "open").length;
  const highSeverity = incidentRows.filter((incident) => incident.severity === "high").length;
  const workflowsWithIncidents = new Set(incidentRows.map((incident) => incident.workflow_id)).size;

  return <>
    <PageHeader title="Automation health" description="A focused view of persisted incidents and your connected n8n workflows. Values become available only when the backend can retrieve them." action={<Link className="button button-secondary" href="/incidents">Review incidents</Link>} />
    <section className="metric-grid" aria-label="Automation health metrics">
      <MetricCard label="Monitored workflows" value={workflows.loading ? "…" : workflows.data?.data.length ?? "—"} detail={workflows.error ? "n8n is unavailable" : "From current workflow page"} />
      <MetricCard label="Workflows with incidents" value={incidents.loading ? "…" : workflowsWithIncidents} detail="Derived from persisted incidents" tone="danger" />
      <MetricCard label="Open incidents" value={incidents.loading ? "…" : openIncidents} detail="Requires human review" tone={openIncidents ? "danger" : "success"} />
      <MetricCard label="Critical incidents" value="Not available yet" detail="Backend has no critical severity" tone="muted" />
      <MetricCard label="High-severity incidents" value={incidents.loading ? "…" : highSeverity} detail="Backend reports medium/high only" tone={highSeverity ? "danger" : "success"} />
      <MetricCard label="Healthy workflows" value="Not available yet" detail="No health history endpoint" tone="muted" />
    </section>
    <section className="overview-secondary mt-4">
      <div className="panel overflow-hidden">
        <div className="panel-header"><div><h2>Recent incidents</h2><p>Persisted incidents from the existing backend.</p></div><Link href="/incidents" className="text-sm text-blue-300 hover:text-blue-200">View all</Link></div>
        {incidents.loading && <StatePanel title="Loading incidents" message="Requesting persisted incidents from FlowMedic." />}
        {incidents.error && <StatePanel title="Incidents unavailable" message={incidents.error.message} action={<button className="button button-secondary" onClick={() => void incidents.refresh()}>Try again</button>} />}
        {!incidents.loading && !incidents.error && incidentRows.length === 0 && <StatePanel title="No incidents yet" message="Connect n8n and sync failed executions to populate this dashboard." />}
        {!incidents.loading && !incidents.error && incidentRows.length > 0 && <IncidentTable incidents={incidentRows.slice(0, 6)} compact />}
      </div>
      <aside className="panel trend-placeholder"><h2>Incident trend</h2><p className="mt-1 text-sm text-slate-400">Historical metrics are not available yet.</p><div className="trend-grid" aria-label="Placeholder: historical incident metrics are unavailable"><span className="trend-line" /></div><small>Retention and time-series aggregation are planned for a later backend phase.</small></aside>
    </section>
    <section className="mt-4 panel p-5"><div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center"><div><h2>Connection status</h2><p className="mt-1 text-sm text-slate-400">Secret values are never displayed in this dashboard.</p></div><div className="flex flex-wrap gap-2 text-sm"><span className={system.data?.n8n_configured ? "badge badge-success" : "badge badge-muted"}>n8n {system.data?.n8n_configured ? "configured" : "not configured"}</span><span className="badge badge-info">AI {system.data?.ai_mode ?? "unknown"}</span><span className="badge badge-muted">DB {system.data?.database_engine ?? "unknown"}</span></div></div></section>
  </>;
}
