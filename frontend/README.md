# React + TypeScript + Vite

The PyCraft web client: challenge catalogue, Monaco workspace, dashboard and
account screens. Built with Vite, React 19, React Router and strict TypeScript.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## Authentication

Sign-in state is split across three small modules under `src/auth/`:

| Module | Responsibility |
| --- | --- |
| `tokenStore.ts` | Persists the token pair under the `pycraft.auth` key, degrades to an in-memory copy when `localStorage` is unavailable, and discards corrupt entries |
| `AuthContext.tsx` | Owns `{user, status}`, restores the session on mount, and exposes `login` / `register` / `logout` / `refreshUser` / `updateProfile` / `acceptTokens` |
| `RequireAuth.tsx` | Route guard; renders a skeleton while `status === "loading"` and redirects to `/login` only once the session is known to be absent |

`src/api/client.ts` attaches `Authorization: Bearer <access_token>` to every
request and, on a 401, rotates the pair through `/auth/refresh` and retries the
request **once**. Refresh tokens are single-use, so concurrent 401s share one
in-flight rotation — two parallel rotations would look like token replay to the
backend and revoke every session on the account.

GitHub sign-in is a browser redirect. The login page links to
`/api/v1/auth/github/authorize` with `redirect_to=/auth/callback?next=<path>`;
the backend sends the browser back with the tokens in the URL **fragment**, and
`AuthCallbackPage` stores them, strips the fragment via `history.replaceState`
and forwards to `next`.

### Screens

| Route | Notes |
| --- | --- |
| `/login` | Hidden when password auth is disabled; GitHub button shown only when configured |
| `/register` | Hidden entirely when `registration_enabled` is false; requirements driven by `min_password_length` |
| `/forgot-password` | Always shows the same confirmation, mirroring the API's non-disclosure |
| `/reset-password` | Reads `?token=`; handles a missing token without a blank screen |
| `/auth/callback` | Consumes the OAuth fragment |
| `/profile` | Details, password change and active sessions with revoke |

Every other route is wrapped in `RequireAuth`.

## Theming

Colours live in `src/styles/tokens.css` as custom properties; no component
hard-codes a colour, which is what makes a second theme a block of values rather
than a rewrite.

The switch is on the **profile page**, under Appearance — a per-device display
preference, not part of the account, so it does not sit behind the same "Save
changes" button as the profile details.

| Piece | Responsibility |
| --- | --- |
| `styles/tokens.css` | The palettes. `:root` is dark; `:root[data-theme="light"]` overrides it. Both are audited to WCAG AA |
| `lib/theme.ts` | Mode (`system` \| `light` \| `dark`), persistence under `pycraft.theme`, OS tracking, and the `useTheme` hook |
| `components/ThemeToggle.tsx` | The radio group on the profile page |
| `index.html` | An inline pre-paint script that sets `data-theme` before the first frame |

Three details are load-bearing:

- **Dark is the default in CSS.** A document with no `data-theme` renders the
  original palette, so a blocked or failed pre-paint script degrades to a
  supported theme instead of an unstyled one.
- **The pre-paint script duplicates `lib/theme.ts`.** It cannot import a module,
  because that would be fetched after the stylesheet is applied and the wrong
  theme would flash for a frame. Changing the storage key means changing both.
- **Monaco is themed separately.** Its colours cannot be CSS custom properties,
  so `lib/monaco.ts` defines `pycraft-dark` and `pycraft-light` and the editors
  pick between them with `monacoThemeName(resolved)`. Both are registered up
  front, so switching is a prop change, not a re-registration.

`e2e/theme.spec.ts` covers the behaviour end to end, including that the header
does not offer the switch.

## Scripts

```bash
npm run dev         # dev server on 127.0.0.1:5173, /api proxied to the backend
npx tsc -b          # strict typecheck (CI gate)
npm run build       # typecheck + production bundle
npm run lint        # oxlint
```

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the Oxlint configuration

If you are developing a production application, we recommend enabling type-aware lint rules by installing `oxlint-tsgolint` and editing `.oxlintrc.json`:

```json
{
  "$schema": "./node_modules/oxlint/configuration_schema.json",
  "plugins": ["react", "typescript", "oxc"],
  "options": {
    "typeAware": true
  },
  "rules": {
    "react/rules-of-hooks": "error",
    "react/only-export-components": ["warn", { "allowConstantExport": true }]
  }
}
```

See the [Oxlint rules documentation](https://oxc.rs/docs/guide/usage/linter/rules) for the full list of rules and categories.
