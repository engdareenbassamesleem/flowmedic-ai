# Engineering review — 2026-10-31

Reviewed baseline: `c01b894` on `main`. The current repository includes monitoring,
alerting, migrations, and a public synthetic demo in addition to the original backend
and dashboard. This review preserves that newer work.

## Defects addressed

1. **P1 — Backend image cannot migrate on startup.** `Dockerfile` copied `app` but not
   `alembic.ini` or the migration scripts. A successful image build did not establish
   that the application could start with its default file-backed database. Copy both
   migration assets and exercise actual container startup in CI.
2. **P1 — Backfill can overwrite the meaning of recent health.** Health windows were
   sorted by ingestion time, so historical failures fetched after fresh successes could
   displace current executions and trigger an incorrect unhealthy classification. Sort
   by execution timestamps, with ingestion time only as a missing-timestamp fallback.
3. **P1 — Running executions never acquire their terminal result.** Deduplication returned
   an existing history row without updating it. Refresh nonterminal rows on subsequent
   observations, preserving row identity and never regressing terminal state on stale polls.
4. **P1 — Monitoring bypassed workflow-name sanitization.** Workflow names were persisted
   unchanged and exposed by metrics, unlike the normalized incident path. Sanitize names
   using configured secrets before persistence. This does not retroactively cleanse rows
   that are never observed again; existing databases may need an operator-reviewed cleanup.
5. **P2 — CORS preflight failed when bearer protection was enabled.** Authentication ran
   before CORS, rejecting unauthenticated browser OPTIONS requests; rejected actual
   requests also lacked CORS headers. Make CORS outermost and include the existing PATCH
   endpoint method, while preserving authentication on actual protected requests.
6. **P2 — Stale frontend requests could replace current incident data.** The shared hook
   had no ordering/unmount guard and retained the previous route's data. Track request
   generations, invalidate on route change/unmount, and hide data from a different key.

Regression tests cover backfill ordering at workflow/global scopes, terminal updates,
redaction, authenticated preflight, and frontend response races.

## Remaining production boundaries

- The dashboard has no credential-entry/session mechanism for bearer-protected backend
  deployments. It remains a local/trusted dashboard or a synthetic public read-only demo.
- Webhook delivery is synchronous and can delay the async polling/API path. A durable
  delivery worker with retry scheduling and recovery is needed before production scale.
- Metrics load retained history into Python memory. Move aggregation/windowing into SQL
  and add scale tests before large deployments.
- Monitoring does not heartbeat its lease during a long sequence of detail requests;
  a slow page can outlive the lease. Per-request lease renewal/fencing needs a dedicated
  concurrency regression before multi-worker production deployment.
- Existing live credentials and real n8n/webhook traffic are not used for this review.
- Synthetic-demo labeling and disabling read-only actions in the dashboard still need
  a dedicated UI pass; a backend 403 alone is not a complete read-only user experience.

These limits mean the project is a useful, modular MVP, not yet a fully hardened
multi-user production service. Passing tests should not be presented as proof otherwise.
