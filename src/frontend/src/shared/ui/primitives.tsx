import type { PropsWithChildren, ReactNode } from 'react';
import { Link, NavLink } from 'react-router-dom';

export function Button({
  children,
  tone = 'primary',
  type = 'button',
  disabled = false,
  onClick,
}: PropsWithChildren<{
  tone?: 'primary' | 'ghost' | 'danger';
  type?: 'button' | 'submit';
  disabled?: boolean;
  onClick?: () => void;
}>) {
  return (
    <button className={`ui-button ui-button--${tone}`} type={type} disabled={disabled} onClick={onClick}>
      {children}
    </button>
  );
}

export function Card({ children, className = '' }: PropsWithChildren<{ className?: string }>) {
  return <section className={`ui-card ${className}`.trim()}>{children}</section>;
}

export function Badge({
  children,
  tone = 'neutral',
}: PropsWithChildren<{ tone?: 'neutral' | 'accent' | 'warning' | 'danger' | 'success' }>) {
  return <span className={`ui-badge ui-badge--${tone}`}>{children}</span>;
}

export function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="ui-stat">
      <span className="ui-stat__label">{label}</span>
      <strong className="ui-stat__value">{value}</strong>
      {hint ? <span className="ui-stat__hint">{hint}</span> : null}
    </div>
  );
}

export function SectionHeading({
  eyebrow,
  title,
  actions,
  className = '',
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <div className={`section-heading ${className}`.trim()}>
      <div>
        {eyebrow ? <p className="section-heading__eyebrow">{eyebrow}</p> : null}
        <h2 className="section-heading__title">{title}</h2>
      </div>
      {actions ? <div className="section-heading__actions">{actions}</div> : null}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <Card className="empty-state">
      <h3>{title}</h3>
      <p>{description}</p>
      {action ? <div>{action}</div> : null}
    </Card>
  );
}

export function AppNavLink({ to, children, end = false }: PropsWithChildren<{ to: string; end?: boolean }>) {
  return (
    <NavLink end={end} to={to} className={({ isActive }) => `app-nav-link${isActive ? ' app-nav-link--active' : ''}`}>
      {children}
    </NavLink>
  );
}

export function TextLink({ to, children }: PropsWithChildren<{ to: string }>) {
  return (
    <Link to={to} className="text-link">
      {children}
    </Link>
  );
}
