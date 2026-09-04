let currentZone = null;
let currentConfigFile = null;
let configFiles = [];
let zoneDoc = null;

// ── Helpers ──────────────────────────────────────────────────────────────

function api(method, path, body) {
  const opts = { method, headers: {} };
  if (body) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  return fetch(path, opts).then(r => {
    if (r.status === 401) showLogin();
    return r.json();
  });
}

// ── Auth ────────────────────────────────────────────────────────────────

function showLogin() {
  document.querySelector("nav").classList.add("hidden");
  $("logout-btn").classList.add("hidden");
  $("app-main").classList.add("hidden");
  $("view-login").classList.remove("hidden");
  document.querySelectorAll(".nav-btn").forEach(b => b.classList.remove("active"));
  $("login-password").focus();
}

function showApp() {
  document.querySelector("nav").classList.remove("hidden");
  $("logout-btn").classList.remove("hidden");
  $("view-login").classList.add("hidden");
  $("app-main").classList.remove("hidden");
  refreshStatus();
}

function checkSession() {
  api("GET", "/api/session").then(r => {
    if (r.ok && r.data && r.data.auth) {
      showApp();
    } else {
      showLogin();
    }
  });
}

function login() {
  const password = $("login-password").value;
  const remember = $("login-remember").checked;
  const btn = $("login-btn");
  $("login-error").classList.add("hidden");
  btn.disabled = true;
  btn.textContent = "Checking...";
  api("POST", "/api/login", { password, remember }).then(r => {
    btn.disabled = false;
    btn.textContent = "Log in";
    if (r.ok) {
      showApp();
      toast("Logged in", true);
    } else {
      $("login-error").textContent = r.error || "Login failed";
      $("login-error").classList.remove("hidden");
      $("login-password").value = "";
      $("login-password").focus();
    }
  });
}

function logout() {
  api("POST", "/api/logout");
  showLogin();
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

// ── Theme ────────────────────────────────────────────────────────────────

function getTheme() {
  return localStorage.getItem("bind9-theme") || "dark";
}

function setTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem("bind9-theme", theme);
  $("theme-btn").innerHTML = theme === "dark" ? "&#9790;" : "&#9728;";
}

function toggleTheme() {
  setTheme(getTheme() === "dark" ? "light" : "dark");
}

setTheme(getTheme());

// ── Navigation ──────────────────────────────────────────────────────────

document.querySelectorAll(".nav-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    if (!btn.dataset.view) return; // skip e.g. the logout button
    document.querySelectorAll(".nav-btn").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
    btn.classList.add("active");
    $("view-" + btn.dataset.view).classList.add("active");

    const view = btn.dataset.view;
    if (view === "dashboard") refreshStatus();
    if (view === "zones") loadZones();
    if (view === "config") initConfig();
    if (view === "logs") loadLogs();
  });
});

// ── Dashboard ───────────────────────────────────────────────────────────

function refreshStatus() {
  api("GET", "/api/status/structured").then(r => {
    if (!r.ok) {
      $("stat-running").textContent = "Error";
      $("stat-running").className = "value red";
      $("status-error").textContent = "rndc error: " + r.error;
      $("status-error").classList.remove("hidden");
      return;
    }
    $("status-error").classList.add("hidden");
    const d = r.data;
    $("stat-running").textContent = d.running ? "Running" : "Stopped";
    $("stat-running").className = "value " + (d.running ? "green" : "red");
    $("stat-version").textContent = d.version || "--";
    $("stat-zones").textContent = d.zones || "--";
    $("stat-workers").textContent = d.workers || "--";
    $("stat-boot").textContent = d.boot_time || "--";
    $("stat-querylog").textContent = d.query_logging || "--";
  });

  api("GET", "/api/status").then(r => {
    $("status-output").textContent = r.ok ? r.data : "Error: " + r.error;
  });
}

