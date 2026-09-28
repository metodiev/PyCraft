/**
 * Theme choice for the profile settings page.
 *
 * A three-way radio group rather than a button that cycles: "System" is a real
 * choice — it keeps following the OS, which a cycle between light and dark
 * cannot express — and showing all three at once means the current one is
 * visible without clicking to find out.
 *
 * The preference is per-browser, kept in `localStorage`, not on the account.
 * It describes how this screen should look, which has no meaning across
 * devices, so syncing it would cost a round trip on every load for nothing.
 */

import { useTheme } from "../lib/theme";
import type { ThemeMode } from "../lib/theme";
import "./theme-toggle.css";

const OPTIONS: { mode: ThemeMode; label: string; icon: string }[] = [
  { mode: "system", label: "System", icon: "◐" },
  { mode: "light", label: "Light", icon: "☀" },
  { mode: "dark", label: "Dark", icon: "☾" },
];

/** What the selected option actually means, shown under the control. */
const EXPLANATIONS: Record<ThemeMode, string> = {
  system: "Following your operating system's light or dark setting.",
  light: "Always use the light theme, whatever your system is set to.",
  dark: "Always use the dark theme, whatever your system is set to.",
};

export function ThemeToggle() {
  const { mode, setMode } = useTheme();

  return (
    <div className="theme-choice">
      <div className="theme-options" role="radiogroup" aria-label="Colour theme">
        {OPTIONS.map((option) => (
          <button
            key={option.mode}
            type="button"
            role="radio"
            aria-checked={mode === option.mode}
            // Only the selected option is reachable by Tab; the arrow keys move
            // between them, which is how a radio group behaves natively.
            tabIndex={mode === option.mode ? 0 : -1}
            onClick={() => setMode(option.mode)}
            onKeyDown={(event) => {
              // Left/Right move within the group. Up/Down are left alone so the
              // browser's own scrolling is not hijacked.
              const step = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
              if (step === 0) return;
              event.preventDefault();
              const index = OPTIONS.findIndex((candidate) => candidate.mode === mode);
              const next = OPTIONS[(index + step + OPTIONS.length) % OPTIONS.length];
              if (next !== undefined) setMode(next.mode);
            }}
          >
            <span className="theme-option-icon" aria-hidden="true">
              {option.icon}
            </span>
            <span>{option.label}</span>
          </button>
        ))}
      </div>
      {/* Describes what the choice does; a bare option name does not. */}
      <p className="theme-hint">{EXPLANATIONS[mode]}</p>
    </div>
  );
}
