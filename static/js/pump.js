(function () {
  "use strict";

  const config = window.PUMP_MQTT_CONFIG || {};
  const byId = (id) => document.getElementById(id);
  const brokerState = byId("broker-state");
  const deviceState = byId("device-state");
  const pumpState = byId("pump-state");
  const runTime = byId("run-time");
  const feedback = byId("pump-feedback");
  const log = byId("pump-log");
  const onButton = byId("pump-on");
  const offButton = byId("pump-off");
  let connected = false;
  let online = false;
  let reportedState = null;
  let runningSince = null;
  let pending = null;
  let logCount = 0;

  function addLog(message) {
    if (logCount === 0) log.replaceChildren();
    const item = document.createElement("li");
    const time = document.createElement("span");
    time.className = "t";
    time.textContent = new Date().toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    item.append(time, document.createTextNode(message));
    log.prepend(item);
    logCount += 1;
    while (log.children.length > 20) log.lastElementChild.remove();
  }

  function updateButtons() {
    const canControl = connected && online;
    onButton.disabled = !canControl;
    offButton.disabled = !canControl;
  }

  function formatDuration(ms) {
    const total = Math.max(0, Math.floor(ms / 1000));
    return String(Math.floor(total / 60)).padStart(2, "0") + ":" + String(total % 60).padStart(2, "0");
  }

  function showStatus(value) {
    if (value !== "ON" && value !== "OFF") return;
    const changed = reportedState !== value;
    reportedState = value;
    pumpState.textContent = value === "ON" ? "BẬT" : "TẮT";
    pumpState.classList.toggle("is-on", value === "ON");
    if (value === "ON" && runningSince === null) runningSince = Date.now();
    if (value === "OFF") runningSince = null;
    runTime.textContent = runningSince === null ? "00:00" : formatDuration(Date.now() - runningSince);
    if (changed) addLog("ESP32 báo bơm " + (value === "ON" ? "BẬT" : "TẮT"));
    if (pending && pending.command === value) {
      clearTimeout(pending.timer);
      feedback.textContent = "ESP32 đã xác nhận bơm " + (value === "ON" ? "BẬT." : "TẮT.");
      pending = null;
    }
  }

  function sendCommand(command) {
    if (!connected || !online || !window.mqttClient) return;
    if (pending) clearTimeout(pending.timer);
    feedback.textContent = "Đang chờ ESP32 xác nhận…";
    addLog("Đã gửi lệnh " + (command === "ON" ? "BẬT" : "TẮT"));
    pending = {
      command,
      timer: setTimeout(() => {
        feedback.textContent = "Cảnh báo: quá 5 giây chưa nhận được trạng thái xác nhận từ ESP32.";
        addLog("Hết thời gian chờ xác nhận lệnh " + command);
        pending = null;
      }, 5000)
    };
    window.mqttClient.publish("adn/pump/cmd", command, { qos: 1, retain: false }, (error) => {
      if (error) {
        if (pending) clearTimeout(pending.timer);
        pending = null;
        feedback.textContent = "Không gửi được lệnh đến broker.";
        addLog("Lỗi gửi lệnh đến broker");
      }
    });
  }

  onButton.addEventListener("click", () => sendCommand("ON"));
  offButton.addEventListener("click", () => sendCommand("OFF"));
  setInterval(() => {
    if (runningSince !== null) runTime.textContent = formatDuration(Date.now() - runningSince);
  }, 1000);

  if (!config.configured) {
    brokerState.textContent = "Chưa cấu hình MQTT";
    feedback.textContent = "Trang vẫn hoạt động, nhưng chưa thể kết nối broker.";
    return;
  }
  if (!window.mqtt || typeof window.mqtt.connect !== "function") {
    brokerState.textContent = "Không tải được thư viện MQTT";
    feedback.textContent = "Không thể khởi tạo kết nối MQTT.";
    return;
  }

  const clientId = "adn_web_" + Math.random().toString(16).slice(2, 12);
  const client = window.mqtt.connect(config.url, {
    clientId,
    username: config.username,
    password: config.password,
    clean: true,
    reconnectPeriod: 2000,
    connectTimeout: 10000,
    keepalive: 15
  });
  window.mqttClient = client;

  client.on("connect", () => {
    connected = true;
    brokerState.textContent = "Đã kết nối broker";
    addLog("Đã kết nối broker MQTT");
    updateButtons();
    client.subscribe(["adn/pump/status", "adn/pump/online"], { qos: 1 }, (error) => {
      if (error) {
        feedback.textContent = "Kết nối được broker nhưng không đăng ký nhận trạng thái.";
        addLog("Không đăng ký được topic trạng thái");
      }
    });
  });
  client.on("reconnect", () => { brokerState.textContent = "Đang kết nối lại broker…"; });
  client.on("close", () => {
    connected = false;
    brokerState.textContent = "Mất kết nối broker";
    updateButtons();
  });
  client.on("error", () => {
    brokerState.textContent = "Lỗi kết nối broker";
    feedback.textContent = "Không kết nối được broker MQTT. Kiểm tra cấu hình và quyền truy cập.";
  });
  client.on("message", (topic, payload) => {
    const value = payload.toString();
    if (topic === "adn/pump/online") {
      if (value !== "online" && value !== "offline") return;
      online = value === "online";
      deviceState.textContent = online ? "Đang trực tuyến" : "Ngoại tuyến";
      addLog("ESP32 " + (online ? "trực tuyến" : "ngoại tuyến"));
      if (!online) {
        reportedState = null;
        pumpState.textContent = "CHƯA RÕ";
        pumpState.classList.remove("is-on");
        runningSince = null;
        runTime.textContent = "00:00";
      }
      updateButtons();
    } else if (topic === "adn/pump/status") {
      showStatus(value);
    }
  });
})();
