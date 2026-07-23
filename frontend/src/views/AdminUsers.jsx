import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { ShieldCheck, MailCheck, MailX, Ban, ChevronRight, Car } from 'lucide-react';
import * as adminApi from '../api/admin';
import { Card, SearchField, Spinner, ErrorMessage } from '../components/UI';

// A little status pill — verified / blocked / superadmin — used per row.
function StatusPills({ user }) {
  const { t } = useTranslation();
  return (
    <div className="mt-0.5 flex flex-wrap items-center gap-1.5">
      {user.blocked ? (
        <span className="inline-flex items-center gap-1 rounded-md bg-crit/15 px-1.5 py-0.5 text-[11px] font-medium text-crit">
          <Ban className="h-3 w-3" /> {t('admin.statusBlocked')}
        </span>
      ) : null}
      {user.is_superadmin ? (
        <span className="inline-flex items-center gap-1 rounded-md bg-amber/15 px-1.5 py-0.5 text-[11px] font-medium text-amber">
          <ShieldCheck className="h-3 w-3" /> {t('admin.statusAdmin')}
        </span>
      ) : null}
      <span
        className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-medium ${
          user.email_verified ? 'bg-ok/15 text-ok' : 'bg-edge-soft/40 text-mist'
        }`}
      >
        {user.email_verified ? <MailCheck className="h-3 w-3" /> : <MailX className="h-3 w-3" />}
        {user.email_verified ? t('admin.statusVerified') : t('admin.statusUnverified')}
      </span>
    </div>
  );
}

export default function AdminUsers() {
  const { t } = useTranslation();
  const [query, setQuery] = useState('');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async (q) => {
    setLoading(true);
    setError('');
    try {
      setData(await adminApi.listUsers({ q }));
    } catch {
      setError(t('admin.loadError'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  // Debounce the search so a query fires after typing settles, not per keystroke.
  useEffect(() => {
    const id = setTimeout(() => load(query), 250);
    return () => clearTimeout(id);
  }, [query, load]);

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-xl font-semibold text-fg">{t('admin.title')}</h1>
        <p className="text-sm text-mist">
          {data ? t('admin.usersTotal', { count: data.total }) : t('admin.subtitle')}
        </p>
      </header>

      <SearchField
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onClear={() => setQuery('')}
        placeholder={t('admin.searchPlaceholder')}
      />

      {error ? <ErrorMessage>{error}</ErrorMessage> : null}

      {loading && !data ? (
        <div className="flex justify-center py-10">
          <Spinner />
        </div>
      ) : data && data.users.length === 0 ? (
        <p className="py-10 text-center text-sm text-mist">{t('admin.empty')}</p>
      ) : (
        <ul className="space-y-2">
          {data?.users.map((u) => (
            <li key={u.id}>
              <Link
                to={`/admin/users/${u.id}`}
                className="block transition active:scale-[0.99] motion-reduce:active:scale-100"
              >
                <Card className="flex items-center gap-3 transition-colors hover:border-edge-soft">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-fg">
                      {u.display_name || u.email.split('@')[0]}
                    </p>
                    <p className="truncate text-xs text-mist">{u.email}</p>
                    <StatusPills user={u} />
                  </div>
                  <span className="flex flex-shrink-0 items-center gap-1 text-xs text-mist">
                    <Car className="h-3.5 w-3.5" /> {u.car_count}
                  </span>
                  <ChevronRight className="h-4 w-4 flex-shrink-0 text-mist" />
                </Card>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
