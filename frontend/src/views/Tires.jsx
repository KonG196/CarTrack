import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import BackLink from '../components/BackLink';
import TiresCard from '../components/TiresCard';
import Toast from '../components/Toast';
import { Card } from '../components/UI';
import { useCarStore } from '../store/carStore';

export default function Tires() {
  const { t } = useTranslation();
  const cars = useCarStore((s) => s.cars);
  const activeCarId = useCarStore((s) => s.activeCarId);
  const activeCar = cars.find((c) => String(c.id) === String(activeCarId)) || null;
  const [toast, setToast] = useState('');

  return (
    <div className="stagger space-y-4">
      <Toast message={toast} onDone={() => setToast('')} />
      <BackLink to="/garage">{t('tires.title')}</BackLink>
      {activeCar ? (
        <TiresCard key={activeCar.id} car={activeCar} onToast={setToast} />
      ) : (
        <Card>
          <p className="text-sm text-mist">{t('tires.noCar')}</p>
        </Card>
      )}
    </div>
  );
}
