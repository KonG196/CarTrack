import { useEffect, useState, useCallback } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { BookOpen, PlusCircle, SearchX, X } from 'lucide-react';
import { useCarStore } from '../store/carStore';
import { getLogs } from '../api/logs';
import { canDo, carIsShared } from '../utils/permissions';
import LogTimelineItem from '../components/LogTimelineItem';
import PendingTimelineItem from '../components/PendingTimelineItem';
import Toast from '../components/Toast';
import { Spinner, ErrorMessage, Card, ConfirmDialog, SearchField } from '../components/UI';

const FILTERS = [
  { value: '', labelKey: 'filterAll' },
  { value: 'refuel', labelKey: 'filterRefuel' },
  { value: 'maintenance', labelKey: 'filterMaintenance' },
  { value: 'repair', labelKey: 'filterRepair' },
  { value: 'expense', labelKey: 'filterExpense' },
];

export default function Logbook() {
  const { t } = useTranslation();
  const cars = useCarStore((s) => s.cars);
  const activeCarId = useCarStore((s) => s.activeCarId);
  const carsLoaded = useCarStore((s) => s.carsLoaded);
  const members = useCarStore((s) => s.members);
  const membersCarId = useCarStore((s) => s.membersCarId);
  const logs = useCarStore((s) => s.logs);
  const logsLoading = useCarStore((s) => s.logsLoading);
  const logsError = useCarStore((s) => s.logsError);
  const fetchLogs = useCarStore((s) => s.fetchLogs);
  const removeLog = useCarStore((s) => s.removeLog);
  const pending = useCarStore((s) => s.pending);
  const fetchPending = useCarStore((s) => s.fetchPending);

  const [filter, setFilter] = useState('');
  const [deletingLog, setDeletingLog] = useState(null);
  const [query, setQuery] = useState('');
  const [debouncedQ, setDebouncedQ] = useState('');
  const [baseTotal, setBaseTotal] = useState(null);
  const location = useLocation();
  const navigate = useNavigate();
  const [toast, setToast] = useState(location.state?.toast || '');
  const [toastVariant] = useState(location.state?.toastVariant || 'ok');

  const searchActive = Boolean(debouncedQ);

  const activeCar = cars.find((c) => String(c.id) === String(activeCarId)) || null;
  const canDelete = canDo(activeCar?.your_role, 'log:delete');
  const canCreate = canDo(activeCar?.your_role, 'log:create');
  const showAuthors =
    String(membersCarId) === String(activeCarId) && carIsShared(members);

  useEffect(() => {
    fetchPending().catch(() => {});
  }, [activeCarId, fetchPending]);

  const visiblePending = searchActive
    ? []
    : pending.filter((record) => !filter || record.payload.type === filter);

  const clearToast = useCallback(() => {
    setToast('');
    navigate(location.pathname, { replace: true, state: null });
  }, [navigate, location.pathname]);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQ(query.trim()), 300);
    return () => clearTimeout(timer);
  }, [query]);

  useEffect(() => {
    if (activeCarId) {
      fetchLogs({ type: filter || undefined, q: debouncedQ || undefined }).catch(() => {});
    }
  }, [activeCarId, filter, debouncedQ, fetchLogs]);

  useEffect(() => {
    if (!activeCarId || !searchActive) return undefined;
    let cancelled = false;
    getLogs(activeCarId, { type: filter || undefined, limit: 1 })
      .then((data) => {
        if (!cancelled) setBaseTotal(data.total);
      })
      .catch(() => {
        if (!cancelled) setBaseTotal(null);
      });
    return () => {
      cancelled = true;
    };
  }, [activeCarId, filter, searchActive]);

  const handleDelete = (log) => setDeletingLog(log);

  const confirmDelete = async () => {
    const log = deletingLog;
    setDeletingLog(null);
    if (!log) return;
    try {
      await removeLog(log.id, { type: filter || undefined, q: debouncedQ || undefined });
      setToast(t('logbook.toastDeleted'));
    } catch {
      setToast('');
      window.alert(t('logbook.deleteFailed'));
    }
  };

  if (carsLoaded && !activeCarId) {
    return (
      <Card className="rise-in mt-8 p-8 text-center">
        <p className="text-sm text-mist">
          {t('logbook.emptyCarBefore')}
          <Link to="/garage" className="text-amber hover:text-amber-deep">
            {t('logbook.emptyCarLink')}
          </Link>
          {t('logbook.emptyCarAfter')}
        </p>
      </Card>
    );
  }

  return (
    <div className="stagger space-y-4">
      <Toast message={toast} variant={toastVariant} onDone={clearToast} />

      <ConfirmDialog
        open={deletingLog !== null}
        title={t('logbook.confirmDeleteTitle')}
        message={t('logbook.confirmDeleteMessage')}
        onConfirm={confirmDelete}
        onCancel={() => setDeletingLog(null)}
      />

      <div data-tour="logbook-search">
        <SearchField
          label={t('logbook.searchLabel')}
          placeholder={t('logbook.searchPlaceholder')}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onClear={() => setQuery('')}
        />
      </div>

      <div data-tour="logbook-filters" className="no-scrollbar -mx-4 overflow-x-auto px-4">
        <div className="flex w-max gap-2">
          {FILTERS.map((f) => (
            <button
              key={f.value}
              type="button"
              onClick={() => setFilter(f.value)}
              className={`whitespace-nowrap rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${
                filter === f.value
                  ? 'bg-amber text-amber-ink'
                  : 'border border-edge-soft bg-panel text-mist hover:text-fg'
              }`}
            >
              {t(`logbook.${f.labelKey}`)}
            </button>
          ))}
        </div>
      </div>

      {logsError && <ErrorMessage>{logsError}</ErrorMessage>}

      {logsLoading ? (
        <Spinner />
      ) : logs.items.length === 0 && visiblePending.length === 0 ? (
        searchActive ? (
          <Card className="flex flex-col items-center gap-3 p-8 text-center">
            <SearchX className="h-8 w-8 text-mist/70" />
            <p className="text-sm text-mist">
              {t('logbook.noResults', { query: debouncedQ })}
            </p>
            <button
              type="button"
              onClick={() => setQuery('')}
              className="inline-flex items-center gap-1.5 text-sm font-medium text-amber hover:text-amber-deep"
            >
              <X className="h-4 w-4" />
              {t('logbook.clearSearch')}
            </button>
          </Card>
        ) : (
          <Card className="flex flex-col items-center gap-3 p-8 text-center">
            <BookOpen className="h-8 w-8 text-mist/70" />
            <p className="text-sm text-mist">
              {filter
                ? t('logbook.emptyOfType')
                : canCreate
                  ? t('logbook.emptyCreate')
                  : t('logbook.emptyViewer')}
            </p>
            {canCreate && (
              <Link
                to="/add"
                className="inline-flex items-center gap-1.5 text-sm font-medium text-amber hover:text-amber-deep"
              >
                <PlusCircle className="h-4 w-4" />
                {t('logbook.addEntry')}
              </Link>
            )}
          </Card>
        )
      ) : (
        <div className="stagger-pass stagger space-y-2.5">
          {searchActive && (
            <p className="px-1 text-xs text-mist">
              {t('logbook.found', { total: logs.total })}
              {baseTotal != null ? t('logbook.foundOf', { base: baseTotal }) : ''}
            </p>
          )}
          {visiblePending.map((record) => (
            <PendingTimelineItem key={`pending-${record.id}`} record={record} />
          ))}
          {logs.items.map((log, i) => (
            <LogTimelineItem
              key={log.id}
              log={log}
              onDelete={canDelete ? handleDelete : undefined}
              showAuthor={showAuthors}
              tourId={i === 0 && visiblePending.length === 0 ? 'log-row' : undefined}
            />
          ))}
          {logs.total > logs.items.length && (
            <p className="pt-1 text-center text-xs text-mist/70">
              {t('logbook.showing', { shown: logs.items.length, total: logs.total })}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
