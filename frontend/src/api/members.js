import client from './client';

export async function getMembers(carId) {
  const { data } = await client.get(`/cars/${carId}/members`);
  return data;
}

export async function createInvite(carId, role) {
  const { data } = await client.post(`/cars/${carId}/invites`, { role });
  return data;
}

export async function getInvite(token) {
  const { data } = await client.get(`/invites/${encodeURIComponent(token)}`);
  return data;
}

export async function acceptInvite(token) {
  const { data } = await client.post(`/invites/${encodeURIComponent(token)}/accept`);
  return data;
}

export async function removeMember(memberId) {
  await client.delete(`/members/${memberId}`);
}

export async function updateMemberRole(memberId, role) {
  const { data } = await client.patch(`/members/${memberId}`, { role });
  return data;
}

export function inviteUrl(invitePath, origin = window.location.origin) {
  if (!invitePath) return '';
  return `${origin.replace(/\/$/, '')}${invitePath}`;
}
