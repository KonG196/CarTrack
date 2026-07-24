import { useTranslation } from 'react-i18next';
import {
  Check,
  Gauge,
  Pencil,
  MoreVertical,
  Wrench,
  FileDown,
  FileSpreadsheet,
  QrCode,
  Trash2,
  Loader2,
} from 'lucide-react';
import { Menu } from './UI';
import CarHeaderCard from './CarHeaderCard';
import CopyCarName from './CopyCarName';
import { roleLabel } from '../utils/permissions';
import { formatKm } from '../utils/format';

// A frosted-glass button that sits over the car photo: translucent + blurred so
// the car shows through, a faint white edge so the button reads, and a light
// hover. Matches the dashboard's glass tiles.
const GLASS_BTN =
  'flex items-center rounded-xl border border-white/10 bg-white/10 px-3 py-2 ' +
  'text-fg backdrop-blur-sm transition-colors hover:bg-white/15 active:bg-white/20';

// One car in the garage list. The car photo (or marque logo) sits as the
// darkened background, like the dashboard block. The primary actions — "Make
// active" and "Edit" — are buttons; everything else (specs, report, CSV, QR
// passport, delete) moves into a "⋯" menu so a car with many tools no longer
// overflows the card.
export default function GarageCarCard({
  car,
  isActive,
  isOwner,
  tourId,
  fuelLabel,
  reporting,
  csvBusy,
  anyBusy,
  onSetActive,
  onEdit,
  onSpecs,
  onReport,
  onCsv,
  onPassport,
  onDelete,
  onCopied,
}) {
  const { t } = useTranslation();

  // The overflow menu's entries, each a {value, label} the Menu dispatches back.
  const menuItems = [
    { value: 'specs', label: <MenuLabel icon={Wrench}>{t('garage.techSpecs')}</MenuLabel> },
    {
      value: 'report',
      label: (
        <MenuLabel icon={reporting ? Loader2 : FileDown} spin={reporting}>
          {t('garage.reportTitleShort')}
        </MenuLabel>
      ),
    },
    {
      value: 'csv',
      label: (
        <MenuLabel icon={csvBusy ? Loader2 : FileSpreadsheet} spin={csvBusy}>
          {t('garage.csvTitleShort')}
        </MenuLabel>
      ),
    },
    ...(isOwner
      ? [
          { value: 'qr', label: <MenuLabel icon={QrCode}>{t('garage.qrPassportTitle')}</MenuLabel> },
          {
            value: 'delete',
            label: (
              <MenuLabel icon={Trash2} danger>
                {t('garage.deleteCarLabel')}
              </MenuLabel>
            ),
          },
        ]
      : []),
  ];

  const onMenu = (value) => {
    if (value === 'specs') onSpecs();
    else if (value === 'report' && !anyBusy) onReport();
    else if (value === 'csv' && !anyBusy) onCsv();
    else if (value === 'qr') onPassport();
    else if (value === 'delete') onDelete();
  };

  return (
    <div data-tour={tourId} className={isActive ? 'rounded-2xl ring-1 ring-amber/40' : ''}>
      <CarHeaderCard carId={car.id}>
       <div className="flex min-h-[92px] flex-col justify-between gap-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="text-base font-semibold text-fg">
              <CopyCarName car={car} onCopied={onCopied}>
                {car.brand} {car.model}
                {car.generation ? ` ${car.generation}` : ''}
              </CopyCarName>
            </p>
            <p className="mt-0.5 text-xs text-mist">
              {car.year} · {car.engine ? `${car.engine} · ` : ''}
              {fuelLabel(car.fuel_type)}
            </p>
            <div className="mt-2 flex items-center gap-1.5 text-sm text-fg">
              <Gauge className="h-4 w-4 text-mist" />
              {formatKm(car.current_odometer)}
              <span className="ml-1 text-xs text-mist/70">
                {t('garage.kmPerDay', { km: Math.round(car.avg_daily_km) })}
              </span>
            </div>
          </div>
          <div className="flex flex-shrink-0 items-center gap-1.5">
            {!isOwner && (
              <span className="flex items-center gap-1 rounded-full bg-signal/15 px-2.5 py-1 text-xs font-medium text-signal">
                {roleLabel(car.your_role)}
              </span>
            )}
            {isActive && (
              <span className="flex items-center gap-1 rounded-full bg-amber/15 px-2.5 py-1 text-xs font-medium text-amber">
                <Check className="h-3 w-3" />
                {t('garage.active')}
              </span>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2">
          {!isActive && (
            <button
              type="button"
              onClick={onSetActive}
              className={`${GLASS_BTN} flex-1 justify-center text-sm font-semibold`}
            >
              {t('garage.makeActive')}
            </button>
          )}
          {isOwner && (
            <button
              type="button"
              onClick={onEdit}
              aria-label={t('garage.editCarLabel')}
              className={`${GLASS_BTN} ${isActive ? 'flex-1 justify-center' : ''}`}
            >
              <Pencil className="h-4 w-4" />
            </button>
          )}
          <Menu
            ariaLabel={t('garage.moreActions')}
            items={menuItems}
            onSelect={onMenu}
            align="right"
            buttonClassName={GLASS_BTN}
            button={<MoreVertical className="h-4 w-4" />}
          />
        </div>
       </div>
      </CarHeaderCard>
    </div>
  );
}

function MenuLabel({ icon: Icon, children, danger, spin }) {
  return (
    <span className={`flex items-center gap-2 ${danger ? 'text-crit' : ''}`}>
      <Icon className={`h-4 w-4 flex-shrink-0 ${spin ? 'animate-spin' : ''}`} />
      {children}
    </span>
  );
}
