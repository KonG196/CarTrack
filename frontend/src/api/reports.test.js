import { describe, it, expect } from 'vitest';
import { reportFilename } from './reports';

describe('reportFilename', () => {
  it('builds the filename from a numeric car id', () => {
    expect(reportFilename(7)).toBe('kapot-tracker-report-7.pdf');
  });

  it('builds the filename from a string car id', () => {
    expect(reportFilename('42')).toBe('kapot-tracker-report-42.pdf');
  });

  it('matches the backend Content-Disposition pattern', () => {
    expect(reportFilename(123)).toMatch(/^kapot-tracker-report-.+\.pdf$/);
  });
});
