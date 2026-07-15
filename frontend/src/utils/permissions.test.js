import { describe, it, expect } from 'vitest';
import { canDo, roleLabel, carIsShared, ACTION_MIN_ROLE, ROLE_RANK } from './permissions';

const MATRIX = {
  owner: {
    'car:view': true,
    'log:create': true,
    'log:edit': true,
    'log:delete': true,
    'photo:manage': true,
    'interval:complete': true,
    'obd:import': true,
    'document:manage': true,
    'car:edit': true,
    'car:delete': true,
    'interval:manage': true,
    'spec:manage': true,
    'tire:manage': true,
    'members:manage': true,
  },
  editor: {
    'car:view': true,
    'log:create': true,
    'log:edit': true,
    'log:delete': true,
    'photo:manage': true,
    'interval:complete': true,
    'obd:import': true,
    'document:manage': true,
    'car:edit': false,
    'car:delete': false,
    'interval:manage': false,
    'spec:manage': false,
    'tire:manage': false,
    'members:manage': false,
  },
  viewer: {
    'car:view': true,
    'log:create': false,
    'log:edit': false,
    'log:delete': false,
    'photo:manage': false,
    'interval:complete': false,
    'obd:import': false,
    'document:manage': false,
    'car:edit': false,
    'car:delete': false,
    'interval:manage': false,
    'spec:manage': false,
    'tire:manage': false,
    'members:manage': false,
  },
};

describe('canDo', () => {
  for (const [role, actions] of Object.entries(MATRIX)) {
    for (const [action, allowed] of Object.entries(actions)) {
      it(`${allowed ? 'lets' : 'stops'} a ${role} ${action}`, () => {
        expect(canDo(role, action)).toBe(allowed);
      });
    }
  }

  it('covers every declared action in the matrix', () => {
    expect(Object.keys(ACTION_MIN_ROLE).sort()).toEqual(Object.keys(MATRIX.owner).sort());
  });

  it('refuses an unknown role', () => {
    expect(canDo('admin', 'log:create')).toBe(false);
    expect(canDo('', 'car:view')).toBe(false);
    expect(canDo(null, 'car:view')).toBe(false);
    expect(canDo(undefined, 'car:view')).toBe(false);
  });

  it('refuses an unknown action', () => {
    expect(canDo('owner', 'car:launch')).toBe(false);
    expect(canDo('owner', undefined)).toBe(false);
  });

  it('ranks the roles owner > editor > viewer', () => {
    expect(ROLE_RANK.owner).toBeGreaterThan(ROLE_RANK.editor);
    expect(ROLE_RANK.editor).toBeGreaterThan(ROLE_RANK.viewer);
  });
});

describe('carIsShared', () => {
  it('is shared once someone else has access', () => {
    expect(carIsShared([{ user_id: 1 }, { user_id: 2 }])).toBe(true);
  });

  it('is not shared with a single member', () => {
    expect(carIsShared([{ user_id: 1 }])).toBe(false);
  });

  it('is not shared when the member list is empty or missing', () => {
    expect(carIsShared([])).toBe(false);
    expect(carIsShared(null)).toBe(false);
    expect(carIsShared(undefined)).toBe(false);
  });
});

describe('roleLabel', () => {
  it('names each role in Ukrainian', () => {
    expect(roleLabel('owner')).toBe('Власник');
    expect(roleLabel('editor')).toBe('Редактор');
    expect(roleLabel('viewer')).toBe('Спостерігач');
  });

  it('falls back to the raw value for an unknown role', () => {
    expect(roleLabel('admin')).toBe('admin');
    expect(roleLabel(null)).toBe('');
  });
});
