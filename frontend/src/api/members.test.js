import { describe, it, expect, vi, beforeEach } from 'vitest';
import client from './client';
import {
  getMembers,
  createInvite,
  getInvite,
  acceptInvite,
  removeMember,
  updateMemberRole,
  inviteUrl,
} from './members';

vi.mock('./client', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

beforeEach(() => {
  vi.clearAllMocks();
});

describe('getMembers', () => {
  it('reads the member list of that car', async () => {
    client.get.mockResolvedValue({ data: [] });

    await getMembers(7);

    expect(client.get).toHaveBeenCalledWith('/cars/7/members');
  });

  it('returns the members as sent', async () => {
    const data = [
      { user_id: 1, label: 'brian', role: 'owner', is_you: true, created_at: '2026-07-01T10:00:00' },
      { user_id: 2, label: 'olha', role: 'editor', is_you: false, created_at: '2026-07-02T10:00:00' },
    ];
    client.get.mockResolvedValue({ data });

    await expect(getMembers(7)).resolves.toEqual(data);
  });
});

describe('createInvite', () => {
  it('posts the chosen role to the invites endpoint of that car', async () => {
    client.post.mockResolvedValue({ data: { token: 't', invite_path: '/join/t' } });

    await createInvite(7, 'editor');

    expect(client.post).toHaveBeenCalledWith('/cars/7/invites', { role: 'editor' });
  });

  it('returns the token, the path and the expiry', async () => {
    const data = { token: 'abc', invite_path: '/join/abc', expires_at: '2026-07-22T10:00:00' };
    client.post.mockResolvedValue({ data });

    await expect(createInvite(7, 'viewer')).resolves.toEqual(data);
  });
});

describe('getInvite', () => {
  it('reads the preview of that token', async () => {
    client.get.mockResolvedValue({ data: {} });

    await getInvite('abc');

    expect(client.get).toHaveBeenCalledWith('/invites/abc');
  });

  it('escapes a token that would otherwise change the path', async () => {
    client.get.mockResolvedValue({ data: {} });

    await getInvite('../cars/1');

    expect(client.get).toHaveBeenCalledWith('/invites/..%2Fcars%2F1');
  });

  it('returns the car, the role and who invited', async () => {
    const data = {
      car: { brand: 'Volkswagen', model: 'Golf', year: 2014 },
      role: 'editor',
      inviter_label: 'brian',
    };
    client.get.mockResolvedValue({ data });

    await expect(getInvite('abc')).resolves.toEqual(data);
  });
});

describe('acceptInvite', () => {
  it('posts to the accept endpoint of that token', async () => {
    client.post.mockResolvedValue({ data: { id: 3, car_id: 7, role: 'editor' } });

    await acceptInvite('abc');

    expect(client.post).toHaveBeenCalledWith('/invites/abc/accept');
  });

  it('escapes the token in the accept path too', async () => {
    client.post.mockResolvedValue({ data: {} });

    await acceptInvite('../cars/1');

    expect(client.post).toHaveBeenCalledWith('/invites/..%2Fcars%2F1/accept');
  });

  it('returns the membership', async () => {
    const data = { id: 3, car_id: 7, role: 'editor' };
    client.post.mockResolvedValue({ data });

    await expect(acceptInvite('abc')).resolves.toEqual(data);
  });
});

describe('removeMember', () => {
  it('deletes that membership', async () => {
    client.delete.mockResolvedValue({ data: null });

    await removeMember(3);

    expect(client.delete).toHaveBeenCalledWith('/members/3');
  });
});

describe('updateMemberRole', () => {
  it('patches the role of that membership', async () => {
    client.patch.mockResolvedValue({ data: { id: 3, role: 'viewer' } });

    await updateMemberRole(3, 'viewer');

    expect(client.patch).toHaveBeenCalledWith('/members/3', { role: 'viewer' });
  });

  it('returns the updated membership', async () => {
    const data = { id: 3, car_id: 7, role: 'viewer' };
    client.patch.mockResolvedValue({ data });

    await expect(updateMemberRole(3, 'viewer')).resolves.toEqual(data);
  });
});

describe('inviteUrl', () => {
  it('turns the path the server gave into a full link to copy', () => {
    expect(inviteUrl('/join/abc', 'https://kapot.example')).toBe('https://kapot.example/join/abc');
  });

  it('does not double the slash', () => {
    expect(inviteUrl('/join/abc', 'https://kapot.example/')).toBe('https://kapot.example/join/abc');
  });

  it('returns an empty string without a path', () => {
    expect(inviteUrl(null, 'https://kapot.example')).toBe('');
    expect(inviteUrl('', 'https://kapot.example')).toBe('');
  });
});
