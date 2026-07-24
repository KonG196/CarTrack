import { useTranslation } from 'react-i18next';
import { useCarStore } from '../store/carStore';
import { canDo } from '../utils/permissions';
import { Spinner } from '../components/UI';
import BackLink from '../components/BackLink';
import GarageCarCard from '../components/GarageCarCard';
import useCarActions from '../hooks/useCarActions';

const FUEL_LABEL_KEYS = {
  petrol: 'fuelPetrol',
  diesel: 'fuelDiesel',
  lpg: 'fuelLpg',
  electric: 'fuelElectric',
  hybrid: 'fuelHybrid',
};

// The full garage: every car, each rendered exactly like the settings-page
// preview cards. Reached from "View all cars" once the garage grows past the
// preview count.
export default function AllCars() {
  const { t } = useTranslation();
  const cars = useCarStore((s) => s.cars);
  const activeCarId = useCarStore((s) => s.activeCarId);
  const carsLoading = useCarStore((s) => s.carsLoading);
  const carsLoaded = useCarStore((s) => s.carsLoaded);
  const { cardProps, Overlays } = useCarActions();

  const fuelLabel = (value) =>
    FUEL_LABEL_KEYS[value] ? t(`garage.${FUEL_LABEL_KEYS[value]}`) : value;

  if (carsLoading && !carsLoaded) return <Spinner />;

  return (
    <div className="stagger space-y-4 pb-12">
      <Overlays />
      <BackLink to="/garage">{t('garage.allCarsTitle')}</BackLink>

      {cars.map((car) => {
        const isActive = String(car.id) === String(activeCarId);
        return (
          <GarageCarCard
            key={car.id}
            car={car}
            isActive={isActive}
            isOwner={canDo(car.your_role, 'car:edit')}
            fuelLabel={fuelLabel}
            {...cardProps(car, activeCarId)}
          />
        );
      })}
    </div>
  );
}
