import { describe, it, expect } from 'vitest';
import { safeNext, withNext } from './nextPath';

describe('safeNext', () => {
  it('keeps an in-app path', () => {
    expect(safeNext('/join/abc123')).toBe('/join/abc123');
    expect(safeNext('/garage')).toBe('/garage');
  });

  it('keeps the query and the hash of an in-app path', () => {
    expect(safeNext('/add?type=refuel')).toBe('/add?type=refuel');
    expect(safeNext('/logbook#top')).toBe('/logbook#top');
  });

  it('rejects an absolute URL to another site', () => {
    expect(safeNext('https://evil.example/steal')).toBe('/');
    expect(safeNext('http://evil.example')).toBe('/');
  });

  it('rejects a protocol-relative URL', () => {
    expect(safeNext('//evil.example/steal')).toBe('/');
    expect(safeNext('/\\evil.example')).toBe('/');
    expect(safeNext('/\t/evil.example')).toBe('/');
  });

  it('rejects a scheme that is not a path at all', () => {
    expect(safeNext('javascript:alert(1)')).toBe('/');
    expect(safeNext('data:text/html,<script>')).toBe('/');
  });

  it('rejects anything that is not a rooted path', () => {
    expect(safeNext('garage')).toBe('/');
    expect(safeNext('../garage')).toBe('/');
  });

  it('falls back for an empty or missing value', () => {
    expect(safeNext(null)).toBe('/');
    expect(safeNext(undefined)).toBe('/');
    expect(safeNext('')).toBe('/');
    expect(safeNext('   ')).toBe('/');
    expect(safeNext(42)).toBe('/');
  });

  it('uses the fallback it was given', () => {
    expect(safeNext(null, '/garage')).toBe('/garage');
    expect(safeNext('https://evil.example', '/garage')).toBe('/garage');
  });
});

describe('withNext', () => {
  it('carries the destination between the login and the register page', () => {
    expect(withNext('/register', '/join/abc')).toBe('/register?next=%2Fjoin%2Fabc');
  });

  it('leaves the link bare when there is nowhere to go back to', () => {
    expect(withNext('/register', '/')).toBe('/register');
    expect(withNext('/register', null)).toBe('/register');
    expect(withNext('/register', '')).toBe('/register');
  });

  it('does not carry a destination it would refuse to follow', () => {
    expect(withNext('/register', 'https://evil.example')).toBe('/register');
  });
});
