import { describe, it, expect, vi, beforeEach } from 'vitest';

// The store reads the active car from localStorage at module load and the test
// environment is node, so a minimal in-memory stand-in is installed first.
const memoryLocalStorage = () => {
  const data = new Map();
  return {
    getItem: (k) => (data.has(k) ? data.get(k) : null),
    setItem: (k, v) => data.set(k, String(v)),
    removeItem: (k) => data.delete(k),
  };
};
vi.stubGlobal('localStorage', memoryLocalStorage());

vi.mock('../api/cars', () => ({
  getCars: vi.fn(),
  createCar: vi.fn(),
  updateCar: vi.fn(),
  deleteCar: vi.fn(),
}));
vi.mock('../api/logs', () => ({
  getLogs: vi.fn(),
  createLog: vi.fn(),
  updateLog: vi.fn(),
  deleteLog: vi.fn(),
}));
vi.mock('../api/intervals', () => ({
  getIntervals: vi.fn(),
  createInterval: vi.fn(),
  updateInterval: vi.fn(),
  deleteInterval: vi.fn(),
  completeInterval: vi.fn(),
}));
vi.mock('../api/analytics', () => ({ getAnalytics: vi.fn() }));
vi.mock('../api/members', () => ({
  getMembers: vi.fn(),
  createInvite: vi.fn(),
  removeMember: vi.fn(),
  updateMemberRole: vi.fn(),
}));
vi.mock('../offline/outbox', () => ({
  default: { enqueue: vi.fn(), listPending: vi.fn(async () => []), count: vi.fn(), flush: vi.fn() },
}));

const { useCarStore } = await import('./carStore');
const carsApi = await import('../api/cars');
const logsApi = await import('../api/logs');
const membersApi = await import('../api/members');

/** An axios network failure: the request never got a response. */
const networkError = () => Object.assign(new Error('Network Error'), { response: undefined });

const payload = { type: 'refuel', odometer: 100500, date: '2026-07-15', total_cost: 1000 };

describe('addLog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useCarStore.setState({ activeCarId: '7', cars: [], logs: { items: [], total: 0 } });
  });

  it('returns the created log and refreshes the car and the journal', async () => {
    logsApi.createLog.mockResolvedValue({ id: 1, ...payload });
    carsApi.getCars.mockResolvedValue([{ id: 7, current_odometer: 100500 }]);
    logsApi.getLogs.mockResolvedValue({ items: [{ id: 1 }], total: 1 });

    const log = await useCarStore.getState().addLog(payload);

    expect(log).toEqual({ id: 1, ...payload });
    expect(logsApi.createLog).toHaveBeenCalledWith('7', payload);
    expect(useCarStore.getState().logs.total).toBe(1);
  });

  it('propagates a failed create so the caller can queue the entry', async () => {
    logsApi.createLog.mockRejectedValue(networkError());

    await expect(useCarStore.getState().addLog(payload)).rejects.toThrow('Network Error');
  });

  // The entry is already on the server once the POST returns. If the refresh
  // that follows it fails, addLog must still resolve: AddEntry queues on any
  // throw it reads as a network error, so a rethrow here would send the same
  // entry a second time on the next flush and duplicate the record.
  it('resolves when the create succeeded but the refresh lost the network', async () => {
    logsApi.createLog.mockResolvedValue({ id: 1, ...payload });
    carsApi.getCars.mockRejectedValue(networkError());
    logsApi.getLogs.mockRejectedValue(networkError());

    await expect(useCarStore.getState().addLog(payload)).resolves.toEqual({ id: 1, ...payload });
  });
});

