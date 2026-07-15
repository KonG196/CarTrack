
export const ROLE_RANK = { viewer: 1, editor: 2, owner: 3 };

export const ACTION_MIN_ROLE = {
  'car:view': 'viewer',

  'log:create': 'editor',
  'log:edit': 'editor',
  'log:delete': 'editor',
  'photo:manage': 'editor',
  'interval:complete': 'editor',
  'obd:import': 'editor',
  'document:manage': 'editor',

  'car:edit': 'owner',
  'car:delete': 'owner',
  'interval:manage': 'owner',
  'spec:manage': 'owner',
  'tire:manage': 'owner',
  'members:manage': 'owner',
};

const ROLE_LABELS = {
  owner: 'Власник',
  editor: 'Редактор',
  viewer: 'Спостерігач',
};

export function canDo(role, action) {
  const required = ACTION_MIN_ROLE[action];
  if (required === undefined) return false;
  const rank = ROLE_RANK[role];
  if (rank === undefined) return false;
  return rank >= ROLE_RANK[required];
}

export function roleLabel(role) {
  if (!role) return '';
  return ROLE_LABELS[role] || role;
}

export function carIsShared(members) {
  return Array.isArray(members) && members.length > 1;
}
