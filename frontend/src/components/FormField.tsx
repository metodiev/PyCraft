/**
 * Accessible form primitives and the avatar.
 *
 * Labels are real `<label>` elements bound with `htmlFor`, and errors are wired
 * through `aria-invalid` + `aria-describedby` so screen readers announce them
 * rather than relying on colour alone.
 */

import { useId, type ChangeEvent, type ReactNode } from "react";
import type { PasswordAssessment } from "../auth/passwordPolicy";
import { initials, toneFor } from "../lib/avatar";
import "../styles/forms.css";
import "../styles/avatar.css";

function describedBy(hintId: string | undefined, errorId: string | undefined): string | undefined {
  const ids = [hintId, errorId].filter((id): id is string => id !== undefined);
  return ids.length === 0 ? undefined : ids.join(" ");
}

export function Field({
  label,
  children,
  hint,
  error,
  optional = false,
  id,
}: {
  label: string;
  children: (props: { id: string; describedBy: string | undefined; invalid: boolean }) => ReactNode;
  hint?: string | undefined;
  error?: string | null | undefined;
  optional?: boolean;
  id?: string;
}) {
  const generated = useId();
  const fieldId = id ?? generated;
  const hintId = hint === undefined ? undefined : `${fieldId}-hint`;
  const errorId = error === null || error === undefined ? undefined : `${fieldId}-error`;

  return (
    <div className="field">
      <div className="field-head">
        <label className="field-label" htmlFor={fieldId}>
          {label}
        </label>
        {optional && <span className="field-optional">optional</span>}
      </div>
      {children({ id: fieldId, describedBy: describedBy(hintId, errorId), invalid: errorId !== undefined })}
      {hint !== undefined && hintId !== undefined && (
        <p className="field-hint" id={hintId}>
          {hint}
        </p>
      )}
      {error !== null && error !== undefined && errorId !== undefined && (
        <p className="field-error" id={errorId} role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

export function TextInput({
  id,
  describedBy,
  invalid,
  type = "text",
  value,
  onChange,
  placeholder,
  autoComplete,
  autoFocus = false,
  disabled = false,
  maxLength,
}: {
  id: string;
  describedBy?: string | undefined;
  invalid: boolean;
  type?: "text" | "email" | "password" | "url";
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  autoComplete?: string;
  autoFocus?: boolean;
  disabled?: boolean;
  maxLength?: number;
}) {
  return (
    <input
      id={id}
      className="field-input"
      type={type}
      value={value}
      placeholder={placeholder}
      autoComplete={autoComplete}
      autoFocus={autoFocus}
      disabled={disabled}
      maxLength={maxLength}
      aria-invalid={invalid}
      aria-describedby={describedBy}
      onChange={(event: ChangeEvent<HTMLInputElement>) => onChange(event.target.value)}
    />
  );
}

export function TextArea({
  id,
  describedBy,
  invalid,
  value,
  onChange,
  placeholder,
  rows = 4,
  maxLength,
  disabled = false,
}: {
  id: string;
  describedBy?: string | undefined;
  invalid: boolean;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  rows?: number;
  maxLength?: number;
  disabled?: boolean;
}) {
  return (
    <textarea
      id={id}
      className="field-textarea"
      value={value}
      placeholder={placeholder}
      rows={rows}
      maxLength={maxLength}
      disabled={disabled}
      aria-invalid={invalid}
      aria-describedby={describedBy}
      onChange={(event: ChangeEvent<HTMLTextAreaElement>) => onChange(event.target.value)}
    />
  );
}

/** Live strength meter + requirement checklist for password inputs. */
export function PasswordChecklist({
  assessment,
  id,
  label = "Password strength",
}: {
  assessment: PasswordAssessment;
  id: string;
  label?: string;
}) {
  return (
    <div className="field">
      <div
        className="password-meter"
        role="meter"
        aria-label={label}
        aria-valuenow={assessment.score}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div
          className="password-meter-fill"
          data-strength={assessment.strength}
          style={{ width: `${Math.max(assessment.score, 3)}%` }}
        />
      </div>
      <ul className="req-list" id={id}>
        {assessment.requirements.map((requirement) => (
          <li key={requirement.id} className="req" data-met={requirement.met}>
            <span className="req-marker" aria-hidden="true">
              {requirement.met ? "✓" : "○"}
            </span>
            <span>
              {requirement.label}
              <span className="visually-hidden">
                {requirement.met ? " — satisfied" : " — not yet satisfied"}
              </span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Avatar image when the account has one, else initials on a stable tone. */
export function Avatar({
  name,
  email,
  src,
  size = 28,
}: {
  name: string;
  email?: string;
  src?: string;
  size?: number;
}) {
  const dimension = `${size}px`;
  const style = { width: dimension, height: dimension, fontSize: `${Math.round(size * 0.4)}px` };

  if (src !== undefined && src !== "") {
    return (
      <img
        className="avatar"
        src={src}
        alt=""
        width={size}
        height={size}
        style={style}
        referrerPolicy="no-referrer"
      />
    );
  }

  return (
    <span className="avatar avatar-initials" data-tone={toneFor(email ?? name)} style={style} aria-hidden="true">
      {initials(name, email ?? "")}
    </span>
  );
}
