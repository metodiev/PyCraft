/**
 * Monaco theme matching the PyCraft palette.
 *
 * Registered before the editor mounts so there is no flash of the default theme.
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
}
