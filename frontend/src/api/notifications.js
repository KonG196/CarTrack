import client from './client';

export async function getNotifications() {
  const { data } = await client.get('/notifications');
  return data; // { items: [{id, kind, severity, car_id, car_label, title, body, action}], count, unread }
}

// The full stored log (active + resolved), newest first.
export async function getNotificationHistory({ limit = 100, offset = 0 } = {}) {
  const { data } = await client.get('/notifications/history', {
    params: { limit, offset },
  });
  return data; // { items: [...rows], unread }
}

// Mark every unread notification read — called when the centre opens.
export async function markNotificationsRead() {
  const { data } = await client.post('/notifications/read');
  return data; // { unread: 0 }
}
