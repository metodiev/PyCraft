/**
 * Small, reusable presentation pieces shared across pages.
 *
 * They are deliberately plain: layout belongs to the page, appearance to the
 * design tokens, and behaviour to the caller.
 */

import type { ReactNode } from "react";
import "./components.css";

export function Card({
  children,
  className = "",
  as: Tag = "section",
}: {
  children: ReactNode;
  className?: string;
  as?: "section" | "article" | "div";
}) {
  return <Tag className={`card ${className}`.trim()}>{children}</Tag>;
}

export function CardHeader({
  title,
  action,
}: {
  title: ReactNode;
  action?: ReactNode;
}) {
  return (
    <header className="card-header">
      <h2 className="card-title">{title}</h2>
      {action}
    </header>
  );
}

/** Horizontal 0-100 meter used for skills and stage progress. */
export function ProgressBar({
  value,
  label,
  tone = "accent",
  showValue = true,
}: {
  value: number;
  label?: string;
  tone?: "accent" | "success" | "warning";
  showValue?: boolean;
}) {
  const clamped = Math.max(0, Math.min(100, Math.round(value)));
  return (
    <div className="progress">
      {label !== undefined && (
        <div className="progress-head">
          <span className="progress-label">{label}</span>
          {showValue && <span className="progress-value">{clamped}%</span>}
        </div>
      )}
      <div
        className="progress-track"
        role="progressbar"
        aria-valuenow={clamped}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label ?? "progress"}
      >
        <div className={`progress-fill progress-${tone}`} style={{ width: `${clamped}%` }} />
      </div>
    </div>
  );
}

export function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "accent" | "success" | "warning" | "danger";
}) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

export function DifficultyBadge({ difficulty }: { difficulty: string }) {
  return (
    <span className="badge difficulty" data-difficulty={difficulty}>
      {difficulty}
    </span>
  );
}

export function Button({
  children,
  onClick,
  variant = "primary",
  disabled = false,
  busy = false,
  type = "button",
  title,
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: "primary" | "secondary" | "ghost" | "danger";
  disabled?: boolean;
  busy?: boolean;
  type?: "button" | "submit";
  title?: string;
}) {
  return (
    <button
      type={type}
      className={`btn btn-${variant}`}
      onClick={onClick}
      disabled={disabled || busy}
      title={title}
    >
      {busy && <span className="spinner" aria-hidden="true" />}
      {children}
    </button>
  );
}

/** Inline notice for errors, warnings and guidance. */
export function Notice({
  tone = "info",
  children,
}: {
  tone?: "info" | "success" | "warning" | "danger";
  children: ReactNode;
}) {
  return (
    <div className={`notice notice-${tone}`} role={tone === "danger" ? "alert" : undefined}>
      {children}
    </div>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="empty-state">
      <p className="empty-title">{title}</p>
      {hint !== undefined && <p className="empty-hint">{hint}</p>}
    </div>
  );
}

/** Loading placeholder that keeps layout stable while data arrives. */
export function Skeleton({ height = "1rem", width = "100%" }: { height?: string; width?: string }) {
  return <div className="skeleton" style={{ height, width }} aria-hidden="true" />;
}
