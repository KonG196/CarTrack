import { useEffect, useState, useCallback } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { BookOpen, PlusCircle } from 'lucide-react';
import { useCarStore } from '../store/carStore';
import LogTimelineItem from '../components/LogTimelineItem';
import Toast from '../components/Toast';
import { Spinner, ErrorMessage, Card } from '../components/UI';

const FILTERS = [
  { value: '', label: 'Всі' },
  { value: 'refuel', label: 'Заправки' },
  { value: 'maintenance', label: 'ТО' },
  { value: 'repair', label: 'Ремонт' },
  { value: 'expense', label: 'Інше' },
];

export default function Logbook() {
  const activeCarId = useCarStore((s) => s.activeCarId);
  const carsLoaded = useCarStore((s) => s.carsLoaded);
  const logs = useCarStore((s) => s.logs);
  const logsLoading = useCarStore((s) => s.logsLoading);
  const logsError = useCarStore((s) => s.logsError);
  const fetchLogs = useCarStore((s) => s.fetchLogs);
  const removeLog = useCarStore((s) => s.removeLog);

  const [filter, setFilter] = useState('');
  const location = useLocation();
  const navigate = useNavigate();
  const [toast, setToast] = useState(location.state?.toast || '');

  const clearToast = useCallback(() => {
    setToast('');
    navigate(location.pathname, { replace: true, state: null });
  }, [navigate, location.pathname]);

  useEffect(() => {
    if (activeCarId) {
      fetchLogs({ type: filter || undefined }).catch(() => {});
    }
  }, [activeCarId, filter, fetchLogs]);

  const handleDelete = async (log) => {
    const ok = window.confirm('Видалити цей запис? Дію не можна скасувати.');
    if (!ok) return;
    try {
      await removeLog(log.id, filter || undefined);
      setToast('Запис видалено');
    } catch {
      setToast('');
      window.alert('Не вдалося видалити запис');
    }
  };

  if (carsLoaded && !activeCarId) {
    return (
      <Card className="mt-8 p-8 text-center">
        <p className="text-sm text-slate-400">
          Спершу додайте авто в розділі{' '}
          <Link to="/garage" className="text-blue-500 hover:text-blue-400">
            «Гараж»
          </Link>
          .
        </p>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <Toast message={toast} onDone={clearToast} />

      <div className="-mx-4 overflow-x-auto px-4">
        <div className="flex w-max gap-2">
          {FILTERS.map((f) => (
            <button
              key={f.value}
              type="button"
              onClick={() => setFilter(f.value)}
              className={`whitespace-nowrap rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${
                filter === f.value
                  ? 'bg-blue-600 text-white'
                  : 'border border-slate-700 bg-slate-900 text-slate-400 hover:text-slate-200'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {logsError && <ErrorMessage>{logsError}</ErrorMessage>}

      {logsLoading ? (
        <Spinner />
      ) : logs.items.length === 0 ? (
        <Card className="flex flex-col items-center gap-3 p-8 text-center">
          <BookOpen className="h-8 w-8 text-slate-600" />
          <p className="text-sm text-slate-400">
            {filter ? 'Немає записів цього типу.' : 'Журнал порожній. Додайте перший запис!'}
          </p>
          <Link
            to="/add"
            className="inline-flex items-center gap-1.5 text-sm font-medium text-blue-500 hover:text-blue-400"
          >
            <PlusCircle className="h-4 w-4" />
            Додати запис
          </Link>
        </Card>
      ) : (
        <div className="space-y-2.5">
          {logs.items.map((log) => (
            <LogTimelineItem key={log.id} log={log} onDelete={handleDelete} />
          ))}
          {logs.total > logs.items.length && (
            <p className="pt-1 text-center text-xs text-slate-600">
              Показано {logs.items.length} з {logs.total} записів
            </p>
          )}
        </div>
      )}
    </div>
  );
}
