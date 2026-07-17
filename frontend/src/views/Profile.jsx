import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Check,
  Copy,
  ExternalLink,
  KeyRound,
  Mail,
  Send,
  Trash2,
  UserCircle,
} from 'lucide-react';
import BackLink from '../components/BackLink';

import { extractError } from '../api/client';
import { confirmEmailChange, requestEmailChange } from '../api/auth';
import * as telegramApi from '../api/telegram';
import Toast from '../components/Toast';
import { Button, Card, ConfirmDialog, ErrorMessage, Spinner, TextField } from '../components/UI';
import { useAuthStore } from '../store/authStore';

function ProfileCard({ onToast }) {
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
    if (!name) return setError('Вкажіть імʼя');
    setError('');
    setSaving(true);
    try {
      await saveDisplayName(name);
      setDraft(null);
      onToast('Імʼя збережено');
    } catch (err) {
      setError(extractError(err, 'Не вдалося зберегти імʼя'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <div>
        <h2 className="flex items-center gap-2 font-display text-sm font-semibold text-fg">
          <UserCircle className="h-4 w-4 text-mist" />
          Ваше імʼя
        </h2>
        <p className="mt-1 text-xs text-mist">
          Так вас підписано під записами у спільних авто. Без імені — {emailPrefix || 'початок email'}.
        </p>
      </div>

      {error && <ErrorMessage className="mt-3">{error}</ErrorMessage>}

      <form onSubmit={handleSave} className="mt-3 flex items-end gap-2">
        <TextField
          label="Імʼя"
          maxLength={80}
          value={value}
          onChange={(e) => setDraft(e.target.value)}
          containerClassName="flex-1"
        />
        <Button type="submit" disabled={saving || !dirty} className="flex-shrink-0">
          {saving ? 'Збереження…' : 'Зберегти'}
        </Button>
      </form>
    </Card>
  );
}

function TelegramCard({ onToast }) {
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
          setError('Не вдалося завантажити статус Telegram');
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
      setError(extractError(err, 'Не вдалося створити код привʼязки'));
    } finally {
      setBusy(false);
    }
  };

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(linkData.code);
      onToast('Код скопійовано');
    } catch {
      setError('Не вдалося скопіювати код');
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
      onToast('Telegram відвʼязано');
    } catch (err) {
      setError(extractError(err, 'Не вдалося відвʼязати Telegram'));
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
            Telegram-бот
          </h2>
          <p className="mt-1 text-xs text-mist">
            Нагадування про ТО та швидкі записи пробігу й витрат просто з Telegram.
          </p>
        </div>
        {status?.linked && (
          <span className="flex flex-shrink-0 items-center gap-1 rounded-full bg-ok/15 px-2.5 py-1 text-xs font-medium text-ok">
            <Check className="h-3 w-3" />
            Привʼязано
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
            Відвʼязати
          </Button>
          <ConfirmDialog
            open={confirmUnlink}
            title="Відвʼязати Telegram?"
            message="Відвʼязати Telegram? Бот перестане надсилати нагадування."
            confirmLabel="Відвʼязати"
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
              aria-label="Скопіювати код"
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
              Відкрити бота
            </Button>
          )}
          <p className="text-xs text-mist">
            Надішліть боту команду{' '}
            <span className="font-mono text-fg">/start {'<код>'}</span>. Код діє{' '}
            {linkData.expires_in_minutes} хвилин.
          </p>
        </div>
      ) : (
        <Button onClick={handleCreateCode} disabled={busy} className="mt-3 w-full">
          {busy ? 'Створення коду…' : 'Привʼязати Telegram'}
        </Button>
      )}
    </Card>
  );
}

