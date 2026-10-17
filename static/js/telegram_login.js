(() => {
  const POLL_INTERVAL_MS = 2000;
  const POLL_TIMEOUT_MS = 5 * 60 * 1000; // token TTL bilan bir xil — 5 daqiqa

  const button = document.getElementById("telegram-login-btn");
  const statusEl = document.getElementById("status");

  function getCookie(name) {
    const match = document.cookie.match(new RegExp(`(^|; )${name}=([^;]+)`));
    return match ? decodeURIComponent(match[2]) : null;
  }

  async function postJSON(url) {
    const response = await fetch(url, {
      method: "POST",
      headers: { "X-CSRFToken": getCookie("csrftoken") },
      credentials: "same-origin",
    });
    return { ok: response.ok, data: await response.json() };
  }

  async function getJSON(url) {
    const response = await fetch(url, { credentials: "same-origin" });
    return { ok: response.ok, data: await response.json() };
  }

  function setStatus(text, className) {
    statusEl.textContent = text;
    statusEl.className = className || "";
  }

  async function pollUntilConfirmed(attemptId, deadline) {
    if (Date.now() > deadline) {
      setStatus("Vaqt tugadi. Qaytadan urinib ko'ring.", "status-error");
      button.disabled = false;
      return;
    }

    const { ok, data } = await getJSON(`/auth/telegram/poll/${attemptId}/`);
    if (!ok) {
      setStatus("Xatolik yuz berdi. Qaytadan urinib ko'ring.", "status-error");
      button.disabled = false;
      return;
    }

    if (data.status === "confirmed") {
      setStatus("Tasdiqlandi! Kirilmoqda...", "status-confirmed");
      const result = await postJSON(`/auth/telegram/complete/${attemptId}/`);
      if (result.ok) {
        window.location.href = "/";
      } else {
        setStatus(result.data.error || "Kirishda xatolik.", "status-error");
        button.disabled = false;
      }
      return;
    }

    if (data.status === "expired") {
      setStatus("Token muddati tugadi. Qaytadan urinib ko'ring.", "status-error");
      button.disabled = false;
      return;
    }

    setTimeout(() => pollUntilConfirmed(attemptId, deadline), POLL_INTERVAL_MS);
  }

  button.addEventListener("click", async () => {
    button.disabled = true;
    setStatus("Telegram botga yo'naltirilmoqda...");

    const { ok, data } = await postJSON("/auth/telegram/start/");
    if (!ok) {
      setStatus("Login urinishini boshlab bo'lmadi.", "status-error");
      button.disabled = false;
      return;
    }

    window.open(data.deep_link, "_blank");
    setStatus("Botda “Start” tugmasini bosing...");
    pollUntilConfirmed(data.attempt_id, Date.now() + POLL_TIMEOUT_MS);
  });
})();
