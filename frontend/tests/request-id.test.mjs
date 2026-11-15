import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import { createRequestId } from '../src/request-id.ts';

test('HTTP browsers without randomUUID still generate valid UUIDv4 request IDs', () => {
  const id = createRequestId({ getRandomValues: bytes => { bytes.fill(255); return bytes; } });
  assert.match(id, /^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/);
  assert.equal(id, 'ffffffff-ffff-4fff-bfff-ffffffffffff');
});
test('secure contexts use the native UUID implementation', () => {
  assert.equal(createRequestId({ randomUUID: () => 'native-id', getRandomValues: () => { throw Error('Unexpected fallback'); } }), 'native-id');
});
test('unsupported browser randomness fails explicitly before the sending latch', () => {
  assert.throws(() => createRequestId({}), /Browser randomness unavailable/);
});