function PasswordCard({ onToast }) {
  const changePassword = useAuthStore((s) => s.changePassword);
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [repeat, setRepeat] = useState('');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (next.length < 6) return setError('Пароль має бути не коротшим за 6 символів');
    // Caught here rather than by the server: a mistyped confirmation is the one
    // error that would otherwise succeed and lock the user out.
    if (next !== repeat) return setError('Паролі не збігаються');
    setError('');
    setSaving(true);
    try {
      await changePassword(current, next);
      setCurrent('');
      setNext('');
      setRepeat('');
      onToast('Пароль змінено');
    } catch (err) {
      setError(extractError(err, 'Не вдалося змінити пароль'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <h2 className="flex items-center gap-2 font-display text-sm font-semibold text-fg">
        <KeyRound className="h-4 w-4 text-mist" />
        Пароль
      </h2>
      <p className="mt-1 text-xs text-mist">
        Поточний пароль потрібен, щоб чужа відкрита сесія не могла забрати акаунт.
      </p>
      <form onSubmit={handleSubmit} className="mt-3 space-y-3">
        <TextField
          label="Поточний пароль"
          type="password"
          autoComplete="current-password"
          value={current}
          onChange={(e) => setCurrent(e.target.value)}
        />
        <div className="grid grid-cols-2 gap-3">
          <TextField
            label="Новий пароль"
            type="password"
            autoComplete="new-password"
            value={next}
            onChange={(e) => setNext(e.target.value)}
          />
          <TextField
            label="Ще раз"
            type="password"
            autoComplete="new-password"
            value={repeat}
            onChange={(e) => setRepeat(e.target.value)}
          />
        </div>
        <ErrorMessage>{error}</ErrorMessage>
        <Button type="submit" disabled={saving || !current || !next}>
          {saving ? 'Збереження…' : 'Змінити пароль'}
        </Button>
      </form>
    </Card>
  );
}

function EmailCard({ onToast }) {
  const user = useAuthStore((s) => s.user);
  const fetchMe = useAuthStore((s) => s.fetchMe);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const [pending, setPending] = useState(user?.pending_email || null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const handleRequest = async (e) => {
    e.preventDefault();
    setError('');
    setBusy(true);
    try {
      const { pending_email: parked } = await requestEmailChange(email.trim(), password);
      setPending(parked);
      setPassword('');
      onToast(`Код надіслано на ${parked}`);
    } catch (err) {
      setError(extractError(err, 'Не вдалося змінити пошту'));
    } finally {
      setBusy(false);
    }
  };

  const handleConfirm = async (e) => {
    e.preventDefault();
    setError('');
    setBusy(true);
    try {
      await confirmEmailChange(code.trim());
      await fetchMe();
      setPending(null);
      setEmail('');
      setCode('');
      onToast('Пошту змінено');
    } catch (err) {
      setError(extractError(err, 'Код невірний або протермінований'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <h2 className="flex items-center gap-2 font-display text-sm font-semibold text-fg">
        <Mail className="h-4 w-4 text-mist" />
        Пошта
      </h2>
      <p className="mt-1 text-xs text-mist">
        Зараз вхід за <span className="text-fg">{user?.email}</span>.
      </p>

      {pending ? (
        <form onSubmit={handleConfirm} className="mt-3 space-y-3">
          {/* The address moves only when a code from it comes back. Until then
              the old one still logs in — a typo costs a retry, not the account. */}
          <p className="rounded-xl border border-edge bg-raised px-3 py-2 text-xs text-mist">
            Код надіслано на <span className="text-fg">{pending}</span>. Поки не
            введете — вхід лишається на старій адресі.
          </p>
          <TextField
            label="Код з листа"
            inputMode="numeric"
            maxLength={6}
            numeric
            value={code}
            onChange={(e) => setCode(e.target.value)}
          />
          <ErrorMessage>{error}</ErrorMessage>
          <div className="flex gap-2">
            <Button type="submit" disabled={busy || !code.trim()} className="flex-1">
              {busy ? 'Перевірка…' : 'Підтвердити'}
            </Button>
            <Button variant="secondary" onClick={() => setPending(null)} disabled={busy}>
              Скасувати
            </Button>
          </div>
        </form>
      ) : (
        <form onSubmit={handleRequest} className="mt-3 space-y-3">
          <TextField
            label="Нова пошта"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <TextField
            label="Пароль"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <ErrorMessage>{error}</ErrorMessage>
          <Button type="submit" disabled={busy || !email.trim() || !password}>
            {busy ? 'Надсилання…' : 'Надіслати код на нову пошту'}
          </Button>
        </form>
      )}
    </Card>
  );
}

function DangerZone() {
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
      setError(extractError(err, 'Не вдалося видалити акаунт'));
      setBusy(false);
    }
  };

  return (
    <Card className="border-crit/30">
      <h2 className="flex items-center gap-2 font-display text-sm font-semibold text-crit">
        <Trash2 className="h-4 w-4" />
        Видалити акаунт
      </h2>
      <p className="mt-1 text-xs text-mist">
        Безповоротно зникнуть усі ваші авто, історія обслуговування, документи й фото.
        Скасувати неможливо. Введіть пароль для підтвердження.
      </p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (password) setConfirming(true);
        }}
        className="mt-3 space-y-3"
      >
        <TextField
          label="Пароль"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <ErrorMessage>{error}</ErrorMessage>
        <Button type="submit" variant="danger" disabled={busy || !password}>
          {busy ? 'Видалення…' : 'Видалити акаунт назавжди'}
        </Button>
      </form>

      <ConfirmDialog
        open={confirming}
        title="Видалити акаунт назавжди?"
        message="Уся сервісна історія ваших авто буде знищена без можливості відновлення."
        confirmLabel="Так, видалити"
        onConfirm={handleDelete}
        onCancel={() => setConfirming(false)}
      />
    </Card>
  );
}

export default function Profile() {
  const [toast, setToast] = useState('');

  return (
    <div className="stagger space-y-4">
      <Toast message={toast} onDone={() => setToast('')} />

      <BackLink to="/garage">Профіль</BackLink>

      <ProfileCard onToast={setToast} />
      <EmailCard onToast={setToast} />
      <PasswordCard onToast={setToast} />
      <TelegramCard onToast={setToast} />
      <DangerZone />
    </div>
  );
}
