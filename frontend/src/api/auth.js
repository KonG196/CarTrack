import client from './client';

export async function register(email, password) {
  const { data } = await client.post('/auth/register', { email, password });
  return data;
}

export async function login(email, password) {
  const body = new URLSearchParams();
  body.append('username', email);
  body.append('password', password);
  const { data } = await client.post('/auth/token', body, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  });
  return data; // {access_token, token_type}
}

export async function getMe() {
  const { data } = await client.get('/auth/me');
  return data;
}

export async function updateMe(displayName) {
  const { data } = await client.patch('/auth/me', { display_name: displayName });
  return data;
}

// Any subset of the mutable profile fields (display_name, digest_enabled,
// reminders_enabled). PATCH only sends what is passed, so an omitted field is
// left untouched.
export async function updateProfile(payload) {
  const { data } = await client.patch('/auth/me', payload);
  return data;
}

export async function requestPasswordReset(email, channel) {
  const { data } = await client.post('/auth/reset/request', { email, channel });
  return data;
}

export async function confirmPasswordReset(email, code, newPassword) {
  const { data } = await client.post('/auth/reset/confirm', {
    email,
    code,
    new_password: newPassword,
  });
  return data;
}

export async function confirmEmail(email, code) {
  const { data } = await client.post('/auth/verify/confirm', { email, code });
  return data;
}

export async function resendVerification(email) {
  const { data } = await client.post('/auth/verify/resend', { email });
  return data;
}

export async function changePassword(currentPassword, newPassword) {
  // Returns a fresh {access_token, refresh_token}: the change revokes other
  // sessions, so this one is re-issued to avoid logging the caller out.
  const { data } = await client.post('/auth/password', {
    current_password: currentPassword,
    new_password: newPassword,
  });
  return data;
}

// Starts a move; nothing changes until the code sent to the new address comes
// back through confirmEmailChange. The old address keeps working meanwhile.
export async function requestEmailChange(newEmail, password) {
  const { data } = await client.post('/auth/email', {
    new_email: newEmail,
    password,
  });
  return data; // {pending_email}
}

export async function confirmEmailChange(code) {
  const { data } = await client.post('/auth/email/confirm', { code });
  return data; // UserOut
}

// Irreversible: deletes the account, every owned car's history, and the files
// on disk. The current password is required — a live session is not enough. A
// DELETE carries its body under `data` in axios.
export async function deleteAccount(password) {
  await client.delete('/auth/me', { data: { password } });
}
