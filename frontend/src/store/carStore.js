import { create } from 'zustand';
import * as carsApi from '../api/cars';
import * as logsApi from '../api/logs';
import * as intervalsApi from '../api/intervals';
import * as analyticsApi from '../api/analytics';

const ACTIVE_CAR_KEY = 'kapot_tracker_active_car';

export const useCarStore = create((set, get) => ({
  cars: [],
  carsLoading: false,
  carsError: null,
  carsLoaded: false,
  activeCarId: localStorage.getItem(ACTIVE_CAR_KEY),

  logs: { items: [], total: 0 },
  logsLoading: false,
  logsError: null,

  intervals: [],
  intervalsLoading: false,
  intervalsError: null,

  analytics: null,
  analyticsLoading: false,
  analyticsError: null,

  activeCar() {
    const { cars, activeCarId } = get();
    return cars.find((c) => String(c.id) === String(activeCarId)) || null;
  },

  async fetchCars() {
    set({ carsLoading: true, carsError: null });
    try {
      const cars = await carsApi.getCars();
      let { activeCarId } = get();
      const exists = cars.some((c) => String(c.id) === String(activeCarId));
      if (!exists) {
        activeCarId = cars.length > 0 ? String(cars[0].id) : null;
        if (activeCarId) localStorage.setItem(ACTIVE_CAR_KEY, activeCarId);
        else localStorage.removeItem(ACTIVE_CAR_KEY);
      }
      set({ cars, activeCarId, carsLoading: false, carsLoaded: true });
      return cars;
    } catch (error) {
      set({ carsLoading: false, carsLoaded: true, carsError: 'Не вдалося завантажити авто' });
      throw error;
    }
  },

  setActiveCar(carId) {
    const id = carId != null ? String(carId) : null;
    if (id) localStorage.setItem(ACTIVE_CAR_KEY, id);
    else localStorage.removeItem(ACTIVE_CAR_KEY);
    set({
      activeCarId: id,
      logs: { items: [], total: 0 },
      intervals: [],
      analytics: null,
      logsError: null,
      intervalsError: null,
      analyticsError: null,
    });
  },

  async fetchLogs({ type, limit = 50, offset = 0 } = {}) {
    const { activeCarId } = get();
    if (!activeCarId) return;
    set({ logsLoading: true, logsError: null });
    try {
      const logs = await logsApi.getLogs(activeCarId, { type, limit, offset });
      set({ logs, logsLoading: false });
      return logs;
    } catch (error) {
      set({ logsLoading: false, logsError: 'Не вдалося завантажити журнал' });
      throw error;
    }
  },

  async fetchIntervals() {
    const { activeCarId } = get();
    if (!activeCarId) return;
    set({ intervalsLoading: true, intervalsError: null });
    try {
      const intervals = await intervalsApi.getIntervals(activeCarId);
      set({ intervals, intervalsLoading: false });
      return intervals;
    } catch (error) {
      set({ intervalsLoading: false, intervalsError: 'Не вдалося завантажити інтервали ТО' });
      throw error;
    }
  },

  async fetchAnalytics() {
    const { activeCarId } = get();
    if (!activeCarId) return;
    set({ analyticsLoading: true, analyticsError: null });
    try {
      const analytics = await analyticsApi.getAnalytics(activeCarId);
      set({ analytics, analyticsLoading: false });
      return analytics;
    } catch (error) {
      set({ analyticsLoading: false, analyticsError: 'Не вдалося завантажити аналітику' });
      throw error;
    }
  },

  // --- Mutations (refresh related data after each) ---

  async addCar(payload) {
    const car = await carsApi.createCar(payload);
    await get().fetchCars();
    if (!get().activeCarId) get().setActiveCar(car.id);
    return car;
  },

  async editCar(carId, payload) {
    const car = await carsApi.updateCar(carId, payload);
    await get().fetchCars();
    return car;
  },

  async removeCar(carId) {
    await carsApi.deleteCar(carId);
    if (String(get().activeCarId) === String(carId)) {
      get().setActiveCar(null);
    }
    await get().fetchCars();
  },

  async addLog(payload) {
    const { activeCarId } = get();
    const log = await logsApi.createLog(activeCarId, payload);
    // creating a log can bump car.current_odometer
    await Promise.all([get().fetchCars(), get().fetchLogs()]);
    return log;
  },

  async removeLog(logId, currentType) {
    await logsApi.deleteLog(logId);
    await get().fetchLogs({ type: currentType });
  },

  async addInterval(payload) {
    const { activeCarId } = get();
    const interval = await intervalsApi.createInterval(activeCarId, payload);
    await get().fetchIntervals();
    return interval;
  },

  async removeInterval(intervalId) {
    await intervalsApi.deleteInterval(intervalId);
    await get().fetchIntervals();
  },

  async addIntervalPresets(car) {
    const today = new Date().toISOString().slice(0, 10);
    const base = { last_odometer: car.current_odometer, last_date: today };
    const presets = [
      { title: 'Олива двигуна', interval_km: 10000, interval_days: 365, ...base },
      { title: 'Повітряний фільтр', interval_km: 20000, ...base },
      { title: 'Паливний фільтр', interval_km: 30000, ...base },
      { title: 'Салонний фільтр', interval_km: 15000, interval_days: 365, ...base },
      { title: 'ГРМ', interval_km: 120000, ...base },
      { title: 'Гальмівна рідина', interval_km: 60000, interval_days: 730, ...base },
    ];
    for (const preset of presets) {
      await intervalsApi.createInterval(car.id, preset);
    }
    await get().fetchIntervals();
  },

  reset() {
    set({
      cars: [],
      carsLoaded: false,
      activeCarId: null,
      logs: { items: [], total: 0 },
      intervals: [],
      analytics: null,
    });
    localStorage.removeItem(ACTIVE_CAR_KEY);
  },
}));
