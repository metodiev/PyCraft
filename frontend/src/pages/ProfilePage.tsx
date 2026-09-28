/**
 * Profile — the signed-in user's account.
 *
 * Three independent concerns share one page: editable details, credentials, and
 * active sessions. Each has its own busy/error state so a failure in one never
 * blocks the others, and the sessions list is only fetched once the page mounts
 * rather than through the shell.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { SessionInfo } from "../api/client";
import { Badge, Button, Card, CardHeader, EmptyState, Notice, Skeleton } from "../components";
import { Avatar, Field, PasswordChecklist, TextArea, TextInput } from "../components/FormField";
import { ThemeToggle } from "../components/ThemeToggle";
import { useAuth } from "../auth/AuthContext";
import { assessPassword } from "../auth/passwordPolicy";
import { useApi } from "../hooks/useApi";
import { formatDate, formatDateTime, formatRelative, describeUserAgent } from "../lib/format";
import { formatProvider } from "../lib/avatar";
import "./profile.css";

interface ProfileForm {
  display_name: string;
  headline: string;
  bio: string;
  location: string;
  website: string;
}

const EMPTY_FORM: ProfileForm = {
  display_name: "",
  headline: "",
  bio: "",
  location: "",
  website: "",
};

export function ProfilePage() {
  const { user, refreshUser, updateProfile } = useAuth();

  if (user === null) {
    // The guard guarantees a user, but a hard refresh can render one frame
    // before the profile arrives.
    return (
      <div className="profile-page">
        <Card as="div">
          <Skeleton height="1.5rem" width="200px" />
          <div className="profile-gap" />
          <Skeleton height="1rem" />
        </Card>
      </div>
    );
  }

  return (
    <div className="profile-page">
      <ProfileHeader
        displayName={user.display_name}
        email={user.email}
        avatarUrl={user.avatar_url}
        headline={user.headline}
        role={String(user.role)}
      />

      <div className="profile-grid">
        <DetailsCard user={user} onSave={updateProfile} onRefresh={refreshUser} />
        <StatsCard user={user} />
      </div>

      <div className="profile-grid">
        <PasswordCard hasPassword={user.has_password} />
        <AppearanceCard />
      </div>

      <SessionsCard />
    </div>
  );
}

function ProfileHeader({
  displayName,
  email,
  avatarUrl,
  headline,
  role,
}: {
  displayName: string;
  email: string;
  avatarUrl: string;
  headline: string;
  role: string;
}) {
  return (
    <Card className="profile-head-card" as="article">
      <Avatar name={displayName} email={email} src={avatarUrl} size={64} />
      <div className="profile-identity">
        <h1 className="profile-name">{displayName}</h1>
        <p className="profile-email">{email}</p>
        {headline !== "" && <p className="profile-headline">{headline}</p>}
      </div>
      <Badge tone="accent">{role}</Badge>
    </Card>
  );
}

function DetailsCard({
  user,
  onSave,
  onRefresh,
}: {
  user: NonNullable<ReturnType<typeof useAuth>["user"]>;
  onSave: (patch: ProfileForm) => Promise<unknown>;
  onRefresh: () => Promise<void>;
}) {
  const [form, setForm] = useState<ProfileForm>(EMPTY_FORM);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // The form is seeded from the server profile, so `display_name === ""` is only
  // an error after the user has actually emptied the field.
  const [nameTouched, setNameTouched] = useState(false);

  // Re-seed the form whenever the server profile changes, so a refresh or an
  // edit elsewhere is reflected without losing in-progress typing on save.
  useEffect(() => {
    setForm({
      display_name: user.display_name,
      headline: user.headline,
      bio: user.bio,
      location: user.location,
      website: user.website,
    });
  }, [user.id, user.display_name, user.headline, user.bio, user.location, user.website]);

  const dirty = useMemo(() => {
    return (
      form.display_name !== user.display_name ||
      form.headline !== user.headline ||
      form.bio !== user.bio ||
      form.location !== user.location ||
      form.website !== user.website
    );
  }, [form, user]);

  const websiteInvalid = form.website !== "" && !/^https?:\/\//.test(form.website);
  const nameInvalid = nameTouched && form.display_name.trim() === "";

  async function save() {
    setError(null);
    setSaved(false);
    setBusy(true);
    try {
      await onSave(form);
      setSaved(true);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "The profile could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="profile-card">
      <CardHeader
        title="Profile details"
        action={
          <Button
            variant="primary"
            onClick={() => void save()}
            busy={busy}
            disabled={!dirty || websiteInvalid || nameInvalid}
          >
            {busy ? "Saving…" : "Save changes"}
          </Button>
        }
      />

      {error !== null && (
        <div className="profile-notice">
          <Notice tone="danger">{error}</Notice>
        </div>
      )}
      {saved && !dirty && (
        <div className="profile-notice">
          <Notice tone="success">Profile saved.</Notice>
        </div>
      )}

      <div className="profile-form">
        <Field
          label="Display name"
          error={nameInvalid ? "A display name is required" : null}
        >
          {({ id, describedBy, invalid }) => (
            <TextInput
              id={id}
              describedBy={describedBy}
              invalid={invalid}
              value={form.display_name}
              onChange={(value) => {
                setNameTouched(true);
                setForm({ ...form, display_name: value });
              }}
              maxLength={80}
              disabled={busy}
            />
          )}
        </Field>

        <Field label="Headline" optional hint="A short line about what you are working on.">
          {({ id, describedBy, invalid }) => (
            <TextInput
              id={id}
              describedBy={describedBy}
              invalid={invalid}
              value={form.headline}
              onChange={(value) => setForm({ ...form, headline: value })}
              maxLength={160}
              disabled={busy}
            />
          )}
        </Field>

        <Field label="Bio" optional hint="Up to 600 characters.">
          {({ id, describedBy, invalid }) => (
            <TextArea
              id={id}
              describedBy={describedBy}
              invalid={invalid}
              value={form.bio}
              onChange={(value) => setForm({ ...form, bio: value })}
              rows={5}
              maxLength={600}
              disabled={busy}
            />
          )}
        </Field>

        <div className="field-row">
          <Field label="Location" optional>
            {({ id, describedBy, invalid }) => (
              <TextInput
                id={id}
                describedBy={describedBy}
                invalid={invalid}
                value={form.location}
                onChange={(value) => setForm({ ...form, location: value })}
                maxLength={120}
                disabled={busy}
              />
            )}
          </Field>

          <Field
            label="Website"
            optional
            error={websiteInvalid ? "Must start with http:// or https://" : null}
          >
            {({ id, describedBy, invalid }) => (
              <TextInput
                id={id}
                describedBy={describedBy}
                invalid={invalid}
                type="url"
                value={form.website}
                onChange={(value) => setForm({ ...form, website: value })}
                placeholder="https://example.com"
                maxLength={200}
                disabled={busy}
              />
            )}
          </Field>
        </div>
      </div>

      <div className="profile-footer">
        <span className="profile-meta">
          {user.linked_providers.length > 0
            ? `Signed in with ${user.linked_providers.map(formatProvider).join(", ")}`
            : "Password account"}
        </span>
        <button
          className="link-button"
          disabled={busy}
          onClick={() => {
            void onRefresh().catch(() => {
              setError("Could not reload your profile.");
            });
          }}
        >
          Reload from server
        </button>
      </div>
    </Card>
  );
}

function StatsCard({ user }: { user: NonNullable<ReturnType<typeof useAuth>["user"]> }) {
  return (
    <Card className="profile-card">
      <CardHeader title="Progress" />
      <dl className="stat-grid">
        <StatTerm label="XP" value={user.xp.toLocaleString()} />
        <StatTerm label="Current streak" value={`${user.current_streak} d`} />
        <StatTerm label="Longest streak" value={`${user.longest_streak} d`} />
        <StatTerm label="Role" value={String(user.role)} />
        <StatTerm
          label="Last active"
          value={user.last_active_date === null ? "—" : formatDate(user.last_active_date)}
        />
        <StatTerm label="Member since" value={formatDate(user.created_at)} />
      </dl>
      <p className="profile-hint">
        XP and streaks are earned by passing tests — see the{" "}
        <Link to="/roadmap">roadmap</Link> for what comes next.
      </p>
    </Card>
  );
}

function StatTerm({ label, value }: { label: string; value: string }) {
  return (
    <div className="stat-term">
      <dt className="stat-label">{label}</dt>
      <dd className="stat-value">{value}</dd>
    </div>
  );
}

/**
 * Display preferences.
 *
 * Deliberately separate from `DetailsCard`: theme is stored in this browser
 * rather than on the account, so it must not sit behind the same "Save changes"
 * button as profile details — saving or failing to save those would otherwise
 * appear to apply to the theme too.
 */