describe('fetchMembers', () => {
  const members = [
    { user_id: 1, label: 'brian', role: 'owner', is_you: true },
    { user_id: 2, label: 'olha', role: 'editor', is_you: false },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    useCarStore.setState({ activeCarId: '7', members: [], membersCarId: null });
  });

  it('reads the members of the active car', async () => {
    membersApi.getMembers.mockResolvedValue(members);

    await useCarStore.getState().fetchMembers();

    expect(membersApi.getMembers).toHaveBeenCalledWith('7');
    expect(useCarStore.getState().members).toEqual(members);
  });

  it('records which car the members belong to', async () => {
    membersApi.getMembers.mockResolvedValue(members);

    await useCarStore.getState().fetchMembers();

    expect(useCarStore.getState().membersCarId).toBe('7');
  });

  it('drops the members when the read fails', async () => {
    useCarStore.setState({ members, membersCarId: '7' });
    membersApi.getMembers.mockRejectedValue(networkError());

    await expect(useCarStore.getState().fetchMembers()).rejects.toThrow('Network Error');

    expect(useCarStore.getState().members).toEqual([]);
    expect(useCarStore.getState().membersCarId).toBe(null);
  });

  it('does nothing without an active car', async () => {
    useCarStore.setState({ activeCarId: null });

    await expect(useCarStore.getState().fetchMembers()).resolves.toEqual([]);

    expect(membersApi.getMembers).not.toHaveBeenCalled();
  });
});

describe('setActiveCar', () => {
  it('forgets the members of the car it left', () => {
    useCarStore.setState({
      members: [{ user_id: 1 }, { user_id: 2 }],
      membersCarId: '7',
    });

    useCarStore.getState().setActiveCar(8);

    expect(useCarStore.getState().members).toEqual([]);
    expect(useCarStore.getState().membersCarId).toBe(null);
  });
});

describe('leaveCar', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useCarStore.setState({ activeCarId: '7', cars: [{ id: 7 }, { id: 8 }] });
  });

  it('drops the membership and refreshes the garage', async () => {
    membersApi.removeMember.mockResolvedValue(undefined);
    carsApi.getCars.mockResolvedValue([{ id: 8, your_role: 'owner' }]);

    await useCarStore.getState().leaveCar(7, 3);

    expect(membersApi.removeMember).toHaveBeenCalledWith(3);
    expect(useCarStore.getState().cars).toEqual([{ id: 8, your_role: 'owner' }]);
  });

  it('moves off the car it just left', async () => {
    membersApi.removeMember.mockResolvedValue(undefined);
    carsApi.getCars.mockResolvedValue([{ id: 8, your_role: 'owner' }]);

    await useCarStore.getState().leaveCar(7, 3);

    expect(useCarStore.getState().activeCarId).toBe('8');
  });

  it('leaves the active car alone when another member was removed', async () => {
    membersApi.removeMember.mockResolvedValue(undefined);
    carsApi.getCars.mockResolvedValue([{ id: 7, your_role: 'owner' }, { id: 8 }]);

    await useCarStore.getState().leaveCar(8, 4);

    expect(useCarStore.getState().activeCarId).toBe('7');
  });
});

describe('removeMember', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useCarStore.setState({ activeCarId: '7' });
  });

  it('removes the membership and refreshes the list', async () => {
    membersApi.removeMember.mockResolvedValue(undefined);
    membersApi.getMembers.mockResolvedValue([{ user_id: 1, role: 'owner', is_you: true }]);

    await useCarStore.getState().removeMember(3);

    expect(membersApi.removeMember).toHaveBeenCalledWith(3);
    expect(useCarStore.getState().members).toHaveLength(1);
  });
});

describe('changeMemberRole', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useCarStore.setState({ activeCarId: '7' });
  });

  it('patches the role and refreshes the list', async () => {
    membersApi.updateMemberRole.mockResolvedValue({ id: 3, role: 'viewer' });
    membersApi.getMembers.mockResolvedValue([{ user_id: 2, role: 'viewer', is_you: false }]);

    await useCarStore.getState().changeMemberRole(3, 'viewer');

    expect(membersApi.updateMemberRole).toHaveBeenCalledWith(3, 'viewer');
    expect(useCarStore.getState().members[0].role).toBe('viewer');
  });
});
