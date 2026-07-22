import { useTranslation } from 'react-i18next';
import { formatMoney, formatKm, formatDate } from '../utils/format';
import { LOG_TYPE_META, logTitle } from './LogTimelineItem';

export default function PendingTimelineItem({ record }) {
  const { t } = useTranslation();
  const { payload } = record;
  const meta = LOG_TYPE_META[payload.type] || LOG_TYPE_META.expense;
  const Icon = meta.icon;

  return (
    <div className="flex items-start gap-3 rounded-2xl border border-dashed border-amber/40 bg-panel/60 p-3.5">
      <span
        className={`mt-0.5 flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl ${meta.bg}`}
      >
        <Icon className={`h-5 w-5 ${meta.color}`} />
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-fg">{logTitle(payload)}</p>
        <p className="mt-0.5 font-mono text-xs tabular-nums text-mist">
          {formatDate(payload.date)} · {formatKm(payload.odometer)}
        </p>
        <span className="mt-1.5 inline-flex items-center gap-1 rounded-lg bg-amber/10 px-2 py-0.5 text-[11px] font-medium text-amber">
          ⏳ {t('pendingTimeline.awaitingSync')}
        </span>
      </div>
      <span className="whitespace-nowrap font-mono text-sm font-semibold tabular-nums text-mist">
        {formatMoney(payload.total_cost)}
      </span>
    </div>
  );
}