function AppearanceCard() {
  return (
    <Card className="profile-card">
      <CardHeader title="Appearance" />
      <p className="profile-hint">
        How PyCraft looks on this device. This is saved in this browser, not on
        your account.
      </p>
      <ThemeToggle />
    </Card>
  );
}

function PasswordCard({ hasPassword }: { hasPassword: boolean }) {
  const { logout } = useAuth();
  const navigate = useNavigate();
  const config = useApi(() => api.getAuthConfig(), []);
  const minLength = config.data?.min_password_length ?? 10;

  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const assessment = useMemo(() => assessPassword(next, minLength), [next, minLength]);
  const mismatch = confirm !== "" && confirm !== next;
  const canSubmit = assessment.satisfied && confirm === next && !busy;

  async function submit() {
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      const result = await api.changePassword({ current_password: current, password: next });
      setNotice(result.message);
      // The backend revokes every session on a password change, including this
      // one, so the local session must end too.
      await logout();
      navigate("/login", { replace: true });
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "The password could not be changed.");
      setBusy(false);
    }
  }

  return (
    <Card className="profile-card">
      <CardHeader title="Password" />
      <p className="profile-hint">
        {hasPassword
          ? "Changing your password signs out every device, including this one."
          : "This account has no password yet. Set one to sign in without GitHub."}
      </p>

      {error !== null && (
        <div className="profile-notice">
          <Notice tone="danger">{error}</Notice>
        </div>
      )}
      {notice !== null && (
        <div className="profile-notice">
          <Notice tone="success">{notice}</Notice>
        </div>
      )}

      <form
        className="profile-form"
        onSubmit={(event) => {
          event.preventDefault();
          if (canSubmit) void submit();
        }}
        noValidate
      >
        {hasPassword && (
          <Field label="Current password">
            {({ id, describedBy, invalid }) => (
              <TextInput
                id={id}
                describedBy={describedBy}
                invalid={invalid}
                type="password"
                value={current}
                onChange={setCurrent}
                autoComplete="current-password"
                disabled={busy}
              />
            )}
          </Field>
        )}

        <Field label={hasPassword ? "New password" : "Password"}>
          {({ id, describedBy, invalid }) => (
            <>
              <TextInput
                id={id}
                describedBy={[describedBy, `${id}-checklist`].filter(Boolean).join(" ")}
                invalid={invalid}
                type="password"
                value={next}
                onChange={setNext}
                autoComplete="new-password"
                disabled={busy}
              />
              <PasswordChecklist assessment={assessment} id={`${id}-checklist`} />
            </>
          )}
        </Field>

        <Field label="Confirm password" error={mismatch ? "Passwords do not match" : null}>
          {({ id, describedBy, invalid }) => (
            <TextInput
              id={id}
              describedBy={describedBy}
              invalid={invalid}
              type="password"
              value={confirm}
              onChange={setConfirm}
              autoComplete="new-password"
              disabled={busy}
            />
          )}
        </Field>

        <Button type="submit" variant="primary" busy={busy} disabled={!canSubmit}>
          {busy ? "Updating…" : hasPassword ? "Change password" : "Set password"}
        </Button>
      </form>
    </Card>
  );
}

