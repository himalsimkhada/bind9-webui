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
  $("login-password").value = "";
  $("login-remember").checked = false;
  $("login-error").classList.add("hidden");
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

// Wire the zones search/filter and Add Zone wizard inputs.
document.querySelectorAll("#zone-search").forEach(el => el.addEventListener("input", loadZones));
document.querySelectorAll("#zone-filter").forEach(el => el.addEventListener("change", loadZones));
["wz-name", "wz-ttl", "wz-ip"].forEach(id => {
  document.querySelectorAll("#" + id).forEach(el => el.addEventListener("input", updateWizardPreview));
});
document.querySelectorAll("#wizard-simple input[type=checkbox]").forEach(el => {
  el.addEventListener("change", updateWizardPreview);
});
document.querySelectorAll("#wz-name, #wz-name-adv").forEach(el => {
  el.addEventListener("keydown", e => {
    if (e.key === "Enter") { e.preventDefault(); createZone(); }
  });
});
document.querySelectorAll("#add-zone-modal").forEach(el => {
  el.addEventListener("keydown", e => {
    if (e.key === "Escape") hideAddZone();
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
    const q = ($("zone-search").value || "").trim().toLowerCase();
    const f = $("zone-filter").value;
    const all = r.data || [];
    const filtered = all.filter(z =>
      (f === "all" || z.source === f) &&
      (!q || z.name.toLowerCase().includes(q))
    );
    $("zones-count").textContent = "· " + filtered.length + (filtered.length === 1 ? " zone" : " zones");
    $("zones-empty").classList.toggle("hidden", filtered.length > 0);

    const list = $("zones-list");
    list.innerHTML = "";
    filtered.forEach(z => {
      const item = document.createElement("button");
      item.type = "button";
      item.className = "zone-item" + (z.name === currentZone ? " active" : "");
      const srcCls = z.source === "default" ? "default" : "local";
      item.innerHTML = `<span class="zone-item-name">${z.name}</span>
        <span class="zone-item-tags">
          <span class="zone-item-type">${z.type}</span>
          <span class="zone-item-src ${srcCls}">${z.source}</span>
        </span>`;
      item.onclick = () => viewZone(z.name);
      item.dataset.zone = z.name;
      list.appendChild(item);
    });
    if (currentZone && !all.some(z => z.name === currentZone)) {
      currentZone = null;
      $("zone-detail").classList.add("hidden");
      $("zone-placeholder").classList.remove("hidden");
    }
  });
}

// ── Add Zone wizard ──────────────────────────────────────────────────────

let wizardMode = "simple";

function showAddZone() {
  wizardMode = "simple";
  $("wz-status").classList.add("hidden");
  $("add-zone-modal").classList.remove("hidden");
  $("wizard-simple").classList.remove("hidden");
  $("wizard-advanced").classList.add("hidden");
  $("tab-simple").classList.add("active");
  $("tab-advanced").classList.remove("active");
  updateWizardPreview();
  $("wz-name").focus();
}

function hideAddZone() {
  $("add-zone-modal").classList.add("hidden");
}

function wizardTab(mode) {
  wizardMode = mode;
  $("wizard-simple").classList.toggle("hidden", mode !== "simple");
  $("wizard-advanced").classList.toggle("hidden", mode !== "advanced");
  $("tab-simple").classList.toggle("active", mode === "simple");
  $("tab-advanced").classList.toggle("active", mode === "advanced");
  if (mode === "advanced") $("wz-name-adv").focus();
  else updateWizardPreview();
}

function wizardZoneName() {
  return (wizardMode === "simple" ? $("wz-name").value : $("wz-name-adv").value).trim();
}

function wizardRecords(name) {
  const ttl = parseInt($("wz-ttl").value) || 3600;
  const ip = ($("wz-ip").value || "").trim() || "127.0.0.1";
  const recs = [];
  if ($("p-ns").checked) {
    recs.push({ name: "@", type: "NS", value: "ns1." + name + "." });
    recs.push({ name: "ns1", type: "A", value: ip });
  }
  if ($("p-ns2").checked) recs.push({ name: "ns2", type: "A", value: ip });
  if ($("p-www").checked) recs.push({ name: "www", type: "A", value: ip });
  if ($("p-mail").checked) {
    recs.push({ name: "mail", type: "A", value: ip });
    recs.push({ name: "@", type: "MX", value: "10 mail." + name + "." });
  }
  if ($("p-txt").checked) recs.push({ name: "@", type: "TXT", value: "v=spf1 ip4:" + ip + " -all" });
  return recs;
}

let _wzPreviewTimer = null;

function updateWizardPreview() {
  const name = $("wz-name").value.trim();
  if (!name) {
    $("wz-preview").textContent = "Enter a zone name to see it live.";
    return;
  }
  if (!/^[a-zA-Z0-9-]+(\.[a-zA-Z0-9-]+)+\.?$/.test(name)) {
    $("wz-preview").textContent = "Zone names look like example.com (letters, numbers, hyphens, dots).";
    return;
  }
  clearTimeout(_wzPreviewTimer);
  _wzPreviewTimer = setTimeout(() => {
    api("POST", "/api/zone/preview", {
      name,
      ttl: parseInt($("wz-ttl").value) || 3600,
      records: wizardRecords(name),
    }).then(r => {
      $("wz-preview").textContent = r.ok ? r.data.body : "Preview error: " + r.error;
    });
  }, 150);
}

function showWzError(msg) {
  const el = $("wz-status");
  el.textContent = msg;
  el.classList.remove("hidden");
}

function createZone() {
  const name = wizardZoneName();
  if (!name) return showWzError("Enter a zone name");
  $("wz-status").classList.add("hidden");
  const payload = { name, type: wizardMode === "simple" ? $("wz-type").value : "master" };
  if (wizardMode === "simple") {
    payload.records = wizardRecords(name);
    payload.ttl = parseInt($("wz-ttl").value) || 3600;
  } else {
    payload.body = $("wz-raw").value;
    if (!payload.body.trim()) return showWzError("Paste a zone file first, or use the Simple tab");
  }
  api("POST", "/api/zone", payload).then(r => {
    if (!r.ok) return showWzError(r.error);
    toast("Zone created", true);
    hideAddZone();
    loadZones();
    viewZone(name);
  });
}

function viewZone(name) {
  currentZone = name;
  $("zone-placeholder").classList.add("hidden");
  document.querySelectorAll(".zone-item").forEach(el => {
    el.classList.toggle("active", el.dataset.zone === name);
  });
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
      $("zone-placeholder").classList.remove("hidden");
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

// ── Dig ─────────────────────────────────────────────────────────────────

function runDig() {
  const q = $("dig-q").value.trim();
  if (!q) return toast("Enter a name to look up", false);
  const type = $("dig-type").value;
  const server = $("dig-server").value.trim();
  const el = $("dig-output");
  el.textContent = "Querying...";
  api("POST", "/api/dig", { q, type, server }).then(r => {
    if (!r.ok) {
      el.textContent = "Error: " + r.error;
      return;
    }
    const d = r.data;
    el.textContent = `> dig @${d.server} ${d.query} ${d.type}\n\n` + d.output;
  });
}

$("dig-q").addEventListener("keydown", e => { if (e.key === "Enter") runDig(); });

// ── Backup / Restore ────────────────────────────────────────────────────

function downloadBackup() {
  const status = $("backup-status");
  status.textContent = "Preparing backup...";
  fetch("/api/backup").then(r => {
    if (!r.ok) return r.json().then(j => {
      status.textContent = "Error: " + j.error;
    });
    return r.blob();
  }).then(blob => {
    if (!blob) return;
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = ("bind9-backup-" + new Date().toISOString().slice(0, 19).replace(/[T:]/g, "-") + ".tar.gz");
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    status.textContent = "Backup downloaded.";
  });
}

document.getElementById("restore-file").addEventListener("change", function() {
  const file = this.files[0];
  if (!file) return;
  if (!confirm("Restore this backup? This OVERWRITES the current BIND config and zone files. A backup of the current state is kept for rollback.")) {
    this.value = "";
    return;
  }
  const status = $("backup-status");
  status.textContent = "Restoring...";
  const fd = new FormData();
  fd.append("file", file);
  fetch("/api/restore", { method: "POST", body: fd }).then(r => r.json()).then(r => {
    if (r.ok) {
      const w = r.data && r.data.warnings;
      if (w && w.length) {
        status.textContent = "Restored with zone warnings: " + w.join(" | ");
        toast("Restored (some zones flagged)", false);
      } else {
        status.textContent = "Restored.";
        toast("Backup restored", true);
      }
      if (currentConfigFile) loadCurrentConfig();
    } else {
      status.textContent = "Restore failed: " + r.error;
      toast("Restore failed", false);
    }
  });
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
