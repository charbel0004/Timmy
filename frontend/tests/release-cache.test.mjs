import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import { freshApplicationUrl } from '../src/release-cache.ts';

test('fresh app URLs bypass stale HTML while preserving the active conversation', () => {
  assert.equal(freshApplicationUrl('http://example.test/?filter=mine#assistant/abc', 123),
    'http://example.test/?filter=mine&_timmy_refresh=123#assistant/abc');
});
test('each refresh changes the cache key without changing origin', () => {
  const original = 'http://example.test/?_timmy_refresh=1#observatory';
  const fresh = new URL(freshApplicationUrl(original, 2));
  assert.equal(fresh.origin, 'http://example.test');
  assert.equal(fresh.searchParams.getAll('_timmy_refresh').length, 1);
  assert.equal(fresh.searchParams.get('_timmy_refresh'), '2');
});
