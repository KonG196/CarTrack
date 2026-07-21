import client from './client';

export async function getNotifications() {
  const { data } = await client.get('/notifications');
  return data; // { items: [{id, kind, severity, car_id, car_label, title, body, action}], count }
}
