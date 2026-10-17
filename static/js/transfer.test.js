const assert = require("node:assert/strict");
const test = require("node:test");

const { crc32Start, crc32Update, crc32Finalize, FileTransferSession } = require("./transfer.js");

test("CRC32: standart tekshiruv vektori ('123456789' -> 0xCBF43926)", () => {
  const bytes = new TextEncoder().encode("123456789");
  const crc = crc32Update(crc32Start(), bytes.buffer);
  assert.equal(crc32Finalize(crc), 0xcbf43926);
});

test("CRC32: bo'sh kirish uchun 0", () => {
  assert.equal(crc32Finalize(crc32Start()), 0);
});

/** Ikki tomonlama fake DataChannel: test uchun haqiqiy WebRTC shart emas. */
class FakeChannel {
  constructor() {
    this._listeners = {};
    this.bufferedAmount = 0;
    this.bufferedAmountLowThreshold = 0;
    this.binaryType = "blob";
    this.peer = null;
  }

  addEventListener(type, handler) {
    (this._listeners[type] ??= []).push(handler);
  }

  removeEventListener(type, handler) {
    this._listeners[type] = (this._listeners[type] || []).filter((h) => h !== handler);
  }

  dispatch(type, event) {
    for (const handler of this._listeners[type] || []) handler(event);
  }

  send(data) {
    queueMicrotask(() => this.peer.dispatch("message", { data }));
  }
}

function makeChannelPair() {
  const a = new FakeChannel();
  const b = new FakeChannel();
  a.peer = b;
  b.peer = a;
  return [a, b];
}

function waitFor(predicate, timeoutMs = 2000) {
  return new Promise((resolve, reject) => {
    const start = Date.now();
    const tick = () => {
      if (predicate()) return resolve();
      if (Date.now() - start > timeoutMs) return reject(new Error("timeout"));
      setTimeout(tick, 5);
    };
    tick();
  });
}

test("FileTransferSession: to'liq fayl to'g'ri uzatiladi va checksum tasdiqlanadi", async () => {
  const [channelA, channelB] = makeChannelPair();

  const pattern = Buffer.from("Endi Oson - lokal fayl uzatish! ");
  const original = Buffer.concat(Array.from({ length: 500 }, () => pattern)); // ~16.5KB
  const sourceBlob = new Blob([original], { type: "text/plain" });

  let received = null;
  const sender = new FileTransferSession(channelA, { chunkSize: 777 });
  const receiver = new FileTransferSession(channelB, {
    chunkSize: 777,
    onReceived: (file) => {
      received = file;
    },
  });

  await sender.sendFile({
    name: "test.txt",
    size: sourceBlob.size,
    type: "text/plain",
    slice: (start, end) => sourceBlob.slice(start, end),
  });

  await waitFor(() => received !== null);

  const receivedBuffer = Buffer.from(await received.blob.arrayBuffer());
  assert.equal(received.name, "test.txt");
  assert.equal(received.size, original.length);
  assert.ok(receivedBuffer.equals(original));
  assert.equal(sender.sending, false);

  void receiver; // faqat message handler o'rnatish uchun ushlab turiladi
});

test("FileTransferSession: checksum mos kelmasa onError chaqiriladi", async () => {
  const [channelA, channelB] = makeChannelPair();

  let errorMessage = null;
  const sender = new FileTransferSession(channelA, { chunkSize: 16 });
  new FileTransferSession(channelB, {
    chunkSize: 16,
    onError: (err) => {
      errorMessage = err;
    },
  });

  const original = Buffer.from("buzilgan checksum sinovi uchun matn");
  const sourceBlob = new Blob([original]);

  // "done" yuborilishidan oldin checksum'ni buzish uchun channel.send'ni
  // vaqtincha ushlaymiz: oxirgi matn xabarini (done) qo'lda o'zgartiramiz.
  const originalSend = channelA.send.bind(channelA);
  channelA.send = (data) => {
    if (typeof data === "string") {
      const msg = JSON.parse(data);
      if (msg.type === "done") {
        msg.checksum = msg.checksum ^ 0xff; // ataylab buzamiz
        originalSend(JSON.stringify(msg));
        return;
      }
    }
    originalSend(data);
  };

  await sender.sendFile({
    name: "broken.txt",
    size: sourceBlob.size,
    type: "text/plain",
    slice: (start, end) => sourceBlob.slice(start, end),
  });

  await waitFor(() => errorMessage !== null);
  assert.match(errorMessage, /checksum/);
});

test("FileTransferSession: cancel() ikki tarafga ham xabar beradi", async () => {
  const [channelA, channelB] = makeChannelPair();

  let cancelledOnB = false;
  const sender = new FileTransferSession(channelA, { chunkSize: 16 });
  new FileTransferSession(channelB, {
    chunkSize: 16,
    onCancelled: () => {
      cancelledOnB = true;
    },
  });

  sender.cancel();

  await waitFor(() => cancelledOnB === true);
  assert.equal(cancelledOnB, true);
});

test("FileTransferSession: _waitForBufferSpace faqat 'bufferedamountlow' kelganda yechiladi", async () => {
  const [channelA] = makeChannelPair();
  channelA.bufferedAmount = 10 * 1024 * 1024; // yuqori chegaradan katta

  const session = new FileTransferSession(channelA, { highWaterMark: 1024 });

  let resolved = false;
  const promise = session._waitForBufferSpace().then(() => {
    resolved = true;
  });

  await new Promise((resolve) => setTimeout(resolve, 20));
  assert.equal(resolved, false, "bufferedamountlow hali kelmagan bo'lsa yechilmasligi kerak");

  channelA.dispatch("bufferedamountlow", {});
  await promise;
  assert.equal(resolved, true);
});
