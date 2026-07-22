import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { FileText, Plus, Trash2, Download, Loader2, CalendarClock } from 'lucide-react';
import { extractError } from '../api/client';
import {
  getDocuments,
  uploadDocument,
  getDocumentBlob,
  deleteDocument,
  documentKindLabel,
  expiresInDays,
  DOCUMENT_KINDS,
  EXPIRING_KINDS,
} from '../api/documents';
import { formatDate } from '../utils/format';
import { canDo } from '../utils/permissions';
import { Button, DateField, TextField, SelectField, Card, Spinner, ErrorMessage, ConfirmDialog } from './UI';

const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
const ACCEPT = 'image/*,application/pdf';

function expiryNotice(doc, t) {
  const days = expiresInDays(doc.expires_at);
  if (days === null) return null;
  if (days < 0) return { text: t('documentsCard.expiredOn', { date: formatDate(doc.expires_at) }), tone: 'text-crit' };
  if (days <= 30) return { text: t('documentsCard.daysLeft', { days }), tone: 'text-amber' };
  return { text: t('documentsCard.validUntil', { date: formatDate(doc.expires_at) }), tone: 'text-mist' };
}

function DocumentForm({ onSubmit, onCancel }) {
  const { t } = useTranslation();
  const [form, setForm] = useState({ kind: 'insurance', title: '', expires_at: '' });
  const [file, setFile] = useState(null);
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    if (!file) return setError(t('documentsCard.errChooseFile'));
    if (file.size > MAX_UPLOAD_BYTES) return setError(t('documentsCard.errFileTooLarge'));
    if (!form.title.trim()) return setError(t('documentsCard.errEnterTitle'));

    setSubmitting(true);
    try {
      await onSubmit({
        file,
        kind: form.kind,
        title: form.title.trim(),
        expiresAt: form.expires_at,
      });
    } catch (err) {
      setError(extractError(err, t('documentsCard.errUpload')));
      setSubmitting(false);
    }
  };

  const linksReminder = EXPIRING_KINDS.includes(form.kind);

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <SelectField label={t('documentsCard.kindLabel')} value={form.kind} onChange={set('kind')} options={DOCUMENT_KINDS} />
      <TextField label={t('documentsCard.titleLabel')} required value={form.title} onChange={set('title')} />
      <DateField
        label={t('documentsCard.validUntilLabel')}
        clearable
        value={form.expires_at}
        onChange={(v) => setForm((f) => ({ ...f, expires_at: v }))}
        hint={
          linksReminder
            ? t('documentsCard.reminderHint')
            : t('documentsCard.reminderHintNone')
        }
      />
      <div>
        <label className="mb-1.5 block text-xs text-mist" htmlFor="document-file">
          {t('documentsCard.fileFieldLabel')}
        </label>
        <input
          id="document-file"
          type="file"
          accept={ACCEPT}
          onChange={(e) => setFile(e.target.files?.[0] || null)}
          className="block w-full text-sm text-mist file:mr-3 file:rounded-lg file:border-0 file:bg-raised file:px-3 file:py-2 file:text-sm file:font-medium file:text-fg"
        />
      </div>
      <ErrorMessage>{error}</ErrorMessage>
      <div className="flex gap-2">
        <Button type="submit" disabled={submitting} className="flex-1">
          {submitting ? t('documentsCard.uploading') : t('documentsCard.upload')}
        </Button>
        <Button variant="secondary" onClick={onCancel}>
          {t('common.cancel')}
        </Button>
      </div>
    </form>
  );
}

