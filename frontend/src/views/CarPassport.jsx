import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Car, Phone, Printer, ShieldCheck, Gauge, Fuel, Hash } from 'lucide-react';

import { getPublicPassport } from '../api/passport';
import { formatDate } from '../utils/format';

const FUEL_LABELS = {
  petrol: 'Бензин',
  diesel: 'Дизель',
  lpg: 'ГБО',
  electric: 'Електро',
  hybrid: 'Гібрид',
};

function Row({ icon: Icon, label, children }) {
  if (!children) return null;
  return (
    <div className="flex items-start gap-3 border-t border-edge py-3 first:border-t-0">
      <Icon className="mt-0.5 h-4 w-4 flex-shrink-0 text-mist" />
      <div className="min-w-0">
        <p className="text-xs text-mist">{label}</p>
        <p className="mt-0.5 break-words text-sm font-medium text-fg">{children}</p>
      </div>
    </div>
  );
}

export default function CarPassport() {
  const { token } = useParams();
  const [state, setState] = useState({ loading: true, car: null, missing: false });

  useEffect(() => {
    let cancelled = false;
    getPublicPassport(token)
      .then((car) => {
        if (!cancelled) setState({ loading: false, car, missing: car === null });
      })
      .catch(() => {
        if (!cancelled) setState({ loading: false, car: null, missing: true });
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  const { loading, car, missing } = state;

  const title = car
    ? [car.brand, car.model, car.generation].filter(Boolean).join(' ')
    : '';

  return (
    <div className="min-h-screen bg-garage px-4 py-8">
      <div className="mx-auto max-w-md">
        {loading ? (
          <p className="py-16 text-center text-sm text-mist">Завантаження…</p>
        ) : missing || !car ? (
          <div className="rounded-2xl border border-edge bg-panel p-8 text-center">
            <Car className="mx-auto h-8 w-8 text-mist/70" />
            <p className="mt-3 text-sm text-mist">
              Паспорт не знайдено. Можливо, посилання відкликали.
            </p>
          </div>
        ) : (
          <>
            <div className="rounded-2xl border border-edge bg-panel p-5">
              <div className="mb-1 flex items-center gap-2">
                <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-amber/15">
                  <Car className="h-5 w-5 text-amber" />
                </span>
                <div className="min-w-0">
                  <h1 className="font-display text-lg font-semibold text-fg">{title}</h1>
                  <p className="text-xs text-mist">
                    {car.year}
                    {car.engine ? ` · ${car.engine}` : ''} · {FUEL_LABELS[car.fuel_type] || car.fuel_type}
                  </p>
                </div>
              </div>
              {car.plate && (
                <div className="mt-3 inline-flex items-center rounded-lg border border-edge-soft bg-garage px-3 py-1.5 font-mono text-base font-semibold tracking-wide text-fg">
                  {car.plate}
                </div>
              )}

              {car.contact_phone && (
                <a
                  href={`tel:${car.contact_phone.replace(/\s/g, '')}`}
                  className="mt-4 flex items-center justify-center gap-2 rounded-xl bg-amber py-3 text-sm font-semibold text-amber-ink transition active:scale-[0.98]"
                >
                  <Phone className="h-4 w-4" />
                  Зателефонувати власнику · {car.contact_phone}
                </a>
              )}

              <div className="mt-4">
                <Row icon={Hash} label="VIN">{car.vin}</Row>
                <Row icon={ShieldCheck} label="Страховка ОСЦПВ">
                  {car.insurance_number || car.insurance_until ? (
                    <>
                      {car.insurance_number}
                      {car.insurance_until ? (
                        <span className="text-mist">
                          {car.insurance_number ? ' · ' : ''}
                          дійсна до {formatDate(car.insurance_until)}
                        </span>
                      ) : null}
                    </>
                  ) : null}
                </Row>
                <Row icon={Fuel} label="Допуск пального">{car.fuel_approval}</Row>
                <Row icon={Gauge} label="Тиск у шинах">{car.tire_pressure}</Row>
              </div>
            </div>

            <button
              type="button"
              onClick={() => window.print()}
              className="mt-4 flex w-full items-center justify-center gap-2 rounded-xl border border-edge bg-panel py-2.5 text-sm font-medium text-fg transition active:scale-[0.99] print:hidden"
            >
              <Printer className="h-4 w-4" />
              Роздрукувати
            </button>
            <p className="mt-3 text-center text-xs text-mist/60">Kapot Tracker · паспорт авто</p>
          </>
        )}
      </div>
    </div>
  );
}
