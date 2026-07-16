import { useEffect, useRef, useState } from 'react';
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

function expiryNotice(doc) {
  const days = expiresInDays(doc.expires_at);
  if (days === null) return null;
  if (days < 0) return { text: `Прострочено ${formatDate(doc.expires_at)}`, tone: 'text-crit' };
  if (days <= 30) return { text: `Діє ще ${days} дн.`, tone: 'text-amber' };
  return { text: `До ${formatDate(doc.expires_at)}`, tone: 'text-mist' };
}

function DocumentForm({ onSubmit, onCancel }) {
  const [form, setForm] = useState({ kind: 'insurance', title: '', expires_at: '' });
  const [file, setFile] = useState(null);
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    if (!file) return setError('Виберіть файл');
    if (file.size > MAX_UPLOAD_BYTES) return setError('Файл завеликий (максимум 10 МБ)');
    if (!form.title.trim()) return setError('Вкажіть назву');

    setSubmitting(true);
    try {
      await onSubmit({
        file,
        kind: form.kind,
        title: form.title.trim(),
        expiresAt: form.expires_at,
      });
    } catch (err) {
      setError(extractError(err, 'Не вдалося завантажити документ'));
      setSubmitting(false);
    }
  };

  const linksReminder = EXPIRING_KINDS.includes(form.kind);

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <SelectField label="Вид" value={form.kind} onChange={set('kind')} options={DOCUMENT_KINDS} />
      <TextField label="Назва" required value={form.title} onChange={set('title')} />
      <DateField
        label="Діє до"
        clearable
        value={form.expires_at}
        onChange={(v) => setForm((f) => ({ ...f, expires_at: v }))}
        hint={
          linksReminder
            ? 'Нагадаємо за 14 днів до кінця дії'
            : 'Нагадування створюємо лише для страховки й техогляду'
        }
      />
      <div>
        <label className="mb-1.5 block text-xs text-mist" htmlFor="document-file">
          Файл (фото або PDF, до 10 МБ)
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
          {submitting ? 'Завантаження…' : 'Завантажити'}
        </Button>
        <Button variant="secondary" onClick={onCancel}>
          Скасувати
        </Button>
      </div>
    </form>
  );
}

export default function DocumentsCard({ car, onToast, onIntervalLinked }) {
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
        if (!cancelled) setError('Не вдалося завантажити документи');
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
        ? 'Документ додано, нагадування створено'
        : 'Документ додано'
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
      setError(extractError(err, 'Не вдалося відкрити документ'));
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
      onToast('Документ видалено');
    } catch (err) {
      setError(extractError(err, 'Не вдалося видалити документ'));
    }
  };

  return (
    <Card>
      <ConfirmDialog
        open={deletingDocument !== null}
        title="Видалити документ?"
        message={
          deletingDocument
            ? `Видалити «${deletingDocument.title}»? Нагадування про термін, якщо воно є, лишиться.`
            : ''
        }
        onConfirm={confirmDelete}
        onCancel={() => setDeletingDocument(null)}
      />

      <div className="mb-2 flex items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 font-display text-sm font-semibold text-fg">
          <FileText className="h-4 w-4 text-mist" />
          Документи · {car.brand} {car.model}
        </h2>
        {!showForm && canManage && (
          <Button variant="ghost" onClick={() => setShowForm(true)} className="px-2.5 py-1.5 text-amber">
            <Plus className="h-4 w-4" />
            Додати
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
          Техпаспорт, поліс, чеки — під рукою й офлайн. Для страховки й техогляду з датою
          «діє до» створимо нагадування.
        </p>
      ) : (
        <div className="divide-y divide-edge">
          {documents.map((doc) => {
            const notice = expiryNotice(doc);
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
                    aria-label={`Відкрити ${doc.title}`}
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
                      aria-label={`Видалити ${doc.title}`}
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
