import { Link, useParams } from 'react-router-dom';

import { useWorkspaceQuery } from '../shared/api/hooks';
import { EmptyState } from '../shared/ui/primitives';
import { MetricsSummaryPanel } from '../widgets/app-shell/WorkbenchComponents';

export function ProjectMetricsPage() {
  const params = useParams();
  const projectId = params.projectId ?? '';
  const workspaceQuery = useWorkspaceQuery(projectId);

  if (workspaceQuery.isLoading) {
    return <main className="screen"><EmptyState title="加载中" description="正在读取方法对比指标。" /></main>;
  }

  if (!workspaceQuery.data) {
    return <main className="screen"><EmptyState title="项目不存在" description="请返回工作台重新选择项目。" /></main>;
  }

  return (
    <main className="screen screen--editorial">
      <div className="screen__hero screen__hero--compact">
        <Link className="ui-button ui-button--ghost" to={`/projects/${projectId}`}>
          返回工作台
        </Link>
      </div>
      <MetricsSummaryPanel metrics={workspaceQuery.data.metrics} />
    </main>
  );
}
