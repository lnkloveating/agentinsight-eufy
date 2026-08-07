import { Link, useParams } from 'react-router-dom';

import { useWorkspaceQuery } from '../shared/api/hooks';
import { EmptyState } from '../shared/ui/primitives';

export function ScenarioVerificationPage() {
  const params = useParams();
  const projectId = params.projectId ?? '';
  const workspaceQuery = useWorkspaceQuery(projectId);

  if (workspaceQuery.isLoading) {
    return <main className="screen"><EmptyState title="加载中" description="正在读取场景验证数据。" /></main>;
  }

  if (!workspaceQuery.data) {
    return <main className="screen"><EmptyState title="项目不存在" description="请返回工作台重新选择项目。" /></main>;
  }

  const scenarios = workspaceQuery.data.project.brief.scenarios;

  return (
    <main className="screen screen--editorial">
      <div className="screen__hero screen__hero--compact">
        <Link className="ui-button ui-button--ghost" to={`/projects/${projectId}`}>
          返回工作台
        </Link>
      </div>
      <section className="scenario-verification">
        <header className="scenario-verification__header">
          <p className="section-heading__eyebrow">Scenario Verification</p>
          <h2>场景验证</h2>
          <p className="scenario-verification__desc">
            以下为当前研究项目涉及的验证场景，用于覆盖目标用户在不同真实环境下的使用路径。
          </p>
        </header>
        <div className="scenario-verification__list">
          {scenarios.map((scenario, index) => (
            <article className="scenario-verification__item" key={scenario}>
              <span className="scenario-verification__index">{index + 1}</span>
              <div className="scenario-verification__body">
                <h3 className="scenario-verification__name">{scenario}</h3>
                <p className="scenario-verification__status">待验证</p>
              </div>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}
