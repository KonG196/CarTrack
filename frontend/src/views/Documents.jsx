import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import BackLink from '../components/BackLink';
import DocumentsCard from '../components/DocumentsCard';
import Toast from '../components/Toast';
import { Card } from '../components/UI';
import { useCarStore } from '../store/carStore';

export default function Documents() {
  const { t } = useTranslation();
  const cars = useCarStore((s) => s.cars);
  const activeCarId = useCarStore((s) => s.activeCarId);
  const fetchIntervals = useCarStore((s) => s.fetchIntervals);
  const activeCar = cars.find((c) => String(c.id) === String(activeCarId)) || null;
  const [toast, setToast] = useState('');

  return (
    <div className="stagger space-y-4">
      <Toast message={toast} onDone={() => setToast('')} />
      <BackLink to="/garage">{t('documents.title')}</BackLink>
      {activeCar ? (
        <DocumentsCard
          key={activeCar.id}
          car={activeCar}
          onToast={setToast}
          onIntervalLinked={() => fetchIntervals().catch(() => {})}
        />
      ) : (
        <Card>
          <p className="text-sm text-mist">{t('documents.addCarFirst')}</p>
        </Card>
      )}
    </div>
  );
}
