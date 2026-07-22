import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Fuel, Wrench, Hammer, Receipt, Trash2, User } from 'lucide-react';
import { formatMoney, formatKm, formatDate } from '../utils/format';
import i18n from '../i18n';
import {
  maintenanceItemLabel,
  repairCategoryLabel,
  expenseCategoryLabel,
} from '../i18n/domain';

// `label` is a live getter so a language switch relabels without a reload; this
// object is a module-level constant, so it can't use the `useTranslation` hook.
export const LOG_TYPE_META = {
  refuel: {
    get label() {
      return i18n.t('logTimeline.typeRefuel');
    },
    icon: Fuel,
    color: 'text-[#3987e5]',
    bg: 'bg-[#3987e5]/10',
  },
  maintenance: {
    get label() {
      return i18n.t('logTimeline.typeMaintenance');
    },
    icon: Wrench,
    color: 'text-[#199e70]',
    bg: 'bg-[#199e70]/10',
  },
  repair: {
    get label() {
      return i18n.t('logTimeline.typeRepair');
    },
    icon: Hammer,
    color: 'text-[#c98500]',
    bg: 'bg-[#c98500]/10',
  },
  expense: {
    get label() {
      return i18n.t('logTimeline.typeExpense');
    },
    icon: Receipt,
    color: 'text-[#9085e9]',
    bg: 'bg-[#9085e9]/10',
  },
};

export function logTitle(log) {
  if (log.type === 'refuel') {
    const type = i18n.t('logTimeline.typeRefuel');
    return log.refuel?.gas_station ? `${type} · ${log.refuel.gas_station}` : type;
  }
  if (log.type === 'maintenance') {
    const type = i18n.t('logTimeline.typeMaintenance');
    const items = log.maintenance?.items || [];
    return items.length > 0
      ? `${type} · ${items.slice(0, 2).map(maintenanceItemLabel).join(', ')}${items.length > 2 ? '…' : ''}`
      : type;
  }
  if (log.type === 'repair') {
    const type = i18n.t('logTimeline.typeRepair');
    const cat = log.repair?.category;
    const part = log.repair?.part_name;
    if (cat && part) return `${type} · ${repairCategoryLabel(cat)} · ${part}`;
    if (cat) return `${type} · ${repairCategoryLabel(cat)}`;
    return type;
  }
  const type = i18n.t('logTimeline.typeExpense');
  if (log.expense?.category) return `${type} · ${expenseCategoryLabel(log.expense.category)}`;
  return log.notes ? `${type} · ${log.notes}` : type;
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
  const { t } = useTranslation();
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
            {t('logTimeline.refuelLine', {
              liters: Number(log.refuel.liters).toFixed(1),
              price: formatMoney(log.refuel.price_per_liter),
            })}
            {log.refuel.consumption_l_100km != null
              ? ` · ${t('logTimeline.consumption', { value: log.refuel.consumption_l_100km.toFixed(1) })}`
              : ''}
            {log.refuel.is_full_tank ? ` · ${t('logTimeline.fullTank')}` : ''}
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
            aria-label={t('logTimeline.deleteEntry')}
            className="rounded-lg p-1.5 text-mist/70 transition-colors hover:bg-crit/10 hover:text-crit"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        )}
      </div>
    </div>
  );
}
