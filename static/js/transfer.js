/*
 * Fayl almashish (6-bosqich).
 *
 * Allaqachon lokal-only tasdiqlangan DataChannel ("control", webrtc.js)
 * ustiga quriladi. Server bu bosqichda umuman ishtirok etmaydi — fayl
 * baytlari faqat DataChannel orqali, to'g'ridan-to'g'ri ikki qurilma
 * o'rtasida oqadi.
 *
 * Protokol (channel orqali aralash matn/binary xabarlar):
 *   -> {"type":"meta", name, size, mimeType, totalChunks}   (matn, JSON)
 *   -> <ArrayBuffer> ... <ArrayBuffer>                        (bo'laklar)
 *   -> {"type":"done", totalChunks, checksum}                 (matn, JSON)
 *   -> {"type":"cancel"}                                       (matn, JSON)
 *
 * Yaxlitlik SHA-256 o'rniga CRC32 bilan tekshiriladi: Web Crypto'da
 * oqimli (incremental) digest API yo'q, SHA-256 esa butun faylni xotiraga
 * ikkinchi marta yuklashni talab qiladi — CRC32 bo'lak-bo'lak hisoblanadi
 * va katta fayllar uchun ham xotira sarflamaydi.
 */

const DEFAULT_CHUNK_SIZE = 64 * 1024;
const DEFAULT_HIGH_WATERMARK = 1024 * 1024;
const DEFAULT_LOW_WATERMARK = 256 * 1024;

const CRC32_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) {
      c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    }
    table[n] = c;
  }
  return table;
})();

function crc32Start() {
  return 0xffffffff;
}

function crc32Update(crc, arrayBuffer) {
  const bytes = new Uint8Array(arrayBuffer);
  for (let i = 0; i < bytes.length; i++) {
    crc = CRC32_TABLE[(crc ^ bytes[i]) & 0xff] ^ (crc >>> 8);
  }
  return crc;
}

function crc32Finalize(crc) {
  return (crc ^ 0xffffffff) >>> 0;
}

/**
 * Bitta DataChannel ustida bitta faylni yuborish/qabul qilishni boshqaradi.
 * Bir vaqtda faqat bitta faol uzatish qo'llab-quvvatlanadi (MVP).
 */
class FileTransferSession {
  constructor(
    channel,
    {
      chunkSize = DEFAULT_CHUNK_SIZE,
      highWaterMark = DEFAULT_HIGH_WATERMARK,
      lowWaterMark = DEFAULT_LOW_WATERMARK,
      onProgress,
      onReceived,
      onError,
      onCancelled,
    } = {}
  ) {
    this.channel = channel;
    this.chunkSize = chunkSize;
    this.highWaterMark = highWaterMark;
    this.onProgress = onProgress;
    this.onReceived = onReceived;
    this.onError = onError;
    this.onCancelled = onCancelled;

    this.sending = false;
    this._cancelled = false;
    this._incoming = null;

    this.channel.binaryType = "arraybuffer";
    this.channel.bufferedAmountLowThreshold = lowWaterMark;
    this.channel.addEventListener("message", (event) => this._handleMessage(event));
  }

  async sendFile(file) {
    if (this.sending) {
      throw new Error("Allaqachon fayl yuborilmoqda");
    }

    this.sending = true;
    this._cancelled = false;

    try {
      const totalChunks = Math.max(1, Math.ceil(file.size / this.chunkSize));
      this._sendControl({
        type: "meta",
        name: file.name,
        size: file.size,
        mimeType: file.type || "application/octet-stream",
        totalChunks,
      });

      let crc = crc32Start();
      let offset = 0;
      let sentChunks = 0;

      while (offset < file.size) {
        if (this._cancelled) return;

        const slice = file.slice(offset, offset + this.chunkSize);
        const buffer = await slice.arrayBuffer();
        crc = crc32Update(crc, buffer);

        await this._waitForBufferSpace();
        if (this._cancelled) return;

        this.channel.send(buffer);
        offset += buffer.byteLength;
        sentChunks += 1;

        this.onProgress?.({ direction: "send", sentBytes: offset, totalBytes: file.size });
      }

      this._sendControl({ type: "done", totalChunks: sentChunks, checksum: crc32Finalize(crc) });
    } finally {
      this.sending = false;
    }
  }

  cancel() {
    if (this._cancelled) return;
    this._cancelled = true;
    this._sendControl({ type: "cancel" });
    this._resetIncoming();
    this.onCancelled?.();
  }

  _waitForBufferSpace() {
    if (this.channel.bufferedAmount <= this.highWaterMark) {
      return Promise.resolve();
    }
    return new Promise((resolve) => {
      const handleLow = () => {
        this.channel.removeEventListener("bufferedamountlow", handleLow);
        resolve();
      };
      this.channel.addEventListener("bufferedamountlow", handleLow);
    });
  }

  _sendControl(obj) {
    this.channel.send(JSON.stringify(obj));
  }

  _handleMessage(event) {
    if (typeof event.data === "string") {
      this._handleControlMessage(JSON.parse(event.data));
      return;
    }
    this._handleChunk(event.data);
  }

  _handleControlMessage(message) {
    if (message.type === "meta") {
      this._incoming = {
        name: message.name,
        size: message.size,
        mimeType: message.mimeType,
        totalChunks: message.totalChunks,
        chunks: [],
        receivedBytes: 0,
        crc: crc32Start(),
      };
      return;
    }

    if (message.type === "done") {
      this._finishIncoming(message);
      return;
    }

    if (message.type === "cancel") {
      this._resetIncoming();
      this.onCancelled?.();
    }
  }

  _handleChunk(buffer) {
    const incoming = this._incoming;
    if (!incoming) return; // "meta" kelmay turib chunk kutilmagan holat — e'tiborsiz

    incoming.chunks.push(buffer);
    incoming.receivedBytes += buffer.byteLength;
    incoming.crc = crc32Update(incoming.crc, buffer);

    this.onProgress?.({
      direction: "receive",
      receivedBytes: incoming.receivedBytes,
      totalBytes: incoming.size,
    });
  }

  _finishIncoming(doneMessage) {
    const incoming = this._incoming;
    if (!incoming) return;

    const checksum = crc32Finalize(incoming.crc);
    if (incoming.chunks.length !== doneMessage.totalChunks || checksum !== doneMessage.checksum) {
      this.onError?.("Fayl yaxlitligi buzilgan — checksum mos kelmadi");
      this._resetIncoming();
      return;
    }

    const blob = new Blob(incoming.chunks, { type: incoming.mimeType });
    this.onReceived?.({ name: incoming.name, size: incoming.size, blob });
    this._resetIncoming();
  }

  _resetIncoming() {
    this._incoming = null;
  }
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { crc32Start, crc32Update, crc32Finalize, FileTransferSession };
}
