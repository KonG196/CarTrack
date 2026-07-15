import { describe, it, expect, vi, beforeEach } from 'vitest';
import client from './client';
import {
  getDocuments,
  uploadDocument,
  getDocumentBlob,
  deleteDocument,
  DOCUMENT_KINDS,
  documentKindLabel,
  expiresInDays,
} from './documents';

vi.mock('./client', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

beforeEach(() => {
  vi.clearAllMocks();
});

const file = () => new File(['%PDF-1.4'], 'policy.pdf', { type: 'application/pdf' });

describe('getDocuments', () => {
  it('reads the documents of that car', async () => {
    client.get.mockResolvedValue({ data: [] });

    await getDocuments(7);

    expect(client.get).toHaveBeenCalledWith('/cars/7/documents');
  });
});

describe('uploadDocument', () => {
  it('posts the file, kind and title as multipart form data', async () => {
    client.post.mockResolvedValue({ data: { id: 1 } });

    await uploadDocument(7, { file: file(), kind: 'insurance', title: 'ОСЦПВ 2026' });

    const [url, formData] = client.post.mock.calls[0];
    expect(url).toBe('/cars/7/documents');
    expect(formData).toBeInstanceOf(FormData);
    expect(formData.get('kind')).toBe('insurance');
    expect(formData.get('title')).toBe('ОСЦПВ 2026');
    expect(formData.get('file')).toBeInstanceOf(File);
  });

  it('sends the expiry when there is one', async () => {
    client.post.mockResolvedValue({ data: { id: 1 } });

    await uploadDocument(7, {
      file: file(),
      kind: 'insurance',
      title: 'ОСЦПВ 2026',
      expiresAt: '2027-03-01',
    });

    expect(client.post.mock.calls[0][1].get('expires_at')).toBe('2027-03-01');
  });

  it('omits the expiry rather than sending an empty one', async () => {
    // An empty string is not a date: the field must be absent, or the API
    // rejects the whole upload with a 422.
    client.post.mockResolvedValue({ data: { id: 1 } });

    await uploadDocument(7, { file: file(), kind: 'other', title: 'Чек', expiresAt: '' });

    expect(client.post.mock.calls[0][1].has('expires_at')).toBe(false);
  });

  it('returns the created document with its linked interval', async () => {
    const data = { id: 1, kind: 'insurance', linked_interval_id: 9 };
    client.post.mockResolvedValue({ data });

    await expect(
      uploadDocument(7, { file: file(), kind: 'insurance', title: 'ОСЦПВ' })
    ).resolves.toEqual(data);
  });
});

describe('getDocumentBlob', () => {
  it('reads the file as a blob, since an href cannot carry the token', async () => {
    client.get.mockResolvedValue({ data: new Blob() });

    await getDocumentBlob(3);

    expect(client.get).toHaveBeenCalledWith('/documents/3', { responseType: 'blob' });
  });
});

describe('deleteDocument', () => {
  it('deletes the document by its own id', async () => {
    client.delete.mockResolvedValue({});

    await deleteDocument(3);

    expect(client.delete).toHaveBeenCalledWith('/documents/3');
  });
});

describe('documentKindLabel', () => {
  it('names each backend kind in Ukrainian', () => {
    expect(DOCUMENT_KINDS.map((k) => k.value)).toEqual([
      'tech_passport',
      'insurance',
      'inspection',
      'invoice',
      'other',
    ]);
    expect(documentKindLabel('insurance')).toBe('Страховка');
    expect(documentKindLabel('tech_passport')).toBe('Техпаспорт');
  });

  it('falls back to the raw kind it does not know', () => {
    expect(documentKindLabel('something_new')).toBe('something_new');
  });
});

describe('expiresInDays', () => {
  const today = new Date(2026, 6, 15);

  it('counts whole days to the expiry', () => {
    expect(expiresInDays('2026-07-25', today)).toBe(10);
  });

  it('is zero on the day it expires', () => {
    expect(expiresInDays('2026-07-15', today)).toBe(0);
  });

  it('goes negative once it has lapsed', () => {
    expect(expiresInDays('2026-07-05', today)).toBe(-10);
  });

  it('has nothing to say about a document with no expiry', () => {
    expect(expiresInDays(null, today)).toBeNull();
    expect(expiresInDays('', today)).toBeNull();
  });
});
