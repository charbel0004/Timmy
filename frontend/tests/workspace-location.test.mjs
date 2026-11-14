import { strict as assert } from "node:assert";
import { test } from "node:test";
import { workspaceLocation } from "../src/workspace-location.ts";

test("chat review links retain the exact snapshot and generic navigation clears it", () => {
  assert.deepEqual(workspaceLocation("#imports/validation/42"), {
    page: "imports", validationId: "42",
  });
  assert.deepEqual(workspaceLocation("#imports"), { page: "imports", validationId: undefined });
  assert.equal(workspaceLocation("#imports/validation/0").validationId, undefined);
  assert.equal(workspaceLocation("#imports/validation/42/extra").validationId, undefined);
});
