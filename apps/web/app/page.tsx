// Purpose: the root route.
// Responsibilities: serve the restricted judge workspace where this build offers it, and the
//   ordinary authenticated tenant workspace everywhere else. There is no separate /judge route:
//   maintaining two components with duplicated state was the thing this route model removed.
// Dependencies: deployment mode, judge workspace, tenant dashboard.
'use client';

import { JudgeWorkspace } from '@/components/judge/JudgeWorkspace';
import { TenantDashboard } from '@/components/dashboard/TenantDashboard';
import { judgeWorkspaceEnabled } from '@/services/deploymentMode';

export default function RootPage() {
  return judgeWorkspaceEnabled() ? <JudgeWorkspace /> : <TenantDashboard />;
}
