import { useNavigate } from 'react-router-dom';
import type { Project } from '../types/api';
import { formatDateTime } from '../lib/format';
import { STATUS_LABELS } from '../lib/project';

interface ProjectCardProps {
  project: Project;
}

export function ProjectCard({ project }: ProjectCardProps) {
  const navigate = useNavigate();

  return (
    <div className="demo-project-card">
      <div className="eyebrow">
        {project.status === 'researching' || project.status === 'supplementing_research' ? '当前项目' : '历史项目'}
      </div>
      <h3 style={{ fontSize: 15, margin: '6px 0' }}>{project.brief.category}</h3>
      <div className="meta">
        <span>{STATUS_LABELS[project.status]}</span>
        <span>进度：{project.progress}%</span>
        <span>最近更新：{formatDateTime(project.updated_at)}</span>
      </div>
      <div className="demo-actions">
        <button className="demo-btn demo-btn--primary" onClick={() => navigate(`/projects/${project.project_id}`)}>继续研究</button>
      </div>
    </div>
  );
}

interface EmptyProjectCardProps {
  eyebrow: string;
  title: string;
}

export function EmptyProjectCard({ eyebrow, title }: EmptyProjectCardProps) {
  return (
    <div className="demo-project-card demo-project-card--empty">
      <div className="eyebrow">{eyebrow}</div>
      <h3 style={{ fontSize: 15, margin: '6px 0' }}>{title}</h3>
    </div>
  );
}
