"use client";

import { PageHeader } from "@/components/page-header";
import { StatePanel } from "@/components/state-panel";
import { api } from "@/lib/api";
import { useApi } from "@/lib/use-api";

export default function WorkflowsPage() {
  const workflows = useApi(() => api.workflows(100));
  return <><PageHeader title="Workflows" description="Workflow summaries provided directly by the configured n8n instance. Execution health, last checked time, and incident counts are not exposed by the current backend." />
    <section className="panel overflow-hidden">
      <div className="panel-header"><div><h2>Monitored workflows</h2><p>Current page from the n8n workflow API.</p></div></div>
      {workflows.loading && <StatePanel title="Loading workflows" message="Checking the n8n connection." />}
      {workflows.error && <StatePanel title="Workflows unavailable" message={workflows.error.message} action={<button className="button button-secondary" onClick={() => void workflows.refresh()}>Try again</button>} />}
      {!workflows.loading && !workflows.error && workflows.data?.data.length === 0 && <StatePanel title="No workflows returned" message="Connect an n8n instance with workflow-read permission to view workflow summaries." />}
      {!workflows.loading && !workflows.error && (workflows.data?.data.length ?? 0) > 0 && <div className="data-table-wrap"><table className="data-table"><thead><tr><th>Workflow</th><th>Workflow ID</th><th>Configuration state</th><th>Latest execution</th><th>Last checked</th><th>Incident count</th></tr></thead><tbody>{workflows.data?.data.map((workflow) => <tr key={workflow.id}><td className="font-medium text-slate-100">{workflow.name}</td><td className="font-mono text-xs text-slate-400">{workflow.id}</td><td><span className={workflow.active ? "badge badge-success" : "badge badge-muted"}>{workflow.active ? "active" : "inactive"}</span></td><td>Not available yet</td><td>Not available yet</td><td>Not available yet</td></tr>)}</tbody></table></div>}
    </section>
  </>;
}
