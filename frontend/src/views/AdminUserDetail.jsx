import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Copy, Check } from 'lucide-react';
import BrandLogo from '../components/BrandLogo';
import * as adminApi from '../api/admin';
import { useAuthStore } from '../store/authStore';
import {
  Card,
  Button,
  TextField,
  SelectField,
  Toggle,
  Spinner,
  ErrorMessage,
  ConfirmDialog,
  Modal,
} from '../components/UI';
import Toast from '../components/Toast';
import { CURRENCIES } from '../currency';
import { UNIT_SYSTEMS } from '../units';

const LANGUAGES = [
  { code: 'en', name: 'English' },
  { code: 'uk', name: 'Українська' },
];

function Section({ title, children, tone }) {
  return (
    <section className="space-y-3">
      <h2
        className={`text-xs font-semibold uppercase tracking-wide ${
          tone === 'danger' ? 'text-crit' : 'text-mist'
        }`}
      >
        {title}
      </h2>
      {children}
    </section>
  );
}

// A generated link with a copy button and the "emailed / mail off" note.
function LinkResult({ result, onClose }) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(result.link);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard blocked — the link is visible to select manually */
    }
  };
  return (
    <Card className="space-y-2 border-amber/40">
      <p className="text-xs font-medium text-mist">{t('admin.linkTitle')}</p>
      <p className="break-all rounded-lg bg-raised p-2 font-mono text-xs text-fg">
        {result.link}
      </p>
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs text-mist">
          {result.emailed ? t('admin.emailed') : t('admin.notEmailed')}
        </span>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={copy} className="px-3 py-1.5 text-xs">
            {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
            {copied ? t('admin.linkCopied') : t('admin.copy')}
          </Button>
          <Button variant="ghost" onClick={onClose} className="px-3 py-1.5 text-xs">
            ✕
          </Button>
        </div>
      </div>
    </Card>
  );
}

