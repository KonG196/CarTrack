import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import {
  Check,
  Copy,
  ExternalLink,
  KeyRound,
  LifeBuoy,
  Mail,
  Send,
  Trash2,
  UserCircle,
} from 'lucide-react';
import BackLink from '../components/BackLink';

import { extractError } from '../api/client';
import * as telegramApi from '../api/telegram';
import Toast from '../components/Toast';
import { Button, Card, ConfirmDialog, ErrorMessage, Spinner, TextField } from '../components/UI';
import { useAuthStore } from '../store/authStore';

// Where account-help requests (e.g. changing the sign-in email) go. Both channels
// are offered. Not secrets — safe to ship in the client.
const SUPPORT_EMAIL = 'maks060691@gmail.com';
const SUPPORT_TELEGRAM = 'KonG196';
const SUPPORT_TELEGRAM_URL = `https://t.me/${SUPPORT_TELEGRAM}`;

// The app's Telegram bot — a direct link so users can open it any time (for
// reminders, quick logging), separate from the account-linking flow below.
const BOT_USERNAME = 'Kapot_Tracker_bot';
const BOT_URL = `https://t.me/${BOT_USERNAME}`;

function ProfileCard({ onToast }) {
  const { t } = useTranslation();
  const user = useAuthStore((s) => s.user);
  const saveDisplayName = useAuthStore((s) => s.saveDisplayName);

  // null means untouched, so we show the saved value. The profile arrives
  // asynchronously: seeding state from it via an effect would blank the field
  // and clobber whatever the user had already typed.
  const [draft, setDraft] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const saved = user?.display_name || '';
  const value = draft ?? saved;
  const dirty = draft !== null && draft.trim() !== saved;

  const emailPrefix = (user?.email || '').split('@')[0];

  const handleSave = async (e) => {
    e.preventDefault();
    const name = value.trim();
    if (!name) return setError(t('profile.nameRequired'));
    setError('');
    setSaving(true);
    try {
      await saveDisplayName(name);
      setDraft(null);
      onToast(t('profile.nameSaved'));
    } catch (err) {
      setError(extractError(err, t('profile.nameSaveFailed')));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <div>
        <h2 className="flex items-center gap-2 font-display text-sm font-semibold text-fg">
          <UserCircle className="h-4 w-4 text-mist" />
          {t('profile.yourName')}
        </h2>
        <p className="mt-1 text-xs text-mist">
          {t('profile.nameHint', { name: emailPrefix || t('profile.emailStart') })}
        </p>
      </div>

      {error && <ErrorMessage className="mt-3">{error}</ErrorMessage>}

      <form onSubmit={handleSave} className="mt-3 flex items-end gap-2">
        <TextField
          label={t('profile.name')}
          maxLength={80}
          value={value}
          onChange={(e) => setDraft(e.target.value)}
          containerClassName="flex-1"
        />
        <Button type="submit" disabled={saving || !dirty} className="flex-shrink-0">
          {saving ? t('common.saving') : t('common.save')}
        </Button>
      </form>
    </Card>
  );
}

function TelegramCard({ onToast }) {
  const { t } = useTranslation();
  const [status, setStatus] = useState(null);
  const [linkData, setLinkData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [confirmUnlink, setConfirmUnlink] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    telegramApi
      .getStatus()
      .then((data) => {
        if (!cancelled) setStatus(data);
      })
      .catch(() => {
        if (!cancelled) {
          setStatus({ linked: false });
          setError(t('profile.telegramStatusFailed'));
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleCreateCode = async () => {
    setError('');
    setBusy(true);
    try {
      const data = await telegramApi.createLinkCode();
      setLinkData(data);
    } catch (err) {
      setError(extractError(err, t('profile.linkCodeFailed')));
    } finally {
      setBusy(false);
    }
  };

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(linkData.code);
      onToast(t('profile.codeCopied'));
    } catch {
      setError(t('profile.copyFailed'));
    }
  };

  const handleUnlink = async () => {
    setConfirmUnlink(false);
    setError('');
    setBusy(true);
    try {
      await telegramApi.unlink();
      setStatus({ linked: false });
      setLinkData(null);
      onToast(t('profile.telegramUnlinked'));
    } catch (err) {
      setError(extractError(err, t('profile.unlinkFailed')));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card data-tour="profile-telegram">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h2 className="flex items-center gap-2 font-display text-sm font-semibold text-fg">
            <Send className="h-4 w-4 text-signal" />
            {t('profile.telegramBot')}
          </h2>
          <p className="mt-1 text-xs text-mist">
            {t('profile.telegramHint')}
          </p>
        </div>
        {status?.linked && (
          <span className="flex flex-shrink-0 items-center gap-1 rounded-full bg-ok/15 px-2.5 py-1 text-xs font-medium text-ok">
            <Check className="h-3 w-3" />
            {t('profile.linked')}
          </span>
        )}
      </div>

      {error && <ErrorMessage className="mt-3">{error}</ErrorMessage>}

      {status === null ? (
        <Spinner className="py-3" />
      ) : status.linked ? (
        <>
          <Button
            variant="ghost"
            onClick={() => setConfirmUnlink(true)}
            disabled={busy}
            className="mt-3 text-mist"
          >
            {t('profile.unlink')}
          </Button>
          <ConfirmDialog
            open={confirmUnlink}
            title={t('profile.unlinkTelegramTitle')}
            message={t('profile.unlinkTelegramMessage')}
            confirmLabel={t('profile.unlink')}
            onConfirm={handleUnlink}
            onCancel={() => setConfirmUnlink(false)}
          />
        </>
      ) : linkData ? (
        <div className="mt-3 space-y-2">
          <div className="flex items-center gap-2 rounded-xl border border-edge-soft bg-garage px-3.5 py-2.5">
            <code className="min-w-0 flex-1 break-all font-mono text-xs text-fg">
              {linkData.code}
            </code>
            <button
              type="button"
              onClick={handleCopy}
              aria-label={t('profile.copyCode')}
              className="flex-shrink-0 rounded-lg p-1.5 text-mist transition-colors hover:bg-raised hover:text-fg"
            >
              <Copy className="h-4 w-4" />
            </button>
          </div>
          {linkData.deep_link && (
            <Button
              variant="secondary"
              onClick={() => window.open(linkData.deep_link, '_blank', 'noopener')}
              className="w-full"
            >
              <ExternalLink className="h-4 w-4" />
              {t('profile.openBot')}
            </Button>
          )}
          <p className="text-xs text-mist">
            {t('profile.sendCommand')}{' '}
            <span className="font-mono text-fg">/start {t('profile.codePlaceholder')}</span>.{' '}
            {t('profile.codeExpires', { minutes: linkData.expires_in_minutes })}
          </p>
        </div>
      ) : (
        <Button onClick={handleCreateCode} disabled={busy} className="mt-3 w-full">
          {busy ? t('profile.creatingCode') : t('profile.linkTelegram')}
        </Button>
      )}

      {/* A direct link to the bot, always available — open it to chat with the
          bot regardless of whether the account is linked. */}
      <a
        href={BOT_URL}
        target="_blank"
        rel="noopener noreferrer"
        className="mt-3 flex items-center justify-center gap-1.5 text-xs font-medium text-signal transition-colors hover:text-fg"
      >
        <ExternalLink className="h-3.5 w-3.5" />
        {t('profile.openBotLink', { username: BOT_USERNAME })}
      </a>
    </Card>
  );
}

function PasswordCard({ onToast }) {
  const { t } = useTranslation();
  const changePassword = useAuthStore((s) => s.changePassword);
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [repeat, setRepeat] = useState('');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (next.length < 6) return setError(t('profile.passwordTooShort'));
    // Caught here rather than by the server: a mistyped confirmation is the one
    // error that would otherwise succeed and lock the user out.
    if (next !== repeat) return setError(t('profile.passwordsMismatch'));
    setError('');
    setSaving(true);
    try {
      await changePassword(current, next);
      setCurrent('');
      setNext('');
      setRepeat('');
      onToast(t('profile.passwordChanged'));
    } catch (err) {
      setError(extractError(err, t('profile.passwordChangeFailed')));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <h2 className="flex items-center gap-2 font-display text-sm font-semibold text-fg">
        <KeyRound className="h-4 w-4 text-mist" />
        {t('profile.password')}
      </h2>
      <p className="mt-1 text-xs text-mist">
        {t('profile.passwordHint')}
      </p>
      <form onSubmit={handleSubmit} className="mt-3 space-y-3">
        <TextField
          label={t('profile.currentPassword')}
          type="password"
          autoComplete="current-password"
          value={current}
          onChange={(e) => setCurrent(e.target.value)}
        />
        <div className="grid grid-cols-2 gap-3">
          <TextField
            label={t('profile.newPassword')}
            type="password"
            autoComplete="new-password"
            value={next}
            onChange={(e) => setNext(e.target.value)}
          />
          <TextField
            label={t('profile.repeatPassword')}
            type="password"
            autoComplete="new-password"
            value={repeat}
            onChange={(e) => setRepeat(e.target.value)}
          />
        </div>
        <ErrorMessage>{error}</ErrorMessage>
        <Button type="submit" disabled={saving || !current || !next}>
          {saving ? t('common.saving') : t('profile.changePassword')}
        </Button>
      </form>
    </Card>
  );
}

// The account's email is read-only now: self-service address change was removed
// (too easy to lock yourself out over a typo). Changing it is a support request —
// see SupportCard below.
function EmailCard() {
  const { t } = useTranslation();
  const user = useAuthStore((s) => s.user);

  return (
    <Card>
      <h2 className="flex items-center gap-2 font-display text-sm font-semibold text-fg">
        <Mail className="h-4 w-4 text-mist" />
        {t('profile.email')}
      </h2>
      <p className="mt-1 text-sm text-fg">{user?.email}</p>
      <p className="mt-1 text-xs text-mist">{t('profile.emailChangeViaSupport')}</p>
    </Card>
  );
}

// Where users write in for account help (changing their email, etc.). Both
// channels: a mailto to the owner, and a Telegram link.
function SupportCard() {
  const { t } = useTranslation();
  const user = useAuthStore((s) => s.user);
  const subject = encodeURIComponent(t('support.emailSubject'));
  const body = encodeURIComponent(
    t('support.emailBody', { email: user?.email || '' }),
  );

  return (
    <Card>
      <h2 className="flex items-center gap-2 font-display text-sm font-semibold text-fg">
        <LifeBuoy className="h-4 w-4 text-mist" />
        {t('support.title')}
      </h2>
      <p className="mt-1 text-xs text-mist">{t('support.desc')}</p>
      <div className="mt-3 flex flex-col gap-2">
        <a
          href={`mailto:${SUPPORT_EMAIL}?subject=${subject}&body=${body}`}
          className="flex items-center gap-2.5 rounded-xl border border-edge bg-raised px-3 py-2.5 text-sm text-fg transition-colors hover:border-edge-soft"
        >
          <Mail className="h-4 w-4 flex-shrink-0 text-amber" />
          <span className="min-w-0 flex-1">{t('support.email')}</span>
          <span className="truncate text-xs text-mist">{SUPPORT_EMAIL}</span>
        </a>
        <a
          href={SUPPORT_TELEGRAM_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-2.5 rounded-xl border border-edge bg-raised px-3 py-2.5 text-sm text-fg transition-colors hover:border-edge-soft"
        >
          <Send className="h-4 w-4 flex-shrink-0 text-signal" />
          <span className="min-w-0 flex-1">{t('support.telegram')}</span>
          <span className="truncate text-xs text-mist">@{SUPPORT_TELEGRAM}</span>
        </a>
      </div>
    </Card>
  );
}

function DangerZone() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const deleteAccount = useAuthStore((s) => s.deleteAccount);
  const [password, setPassword] = useState('');
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const handleDelete = async () => {
    setConfirming(false);
    setError('');
    setBusy(true);
    try {
      await deleteAccount(password);
      // Account and session are gone; land on the login screen.
      navigate('/login', { replace: true });
    } catch (err) {
      setError(extractError(err, t('profile.deleteFailed')));
      setBusy(false);
    }
  };

  return (
    <Card className="border-crit/30">
      <h2 className="flex items-center gap-2 font-display text-sm font-semibold text-crit">
        <Trash2 className="h-4 w-4" />
        {t('profile.deleteAccount')}
      </h2>
      <p className="mt-1 text-xs text-mist">
        {t('profile.deleteHint')}
      </p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (password) setConfirming(true);
        }}
        className="mt-3 space-y-3"
      >
        <TextField
          label={t('profile.password')}
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <ErrorMessage>{error}</ErrorMessage>
        <Button type="submit" variant="danger" disabled={busy || !password}>
          {busy ? t('profile.deleting') : t('profile.deleteAccountForever')}
        </Button>
      </form>

      <ConfirmDialog
        open={confirming}
        title={t('profile.deleteForeverTitle')}
        message={t('profile.deleteForeverMessage')}
        confirmLabel={t('profile.yesDelete')}
        onConfirm={handleDelete}
        onCancel={() => setConfirming(false)}
      />
    </Card>
  );
}

export default function Profile() {
  const { t } = useTranslation();
  const [toast, setToast] = useState('');
  // A Google account has no password of its own, so the change-password card
  // has nothing to change — hide it for them.
  const isGoogle = useAuthStore((s) => s.user?.auth_provider) === 'google';

  return (
    <div className="stagger space-y-4">
      <Toast message={toast} onDone={() => setToast('')} />

      <BackLink to="/garage">{t('profile.title')}</BackLink>

      <ProfileCard onToast={setToast} />
      <TelegramCard onToast={setToast} />
      <EmailCard />
      {!isGoogle && <PasswordCard onToast={setToast} />}
      <SupportCard />
      <DangerZone />

      <p className="pt-2 text-center text-xs text-mist">
        © 2026 Kapot Tracker · {t('profile.aboutLicense')}
        {' · '}
        <a
          href="https://github.com/KonG196/CarTrack"
          target="_blank"
          rel="noopener noreferrer"
          className="underline underline-offset-2 hover:text-amber"
        >
          {t('profile.aboutSource')}
        </a>
      </p>
    </div>
  );
}
