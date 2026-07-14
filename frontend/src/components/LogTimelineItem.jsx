import { Fuel, Wrench, Hammer, Receipt, Trash2 } from 'lucide-react';
import { formatMoney, formatKm, formatDate } from '../utils/format';

export const LOG_TYPE_META = {
  refuel: { label: 'Заправка', icon: Fuel, color: 'text-[#3987e5]', bg: 'bg-[#3987e5]/10' },
  maintenance: { label: 'ТО', icon: Wrench, color: 'text-[#199e70]', bg: 'bg-[#199e70]/10' },
  repair: { label: 'Ремонт', icon: Hammer, color: 'text-[#c98500]', bg: 'bg-[#c98500]/10' },
  expense: { label: 'Витрата', icon: Receipt, color: 'text-[#9085e9]', bg: 'bg-[#9085e9]/10' },
};

function logTitle(log) {
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
  return log.notes ? `Витрата · ${log.notes}` : 'Витрата';
}

export default function LogTimelineItem({ log, onDelete }) {
  const meta = LOG_TYPE_META[log.type] || LOG_TYPE_META.expense;
  const Icon = meta.icon;

  return (
    <div className="flex items-start gap-3 rounded-2xl border border-slate-800 bg-slate-900 p-3.5">
      <span className={`mt-0.5 flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl ${meta.bg}`}>
        <Icon className={`h-5 w-5 ${meta.color}`} />
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-slate-100">{logTitle(log)}</p>
        <p className="mt-0.5 text-xs text-slate-500">
          {formatDate(log.date)} · {formatKm(log.odometer)}
        </p>
        {log.type === 'refuel' && log.refuel && (
          <p className="mt-0.5 text-xs text-slate-500">
            {Number(log.refuel.liters).toFixed(1)} л × {formatMoney(log.refuel.price_per_liter)}/л
            {log.refuel.is_full_tank ? ' · повний бак' : ''}
          </p>
        )}
        {log.type !== 'refuel' && log.notes && (
          <p className="mt-0.5 truncate text-xs text-slate-500">{log.notes}</p>
        )}
      </div>
      <div className="flex flex-col items-end gap-1.5">
        <span className="whitespace-nowrap text-sm font-semibold text-slate-100">
          {formatMoney(log.total_cost)}
        </span>
        {onDelete && (
          <button
            type="button"
            onClick={() => onDelete(log)}
            aria-label="Видалити запис"
            className="rounded-lg p-1.5 text-slate-600 transition-colors hover:bg-red-950/50 hover:text-red-400"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        )}
      </div>
    </div>
  );
}