function toggleRawStatus() {
  $("status-output").classList.toggle("hidden");
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
    zoneDoc = r.data;
    $("zone-detail").classList.remove("hidden");
    $("zone-detail-name").textContent = name;
    $("zone-info").innerHTML = `<span class="zone-info-path">File: <code>${r.data.path}</code></span>`;
    renderZoneSource(r.data.source);
    $("zone-raw-editor").value = r.data.raw;
    $("zone-raw-wrap").classList.add("hidden");
    $("zone-raw-status").textContent = "";
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

function renderZoneSource(source) {
  const el = $("zone-source");
  if (zoneDoc.protected) {
    el.innerHTML = `<span class="zone-source-tag default">Protected system zone in named.conf.default-zones</span>
      <span class="small-text">Cannot be moved or deleted</span>`;
  } else if (source === "default") {
    el.innerHTML = `<span class="zone-source-tag default">In named.conf.default-zones</span>
      <button class="secondary" style="margin-left:8px" onclick="moveZoneSource('local')">Move back to local</button>
      <span class="small-text">Zone block lives in named.conf.default-zones</span>`;
  } else {
    el.innerHTML = `<span class="zone-source-tag local">In named.conf.local</span>
      <button class="secondary" style="margin-left:8px" onclick="moveZoneSource('default')">Move to default-zones</button>
      <span class="small-text">Automatically adds the zone block to named.conf.default-zones</span>`;
  }
}

function moveZoneSource(target) {
  if (!currentZone) return;
  api("POST", "/api/zone/" + currentZone + "/source", { target }).then(r => {
    toast(r.ok ? r.message : r.error, r.ok);
    if (r.ok) viewZone(currentZone);
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
  const wrap = $("zone-raw-wrap");
  const hidden = wrap.classList.contains("hidden");
  wrap.classList.toggle("hidden");
  if (hidden) {
    $("zone-raw-editor").value = (zoneDoc && zoneDoc.raw) || "";
    $("zone-raw-status").textContent = "";
  }
}

function saveRawZone() {
  if (!currentZone) return;
  const content = $("zone-raw-editor").value;
  api("PUT", "/api/zone/" + currentZone + "/file", { content }).then(r => {
    if (r.ok) {
      toast("Zone file saved", true);
      $("zone-raw-status").textContent = "Saved. Reloaded BIND.";
      viewZone(currentZone);
    } else {
      toast(r.error, false);
      $("zone-raw-status").textContent = "Error: " + r.error;
    }
  });
}

function reloadRawZone() {
  if (!currentZone) return;
  api("GET", "/api/zone/" + currentZone).then(r => {
    if (r.ok) {
      zoneDoc = r.data;
      $("zone-raw-editor").value = r.data.raw;
      $("zone-raw-status").textContent = "Reverted to saved version.";
    }
  });
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

// ── Host Mapper ─────────────────────────────────────────────────────────

function clearMapper() {
  $("mapper-input").value = "";
  $("mapper-output").classList.add("hidden");
  $("mapper-output").textContent = "";
}

function runMapper() {
  const text = $("mapper-input").value;
  if (!text.trim()) return toast("Enter host lines first", false);
  const out = $("mapper-output");
  out.classList.remove("hidden");
  out.textContent = "Mapping...";
  api("POST", "/api/map-hosts", { text }).then(r => {
    if (!r.ok) {
      out.textContent = "Error: " + r.error;
      return;
    }
    const s = r.data.summary;
    let lines = [];
    lines.push(`=== Summary: ${s.created} added, ${s.duplicates_skipped} duplicates skipped, ${s.missing_zones} missing zone(s), ${s.bad_lines} bad line(s) ===`);
    if (s.missing_zone_names.length) {
      lines.push(`Missing zones (create them first or skip): ${s.missing_zone_names.join(", ")}`);
    }
    lines.push("");
    r.data.results.forEach(res => {
      lines.push(`[${res.type}] ${res.message}`);
    });
    out.textContent = lines.join("\n");
    toast(s.created + " records added", true);
    loadZones();
  });
}

document.getElementById("mapper-file").addEventListener("change", function() {
  const file = this.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = e => {
    $("mapper-input").value = e.target.result;
    toast("File loaded. Click Map Hosts.", true);
  };
  reader.readAsText(file);
  this.value = "";
});

// ── Configuration ───────────────────────────────────────────────────────

function initConfig() {
  api("GET", "/api/config/files").then(r => {
    if (!r.ok) return;
    configFiles = r.data;
    const tabs = $("config-tabs");
    tabs.innerHTML = "";
    configFiles.forEach((f, i) => {
      const btn = document.createElement("button");
      btn.className = "tab-btn" + (i === 0 ? " active" : "");
      btn.textContent = f;
      btn.onclick = () => switchConfigTab(f, btn);
      tabs.appendChild(btn);
    });
    if (configFiles.length > 0) {
      currentConfigFile = configFiles[0];
      loadCurrentConfig();
    }
  });
}

function switchConfigTab(name, btn) {
  document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
  btn.classList.add("active");
  currentConfigFile = name;
  loadCurrentConfig();
}

function loadCurrentConfig() {
  if (!currentConfigFile) return;
  $("config-save-output").textContent = "";
  api("GET", "/api/config/file/" + encodeURIComponent(currentConfigFile)).then(r => {
    if (r.ok) {
      const editors = $("config-editors");
      editors.innerHTML = "";
      const ta = document.createElement("textarea");
      ta.id = "config-editor";
      ta.rows = 24;
      ta.spellcheck = false;
      ta.value = r.data;
      editors.appendChild(ta);
    }
  });
}

function saveCurrentConfig() {
  if (!currentConfigFile) return;
  const content = $("config-editor").value;
  api("PUT", "/api/config/file/" + encodeURIComponent(currentConfigFile), { content }).then(r => {
    toast(r.ok ? currentConfigFile + " saved" : r.error, r.ok);
    $("config-save-output").textContent = r.ok ? "Saved. Reload config to apply." : r.error;
  });
}

function checkConfigFromConf() {
  api("GET", "/api/config/check").then(r => {
    const output = $("config-save-output");
    output.textContent = r.ok ? (r.data.valid ? "Config is valid" : "Error: " + r.data.error) : r.error;
    output.style.color = r.ok && r.data.valid ? "var(--green)" : "var(--red)";
  });
}

// ── Logs ────────────────────────────────────────────────────────────────

function loadLogs() {
  const lines = $("log-lines").value;
  const query = $("log-filter").value;
  const el = $("log-output");
  el.textContent = "Loading...";
  api("GET", "/api/logs?lines=" + lines + "&query=" + encodeURIComponent(query)).then(r => {
    if (!r.ok) {
      el.textContent = "Error: " + r.error;
      return;
    }
    const text = r.data;
    el.innerHTML = "";
    const lines = text.split("\n");
    lines.forEach(line => {
      const span = document.createElement("span");
      span.className = "log-info";
      if (/error|fail|denied|fatal/i.test(line)) span.className = "log-error";
      else if (/warn|warning/i.test(line)) span.className = "log-warn";
      span.textContent = line + "\n";
      el.appendChild(span);
    });
  });
}

// ── Init ────────────────────────────────────────────────────────────────

$("login-password").addEventListener("keydown", e => {
  if (e.key === "Enter") login();
});

checkSession();