export default function AdminUserDetail() {
  const { t } = useTranslation();
  const { id } = useParams();
  const navigate = useNavigate();
  const me = useAuthStore((s) => s.user);

  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [toast, setToast] = useState('');
  const [busy, setBusy] = useState(false);
  const [link, setLink] = useState(null);
  const [confirmBlock, setConfirmBlock] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [blockReason, setBlockReason] = useState('');

  // Editable identity fields, seeded from the loaded user.
  const [form, setForm] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await adminApi.getUser(id);
      setDetail(data);
      setForm({
        email: data.user.email,
        display_name: data.user.display_name || '',
        language: data.user.language,
        currency: data.user.currency,
        unit_system: data.user.unit_system,
      });
    } catch {
      setError(t('admin.loadError'));
    } finally {
      setLoading(false);
    }
  }, [id, t]);

  useEffect(() => {
    load();
  }, [load]);

  const user = detail?.user;
  const isSelf = me && user && me.id === user.id;

  const apply = (data) => {
    setDetail(data);
    setForm({
      email: data.user.email,
      display_name: data.user.display_name || '',
      language: data.user.language,
      currency: data.user.currency,
      unit_system: data.user.unit_system,
    });
  };

  const run = async (fn, okMsg) => {
    setBusy(true);
    try {
      const res = await fn();
      if (okMsg) setToast(okMsg);
      return res;
    } catch (e) {
      setToast(e?.response?.data?.detail || t('admin.actionError'));
      return null;
    } finally {
      setBusy(false);
    }
  };

  const saveIdentity = async () => {
    // Send only what changed from the loaded values.
    const changed = {};
    for (const k of ['email', 'display_name', 'language', 'currency', 'unit_system']) {
      const original = k === 'display_name' ? user.display_name || '' : user[k];
      if (form[k] !== original) changed[k] = form[k];
    }
    if (Object.keys(changed).length === 0) {
      setToast(t('admin.nothingToSave'));
      return;
    }
    const res = await run(() => adminApi.updateUser(id, changed), t('admin.saved'));
    if (res) apply(res);
  };

  const toggleStatus = async (patch) => {
    const res = await run(() => adminApi.setStatus(id, patch), t('admin.saved'));
    if (res) apply(res);
  };

  const doBlock = async () => {
    setConfirmBlock(false);
    const res = await run(
      () => adminApi.setStatus(id, { blocked: true, blocked_reason: blockReason.trim() }),
      t('admin.saved'),
    );
    if (res) {
      apply(res);
      setBlockReason('');
    }
  };

  const doDelete = async () => {
    setConfirmDelete(false);
    const res = await run(() => adminApi.deleteUser(id).then(() => true), t('admin.deleted'));
    if (res) navigate('/admin', { replace: true });
  };

  if (loading) {
    return (
      <div className="flex justify-center py-16">
        <Spinner />
      </div>
    );
  }
  if (error || !user || !form) {
    return (
      <div className="space-y-4">
        <BackLink />
        <ErrorMessage>{error || t('admin.loadError')}</ErrorMessage>
      </div>
    );
  }

  return (
    <div className="space-y-6 pb-4">
      <BackLink />

      <header className="space-y-1">
        <h1 className="text-xl font-semibold text-fg">
          {user.display_name || user.email.split('@')[0]}
        </h1>
        <p className="break-all text-sm text-mist">{user.email}</p>
        <p className="text-xs text-mist">
          {t('admin.provider')}: {user.auth_provider} · {t('admin.createdAt')}:{' '}
          {new Date(user.created_at).toLocaleDateString()}
        </p>
        {user.blocked ? (
          <p className="rounded-lg bg-crit/10 px-2 py-1 text-xs text-crit">
            {t('admin.blockedNote', { reason: user.blocked_reason || '—' })}
          </p>
        ) : null}
        {isSelf ? <p className="text-xs text-amber">{t('admin.selfNote')}</p> : null}
      </header>

      {link ? <LinkResult result={link} onClose={() => setLink(null)} /> : null}

      {/* Identity & preferences */}
      <Section title={t('admin.sectionIdentity')}>
        <Card className="space-y-3">
          <TextField
            label={t('admin.fieldEmail')}
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
          />
          <TextField
            label={t('admin.fieldName')}
            value={form.display_name}
            onChange={(e) => setForm({ ...form, display_name: e.target.value })}
          />
          <SelectField
            label={t('admin.fieldLanguage')}
            value={form.language}
            onChange={(e) => setForm({ ...form, language: e.target.value })}
          >
            {LANGUAGES.map((l) => (
              <option key={l.code} value={l.code}>
                {l.name}
              </option>
            ))}
          </SelectField>
          <SelectField
            label={t('admin.fieldCurrency')}
            value={form.currency}
            onChange={(e) => setForm({ ...form, currency: e.target.value })}
          >
            {CURRENCIES.map((c) => (
              <option key={c.code} value={c.code}>
                {c.code} · {c.symbol}
              </option>
            ))}
          </SelectField>
          <SelectField
            label={t('admin.fieldUnits')}
            value={form.unit_system}
            onChange={(e) => setForm({ ...form, unit_system: e.target.value })}
          >
            {UNIT_SYSTEMS.map((u) => (
              <option key={u.code} value={u.code}>
                {u.name}
              </option>
            ))}
          </SelectField>
          <Button onClick={saveIdentity} disabled={busy} className="w-full">
            {t('admin.save')}
          </Button>
        </Card>
      </Section>

      {/* Status */}
      <Section title={t('admin.sectionStatus')}>
        <Card className="space-y-3">
          <Toggle
            label={t('admin.toggleVerified')}
            checked={user.email_verified}
            onChange={(v) => !busy && toggleStatus({ email_verified: v })}
          />
          <Toggle
            label={t('admin.toggleAdmin')}
            checked={user.is_superadmin}
            onChange={(v) => {
              if (busy) return;
              // Demoting yourself is refused server-side; don't even try.
              if (isSelf && !v) return;
              toggleStatus({ is_superadmin: v });
            }}
          />
          {user.blocked ? (
            <Button
              variant="secondary"
              onClick={() => toggleStatus({ blocked: false })}
              disabled={busy}
              className="w-full"
            >
              {t('admin.unblock')}
            </Button>
          ) : (
            <Button
              variant="danger"
              onClick={() => setConfirmBlock(true)}
              disabled={busy || isSelf}
              className="w-full"
            >
              {t('admin.block')}
            </Button>
          )}
        </Card>
      </Section>

      {/* Password & verification links */}
      <Section title={t('admin.sectionLinks')}>
        <div className="grid grid-cols-2 gap-2">
          <Button
            variant="secondary"
            disabled={busy}
            onClick={() => run(() => adminApi.resetLink(id)).then((r) => r && setLink(r))}
          >
            {t('admin.genResetLink')}
          </Button>
          <Button
            variant="secondary"
            disabled={busy}
            onClick={() => run(() => adminApi.verifyLink(id)).then((r) => r && setLink(r))}
          >
            {t('admin.genVerifyLink')}
          </Button>
          <Button
            variant="ghost"
            disabled={busy}
            onClick={() =>
              run(() => adminApi.sendReset(id), t('admin.saved')).then((r) => r && setLink(r))
            }
          >
            {t('admin.sendReset')}
          </Button>
          <Button
            variant="ghost"
            disabled={busy}
            onClick={() =>
              run(() => adminApi.sendVerify(id), t('admin.saved')).then((r) => r && setLink(r))
            }
          >
            {t('admin.sendVerify')}
          </Button>
        </div>
      </Section>

      {/* Cars (read-only) */}
      <Section title={t('admin.cars')}>
        {detail.cars.length === 0 ? (
          <p className="text-sm text-mist">{t('admin.noCars')}</p>
        ) : (
          <ul className="space-y-2">
            {detail.cars.map((c) => (
              <li key={c.id}>
                <Card className="flex items-center gap-3">
                  {c.image_url ? (
                    <img
                      src={c.image_url}
                      alt=""
                      loading="lazy"
                      className="h-12 w-16 flex-shrink-0 rounded-lg object-cover"
                    />
                  ) : (
                    <BrandLogo brand={c.brand} className="h-9 w-9 rounded-lg" />
                  )}
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm text-fg">
                      {c.brand} {c.model} · {c.year}
                    </p>
                    <p className="text-xs text-mist">
                      {c.fuel_type} · {c.current_odometer.toLocaleString()} · {c.plate || '—'}
                    </p>
                  </div>
                </Card>
              </li>
            ))}
          </ul>
        )}
      </Section>

      {/* Recent activity on this user */}
      <Section title={t('admin.sectionAudit')}>
        {detail.audit.length === 0 ? (
          <p className="text-sm text-mist">{t('admin.auditEmpty')}</p>
        ) : (
          <ul className="space-y-1.5">
            {detail.audit.map((a) => (
              <li key={a.id} className="flex items-center justify-between gap-2 text-xs">
                <span className="text-fg">{t(`admin.action_${a.action}`, a.action)}</span>
                <span className="text-mist">{new Date(a.created_at).toLocaleString()}</span>
              </li>
            ))}
          </ul>
        )}
      </Section>

      {/* Danger zone */}
      <Section title={t('admin.sectionDanger')} tone="danger">
        <Button
          variant="danger"
          onClick={() => setConfirmDelete(true)}
          disabled={busy || isSelf}
          className="w-full"
        >
          {t('admin.delete')}
        </Button>
      </Section>

      {/* Block confirm — asks for a reason inline. A plain Modal (not
          ConfirmDialog) so the reason field is not nested inside a <p>. */}
      <Modal
        open={confirmBlock}
        onClose={() => {
          setConfirmBlock(false);
          setBlockReason('');
        }}
        title={t('admin.blockConfirmTitle')}
        size="sm"
        footer={
          <>
            <Button
              variant="danger"
              onClick={doBlock}
              disabled={!blockReason.trim()}
              className="flex-1"
            >
              {t('admin.block')}
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                setConfirmBlock(false);
                setBlockReason('');
              }}
              className="flex-1"
            >
              {t('common.cancel')}
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <p className="text-sm text-mist">{t('admin.blockConfirmMessage')}</p>
          <TextField
            label={t('admin.blockReasonLabel')}
            placeholder={t('admin.blockReasonPlaceholder')}
            value={blockReason}
            onChange={(e) => setBlockReason(e.target.value)}
          />
        </div>
      </Modal>

      <ConfirmDialog
        open={confirmDelete}
        title={t('admin.deleteConfirmTitle')}
        message={t('admin.deleteConfirmMessage')}
        confirmLabel={t('admin.delete')}
        onConfirm={doDelete}
        onCancel={() => setConfirmDelete(false)}
      />

      <Toast message={toast} onDone={() => setToast('')} />
    </div>
  );
}

function BackLink() {
  const { t } = useTranslation();
  return (
    <Link
      to="/admin"
      className="inline-flex items-center gap-1.5 text-sm text-mist transition-colors hover:text-fg"
    >
      <ArrowLeft className="h-4 w-4" /> {t('admin.back')}
    </Link>
  );
}
