// Purpose: client-side hint for who may run analysis (server enforces analysis:preview centrally).
// Responsibilities: mirror the role->scope catalog for a friendly pre-flight message only. The
//   backend is always the authority; this never grants access.

// Roles that carry analysis:preview (viewer is read-only and included; sensors are not).
const ANALYSIS_ROLES = new Set(['owner', 'admin', 'analyst', 'viewer']);

export function roleCanPreview(role: string | undefined): boolean {
  return role !== undefined && ANALYSIS_ROLES.has(role);
}
