import { useNavigate } from 'react-router-dom';
import { Fuel, Wrench, Hammer, Receipt, Trash2, User } from 'lucide-react';
import { formatMoney, formatKm, formatDate } from '../utils/format';

export const LOG_TYPE_META = {
  refuel: { label: 'Заправка', icon: Fuel, color: 'text-[#3987e5]', bg: 'bg-[#3987e5]/10' },
  maintenance: { label: 'ТО', icon: Wrench, color: 'text-[#199e70]', bg: 'bg-[#199e70]/10' },
  repair: { label: 'Ремонт', icon: Hammer, color: 'text-[#c98500]', bg: 'bg-[#c98500]/10' },
  expense: { label: 'Витрата', icon: Receipt, color: 'text-[#9085e9]', bg: 'bg-[#9085e9]/10' },
};

export function logTitle(log) {
  if (log.type === 'refuel') {
    return log.refuel?.gas_station ? `Заправка · ${log.refuel.gas_station}` : 'Заправка';
  }
  if (log.type === 'maintenance') {
    const items = log.maintenance?.items || [];
    return items.length > 0 ? `ТО · ${items.slice(0, 2).join(', ')}${items.length > 2 ? '…' : ''}` : 'ТО';
  }
  if (log.type === 'repair') {
    const cat = log.repair?.category;
    const part = log.repair?.part_name;
    if (cat && part) return `Ремонт · ${cat} · ${part}`;
    if (cat) return `Ремонт · ${cat}`;
    return 'Ремонт';
  }
  if (log.expense?.category) return `Витрата · ${log.expense.category}`;
  return log.notes ? `Витрата · ${log.notes}` : 'Витрата';
}

export function authorLabel(log) {
  return log?.author?.label || null;
}

export function AuthorChip({ label, className = '' }) {
  if (!label) return null;
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full bg-raised px-2 py-0.5 text-xs text-mist ${className}`}
    >
      <User className="h-3 w-3" />
      {label}
    </span>
  );
}

export default function LogTimelineItem({ log, onDelete, showAuthor = false, tourId }) {
  const navigate = useNavigate();
  const meta = LOG_TYPE_META[log.type] || LOG_TYPE_META.expense;
  const Icon = meta.icon;
  const author = showAuthor ? authorLabel(log) : null;

  return (
    <div
      data-tour={tourId}
      role="link"
      tabIndex={0}
      onClick={() => navigate(`/logbook/${log.id}`)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' && e.target === e.currentTarget) navigate(`/logbook/${log.id}`);
      }}
      className="flex cursor-pointer items-start gap-3 rounded-2xl border border-edge bg-panel p-3.5 transition-colors hover:border-edge-soft"
    >
      <span className={`mt-0.5 flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl ${meta.bg}`}>
        <Icon className={`h-5 w-5 ${meta.color}`} />
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-fg">{logTitle(log)}</p>
        <p className="mt-0.5 font-mono text-xs tabular-nums text-mist">
          {formatDate(log.date)} · {formatKm(log.odometer)}
        </p>
        {log.type === 'refuel' && log.refuel && (
          <p className="mt-0.5 font-mono text-xs tabular-nums text-mist">
            {Number(log.refuel.liters).toFixed(1)} л × {formatMoney(log.refuel.price_per_liter)}/л
            {log.refuel.consumption_l_100km != null
              ? ` · ${log.refuel.consumption_l_100km.toFixed(1)} л/100 км`
              : ''}
            {log.refuel.is_full_tank ? ' · повний бак' : ''}
          </p>
        )}
        {log.type !== 'refuel' && log.notes && (
          <p className="mt-0.5 line-clamp-2 text-xs text-mist">{log.notes}</p>
        )}
        {author && <AuthorChip label={author} className="mt-1.5" />}
      </div>
      <div className="flex flex-col items-end gap-1.5">
        <span className="whitespace-nowrap font-mono text-sm font-semibold tabular-nums text-fg">
          {formatMoney(log.total_cost)}
        </span>
        {onDelete && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onDelete(log);
            }}
            aria-label="Видалити запис"
            className="rounded-lg p-1.5 text-mist/70 transition-colors hover:bg-crit/10 hover:text-crit"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        )}
      </div>
    </div>
  );
}
