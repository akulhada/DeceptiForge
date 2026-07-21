// Purpose: the single source of truth for which surfaces this frontend build exposes.
// Responsibilities: read the build-time deployment mode, decide route eligibility, and derive
//   navigation. Kept in one module so a route cannot disagree with the navigation about whether it
//   exists — hiding a link is not a control, so every gated route also checks eligibility itself.
// Dependencies: none.

export type DeploymentMode = 'development' | 'test' | 'judge' | 'staging' | 'production';

const MODES: readonly DeploymentMode[] = [
  'development',
  'test',
  'judge',
  'staging',
  'production',
];

/**
 * Resolve the build-time mode. An unrecognised or absent value resolves to `production`, the most
 * restrictive mode: a misconfigured deployment must hide demonstration surfaces, never reveal them.
 */
export function deploymentMode(raw: string | undefined = process.env.NEXT_PUBLIC_APP_ENV): DeploymentMode {
  return MODES.includes(raw as DeploymentMode) ? (raw as DeploymentMode) : 'production';
}

/** The curated story. Development and judge only, and only when the build enables it. */
export function demoEnabled(
  mode: DeploymentMode = deploymentMode(),
  flag: string | undefined = process.env.NEXT_PUBLIC_DEMO_MODE,
): boolean {
  return (mode === 'development' || mode === 'judge') && flag === 'true';
}

/** The restricted judge workspace at the root route. */
export function judgeWorkspaceEnabled(
  mode: DeploymentMode = deploymentMode(),
  flag: string | undefined = process.env.NEXT_PUBLIC_JUDGE_WORKSPACE_ENABLED,
): boolean {
  return (mode === 'development' || mode === 'judge') && flag === 'true';
}

/**
 * The Analysis Lab. Development and test only — never a hosted environment. The backend refuses to
 * mount its routes there regardless, so this only keeps the UI honest about what exists.
 */
export function analysisLabEnabled(
  mode: DeploymentMode = deploymentMode(),
  flag: string | undefined = process.env.NEXT_PUBLIC_ANALYSIS_LAB_ENABLED,
): boolean {
  return (mode === 'development' || mode === 'test') && flag === 'true';
}

export interface NavItem {
  readonly href: string;
  readonly label: string;
}

/**
 * Navigation derived from environment, never hardcoded per page.
 *
 * A hosted judge sees the demo and their workspace. They never see the Analysis Lab, platform
 * controls, tenant administration or connector configuration — those are not in this list at all,
 * so there is no link to hide.
 */
export function navigationFor(mode: DeploymentMode = deploymentMode()): NavItem[] {
  const items: NavItem[] = [];
  if (demoEnabled(mode)) items.push({ href: '/demo', label: 'Demo' });
  if (judgeWorkspaceEnabled(mode)) items.push({ href: '/', label: 'Workspace' });
  if (analysisLabEnabled(mode)) items.push({ href: '/analysis-lab', label: 'Analysis Lab' });
  return items;
}
