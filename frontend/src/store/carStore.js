import { create } from 'zustand';
import * as carsApi from '../api/cars';
import * as logsApi from '../api/logs';
import * as intervalsApi from '../api/intervals';
import * as analyticsApi from '../api/analytics';
import * as membersApi from '../api/members';
import outbox from '../offline/outbox';

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

  members: [],
  membersCarId: null,
  membersLoading: false,
  membersError: null,

  pending: [],

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
      members: [],
      membersCarId: null,
      pending: [],
      logsError: null,
      intervalsError: null,
      analyticsError: null,
      membersError: null,
    });
  },

  async fetchLogs({ type, q, limit = 50, offset = 0 } = {}) {
    const { activeCarId } = get();
    if (!activeCarId) return;
    set({ logsLoading: true, logsError: null });
    try {
      const logs = await logsApi.getLogs(activeCarId, { type, q, limit, offset });
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


  async fetchMembers(carId) {
    const id = carId ?? get().activeCarId;
    if (!id) {
      set({ members: [], membersCarId: null });
      return [];
    }
    set({ membersLoading: true, membersError: null });
    try {
      const members = await membersApi.getMembers(id);
      set({ members, membersCarId: String(id), membersLoading: false });
      return members;
    } catch (error) {
      set({
        members: [],
        membersCarId: null,
        membersLoading: false,
        membersError: 'Не вдалося завантажити учасників',
      });
      throw error;
    }
  },

  async inviteMember(role) {
    const { activeCarId } = get();
    return membersApi.createInvite(activeCarId, role);
  },

  async removeMember(memberId) {
    await membersApi.removeMember(memberId);
    await get().fetchMembers();
  },

  async changeMemberRole(memberId, role) {
    await membersApi.updateMemberRole(memberId, role);
    await get().fetchMembers();
  },

  async leaveCar(carId, memberId) {
    await membersApi.removeMember(memberId);
    if (String(get().activeCarId) === String(carId)) {
      get().setActiveCar(null);
    }
    await get().fetchCars();
  },

  // --- Offline outbox ---

  async fetchPending() {
    const { activeCarId } = get();
    if (!activeCarId) {
      set({ pending: [] });
      return [];
    }
    try {
      const pending = await outbox.listPending(activeCarId);
      set({ pending });
      return pending;
    } catch {
      set({ pending: [] });
      return [];
    }
  },

  /** Queues an entry that could not reach the server. */
  async enqueueLog(payload) {
    const { activeCarId } = get();
    const record = await outbox.enqueue(activeCarId, payload);
    await get().fetchPending();
    return record;
  },

  /**
   * Replays the queue. The server is authoritative, so after a successful send
   * the car and the journal are refetched instead of being patched locally.
   */
  async flushOutbox() {
    const report = await outbox.flush((carId, payload) => logsApi.createLog(carId, payload));
    if (report.sent > 0) {
      await Promise.all([get().fetchCars(), get().fetchLogs()]);
    }
    await get().fetchPending();
    return report;
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
    //
    await Promise.all([get().fetchCars(), get().fetchLogs()]).catch(() => {});
    return log;
  },

  async editLog(logId, payload) {
    const log = await logsApi.updateLog(logId, payload);
    // editing a log can bump car.current_odometer
    await Promise.all([get().fetchCars(), get().fetchLogs()]);
    return log;
  },

  async removeLog(logId, params = {}) {
    await logsApi.deleteLog(logId);
    await get().fetchLogs(params);
  },

  async addInterval(payload) {
    const { activeCarId } = get();
    const interval = await intervalsApi.createInterval(activeCarId, payload);
    await get().fetchIntervals();
    return interval;
  },

  async editInterval(intervalId, payload) {
    const interval = await intervalsApi.updateInterval(intervalId, payload);
    await get().fetchIntervals();
    return interval;
  },

  async removeInterval(intervalId) {
    await intervalsApi.deleteInterval(intervalId);
    await get().fetchIntervals();
  },

  /**
   * Closes an interval: the backend logs the maintenance entry and rolls the
   * interval forward, so the odometer, the journal, the intervals and the
   * analytics can all have moved.
   */
  async completeInterval(intervalId, payload) {
    const result = await intervalsApi.completeInterval(intervalId, payload);
    await Promise.all([
      get().fetchCars(),
      get().fetchLogs(),
      get().fetchIntervals(),
      get().fetchAnalytics(),
    ]);
    return result;
  },

  // Skips presets whose title the car already carries. Without this, tapping
  // the button twice — or tapping it on a car that already has these intervals —
  // silently made a second and third copy of each. Returns how many were
  // actually created so the caller can say so instead of implying it added a
  // full set every time.
  async addIntervalPresets(car, presets) {
    const existing = new Set(
      (get().intervals || []).map((i) => i.title.trim().toLowerCase())
    );
    const fresh = presets.filter((p) => !existing.has(p.title.trim().toLowerCase()));
    const today = new Date().toISOString().slice(0, 10);
    const base = { last_odometer: car.current_odometer, last_date: today };
    for (const preset of fresh) {
      await intervalsApi.createInterval(car.id, { ...preset, ...base });
    }
    if (fresh.length) await get().fetchIntervals();
    return fresh.length;
  },

  reset() {
    set({
      cars: [],
      carsLoaded: false,
      activeCarId: null,
      logs: { items: [], total: 0 },
      intervals: [],
      analytics: null,
      members: [],
      membersCarId: null,
      pending: [],
    });
    localStorage.removeItem(ACTIVE_CAR_KEY);
  },
}));
