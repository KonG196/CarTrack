import { describe, it, expect } from 'vitest';
import { exportFilename, csvFilename, summarizeImport } from './backup';

describe('exportFilename', () => {
  it('builds the filename from a date as YYYYMMDD', () => {
    expect(exportFilename(new Date(2026, 6, 15))).toBe('kapot-tracker-export-20260715.json');
  });

  it('zero-pads month and day', () => {
    expect(exportFilename(new Date(2026, 0, 3))).toBe('kapot-tracker-export-20260103.json');
  });

  it('matches the backend Content-Disposition pattern', () => {
    expect(exportFilename()).toMatch(/^kapot-tracker-export-\d{8}\.json$/);
  });
});

describe('csvFilename', () => {
  it('builds the filename from a numeric car id', () => {
    expect(csvFilename(7)).toBe('kapot-tracker-logs-7.csv');
  });

  it('builds the filename from a string car id', () => {
    expect(csvFilename('42')).toBe('kapot-tracker-logs-42.csv');
  });
});

describe('summarizeImport', () => {
  it('counts cars, logs and intervals across the tree', () => {
    const data = {
      schema_version: 1,
      exported_at: '2026-07-15T10:00:00Z',
      cars: [
        { brand: 'Skoda', model: 'Octavia', logs: [{}, {}], intervals: [{}] },
        { brand: 'VW', model: 'Golf', logs: [{}], intervals: [] },
      ],
    };
    expect(summarizeImport(data)).toEqual({ cars: 2, logs: 3, intervals: 1 });
  });

  it('counts an empty export as zeros', () => {
    expect(summarizeImport({ schema_version: 1, cars: [] })).toEqual({
      cars: 0,
      logs: 0,
      intervals: 0,
    });
  });

  it('tolerates cars without logs/intervals arrays', () => {
    expect(summarizeImport({ schema_version: 1, cars: [{ brand: 'Skoda', model: 'Fabia' }] })).toEqual({
      cars: 1,
      logs: 0,
      intervals: 0,
    });
  });

  it('rejects non-object payloads', () => {
    expect(() => summarizeImport(null)).toThrow('Файл не схожий на експорт Kapot Tracker');
    expect(() => summarizeImport([1, 2])).toThrow('Файл не схожий на експорт Kapot Tracker');
    expect(() => summarizeImport('text')).toThrow('Файл не схожий на експорт Kapot Tracker');
  });

  it('accepts the current v2 export', () => {
    expect(
      summarizeImport({ schema_version: 2, cars: [{ brand: 'VW', model: 'Golf', logs: [{}] }] })
    ).toEqual({ cars: 1, logs: 1, intervals: 0 });
  });

  it('rejects an unsupported schema_version', () => {
    expect(() => summarizeImport({ schema_version: 3, cars: [] })).toThrow(
      'Непідтримувана версія експорту'
    );
    expect(() => summarizeImport({ cars: [] })).toThrow('Непідтримувана версія експорту');
  });

  it('rejects a payload without a cars array', () => {
    expect(() => summarizeImport({ schema_version: 1 })).toThrow(
      'Файл не схожий на експорт Kapot Tracker'
    );
    expect(() => summarizeImport({ schema_version: 1, cars: {} })).toThrow(
      'Файл не схожий на експорт Kapot Tracker'
    );
  });

  it('rejects malformed car entries', () => {
    expect(() => summarizeImport({ schema_version: 1, cars: [null] })).toThrow(
      'Файл не схожий на експорт Kapot Tracker'
    );
    expect(() => summarizeImport({ schema_version: 1, cars: [{ logs: 5 }] })).toThrow(
      'Файл не схожий на експорт Kapot Tracker'
    );
    expect(() => summarizeImport({ schema_version: 1, cars: [{ intervals: 'x' }] })).toThrow(
      'Файл не схожий на експорт Kapot Tracker'
    );
  });
});
