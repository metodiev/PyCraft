/**
 * Password policy mirroring `backend/app/schemas/auth.py`.
 *
 * The checklist is advisory UI only — the server re-validates every password —
 * but it must agree with the backend or the form would promise something the API
 * rejects. Keep the two in step.
 */

export interface PasswordRequirement {
  id: string;
  label: string;
  met: boolean;
}

export type PasswordStrength = "weak" | "fair" | "strong";

export interface PasswordAssessment {
  requirements: PasswordRequirement[];
  satisfied: boolean;
  strength: PasswordStrength;
  /** 0-100, for the meter width. */
  score: number;
}

const MAX_PASSWORD_BYTES = 1024;

export function assessPassword(password: string, minLength: number): PasswordAssessment {
  const requirements: PasswordRequirement[] = [
    { id: "length", label: `At least ${minLength} characters`, met: password.length >= minLength },
    { id: "letter", label: "Contains a letter", met: /[A-Za-z]/.test(password) },
    { id: "digit", label: "Contains a number", met: /[0-9]/.test(password) },
    {
      id: "not-blank",
      label: "Not only spaces",
      met: password.length > 0 && password.trim() !== "",
    },
    {
      id: "size",
      label: "Within the length limit",
      met: password.length > 0 && new TextEncoder().encode(password).length <= MAX_PASSWORD_BYTES,
    },
  ];

  const metCount = requirements.filter((requirement) => requirement.met).length;
  const satisfied = metCount === requirements.length;

  // Length beyond the minimum is the main driver of real-world strength, so it
  // dominates the score; character variety only breaks ties.
  const variety = [/[a-z]/, /[A-Z]/, /[0-9]/, /[^A-Za-z0-9]/].filter((pattern) =>
    pattern.test(password),
  ).length;
  const lengthCredit = Math.min(1, password.length / Math.max(minLength * 2, 1));
  const raw = Math.round((lengthCredit * 0.6 + (variety / 4) * 0.4) * 100);
  const score = satisfied ? Math.max(raw, 55) : Math.round(raw * 0.6);

  const strength: PasswordStrength = !satisfied ? "weak" : score >= 80 ? "strong" : "fair";

  return { requirements, satisfied, strength, score };
}
