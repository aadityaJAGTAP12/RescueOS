/**
 * Organization identity context (frontend mirror of agent/org_context.py).
 *
 * IDENTITY / CONTEXT ONLY — NOT AUTHENTICATION.
 *
 * There is no password and no credential anywhere in this flow: anyone can
 * select any organization from the picker (or forge the reliefos_org_id
 * cookie). This is deliberately not safe for a multi-tenant public
 * deployment as-is; real authentication is deferred to a specific future
 * deployment's needs. The value here is the seam: every org-scoped fetch in
 * the workspace derives its target org from this module instead of a
 * hardcoded constant or a client-trusted id.
 *
 * The authoritative org is whatever the SERVER resolves from the
 * reliefos_org_id cookie (GET /api/session/org). This module caches that
 * resolution in memory and mirrors the selection into a cookie for
 * convenience only. Privileged endpoints (/api/my-org/*) do not accept an
 * org id from the client at all — the server always re-derives it.
 */

const ORG_COOKIE_NAME = "reliefos_org_id";
const DEFAULT_ORG_ID = "org_demo";

let cachedOrgId = null;
let inflight = null;

function readCookie(name) {
  const match = document.cookie.match(
    new RegExp(`(?:^|;\\s*)${name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}=([^;]*)`)
  );
  return match ? decodeURIComponent(match[1]) : null;
}

function writeCookie(name, value) {
  // 30-day preference cookie — identity convenience only, NOT a credential.
  document.cookie = `${name}=${encodeURIComponent(value)}; max-age=${30 * 24 * 3600}; path=/; samesite=lax`;
}

/**
 * Resolve the current organization id.
 *
 * Order: in-memory cache → cookie mirror → GET /api/session/org (the
 * server's authoritative resolution) → DEFAULT_ORG_ID. Never guess silently
 * for a privileged action: pass `{ allowFallback: false }` and this throws
 * when no authoritative resolution is available.
 */
export async function getCurrentOrgId({ allowFallback = true } = {}) {
  if (cachedOrgId) return cachedOrgId;
  const cookieOrg = readCookie(ORG_COOKIE_NAME);
  if (cookieOrg) {
    cachedOrgId = cookieOrg;
    return cachedOrgId;
  }
  if (!inflight) {
    inflight = fetch("/api/session/org")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`session org ${r.status}`))))
      .then((data) => {
        cachedOrgId = data.org_id || DEFAULT_ORG_ID;
        return cachedOrgId;
      })
      .finally(() => {
        inflight = null;
      });
  }
  try {
    return await inflight;
  } catch (err) {
    if (allowFallback) return DEFAULT_ORG_ID;
    throw err;
  }
}

/**
 * Select the organization context. Creates the organization first when
 * `create` is provided. Always goes through POST /api/session/org so the
 * server — not the client — is the authority on the selected org.
 */
export async function selectOrg({ orgId, create } = {}) {
  if (create && create.name && create.name.trim()) {
    const resp = await fetch("/api/organizations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: create.name.trim(),
        organization_type: create.organization_type || "ngo",
        description: create.description || "",
      }),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.error || `Failed to create organization (${resp.status})`);
    }
    const data = await resp.json();
    orgId = data.organization.id;
  }
  if (!orgId) throw new Error("orgId or create is required");

  const resp = await fetch("/api/session/org", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ org_id: orgId }),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.error || `Failed to select organization (${resp.status})`);
  }
  const data = await resp.json();
  cachedOrgId = data.org_id;
  // Mirror into a cookie for tools/refreshes; the server cookie is the truth.
  writeCookie(ORG_COOKIE_NAME, data.org_id);
  return data;
}

/** Test/diagnostic helper: forget the in-memory cached resolution. */
export function resetOrgContextCache() {
  cachedOrgId = null;
  inflight = null;
}
