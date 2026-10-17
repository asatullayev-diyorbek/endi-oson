const assert = require("node:assert/strict");
const test = require("node:test");

const { isPrivateIPv4, evaluateStatsReport } = require("./webrtc.js");

test("isPrivateIPv4: 10.x/172.16-31.x/192.168.x true deb topadi", () => {
  assert.equal(isPrivateIPv4("10.0.0.5"), true);
  assert.equal(isPrivateIPv4("172.16.0.1"), true);
  assert.equal(isPrivateIPv4("172.31.255.255"), true);
  assert.equal(isPrivateIPv4("192.168.1.42"), true);
});

test("isPrivateIPv4: public va noto'g'ri IP'larni rad etadi", () => {
  assert.equal(isPrivateIPv4("8.8.8.8"), false);
  assert.equal(isPrivateIPv4("172.32.0.1"), false); // 172.16-31 dan tashqarida
  assert.equal(isPrivateIPv4("172.15.255.255"), false);
  assert.equal(isPrivateIPv4("1.2.3.4.5"), false);
  assert.equal(isPrivateIPv4("not-an-ip"), false);
  assert.equal(isPrivateIPv4(undefined), false);
  assert.equal(isPrivateIPv4("::1"), false); // IPv6 — bosqich 5 faqat IPv4'ni qabul qiladi
});

function buildStatsReport({ transport, pair, local, remote }) {
  const map = new Map();
  map.set("transport-1", { type: "transport", selectedCandidatePairId: transport ? "pair-1" : undefined });
  if (pair) map.set("pair-1", pair);
  if (local) map.set("local-1", local);
  if (remote) map.set("remote-1", remote);
  return map;
}

test("evaluateStatsReport: ikki tarafi ham host+private bo'lsa ok=true", () => {
  const report = buildStatsReport({
    transport: true,
    pair: { localCandidateId: "local-1", remoteCandidateId: "remote-1" },
    local: { candidateType: "host", address: "192.168.1.10" },
    remote: { candidateType: "host", address: "192.168.1.11" },
  });
  assert.deepEqual(evaluateStatsReport(report), { ok: true });
});

test("evaluateStatsReport: legacy 'ip' maydoni bilan ham ishlaydi", () => {
  const report = buildStatsReport({
    transport: true,
    pair: { localCandidateId: "local-1", remoteCandidateId: "remote-1" },
    local: { candidateType: "host", ip: "10.0.0.5" },
    remote: { candidateType: "host", ip: "10.0.0.6" },
  });
  assert.deepEqual(evaluateStatsReport(report), { ok: true });
});

test("evaluateStatsReport: relay candidate turini rad etadi", () => {
  const report = buildStatsReport({
    transport: true,
    pair: { localCandidateId: "local-1", remoteCandidateId: "remote-1" },
    local: { candidateType: "host", address: "192.168.1.10" },
    remote: { candidateType: "relay", address: "203.0.113.5" },
  });
  const result = evaluateStatsReport(report);
  assert.equal(result.ok, false);
  assert.match(result.reason, /Lokal bo'lmagan ulanish turi/);
});

test("evaluateStatsReport: public IP'li host candidate'ni rad etadi", () => {
  const report = buildStatsReport({
    transport: true,
    pair: { localCandidateId: "local-1", remoteCandidateId: "remote-1" },
    local: { candidateType: "host", address: "192.168.1.10" },
    remote: { candidateType: "host", address: "203.0.113.5" },
  });
  const result = evaluateStatsReport(report);
  assert.equal(result.ok, false);
  assert.match(result.reason, /Lokal bo'lmagan IP manzil/);
});

test("evaluateStatsReport: transport/pair topilmasa rad etadi", () => {
  assert.equal(evaluateStatsReport(buildStatsReport({})).ok, false);
  assert.equal(
    evaluateStatsReport(buildStatsReport({ transport: true })).ok,
    false
  );
});
