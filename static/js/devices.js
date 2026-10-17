(() => {
  const STORAGE_KEY = "endi_oson_device_id";
  const listEl = document.getElementById("device-list");
  const statusEl = document.getElementById("connection-status");
  const renameForm = document.getElementById("rename-form");
  const renameInput = document.getElementById("rename-input");
  const connectionLogEl = document.getElementById("connection-log");
  const incomingRequestEl = document.getElementById("incoming-request");

  function guessDefaultLabel() {
    const ua = navigator.userAgent || "";
    if (/iPhone/.test(ua)) return "iPhone";
    if (/iPad/.test(ua)) return "iPad";
    if (/Android/.test(ua)) return "Android qurilma";
    if (/Macintosh/.test(ua)) return "Mac";
    if (/Windows/.test(ua)) return "Windows kompyuter";
    if (/Linux/.test(ua)) return "Linux kompyuter";
    return "Noma'lum qurilma";
  }

  function getStoredDeviceId() {
    try {
      return localStorage.getItem(STORAGE_KEY);
    } catch {
      return null;
    }
  }

  function storeDeviceId(id) {
    try {
      localStorage.setItem(STORAGE_KEY, id);
    } catch {
      /* xususiy rejim yoki bloklangan xotira — jim o'tkazib yuboramiz */
    }
  }

  let selfDeviceId = getStoredDeviceId();
  const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const params = new URLSearchParams();
  if (selfDeviceId) params.set("device_id", selfDeviceId);
  params.set("label", guessDefaultLabel());

  const socket = new WebSocket(
    `${wsProtocol}//${window.location.host}/ws/devices/?${params.toString()}`
  );

  socket.addEventListener("open", () => {
    statusEl.textContent = "Ulandi";
  });

  socket.addEventListener("close", () => {
    statusEl.textContent = "Ulanish uzildi";
  });

  socket.addEventListener("error", () => {
    statusEl.textContent = "Ulanish xatosi";
  });

  socket.addEventListener("message", (event) => {
    const data = JSON.parse(event.data);

    if (data.type === "device.self") {
      selfDeviceId = String(data.device_id);
      storeDeviceId(selfDeviceId);
      return;
    }

    if (data.type === "device.list") {
      renderDevices(data.devices);
      return;
    }

    if (data.type === "connection.request") {
      showIncomingRequest(data);
      return;
    }

    if (data.type === "connection.response") {
      connectionLogEl.textContent = `So'rov holati: ${data.status}`;
      return;
    }

    if (data.type === "connection.error") {
      connectionLogEl.textContent = `Xatolik: ${data.error}`;
    }
  });

  function renderDevices(devices) {
    listEl.innerHTML = "";
    devices.forEach((device) => {
      const li = document.createElement("li");
      const isSelf = String(device.id) === String(selfDeviceId);
      li.textContent = device.device_label + (isSelf ? " (shu qurilma)" : "");
      if (!isSelf) {
        li.style.cursor = "pointer";
        li.title = "Ulanish so'rovi yuborish";
        li.addEventListener("click", () => {
          socket.send(
            JSON.stringify({ type: "connection.request", to_device_id: device.id })
          );
          connectionLogEl.textContent = `${device.device_label}ga so'rov yuborildi...`;
        });
      }
      listEl.appendChild(li);
    });
  }

  function showIncomingRequest(data) {
    incomingRequestEl.hidden = false;
    incomingRequestEl.innerHTML = "";

    const text = document.createElement("p");
    text.textContent = `"${data.from_device_label}" ulanish so'ramoqda.`;
    incomingRequestEl.appendChild(text);

    const acceptBtn = document.createElement("button");
    acceptBtn.className = "btn";
    acceptBtn.textContent = "Qabul qilish";
    acceptBtn.addEventListener("click", () => respond(data.request_id, true));

    const rejectBtn = document.createElement("button");
    rejectBtn.textContent = "Rad etish";
    rejectBtn.addEventListener("click", () => respond(data.request_id, false));

    incomingRequestEl.appendChild(acceptBtn);
    incomingRequestEl.appendChild(rejectBtn);
  }

  function respond(requestId, accept) {
    socket.send(JSON.stringify({ type: "connection.respond", request_id: requestId, accept }));
    incomingRequestEl.hidden = true;
  }

  renameForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const label = renameInput.value.trim();
    if (label && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: "rename", label }));
      renameInput.value = "";
    }
  });
})();
