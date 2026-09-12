import { after, before, beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { assertFails, assertSucceeds, initializeTestEnvironment } from "@firebase/rules-unit-testing";

const HERE = dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = resolve(HERE, "../..");
const PROJECT_ID = "demo-aria-phase12-3";
const DATABASE_URL = `http://127.0.0.1:9000?ns=${PROJECT_ID}`;
const SYNC_UID = "aria-phase12-3-sync";
const PREDICTION_PATH = "aria/schema_version_1/predictions/prediction_emulator1203";
const ACCEPTANCE_PATH = "aria/schema_version_1/acceptance/acceptance_emulator1203";
let environment;

function availablePrediction() {
  return {
    schema_version: 1,
    prediction_id: "prediction_emulator1203",
    emitted_at_sgt: "2026-08-24T20:00:00.000+08:00",
    uploaded_at_sgt: "2026-08-24T20:00:01.000+08:00",
    zone: "A",
    model_version: "zone-a-camera-only-rf-v1",
    preprocessing_version: "zone-a-phase12.1-single-track-window-v1",
    prediction_available: true,
    predicted_activity: "Serving/Processing",
    confidence: 0.72,
    availability: {
      camera_available: true,
      pose_available: true,
      esp_a1_available: true,
      esp_a2_available: true,
    },
  };
}

function unavailablePrediction() {
  const value = availablePrediction();
  value.prediction_available = false;
  delete value.predicted_activity;
  delete value.confidence;
  value.unavailable_reason = "missing_camera_track";
  return value;
}

function databaseFor(context) {
  return context.database(DATABASE_URL);
}

before(async () => {
  const rules = await readFile( resolve(PROJECT_ROOT, "config/firebase_realtime_database.rules.json"), "utf8");
  environment = await initializeTestEnvironment({
    projectId: PROJECT_ID,
    database: {
      host: "127.0.0.1",
      port: 9000,
      rules,
    },
  });
});

beforeEach(async () => {
  await environment.clearDatabase();
});

after(async () => {
  if (environment) {
    await environment.cleanup();
  }
});

test("sync identity can create and read one valid available prediction", async () => {
  const database = databaseFor(environment.authenticatedContext(SYNC_UID));
  const reference = database.ref(PREDICTION_PATH);
  const payload = availablePrediction();
  await assertSucceeds(reference.set(payload));
  const snapshot = await assertSucceeds(reference.get());
  assert.deepEqual(snapshot.val(), payload);
});

test("sync identity can create one valid unavailable prediction", async () => {
  const database = databaseFor(environment.authenticatedContext(SYNC_UID));
  await assertSucceeds(database.ref(PREDICTION_PATH).set(unavailablePrediction()));
});

test("unauthenticated and wrong identities cannot read or write predictions", async () => {
  const anonymous = databaseFor(environment.unauthenticatedContext());
  const wrongIdentity = databaseFor(environment.authenticatedContext("not-aria-sync"));
  await assertFails(anonymous.ref(PREDICTION_PATH).set(availablePrediction()));
  await assertFails(wrongIdentity.ref(PREDICTION_PATH).set(availablePrediction()));
  await assertFails(anonymous.ref(PREDICTION_PATH).get());
  await assertFails(wrongIdentity.ref(PREDICTION_PATH).get());
});

test("prediction records are immutable, including identical client retries", async () => {
  const database = databaseFor(environment.authenticatedContext(SYNC_UID));
  const reference = database.ref(PREDICTION_PATH);
  const payload = availablePrediction();
  await assertSucceeds(reference.set(payload));
  await assertFails(reference.set(payload));
  await assertFails(reference.set({ ...payload, confidence: 0.01 }));
  assert.deepEqual((await assertSucceeds(reference.get())).val(), payload);
});

test("rules reject identifying, media and arbitrary extra fields", async () => {
  const database = databaseFor(environment.authenticatedContext(SYNC_UID));
  const forbidden = [
    ["session_id", "zone_a_20260824T200000SGT_synthetic1203"],
    ["window_id", "zone_a_1_2"],
    ["local_track_id", 1],
    ["participant_id", "forbidden"],
    ["feature_vector", [0.1]],
    ["raw_audio", "forbidden"],
    ["raw_video", "forbidden"],
  ];
  for (const [field, value] of forbidden) {
    await assertFails(
      database.ref(PREDICTION_PATH).set({
        ...availablePrediction(),
        [field]: value,
      }),
    );
  }
});

test("rules enforce available and unavailable conditional fields", async () => {
  const database = databaseFor(environment.authenticatedContext(SYNC_UID));
  const missingConfidence = availablePrediction();
  delete missingConfidence.confidence;
  const nullLikeAvailable = { ...unavailablePrediction(), predicted_activity: "Serving/Processing"};
  const missingReason = unavailablePrediction();
  delete missingReason.unavailable_reason;
  await assertFails(database.ref(PREDICTION_PATH).set(missingConfidence));
  await assertFails(database.ref(PREDICTION_PATH).set(nullLikeAvailable));
  await assertFails(database.ref(PREDICTION_PATH).set(missingReason));
});

test("rules enforce prediction ID, versions, activity and confidence", async () => {
  const database = databaseFor(environment.authenticatedContext(SYNC_UID));
  const invalidValues = [
    ["prediction_id", "wrong"],
    ["zone", "B"],
    ["model_version", "changed-model"],
    ["preprocessing_version", "changed-preprocessing"],
    ["predicted_activity", "Station Manager"],
    ["confidence", 1.1],
  ];
  for (const [field, value] of invalidValues) {
    await assertFails(
      database.ref(PREDICTION_PATH).set({
        ...availablePrediction(),
        [field]: value,
      }),
    );
  }
});

test("only synthetic acceptance evidence is writable and immediately deletable", async () => {
  const database = databaseFor(environment.authenticatedContext(SYNC_UID));
  const reference = database.ref(ACCEPTANCE_PATH);
  const evidence = {
    schema_version: 1,
    input_scope: "synthetic",
    participant_data_used: false,
    created_at_sgt: "2026-08-24T20:05:00.000+08:00",
  };
  await assertSucceeds(reference.set(evidence));
  await assertSucceeds(reference.remove());
  assert.equal((await assertSucceeds(reference.get())).exists(), false);
});

test("acceptance path rejects participant, non-synthetic and extra data", async () => {
  const database = databaseFor(environment.authenticatedContext(SYNC_UID));
  const reference = database.ref(ACCEPTANCE_PATH);
  const evidence = {
    schema_version: 1,
    input_scope: "synthetic",
    participant_data_used: false,
    created_at_sgt: "2026-08-24T20:05:00.000+08:00",
  };
  await assertFails(reference.set({ ...evidence, input_scope: "participant" }));
  await assertFails(reference.set({ ...evidence, participant_data_used: true }));
  await assertFails(reference.set({ ...evidence, participant_id: "forbidden" }));
});

test("sync identity cannot write outside the versioned contract paths", async () => {
  const database = databaseFor(environment.authenticatedContext(SYNC_UID));
  await assertFails(database.ref("unversioned/predictions/test").set({ safe: false }));
  await assertFails(database.ref("aria/schema_version_2/test").set({ safe: false }));
});