/*
 * Lokal-only WebRTC (5-bosqich).
 *
 * STUN/TURN serversiz RTCPeerConnection, faqat host candidate'lar orqali
 * ulanadi. Ulanish "connected" holatiga o'tgach va undan keyin davomiy
 * ravishda getStats() orqali tanlangan candidate juftligi tekshiriladi:
 * ikki taraf ham "host" turida va private IPv4 diapazonida bo'lishi shart,
 * aks holda ulanish darhol yopiladi.
 *
 * DIQQAT (ochiq cheklov): bu tekshiruv amaliy darajada ishonchli, lekin
 * brauzer xavfsizlik modeli tufayli OS tarmoq interfeysini to'liq
 * dasturiy nazorat qilish imkonsiz — matematik 100% kafolat emas.
 */

const LOCAL_CHECK_INTERVAL_MS = 3000;

const PRIVATE_IPV4_RANGES = [
  { base: [10, 0, 0, 0], prefix: 8 },
  { base: [172, 16, 0, 0], prefix: 12 },
  { base: [192, 168, 0, 0], prefix: 16 },
];

function ipv4ToInt(octets) {
  return ((octets[0] << 24) | (octets[1] << 16) | (octets[2] << 8) | octets[3]) >>> 0;
}

function isPrivateIPv4(ip) {
  if (typeof ip !== "string") return false;
  const parts = ip.split(".");
  if (parts.length !== 4) return false;

  const octets = parts.map(Number);
  if (octets.some((o) => !Number.isInteger(o) || o < 0 || o > 255)) return false;

  const ipInt = ipv4ToInt(octets);
  return PRIVATE_IPV4_RANGES.some(({ base, prefix }) => {
    const maskInt = prefix === 0 ? 0 : (~0 << (32 - prefix)) >>> 0;
    return (ipInt & maskInt) === (ipv4ToInt(base) & maskInt);
  });
}

/**
 * `statsReport` — RTCPeerConnection.getStats() natijasi (Map-like: forEach/get).
 * Sof funksiya — Node'da ham oddiy Map bilan test qilinadi.
 */
function evaluateStatsReport(statsReport) {
  let transportReport = null;
  statsReport.forEach((report) => {
    if (report.type === "transport") transportReport = report;
  });

  if (!transportReport || !transportReport.selectedCandidatePairId) {
    return { ok: false, reason: "Faol ulanish holati topilmadi" };
  }

  const pair = statsReport.get(transportReport.selectedCandidatePairId);
  if (!pair) {
    return { ok: false, reason: "Tanlangan candidate juftligi topilmadi" };
  }

  const local = statsReport.get(pair.localCandidateId);
  const remote = statsReport.get(pair.remoteCandidateId);
  if (!local || !remote) {
    return { ok: false, reason: "Candidate ma'lumotlari topilmadi" };
  }

  for (const candidate of [local, remote]) {
    if (candidate.candidateType !== "host") {
      return { ok: false, reason: `Lokal bo'lmagan ulanish turi: ${candidate.candidateType}` };
    }
    const ip = candidate.address || candidate.ip;
    if (!isPrivateIPv4(ip)) {
      return { ok: false, reason: `Lokal bo'lmagan IP manzil: ${ip}` };
    }
  }

  return { ok: true };
}

async function verifyConnectionIsLocalOnly(pc) {
  const statsReport = await pc.getStats();
  return evaluateStatsReport(statsReport);
}

/**
 * Bitta peer-to-peer ulanishni boshqaradi: signaling xabarlarini yuborish/
 * qabul qilish, lokal-only tekshiruvi va natijasi haqida xabar berish.
 * Fayl uzatish mantiqi (DataChannel orqali) 6-bosqichda shu klass ustiga
 * quriladi — `onLocalVerified` chaqirilgandan keyin control DataChannel
 * tayyor bo'ladi.
 */
class LocalOnlyPeer {
  constructor({ send, onLocalVerified, onRejected, onDataChannel }) {
    this.send = send;
    this.onLocalVerified = onLocalVerified;
    this.onRejected = onRejected;
    this.onDataChannel = onDataChannel;

    this.verified = false;
    this._monitorHandle = null;
    this._closed = false;

    this.pc = new RTCPeerConnection({ iceServers: [], iceTransportPolicy: "all" });

    this.pc.addEventListener("icecandidate", (event) => {
      if (event.candidate) {
        this.send({ kind: "ice", candidate: event.candidate.toJSON() });
      }
    });

    this.pc.addEventListener("connectionstatechange", () => this._handleStateChange());

    this.pc.addEventListener("datachannel", (event) => {
      this.onDataChannel?.(event.channel);
    });
  }

  createControlChannel() {
    this.controlChannel = this.pc.createDataChannel("control");
    return this.controlChannel;
  }

  async createOffer() {
    const offer = await this.pc.createOffer();
    await this.pc.setLocalDescription(offer);
    this.send({ kind: "offer", sdp: offer.sdp });
  }

  async handleRemoteMessage(payload) {
    if (payload.kind === "offer") {
      await this.pc.setRemoteDescription({ type: "offer", sdp: payload.sdp });
      const answer = await this.pc.createAnswer();
      await this.pc.setLocalDescription(answer);
      this.send({ kind: "answer", sdp: answer.sdp });
      return;
    }

    if (payload.kind === "answer") {
      await this.pc.setRemoteDescription({ type: "answer", sdp: payload.sdp });
      return;
    }

    if (payload.kind === "ice") {
      try {
        await this.pc.addIceCandidate(payload.candidate);
      } catch (err) {
        console.warn("ICE candidate qo'shib bo'lmadi:", err);
      }
    }
  }

  async _handleStateChange() {
    if (this._closed) return;

    if (this.pc.connectionState === "connected") {
      await this._verifyAndStartMonitoring();
    } else if (["failed", "disconnected", "closed"].includes(this.pc.connectionState)) {
      this._stopMonitoring();
    }
  }

  async _verifyAndStartMonitoring() {
    const result = await verifyConnectionIsLocalOnly(this.pc);
    if (!result.ok) {
      this._reject(result.reason);
      return;
    }

    if (!this.verified) {
      this.verified = true;
      this.onLocalVerified?.();
    }

    this._stopMonitoring();
    this._monitorHandle = setInterval(async () => {
      if (this._closed) return;
      const check = await verifyConnectionIsLocalOnly(this.pc);
      if (!check.ok) {
        this._reject(check.reason);
      }
    }, LOCAL_CHECK_INTERVAL_MS);
  }

  _reject(reason) {
    this._stopMonitoring();
    this.onRejected?.(reason);
    this.close();
  }

  _stopMonitoring() {
    if (this._monitorHandle) {
      clearInterval(this._monitorHandle);
      this._monitorHandle = null;
    }
  }

  close() {
    this._closed = true;
    this._stopMonitoring();
    this.pc.close();
  }
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { isPrivateIPv4, evaluateStatsReport, verifyConnectionIsLocalOnly, LocalOnlyPeer };
}