function SessionsCard() {
  const { logout, status } = useAuth();
  const navigate = useNavigate();
  const [sessions, setSessions] = useState<SessionInfo[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [revoking, setRevoking] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setSessions(await api.listSessions());
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Sessions could not be loaded.");
      setSessions(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (status !== "authenticated") return;
    void load();
  }, [load, status]);

  async function revoke(session: SessionInfo) {
    setRevoking(session.id);
    setError(null);
    try {
      await api.revokeSession(session.id);
      if (session.is_current) {
        // Revoking the session in use: end it locally rather than showing a
        // list that no longer matches reality.
        await logout();
        navigate("/login", { replace: true });
        return;
      }
      setSessions((previous) =>
        previous === null ? previous : previous.filter((item) => item.id !== session.id),
      );
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "The session could not be revoked.");
    } finally {
      setRevoking(null);
    }
  }

  const activeCount = sessions?.length ?? 0;

  return (
    <Card className="profile-card">
      <CardHeader
        title="Active sessions"
        action={
          <Button variant="ghost" onClick={() => void load()} disabled={loading}>
            {loading ? "Loading…" : "Refresh"}
          </Button>
        }
      />

      {error !== null && (
        <div className="profile-notice">
          <Notice tone="danger">{error}</Notice>
        </div>
      )}

      {loading && sessions === null ? (
        <div className="profile-form">
          <Skeleton height="3.25rem" />
          <Skeleton height="3.25rem" />
        </div>
      ) : sessions === null ? null : sessions.length === 0 ? (
        <EmptyState title="No active sessions" hint="Sign in again to start a new session." />
      ) : (
        <>
          <p className="profile-hint">
            {activeCount === 1 ? "1 session is signed in." : `${activeCount} sessions are signed in.`}
          </p>
          <ul className="session-list">
            {sessions.map((session) => (
              <li key={session.id} className="session-row">
                <div className="session-main">
                  <div className="session-title">
                    <span>{describeUserAgent(session.user_agent)}</span>
                    {session.is_current && <Badge tone="accent">This device</Badge>}
                    {session.provider !== "password" && <Badge>{formatProvider(session.provider)}</Badge>}
                  </div>
                  <p className="session-meta">
                    {session.ip_address !== "" ? `${session.ip_address} · ` : ""}
                    last used {formatRelative(session.last_used_at) || "recently"} · expires{" "}
                    {formatDateTime(session.expires_at)}
                  </p>
                  <p className="session-meta muted" title={session.user_agent}>
                    Started {formatDateTime(session.created_at)}
                  </p>
                </div>
                <Button
                  variant={session.is_current ? "danger" : "secondary"}
                  busy={revoking === session.id}
                  disabled={revoking !== null && revoking !== session.id}
                  onClick={() => void revoke(session)}
                >
                  {session.is_current ? "Sign out" : "Revoke"}
                </Button>
              </li>
            ))}
          </ul>
        </>
      )}
    </Card>
  );
}