export default function DocumentsCard({ car, onToast, onIntervalLinked }) {
  const { t } = useTranslation();
  const canManage = canDo(car?.your_role, 'document:manage');
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [deletingDocument, setDeletingDocument] = useState(null);
  const [openingId, setOpeningId] = useState(null);

  const urlsRef = useRef({});

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError('');
    getDocuments(car.id)
      .then((data) => {
        if (!cancelled) setDocuments(data);
      })
      .catch(() => {
        if (!cancelled) setError(t('documentsCard.errLoad'));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [car.id]);

  useEffect(() => {
    const urls = urlsRef.current;
    return () => {
      Object.values(urls).forEach((url) => URL.revokeObjectURL(url));
    };
  }, []);

  const handleUpload = async (payload) => {
    const created = await uploadDocument(car.id, payload);
    setDocuments((prev) => [created, ...prev]);
    setShowForm(false);
    onToast(
      created.linked_interval_id
        ? t('documentsCard.addedWithReminder')
        : t('documentsCard.added')
    );
    if (created.linked_interval_id) await onIntervalLinked();
  };

  const handleOpen = async (doc) => {
    if (openingId != null) return;
    setError('');
    setOpeningId(doc.id);
    try {
      let url = urlsRef.current[doc.id];
      if (!url) {
        url = URL.createObjectURL(await getDocumentBlob(doc.id));
        urlsRef.current[doc.id] = url;
      }
      window.open(url, '_blank', 'noopener');
    } catch (err) {
      setError(extractError(err, t('documentsCard.errOpen')));
    } finally {
      setOpeningId(null);
    }
  };

  const confirmDelete = async () => {
    const doc = deletingDocument;
    setDeletingDocument(null);
    if (!doc) return;
    setError('');
    try {
      await deleteDocument(doc.id);
      setDocuments((prev) => prev.filter((d) => d.id !== doc.id));
      const url = urlsRef.current[doc.id];
      if (url) {
        URL.revokeObjectURL(url);
        delete urlsRef.current[doc.id];
      }
      onToast(t('documentsCard.deleted'));
    } catch (err) {
      setError(extractError(err, t('documentsCard.errDelete')));
    }
  };

  return (
    <Card>
      <ConfirmDialog
        open={deletingDocument !== null}
        title={t('documentsCard.confirmDeleteTitle')}
        message={
          deletingDocument
            ? t('documentsCard.confirmDeleteMessage', { title: deletingDocument.title })
            : ''
        }
        onConfirm={confirmDelete}
        onCancel={() => setDeletingDocument(null)}
      />

      <div className="mb-2 flex items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 font-display text-sm font-semibold text-fg">
          <FileText className="h-4 w-4 text-mist" />
          {t('documentsCard.heading')} · {car.brand} {car.model}
        </h2>
        {!showForm && canManage && (
          <Button variant="ghost" onClick={() => setShowForm(true)} className="px-2.5 py-1.5 text-amber">
            <Plus className="h-4 w-4" />
            {t('common.add')}
          </Button>
        )}
      </div>

      {error && <ErrorMessage className="mb-2">{error}</ErrorMessage>}

      {showForm && (
        <div className="mb-3 rounded-xl border border-edge bg-raised p-3">
          <DocumentForm onSubmit={handleUpload} onCancel={() => setShowForm(false)} />
        </div>
      )}

      {loading ? (
        <Spinner className="py-4" />
      ) : documents.length === 0 ? (
        <p className="py-2 text-sm text-mist">
          {t('documentsCard.empty')}
        </p>
      ) : (
        <div className="divide-y divide-edge">
          {documents.map((doc) => {
            const notice = expiryNotice(doc, t);
            return (
              <div key={doc.id} className="flex items-start justify-between gap-3 py-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-fg">{doc.title}</p>
                  <p className="mt-0.5 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-mist">
                    <span>{documentKindLabel(doc.kind)}</span>
                    {notice && (
                      <span className={`flex items-center gap-1 ${notice.tone}`}>
                        <CalendarClock className="h-3 w-3" />
                        {notice.text}
                      </span>
                    )}
                  </p>
                </div>
                <div className="flex flex-shrink-0 items-center">
                  <button
                    type="button"
                    onClick={() => handleOpen(doc)}
                    disabled={openingId != null}
                    aria-label={t('documentsCard.openAria', { title: doc.title })}
                    className="rounded-lg p-1.5 text-mist/70 transition-colors hover:bg-raised hover:text-fg disabled:text-edge"
                  >
                    {openingId === doc.id ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Download className="h-4 w-4" />
                    )}
                  </button>
                  {canManage && (
                    <button
                      type="button"
                      onClick={() => setDeletingDocument(doc)}
                      aria-label={t('documentsCard.deleteAria', { title: doc.title })}
                      className="rounded-lg p-1.5 text-mist/70 transition-colors hover:bg-crit/10 hover:text-crit"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
}
