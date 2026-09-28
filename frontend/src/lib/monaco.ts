/**
 * Monaco themes matching the PyCraft palette.
 *
 * Both are registered before the editor mounts — the dark one as a fallback so
 * there is never a flash of the stock theme, and the light one so switching
 * between them is a prop change rather than a re-registration.
 */

import type { Monaco } from "@monaco-editor/react";

export function registerPyCraftTheme(monaco: Monaco): void {
  monaco.editor.defineTheme("pycraft-dark", {
    base: "vs-dark",
    inherit: true,
    rules: [
      { token: "comment", foreground: "5c6b7a", fontStyle: "italic" },
      { token: "keyword", foreground: "3fb6a8" },
      { token: "string", foreground: "a8d8a0" },
      { token: "number", foreground: "e3b341" },
      { token: "type", foreground: "6aa8f0" },
      { token: "function", foreground: "8ab4f8" },
      { token: "identifier", foreground: "e6edf3" },
      { token: "delimiter", foreground: "9aa7b8" },
    ],
    colors: {
      "editor.background": "#0d1117",
      "editor.foreground": "#e6edf3",
      "editorLineNumber.foreground": "#3a4557",
      "editorLineNumber.activeForeground": "#9aa7b8",
      "editor.lineHighlightBackground": "#161b26",
      "editor.selectionBackground": "#264f78",
      "editorCursor.foreground": "#3fb6a8",
      "editorIndentGuide.background1": "#1f2634",
      "editorWidget.background": "#171c28",
      "editorWidget.border": "#2a3342",
      "editorSuggestWidget.background": "#171c28",
      "editorSuggestWidget.selectedBackground": "#1e2533",
      "editorHoverWidget.background": "#171c28",
      "editorHoverWidget.border": "#2a3342",
      "scrollbarSlider.background": "#2a334280",
      "scrollbarSlider.hoverBackground": "#3a455780",
    },
  });

  // Mirrors the light values in `styles/tokens.css`; Monaco colours cannot be
  // CSS custom properties, so the palette is necessarily duplicated here.
  monaco.editor.defineTheme("pycraft-light", {
    base: "vs",
    inherit: true,
    rules: [
      { token: "comment", foreground: "6b7688", fontStyle: "italic" },
      { token: "keyword", foreground: "0b6b60" },
      { token: "string", foreground: "2f6b2a" },
      { token: "number", foreground: "875f08" },
      { token: "type", foreground: "1f63b8" },
      { token: "function", foreground: "1f50a8" },
      { token: "identifier", foreground: "1b2027" },
      { token: "delimiter", foreground: "566074" },
    ],
    colors: {
      "editor.background": "#ffffff",
      "editor.foreground": "#1b2027",
      "editorLineNumber.foreground": "#b3bccb",
      "editorLineNumber.activeForeground": "#566074",
      "editor.lineHighlightBackground": "#f2f4f8",
      "editor.selectionBackground": "#bcd9f5",
      "editorCursor.foreground": "#0d7f72",
      "editorIndentGuide.background1": "#e3e7ee",
      "editorWidget.background": "#ffffff",
      "editorWidget.border": "#d3d9e3",
      "editorSuggestWidget.background": "#ffffff",
      "editorSuggestWidget.selectedBackground": "#e7ebf1",
      "editorHoverWidget.background": "#ffffff",
      "editorHoverWidget.border": "#d3d9e3",
      "scrollbarSlider.background": "#d3d9e380",
      "scrollbarSlider.hoverBackground": "#b3bccb80",
    },
  });
}
