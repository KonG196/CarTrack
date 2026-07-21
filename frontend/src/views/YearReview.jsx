import { useEffect, useState } from 'react';
import { Share2, Fuel, Route, Gauge, Wallet, MapPin, TrendingUp, CalendarDays } from 'lucide-react';
import { useCarStore } from '../store/carStore';
import { getYearReview } from '../api/yearReview';
import { shareYearImage } from '../utils/shareYearImage';
import { formatMoney, formatKm } from '../utils/format';
import BackLink from '../components/BackLink';
import Toast from '../components/Toast';
import { Button, Card, Spinner, ErrorMessage } from '../components/UI';

const MONTHS = [
  'Січень', 'Лютий', 'Березень', 'Квітень', 'Травень', 'Червень',
  'Липень', 'Серпень', 'Вересень', 'Жовтень', 'Листопад', 'Грудень',
];

function Stat({ icon: Icon, label, value }) {
  return (
    <Card className="flex flex-col gap-1 p-3.5">
      <span className="flex items-center gap-1.5 text-xs text-mist">
        <Icon className="h-3.5 w-3.5 flex-shrink-0" />
        {label}
      </span>
      <span className="font-mono text-base font-semibold leading-tight tabular-nums text-fg">
        {value}
      </span>
    </Card>
  );
}

export default function YearReview() {
  const cars = useCarStore((s) => s.cars);
  const carsLoaded = useCarStore((s) => s.carsLoaded);
  const activeCarId = useCarStore((s) => s.activeCarId);
  // activeCarId is a string (from localStorage); car ids are numbers — coerce.
  const car = cars.find((c) => String(c.id) === String(activeCarId)) || cars[0];

  const [review, setReview] = useState(null);
  const [year, setYear] = useState(null); // null = let the server pick the latest
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [toast, setToast] = useState('');

  useEffect(() => {
    if (!car) return undefined;
    let cancelled = false;
    setLoading(true);
    setError('');
    getYearReview(car.id, year)
      .then((data) => {
        if (cancelled) return;
        setReview(data);
        // Don't echo data.year back into `year` — the selector highlights
        // review.year directly, and re-setting it would trigger a redundant
        // refetch (and could skip a later car switch).
      })
      .catch(() => {
        if (!cancelled) setError('Не вдалося завантажити підсумок року');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [car?.id, year]);

  const share = async () => {
    if (!review?.has_data) return;
    const result = await shareYearImage(review, `${car.brand} ${car.model}`);
    if (result === 'downloaded') setToast('Картку збережено');
    else if (result === 'error') setToast('Не вдалося створити картку');
  };

  if (!carsLoaded) {
    return (
      <div className="stagger space-y-4">
        <BackLink to="/analytics">Ваш рік</BackLink>
        <Spinner />
      </div>
    );
  }

  if (!car) {
    return (
      <div className="stagger space-y-4">
        <BackLink to="/analytics">Ваш рік</BackLink>
        <Card>
          <p className="text-sm text-mist">Спочатку додайте авто.</p>
        </Card>
      </div>
    );
  }

  return (
    <div className="stagger space-y-4">
      <Toast message={toast} onDone={() => setToast('')} />
      <BackLink to="/analytics">Ваш рік</BackLink>

      {review?.available_years?.length > 1 && (
        <div className="no-scrollbar -mx-1 flex gap-2 overflow-x-auto px-1">
          {review.available_years.map((y) => (
            <button
              key={y}
              type="button"
              onClick={() => setYear(y)}
              className={`flex-shrink-0 rounded-full px-3.5 py-1.5 font-mono text-sm font-medium tabular-nums transition-colors ${
                y === review.year ? 'bg-amber text-amber-ink' : 'bg-panel text-mist hover:text-fg'
              }`}
            >
              {y}
            </button>
          ))}
        </div>
      )}

      {error && <ErrorMessage>{error}</ErrorMessage>}

      {loading && !review ? (
        <Spinner />
      ) : review && !review.has_data ? (
        <Card>
          <p className="py-2 text-sm text-mist">
            За {review.year} рік ще немає записів. Ведіть журнал — і наприкінці року отримаєте
            підсумок.
          </p>
        </Card>
      ) : (
        review?.has_data && (
          <>
            <Card className="overflow-hidden">
              <p className="font-display text-xs font-semibold uppercase tracking-wide text-amber">
                Ваш рік {review.year}
              </p>
              <p className="mt-2 text-xs text-mist">Витрачено за рік</p>
              <p className="font-mono text-4xl font-bold leading-none tabular-nums text-fg">
                {formatMoney(review.total_spent)}
              </p>
              <p className="mt-2 text-xs text-mist">
                {review.entries_count} записів · {review.refuels_count} заправок
                {review.busiest_month != null && ` · найактивніший ${MONTHS[review.busiest_month - 1]}`}
              </p>
            </Card>

            <div className="grid grid-cols-2 gap-2.5">
              <Stat icon={Route} label="Пробіг" value={formatKm(review.km_driven)} />
              <Stat icon={Fuel} label="Заправлено" value={review.liters != null ? `${review.liters} л` : '—'} />
              <Stat
                icon={Gauge}
                label="Витрата"
                value={
                  review.avg_consumption_l_100km != null
                    ? `${review.avg_consumption_l_100km.toFixed(1)} л/100`
                    : '—'
                }
              />
              <Stat
                icon={Wallet}
                label="на 100 км"
                value={review.cost_per_km != null ? `${Math.round(review.cost_per_km * 100)} ₴` : '—'}
              />
            </div>

            {review.cheapest_station && (
              <Card className="flex items-center gap-3 p-3.5">
                <MapPin className="h-4 w-4 flex-shrink-0 text-ok" />
                <div className="min-w-0 flex-1">
                  <p className="text-xs text-mist">Найдешевша АЗС</p>
                  <p className="truncate text-sm font-medium text-fg">
                    {review.cheapest_station.name}
                  </p>
                </div>
                <span className="flex-shrink-0 font-mono text-sm font-medium tabular-nums text-fg">
                  {review.cheapest_station.avg_price_per_liter} ₴/л
                </span>
              </Card>
            )}

            {review.biggest_expense && (
              <Card className="flex items-center gap-3 p-3.5">
                <TrendingUp className="h-4 w-4 flex-shrink-0 text-amber" />
                <div className="min-w-0 flex-1">
                  <p className="text-xs text-mist">Найбільша витрата</p>
                  <p className="truncate text-sm font-medium text-fg">
                    {review.biggest_expense.title}
                  </p>
                </div>
                <span className="flex-shrink-0 font-mono text-sm font-medium tabular-nums text-fg">
                  {formatMoney(review.biggest_expense.amount)}
                </span>
              </Card>
            )}

            <Button onClick={share} className="w-full">
              <Share2 className="h-4 w-4" />
              Поділитися карткою
            </Button>
          </>
        )
      )}
    </div>
  );
}
