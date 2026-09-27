/**
 * Monaco loader configuration.
 *
 * ``@monaco-editor/react`` fetches Monaco from a public CDN by default. PyCraft
 * must run offline and in air-gapped deployments, so the editor is served from
 * the bundled ``monaco-editor`` package instead.
 *
 * Only the editor core and Python syntax are imported: the full
 * ``monaco-editor`` entry point bundles every language (a ~7 MB TypeScript
 * worker among them), none of which PyCraft executes.
 */

import { loader } from "@monaco-editor/react";
import * as monaco from "monaco-editor/editor/editor.api.js";

// Registers the Python tokeniser and language configuration.
import "monaco-editor/languages/definitions/python/register.js";

// Vite bundles the worker as a separate entry point. The bare subpath is
// required because monaco-editor publishes an export map that remaps it.
import editorWorker from "monaco-editor/editor/editor.worker.js?worker";

// Python ships no language server, so the generic editor worker is enough: it
// provides tokenisation, highlighting and basic word-based IntelliSense.
declare global {
  interface Window {
    MonacoEnvironment?: {
      getWorker: (moduleId: string, label: string) => Worker;
    };
  }
}

window.MonacoEnvironment = {
  getWorker: () => new editorWorker(),
};

loader.config({ monaco });

// Expose the editor API so end-to-end tests can drive Monaco deterministically.
// Monaco keeps a hidden readonly textarea and intercepts key handling, so
// synthetic input is unreliable: a select-all press is dropped and the typing
// that follows appends to the starter instead of replacing it, which would let
// a test grade code the learner never wrote.
//
// Dev and test builds only — this is stripped from a production bundle. It is
// an escape hatch for tests, not part of the application's runtime surface.
if (import.meta.env.DEV || import.meta.env.MODE === "test") {
  (window as Window & { monaco?: typeof monaco }).monaco = monaco;
}
