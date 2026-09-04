let currentZone = null;

// ── Helpers ──────────────────────────────────────────────────────────────

function api(method, path, body) {
  const opts = { method, headers: {} };
  if (body) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  return fetch(path, opts).then(r => r.json());
}

function toast(msg, ok) {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.className = "toast " + (ok ? "ok" : "err");
  el.classList.remove("hidden");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.add("hidden"), 2500);
}

function $(id) { return document.getElementById(id); }

// ── Navigation ──────────────────────────────────────────────────────────

document.querySelectorAll(".nav-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".nav-btn").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
    btn.classList.add("active");
    $("view-" + btn.dataset.view).classList.add("active");

    if (btn.dataset.view === "dashboard") refreshStatus();
    if (btn.dataset.view === "zones") loadZones();
    if (btn.dataset.view === "config") loadConfig();
  });
});

// ── Dashboard ───────────────────────────────────────────────────────────

function refreshStatus() {
  api("GET", "/api/status").then(r => {
    $("status-output").textContent = r.ok ? r.data : "Error: " + r.error;
  });
}

function rndcAction(action) {
  const output = $("control-output");
  output.textContent = "Running " + action + "...";
  api("POST", "/api/control/" + action).then(r => {
    output.textContent = r.ok ? r.data : "Error: " + r.error;
    toast(r.ok ? action + " done" : r.error, r.ok);
  });
}

function checkConfig() {
  api("GET", "/api/config/check").then(r => {
    const el = $("config-check-output");
    el.textContent = r.ok ? (r.data.valid ? "Config is valid" : "Error: " + r.data.error) : r.error;
    el.style.color = r.ok && r.data.valid ? "var(--green)" : "var(--red)";
  });
}

// ── Zones ───────────────────────────────────────────────────────────────

function loadZones() {
  api("GET", "/api/zones").then(r => {
    if (!r.ok) return toast(r.error, false);
    const body = $("zones-body");
    body.innerHTML = "";
    r.data.forEach(z => {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${z.name}</td><td>${z.type}</td><td>${z.source}</td>
        <td><button class="secondary" onclick="viewZone('${z.name}')">View</button></td>`;
      body.appendChild(tr);
    });
  });
}

function showAddZone() { $("add-zone-form").classList.remove("hidden"); }
function hideAddZone() { $("add-zone-form").classList.add("hidden"); }

function createZone() {
  const name = $("new-zone-name").value.trim();
  if (!name) return;
  api("POST", "/api/zone", { name, type: $("new-zone-type").value }).then(r => {
    toast(r.ok ? "Zone created" : r.error, r.ok);
    if (r.ok) {
      hideAddZone();
      $("new-zone-name").value = "";
      loadZones();
    }
  });
}

function viewZone(name) {
  currentZone = name;
  api("GET", "/api/zone/" + name).then(r => {
    if (!r.ok) return toast(r.error, false);
    $("zone-detail").classList.remove("hidden");
    $("zone-detail-name").textContent = name;
    $("zone-raw").textContent = r.data.raw;
    $("zone-raw").classList.add("hidden");
    $("zone-check-output").textContent = "";

    const body = $("records-body");
    body.innerHTML = "";
    r.data.records.forEach((rec, i) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${rec.name}</td><td>${rec.ttl}</td><td>${rec.type}</td>
        <td>${rec.value}</td>
        <td><button class="danger" style="padding:2px 8px" onclick="deleteRecord(${i})">x</button></td>`;
      body.appendChild(tr);
    });
  });
}

function addRecord() {
  if (!currentZone) return;
  const data = {
    name: $("rec-name").value.trim() || "@",
    type: $("rec-type").value,
    value: $("rec-value").value.trim(),
    ttl: parseInt($("rec-ttl").value) || 3600,
  };
  if (!data.value) return toast("Value required", false);
  api("POST", "/api/zone/" + currentZone + "/record", data).then(r => {
    toast(r.ok ? "Record added" : r.error, r.ok);
    if (r.ok) {
      $("rec-name").value = "";
      $("rec-value").value = "";
      viewZone(currentZone);
    }
  });
}

function deleteRecord(idx) {
  if (!currentZone) return;
  api("DELETE", "/api/zone/" + currentZone + "/record/" + idx).then(r => {
    toast(r.ok ? "Record removed" : r.error, r.ok);
    if (r.ok) viewZone(currentZone);
  });
}

function deleteZone() {
  if (!currentZone) return;
  if (!confirm("Delete zone " + currentZone + "?")) return;
  api("DELETE", "/api/zone/" + currentZone).then(r => {
    toast(r.ok ? "Zone deleted" : r.error, r.ok);
    if (r.ok) {
      currentZone = null;
      $("zone-detail").classList.add("hidden");
      loadZones();
    }
  });
}

function toggleRaw() {
  $("zone-raw").classList.toggle("hidden");
}

function checkZone() {
  if (!currentZone) return;
  api("GET", "/api/zone/" + currentZone + "/check").then(r => {
    const el = $("zone-check-output");
    if (r.ok) {
      el.textContent = r.data.output || (r.data.valid ? "Zone is valid" : "Error: " + r.data.error);
      el.style.color = r.data.valid ? "var(--green)" : "var(--red)";
    } else {
      el.textContent = r.error;
      el.style.color = "var(--red)";
    }
  });
}

// ── Config ──────────────────────────────────────────────────────────────

function loadConfig() {
  api("GET", "/api/config/options").then(r => {
    if (r.ok) $("config-editor").value = r.data;
  });
}

function saveConfig() {
  const content = $("config-editor").value;
  api("PUT", "/api/config/options", { content }).then(r => {
    toast(r.ok ? "Options saved" : r.error, r.ok);
    $("config-save-output").textContent = r.ok ? "Saved. Reload config to apply." : r.error;
  });
}

// ── Init ────────────────────────────────────────────────────────────────

refreshStatus();
