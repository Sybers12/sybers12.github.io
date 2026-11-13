/* NBTS Blood Bank Management System - frontend */

const API = "/api";
const NAV_ITEMS = [
  { key: "dashboard",  label: "Dashibodi",       perm: "stats" },
  { key: "donors",     label: "Wachangiaji",     perm: "donors" },
  { key: "donations",  label: "Michango",        perm: "donations" },
  { key: "recruiting", label: "Urekruitimenti",  perm: "recruiting" },
  { key: "lab",        label: "Maabara",         perm: "lab" },
  { key: "products",   label: "Bidhaa za Damu",  perm: "products" },
  { key: "council",    label: "Halmashauri",     perm: "council" },
];

const ROLE_PERMS = {
  MANAGER:       ["stats", "donors", "donations", "recruiting", "lab", "products"],
  QUALITY:       ["stats", "lab", "products"],
  RECRUITER:     ["stats", "recruiting"],
  HEAD_DONATION: ["stats", "donors", "donations", "recruiting"],
  COUNSELOR:     ["stats", "donors", "donations"],
  HEAD_LAB:      ["stats", "lab", "products"],
  PHLEBOTOMIST:  ["stats", "donations"],
  LAB_TECH:      ["stats", "lab", "products"],
  DATA_CLERK:    ["stats", "donors", "donations"],
  COUNCIL:       ["council"],
};

const APPROVERS = new Set(["HEAD_LAB", "QUALITY", "MANAGER"]);
const PRODUCT_TYPES = ["PRC", "FFP", "PLT", "CRYO"];
const ABOD_GROUPS = ["O+", "O-", "A+", "A-", "B+", "B-", "AB+", "AB-"];

let token = localStorage.getItem("bb_token") || "";
let user = null;
let currentSection = "dashboard";
let editingResultId = null;

/* ---------------- helpers ---------------- */

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

async function api(path, opts = {}) {
  const headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
  if (token) headers["Authorization"] = "Bearer " + token;
  const res = await fetch(API + path, { ...opts, headers });
  if (res.status === 401 && user) { doLogout(); throw new Error("Kipindi kimeisha"); }
  let data = null;
  try { data = await res.json(); } catch { /* no body */ }
  if (!res.ok) throw new Error((data && data.detail) || "Hitilafu / Error " + res.status);
  return data;
}

function toast(msg, isErr = false) {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.classList.toggle("err", isErr);
  el.classList.remove("hidden");
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.add("hidden"), 3500);
}

function badge(status) {
  const map = {
    APPROVED: "ok", READY: "ok", DONE: "ok", NEGATIVE: "ok",
    REVIEWED: "info", ISSUED: "info",
    QUARANTINE: "warn", REQUESTED: "warn",
    DISCREPANCY: "bad", POSITIVE: "bad",
    COLLECTED: "neutral",
  };
  return `<span class="badge ${map[status] || "neutral"}">${esc(status)}</span>`;
}

function bgroup(g) { return g ? `<span class="bgroup">${esc(g)}</span>` : '<span class="muted">—</span>'; }

function barChart(items, cls = "") {
  const max = Math.max(1, ...items.map(i => i.value));
  return items.map(i => `
    <div class="bar-row">
      <div class="bar-lbl">${esc(i.label)}</div>
      <div class="bar-track"><div class="bar-fill ${cls}" style="width:${(i.value * 100 / max).toFixed(1)}%"></div></div>
      <div class="bar-val">${esc(i.valueText ?? i.value)}</div>
    </div>`).join("");
}

function hasPerm(perm) { return (ROLE_PERMS[user.role] || []).includes(perm); }

/* ---------------- auth ---------------- */

async function doLogin(e) {
  e.preventDefault();
  const errEl = document.getElementById("loginError");
  errEl.classList.add("hidden");
  try {
    const data = await api("/login", {
      method: "POST",
      body: JSON.stringify({
        username: document.getElementById("loginUser").value.trim(),
        password: document.getElementById("loginPass").value,
      }),
    });
    token = data.token;
    localStorage.setItem("bb_token", token);
    user = { role: data.role, full_name: data.full_name, council: data.council };
    enterApp();
  } catch (err) {
    errEl.textContent = err.message;
    errEl.classList.remove("hidden");
  }
}

async function doLogout() {
  try { await api("/logout", { method: "POST" }); } catch { /* ignore */ }
  localStorage.removeItem("bb_token");
  token = ""; user = null;
  document.getElementById("appView").classList.add("hidden");
  document.getElementById("loginView").classList.remove("hidden");
}

async function restoreSession() {
  if (!token) return false;
  try {
    user = await api("/me");
    return true;
  } catch {
    localStorage.removeItem("bb_token");
    token = "";
    return false;
  }
}

function enterApp() {
  document.getElementById("loginView").classList.add("hidden");
  document.getElementById("appView").classList.remove("hidden");
  document.getElementById("userName").textContent = user.full_name || user.username || "";
  document.getElementById("userRole").textContent = user.role;
  renderNav();
  showSection("dashboard");
}

function renderNav() {
  const nav = document.getElementById("mainNav");
  nav.innerHTML = NAV_ITEMS
    .filter(item => hasPerm(item.perm))
    .map(item => `<button class="navbtn" data-section="${item.key}">${item.label}</button>`)
    .join("");
  nav.querySelectorAll(".navbtn").forEach(btn =>
    btn.addEventListener("click", () => showSection(btn.dataset.section)));
}

function showSection(key) {
  currentSection = key;
  document.querySelectorAll(".navbtn").forEach(b =>
    b.classList.toggle("active", b.dataset.section === key));
  const content = document.getElementById("content");
  content.innerHTML = '<p class="empty">Inapakia… / Loading…</p>';
  const views = {
    dashboard: viewDashboard, donors: viewDonors, donations: viewDonations,
    recruiting: viewRecruiting, lab: viewLab, products: viewProducts,
    council: viewCouncil,
  };
  (views[key] || viewDashboard)(content).catch(err => {
    content.innerHTML = `<div class="card"><p class="empty">${esc(err.message)}</p></div>`;
  });
}

/* ---------------- dashboard ---------------- */

async function viewDashboard(el) {
  const s = await api("/stats");
  const groups = Object.entries(s.blood_groups).map(([g, v]) => ({
    label: g, value: v.count, valueText: `${v.count} (${v.pct}%)`,
  }));
  const tti = [
    { label: "HIV", value: s.tti.hiv },
    { label: "HBV", value: s.tti.hbv },
    { label: "HCV", value: s.tti.hcv },
    { label: "VDRL (Syphilis)", value: s.tti.syphilis },
  ];
  const prodStatus = Object.entries(s.products.by_status).map(([k, v]) => ({ label: k, value: v }));
  const prodType = PRODUCT_TYPES.map(t => ({ label: t, value: s.products.by_type[t] || 0 }));
  const byHospital = Object.entries(s.products.issued_by_hospital).map(([k, v]) => ({ label: k, value: v }));

  el.innerHTML = `
    <h2 class="section">Dashibodi / Dashboard</h2>
    <p class="section-sub">Takwimu za jumla za banki ya damu</p>
    <div class="grid-4">
      <div class="card stat-card"><div class="num">${s.donors.total}</div><div class="lbl">Wachangiaji / Donors</div></div>
      <div class="card stat-card"><div class="num">${s.donors.eligible}</div><div class="lbl">Wanaostahili / Eligible now</div></div>
      <div class="card stat-card"><div class="num">${s.donations.total}</div><div class="lbl">Michango / Donations</div></div>
      <div class="card stat-card"><div class="num">${s.tti.tested}</div><div class="lbl">Vipimo / Tested</div></div>
    </div>
    <div class="grid-2">
      <div class="card"><h3>Makundi ya damu / Blood groups (count & %)</h3>${barChart(groups) || '<p class="empty">Hakuna data</p>'}</div>
      <div class="card"><h3>TTI reactive (${s.tti.reactive_pct}% ya vipimo)</h3>${barChart(tti, "green")}</div>
      <div class="card"><h3>Bidhaa kwa hali / Products by status</h3>${barChart(prodStatus, "alt")}</div>
      <div class="card"><h3>Bidhaa kwa aina / Products by type</h3>${barChart(prodType, "alt")}</div>
      <div class="card wide"><h3>Zilizotumwa hospitalini / Issued by hospital</h3>${barChart(byHospital, "green") || '<p class="empty">Hakuna data</p>'}</div>
    </div>`;
}

/* ---------------- donors ---------------- */

async function viewDonors(el) {
  el.innerHTML = `
    <h2 class="section">Wachangiaji Damu / Donors</h2>
    <p class="section-sub">Kusajili na kutafuta wachangiaji damu</p>
    <div class="grid-2">
      <div class="card wide">
        <div class="filters">
          <div style="flex:1"><label>Tafuta / Search</label><input id="donorSearch" placeholder="Jina, namba au simu…"></div>
          <div><button class="btn btn-primary" id="btnSearchDonors">Tafuta</button></div>
        </div>
        <div id="donorTable" class="table-scroll"></div>
      </div>
      <div class="card">
        <h3>Ongeza mchangiaji / Add donor</h3>
        <form id="donorForm" class="inline">
          <div class="full"><label>Majina / Names *</label><input name="names" required></div>
          <div><label>Tarehe ya kuzaliwa</label><input name="birth_date" type="date"></div>
          <div><label>Jinsia</label><select name="sex"><option value=""></option><option>M</option><option>F</option></select></div>
          <div><label>Simu / Phone</label><input name="phone"></div>
          <div><label>Wilaya / District</label><input name="district"></div>
          <div><label>Halmashauri / Council</label><input name="council"></div>
          <div><button class="btn btn-primary">Hifadhi</button></div>
        </form>
      </div>
    </div>`;

  async function loadDonors(search = "") {
    const rows = await api("/donors?search=" + encodeURIComponent(search));
    document.getElementById("donorTable").innerHTML = rows.length ? `
      <table><thead><tr>
        <th>Donation No</th><th>Majina</th><th>Mara</th><th>Mwisho</th>
        <th>Eligible hadi</th><th>Hali</th><th></th>
      </tr></thead><tbody>
      ${rows.map(d => `
        <tr>
          <td><b>${esc(d.donor_no)}</b></td>
          <td>${esc(d.names)}<br><span class="muted">${esc(d.phone || "")} ${esc(d.district || "")}</span></td>
          <td>${d.times_donated}</td>
          <td>${esc(d.last_donation_date || "—")}</td>
          <td>${esc(d.eligible_after || "—")}</td>
          <td>${d.eligible ? '<span class="badge ok">ELIGIBLE</span>' : '<span class="badge warn">DEFERRED</span>'}</td>
          <td><button class="btn btn-sm btn-edit" data-id="${d.id}">Taarifa</button></td>
        </tr>`).join("")}
      </tbody></table>` : '<p class="empty">Hakuna wachangiaji</p>';
    document.querySelectorAll("#donorTable [data-id]").forEach(b =>
      b.addEventListener("click", () => donorDetail(Number(b.dataset.id))));
  }

  document.getElementById("btnSearchDonors").addEventListener("click",
    () => loadDonors(document.getElementById("donorSearch").value.trim()));
  document.getElementById("donorSearch").addEventListener("keydown", e => {
    if (e.key === "Enter") loadDonors(e.target.value.trim());
  });
  document.getElementById("donorForm").addEventListener("submit", async e => {
    e.preventDefault();
    const f = new FormData(e.target);
    try {
      await api("/donors", { method: "POST", body: JSON.stringify(Object.fromEntries(f)) });
      toast("Mchangiaji Amesajiliwa / Donor added");
      e.target.reset();
      loadDonors();
    } catch (err) { toast(err.message, true); }
  });

  await loadDonors();
}

async function donorDetail(id) {
  const data = await api("/donors/" + id);
  const d = data.donor;
  const content = document.getElementById("content");
  content.innerHTML = `
    <button class="btn btn-sm" id="btnBack">← Rudi / Back</button>
    <h2 class="section mt">${esc(d.names)} <span class="muted">(${esc(d.donor_no)})</span></h2>
    <div class="card">
      <div class="detail-grid">
        <div class="item"><b>Tarehe ya kuzaliwa</b>${esc(d.birth_date || "—")}</div>
        <div class="item"><b>Jinsia</b>${esc(d.sex || "—")}</div>
        <div class="item"><b>Simu</b>${esc(d.phone || "—")}</div>
        <div class="item"><b>Wilaya</b>${esc(d.district || "—")}</div>
        <div class="item"><b>Halmashauri</b>${esc(d.council || "—")}</div>
        <div class="item"><b>Mara amedonate</b>${d.times_donated}</div>
        <div class="item"><b>Mwisho ku-donate</b>${esc(d.last_donation_date || "—")}</div>
        <div class="item"><b>Eligible hadi</b>${esc(d.eligible_after || "—")}</div>
      </div>
    </div>
    <div class="card">
      <h3>Michango ya awali / Previous donations</h3>
      <div class="table-scroll">${data.donations.length ? `
        <table><thead><tr>
          <th>Donation No</th><th>Tarehe</th><th>Sehemu</th><th>Hb</th><th>BP</th><th>ml</th><th>Majibu</th>
        </tr></thead><tbody>
        ${data.donations.map(x => `
          <tr>
            <td><b>${esc(x.donation_no)}</b></td>
            <td>${esc(x.donation_date)}</td>
            <td>${esc(x.venue || "—")}</td>
            <td>${x.hemoglobin || "—"}</td>
            <td>${esc(x.blood_pressure || "—")}</td>
            <td>${x.volume_ml}</td>
            <td>${x.result ? `${bgroup(x.result.abod)} ${badge(x.result.status)}` : '<span class="muted">Haijapimwa</span>'}</td>
          </tr>`).join("")}
        </tbody></table>` : '<p class="empty">Hakuna michango</p>'}</div>
    </div>`;
  document.getElementById("btnBack").addEventListener("click", () => showSection("donors"));
}

/* ---------------- donations ---------------- */

async function viewDonations(el) {
  el.innerHTML = `
    <h2 class="section">Michango / Donations</h2>
    <p class="section-sub">Kurekodi michango mipya na kuona michango ya awali</p>
    <div class="card">
      <h3>Rekodi mchango / Record donation</h3>
      <form id="donationForm" class="inline">
        <div><label>Donor ID *</label><input name="donor_id" type="number" required></div>
        <div><label>Sehemu / Venue</label><input name="venue"></div>
        <div><label>Wilaya</label><input name="district"></div>
        <div><label>Hemoglobin</label><input name="hemoglobin" type="number" step="0.1"></div>
        <div><label>BP</label><input name="blood_pressure" placeholder="120/80"></div>
        <div><label>Volume (ml)</label><input name="volume_ml" type="number" value="450"></div>
        <div><button class="btn btn-primary">Rekodi</button></div>
      </form>
    </div>
    <div class="card">
      <div class="filters">
        <div><label>Kuanzia</label><input id="dFrom" type="date"></div>
        <div><label>Hadi</label><input id="dTo" type="date"></div>
        <div><button class="btn" id="btnFilterDon">Chuja</button></div>
      </div>
      <div id="donationTable" class="table-scroll"></div>
    </div>`;

  async function loadDonations() {
    const from = document.getElementById("dFrom").value;
    const to = document.getElementById("dTo").value;
    const rows = await api(`/donations?date_from=${from}&date_to=${to}`);
    document.getElementById("donationTable").innerHTML = rows.length ? `
      <table><thead><tr>
        <th>Donation No</th><th>Donor</th><th>Tarehe</th><th>Sehemu</th>
        <th>Hb</th><th>ml</th><th>Majibu</th>
      </tr></thead><tbody>
      ${rows.map(d => `
        <tr>
          <td><b>${esc(d.donation_no)}</b></td>
          <td>${esc(d.donor_names || "")} <span class="muted">${esc(d.donor_no || "")}</span></td>
          <td>${esc(d.donation_date)}</td>
          <td>${esc(d.venue || "—")}</td>
          <td>${d.hemoglobin || "—"}</td>
          <td>${d.volume_ml}</td>
          <td>${d.result ? `${bgroup(d.result.abod)} ${badge(d.result.status)}` : '<span class="muted">Haijapimwa</span>'}</td>
        </tr>`).join("")}
      </tbody></table>` : '<p class="empty">Hakuna michango</p>';
  }

  document.getElementById("btnFilterDon").addEventListener("click", loadDonations);
  document.getElementById("donationForm").addEventListener("submit", async e => {
    e.preventDefault();
    const f = new FormData(e.target);
    const body = {
      donor_id: Number(f.get("donor_id")),
      venue: f.get("venue"), district: f.get("district"),
      hemoglobin: Number(f.get("hemoglobin") || 0),
      blood_pressure: f.get("blood_pressure"),
      volume_ml: Number(f.get("volume_ml") || 450),
    };
    try {
      const d = await api("/donations", { method: "POST", body: JSON.stringify(body) });
      toast(`Mchango ${d.donation_no} umerekodiwa`);
      e.target.reset();
      loadDonations();
    } catch (err) { toast(err.message, true); }
  });

  await loadDonations();
}

/* ---------------- recruiting ---------------- */

async function viewRecruiting(el) {
  el.innerHTML = `
    <h2 class="section">Urekruitimenti / Recruiting</h2>
    <p class="section-sub">Maombi ya viwanja, SMS kwa wachangiaji na takwimu za maeneo</p>
    <div class="grid-2">
      <div class="card">
        <h3>Omba sehemu ya zoezi / Request venue</h3>
        <form id="visitForm" class="inline">
          <div><label>Sehemu / Venue *</label><input name="venue" required></div>
          <div><label>Wilaya</label><input name="district"></div>
          <div><label>Tarehe *</label><input name="visit_date" type="date" required></div>
          <div><label>Watarajiwa / Expected</label><input name="expected_donors" type="number" value="50"></div>
          <div><button class="btn btn-primary">Omba</button></div>
        </form>
      </div>
      <div class="card">
        <h3>Tuma SMS kwa wachangiaji / Send SMS</h3>
        <form id="smsForm">
          <label>Ujumbe / Message</label>
          <textarea name="message" rows="2" required>Tafadhali njoo kuchangia damu wiki hii. Damu ni uzima!</textarea>
          <div class="filters mt">
            <div><label>Kwa nani</label>
              <select name="target">
                <option value="ELIGIBLE">Wanaostahili (eligible)</option>
                <option value="ALL">Wote (all)</option>
              </select></div>
            <div><button class="btn btn-primary">Tuma SMS</button></div>
          </div>
        </form>
      </div>
      <div class="card wide"><h3>Ziara za uwanjani / Site visits</h3><div id="visitTable" class="table-scroll"></div></div>
      <div class="card"><h3>Takwimu za maeneo / Area statistics</h3><div id="areaStats"></div></div>
      <div class="card"><h3>Historia ya SMS / SMS log</h3><div id="smsLog" class="table-scroll"></div></div>
    </div>`;

  async function loadAll() {
    const [visits, stats, sms] = await Promise.all([
      api("/visits"), api("/recruiter/stats"), api("/sms"),
    ]);
    document.getElementById("visitTable").innerHTML = visits.length ? `
      <table><thead><tr>
        <th>Tarehe</th><th>Sehemu</th><th>Wilaya</th><th>Watarajiwa</th>
        <th>Waliofanikisha</th><th>Hali</th><th></th>
      </tr></thead><tbody>
      ${visits.map(v => `
        <tr>
          <td>${esc(v.visit_date)}</td>
          <td><b>${esc(v.venue)}</b></td>
          <td>${esc(v.district || "—")}</td>
          <td>${v.expected_donors}</td>
          <td>${v.actual_donors || "—"}</td>
          <td>${badge(v.status)}</td>
          <td>${v.status === "REQUESTED"
            ? `<button class="btn btn-sm btn-approve" data-id="${v.id}">Kamilisha</button>` : ""}</td>
        </tr>`).join("")}
      </tbody></table>` : '<p class="empty">Hakuna ziara</p>';
    document.querySelectorAll("#visitTable [data-id]").forEach(btn =>
      btn.addEventListener("click", async () => {
        const n = Number(prompt("Idadi ya waliocahangia / Actual donors:", "0") || 0);
        try {
          await api(`/visits/${btn.dataset.id}/complete?actual_donors=${n}`, { method: "POST" });
          toast("Ziara imekamilika"); loadAll();
        } catch (err) { toast(err.message, true); }
      }));

    const areas = Object.entries(stats.donations_by_area).map(([k, v]) => ({ label: k || "—", value: v }));
    document.getElementById("areaStats").innerHTML = `
      <p class="muted mt" style="margin-bottom:10px">
        Ziara: ${stats.visits.total} jumla · ${stats.visits.requested} zinazosubiri ·
        ${stats.visits.done} zimekamilika · ${stats.visits.actual_donors} wachangiaji
      </p>
      ${barChart(areas, "alt") || '<p class="empty">Hakuna data</p>'}`;

    document.getElementById("smsLog").innerHTML = sms.length ? `
      <table><thead><tr><th>Muda</th><th>Mchangiaji</th><th>Simu</th><th>Ujumbe</th></tr></thead><tbody>
      ${sms.map(s => `
        <tr>
          <td class="muted">${esc(s.sent_at)}</td>
          <td>${esc(s.donor || "—")}</td>
          <td>${esc(s.phone)}</td>
          <td>${esc(s.message)}</td>
        </tr>`).join("")}
      </tbody></table>` : '<p class="empty">Hakuna SMS</p>';
  }

  document.getElementById("visitForm").addEventListener("submit", async e => {
    e.preventDefault();
    const f = new FormData(e.target);
    try {
      await api("/visits", {
        method: "POST",
        body: JSON.stringify({
          venue: f.get("venue"), district: f.get("district"),
          visit_date: f.get("visit_date"),
          expected_donors: Number(f.get("expected_donors") || 0),
        }),
      });
      toast("Ombi la ziara limetumwa");
      e.target.reset(); loadAll();
    } catch (err) { toast(err.message, true); }
  });

  document.getElementById("smsForm").addEventListener("submit", async e => {
    e.preventDefault();
    const f = new FormData(e.target);
    try {
      const r = await api("/sms", {
        method: "POST",
        body: JSON.stringify({ target: f.get("target"), message: f.get("message") }),
      });
      toast(`SMS ${r.sent} zimetumwa`);
      loadAll();
    } catch (err) { toast(err.message, true); }
  });

  await loadAll();
}

/* ---------------- laboratory ---------------- */

function resultRow(d, canApprove) {
  const r = d.result || {};
  const ttiBad = ["hiv", "hbv", "hcv", "syphilis"].some(f => r[f] === "POSITIVE");
  return `
    <tr>
      <td><b>${esc(d.donation_no)}</b></td>
      <td>${esc(d.donor_names || "")}<br><span class="muted">${esc(d.donor_no || "")}</span></td>
      <td>${esc(d.donation_date)}</td>
      <td>${bgroup(r.abod)}</td>
      <td>${badge(r.hiv)}</td><td>${badge(r.hbv)}</td>
      <td>${badge(r.hcv)}</td><td>${badge(r.syphilis)}</td>
      <td>${esc(r.machine_ref || "—")}</td>
      <td>${badge(r.status || "")}${r.approved_by ? `<br><span class="muted">${esc(r.approved_by)}</span>` : ""}</td>
      <td>
        <button class="btn btn-sm btn-edit" data-edit="${r.id}"
          data-d='${esc(JSON.stringify({ id: r.id, donation_id: d.id, abod: r.abod, hiv: r.hiv, hbv: r.hbv, hcv: r.hcv, syphilis: r.syphilis, machine_ref: r.machine_ref, notes: r.notes }))}'>Hariri</button>
        ${canApprove && r.status !== "APPROVED" && !ttiBad
          ? `<button class="btn btn-sm btn-approve" data-approve="${r.id}">Idhinisha</button>` : ""}
      </td>
    </tr>`;
}

function resultFormHTML() {
  return `
    <h3 id="resultFormTitle">Weka majibu / Enter results (ABOD & TTIs)</h3>
    <form id="resultForm" class="inline">
      <div><label>Donation ID *</label><input name="donation_id" type="number" required></div>
      <div><label>Kundi (ABOD) *</label><select name="abod" required>
        ${ABOD_GROUPS.map(g => `<option>${g}</option>`).join("")}</select></div>
      <div><label>HIV</label><select name="hiv"><option>NEGATIVE</option><option>POSITIVE</option></select></div>
      <div><label>HBV</label><select name="hbv"><option>NEGATIVE</option><option>POSITIVE</option></select></div>
      <div><label>HCV</label><select name="hcv"><option>NEGATIVE</option><option>POSITIVE</option></select></div>
      <div><label>VDRL</label><select name="syphilis"><option>NEGATIVE</option><option>POSITIVE</option></select></div>
      <div><label>Mashine ref / Machine ref</label><input name="machine_ref" placeholder="eg. ABOD-01:R4521"></div>
      <div class="full"><label>Maelezo / Notes</label><input name="notes"></div>
      <div>
        <button class="btn btn-primary" type="submit">Hifadhi</button>
        <button class="btn hidden" type="button" id="btnCancelEdit">Ghairi</button>
      </div>
    </form>`;
}

function bindResultForm(loadResults) {
  const form = document.getElementById("resultForm");
  form.addEventListener("submit", async e => {
    e.preventDefault();
    const f = new FormData(form);
    const body = {
      donation_id: Number(f.get("donation_id")), abod: f.get("abod"),
      hiv: f.get("hiv"), hbv: f.get("hbv"), hcv: f.get("hcv"),
      syphilis: f.get("syphilis"), machine_ref: f.get("machine_ref"),
      notes: f.get("notes"),
    };
    try {
      if (editingResultId) {
        await api("/lab/results/" + editingResultId, { method: "PUT", body: JSON.stringify(body) });
        toast("Majibu yamehaririwa");
      } else {
        await api("/lab/results", { method: "POST", body: JSON.stringify(body) });
        toast("Majibu yamewekwa");
      }
      resetResultForm();
      loadResults();
    } catch (err) { toast(err.message, true); }
  });
  document.getElementById("btnCancelEdit").addEventListener("click", resetResultForm);
}

function resetResultForm() {
  editingResultId = null;
  const form = document.getElementById("resultForm");
  if (!form) return;
  form.reset();
  document.getElementById("resultFormTitle").textContent = "Weka majibu / Enter results (ABOD & TTIs)";
  document.getElementById("btnCancelEdit").classList.add("hidden");
}

function bindResultActions(loadResults) {
  document.querySelectorAll("[data-approve]").forEach(btn =>
    btn.addEventListener("click", async () => {
      try {
        await api(`/lab/results/${btn.dataset.approve}/approve`, { method: "POST" });
        toast("Majibu yameidhinishwa / Approved");
        loadResults();
      } catch (err) { toast(err.message, true); }
    }));
  document.querySelectorAll("[data-edit]").forEach(btn =>
    btn.addEventListener("click", () => {
      const d = JSON.parse(btn.dataset.d);
      editingResultId = d.id;
      const form = document.getElementById("resultForm");
      form.donation_id.value = d.donation_id;
      form.abod.value = d.abod || "O+";
      form.hiv.value = d.hiv || "NEGATIVE";
      form.hbv.value = d.hbv || "NEGATIVE";
      form.hcv.value = d.hcv || "NEGATIVE";
      form.syphilis.value = d.syphilis || "NEGATIVE";
      form.machine_ref.value = d.machine_ref || "";
      form.notes.value = d.notes || "";
      document.getElementById("resultFormTitle").textContent = `Hariri majibu #${d.id} / Edit result`;
      document.getElementById("btnCancelEdit").classList.remove("hidden");
      window.scrollTo({ top: 0, behavior: "smooth" });
    }));
}

async function viewLab(el) {
  el.innerHTML = `
    <h2 class="section">Maabara / Laboratory</h2>
    <p class="section-sub">Majibu ya ABOD & TTIs, idhini na ripoti</p>
    <div class="card">${resultFormHTML()}</div>
    <div class="card">
      <h3>Michango inayosubiri vipimo / Pending testing</h3>
      <div id="pendingTable" class="table-scroll"></div>
    </div>
    <div class="card">
      <h3>Majibu yote / All results</h3>
      <div class="filters">
        <div><label>Hali</label><select id="fStatus">
          <option value="">Zote</option><option>REVIEWED</option>
          <option>APPROVED</option><option>DISCREPANCY</option></select></div>
        <div><label>Donation No kuanzia</label><input id="fNoFrom" type="number" placeholder="23000"></div>
        <div><label>Donation No hadi</label><input id="fNoTo" type="number" placeholder="25000"></div>
        <div><label>Kundi</label><select id="fAbod"><option value="">Zote</option>
          ${ABOD_GROUPS.map(g => `<option>${g}</option>`).join("")}</select></div>
        <div><label>TTI</label><select id="fTti">
          <option value="">Zote</option><option value="REACTIVE">Reactive</option>
          <option value="NON_REACTIVE">Non-reactive</option></select></div>
        <div><button class="btn btn-primary" id="btnFilterRes">Chuja</button></div>
        <div>
          <a class="btn btn-sm pdf-link" id="btnPdfResults" href="#" target="_blank">⬇ PDF majibu</a>
          <a class="btn btn-sm pdf-link" id="btnPdfProducts" href="#" target="_blank">⬇ PDF bidhaa</a>
        </div>
      </div>
      <div id="resultsTable" class="table-scroll"></div>
    </div>`;

  async function loadPending() {
    const rows = await api("/lab/pending");
    document.getElementById("pendingTable").innerHTML = rows.length ? `
      <table><thead><tr><th>Donation No</th><th>Mchangiaji</th><th>Tarehe</th><th>Sehemu</th><th></th></tr></thead><tbody>
      ${rows.map(d => `
        <tr>
          <td><b>${esc(d.donation_no)}</b></td>
          <td>${esc(d.donor_names || "")} <span class="muted">${esc(d.donor_no || "")}</span></td>
          <td>${esc(d.donation_date)}</td>
          <td>${esc(d.venue || "—")}</td>
          <td><button class="btn btn-sm" data-use="${d.id}">Weka majibu</button></td>
        </tr>`).join("")}
      </tbody></table>` : '<p class="empty">Hakuna michango inayosubiri</p>';
    document.querySelectorAll("[data-use]").forEach(b =>
      b.addEventListener("click", () => {
        const form = document.getElementById("resultForm");
        form.donation_id.value = b.dataset.use;
        window.scrollTo({ top: 0, behavior: "smooth" });
      }));
  }

  function filterQuery() {
    const p = new URLSearchParams();
    if (document.getElementById("fStatus").value) p.set("status", document.getElementById("fStatus").value);
    if (document.getElementById("fNoFrom").value) p.set("no_from", document.getElementById("fNoFrom").value);
    if (document.getElementById("fNoTo").value) p.set("no_to", document.getElementById("fNoTo").value);
    if (document.getElementById("fAbod").value) p.set("abod", document.getElementById("fAbod").value);
    if (document.getElementById("fTti").value) p.set("tti", document.getElementById("fTti").value);
    return p.toString();
  }

  async function loadResults() {
    const rows = await api("/lab/results?" + filterQuery());
    document.getElementById("resultsTable").innerHTML = rows.length ? `
      <table><thead><tr>
        <th>Donation No</th><th>Mchangiaji</th><th>Tarehe</th><th>ABOD</th>
        <th>HIV</th><th>HBV</th><th>HCV</th><th>VDRL</th><th>Mashine</th><th>Hali</th><th></th>
      </tr></thead><tbody>
      ${rows.map(d => resultRow(d, APPROVERS.has(user.role))).join("")}
      </tbody></table>` : '<p class="empty">Hakuna majibu</p>';
    bindResultActions(loadResults);
  }

  function updatePdfLinks() {
    const q = filterQuery();
    document.getElementById("btnPdfResults").href = `/api/pdf/results?${q}&token=${token}`;
    document.getElementById("btnPdfProducts").href = `/api/pdf/products?token=${token}`;
  }

  document.getElementById("btnFilterRes").addEventListener("click", () => { loadResults(); updatePdfLinks(); });
  bindResultForm(loadResults);
  updatePdfLinks();
  await Promise.all([loadPending(), loadResults()]);
}

/* ---------------- products ---------------- */

async function viewProducts(el) {
  el.innerHTML = `
    <h2 class="section">Bidhaa za Damu / Blood Products</h2>
    <p class="section-sub">Sorting (PRC, FFP, PLT, CRYO), labeling na kutuma hospitalini</p>
    <div class="card">
      <h3>Fanya sorting / Sort products</h3>
      <form id="sortForm" class="inline">
        <div><label>Donation ID *</label><input name="donation_id" type="number" required></div>
        <div class="full">
          <label>Aina / Types</label>
          <div class="filters" style="margin:0">
            ${PRODUCT_TYPES.map(t => `
              <label style="font-weight:400;text-transform:none;display:flex;align-items:center;gap:6px">
                <input type="checkbox" name="type" value="${t}" style="width:auto"> ${t}</label>`).join("")}
          </div>
        </div>
        <div><button class="btn btn-primary">Sort</button></div>
      </form>
    </div>
    <div class="card">
      <div class="filters">
        <div><label>Aina</label><select id="pType"><option value="">Zote</option>
          ${PRODUCT_TYPES.map(t => `<option>${t}</option>`).join("")}</select></div>
        <div><label>Hali</label><select id="pStatus">
          <option value="">Zote</option><option>QUARANTINE</option>
          <option>READY</option><option>ISSUED</option></select></div>
        <div><button class="btn btn-primary" id="btnFilterProd">Chuja</button></div>
      </div>
      <div id="productTable" class="table-scroll"></div>
    </div>`;

  async function loadHospitals() {
    return api("/hospitals");
  }

  async function loadProducts() {
    const p = new URLSearchParams();
    if (document.getElementById("pType").value) p.set("product_type", document.getElementById("pType").value);
    if (document.getElementById("pStatus").value) p.set("status", document.getElementById("pStatus").value);
    const [rows, hospitals] = await Promise.all([api("/products?" + p), loadHospitals()]);
    const hospitalOptions = hospitals.map(h =>
      `<option value="${h.id}">${esc(h.name)} (${esc(h.region)})</option>`).join("");
    document.getElementById("productTable").innerHTML = rows.length ? `
      <table><thead><tr>
        <th>Code</th><th>Aina</th><th>Donation</th><th>ABOD</th><th>Muda wa mwisho</th>
        <th>Hali</th><th>Salama?</th><th>Hospitali</th><th></th>
      </tr></thead><tbody>
      ${rows.map(pr => `
        <tr>
          <td><b>${esc(pr.product_code)}</b></td>
          <td>${esc(pr.product_type)}</td>
          <td>${esc(pr.donation_no)}</td>
          <td>${bgroup(pr.abod)}</td>
          <td>${esc(pr.expiry_date || "—")}</td>
          <td>${badge(pr.status)}</td>
          <td>${pr.safe ? '<span class="badge ok">SAFE</span>' : '<span class="badge bad">NOT SAFE</span>'}</td>
          <td>${esc(pr.hospital || "—")}</td>
          <td>
            ${pr.status === "QUARANTINE" ? `<button class="btn btn-sm btn-warn" data-label="${pr.id}">Lebeli</button>` : ""}
            ${pr.status === "READY" ? `
              <select data-hosp="${pr.id}" style="width:auto">${hospitalOptions}</select>
              <button class="btn btn-sm btn-approve" data-issue="${pr.id}">Tuma</button>` : ""}
          </td>
        </tr>`).join("")}
      </tbody></table>` : '<p class="empty">Hakuna bidhaa</p>';

    document.querySelectorAll("[data-label]").forEach(b =>
      b.addEventListener("click", async () => {
        try {
          await api(`/products/${b.dataset.label}/label`, { method: "POST" });
          toast("Bidhaa imelebeliwa / Labeled READY");
          loadProducts();
        } catch (err) { toast(err.message, true); }
      }));
    document.querySelectorAll("[data-issue]").forEach(b =>
      b.addEventListener("click", async () => {
        const hospId = document.querySelector(`[data-hosp="${b.dataset.issue}"]`).value;
        try {
          await api(`/products/${b.dataset.issue}/issue`, {
            method: "POST", body: JSON.stringify({ hospital_id: Number(hospId) }),
          });
          toast("Bidhaa imetumwa hospitalini / Issued");
          loadProducts();
        } catch (err) { toast(err.message, true); }
      }));
  }

  document.getElementById("btnFilterProd").addEventListener("click", loadProducts);
  document.getElementById("sortForm").addEventListener("submit", async e => {
    e.preventDefault();
    const types = [...document.querySelectorAll("#sortForm input[name=type]:checked")].map(c => c.value);
    if (!types.length) { toast("Chagua angalau aina moja", true); return; }
    try {
      await api("/products/sort", {
        method: "POST",
        body: JSON.stringify({
          donation_id: Number(document.getElementById("sortForm").donation_id.value),
          types,
        }),
      });
      toast("Bidhaa zimeundwa / Products created");
      loadProducts();
    } catch (err) { toast(err.message, true); }
  });

  await loadProducts();
}

/* ---------------- council ---------------- */

async function viewCouncil(el) {
  const rows = await api("/council/results");
  el.innerHTML = `
    <h2 class="section">Halmashauri / Council View</h2>
    <p class="section-sub">Majibu yaliyoidhinishwa tu ${user.council ? `— ${esc(user.council)}` : "(maeneo yote)"} · view only</p>
    <div class="card table-scroll">
      ${rows.length ? `
        <table><thead><tr>
          <th>Donation No</th><th>Mchangiaji</th><th>Wilaya</th><th>Tarehe</th>
          <th>ABOD</th><th>HIV</th><th>HBV</th><th>HCV</th><th>VDRL</th><th>Idhini</th>
        </tr></thead><tbody>
        ${rows.map(d => `
          <tr>
            <td><b>${esc(d.donation_no)}</b></td>
            <td>${esc(d.donor_names || "")}</td>
            <td>${esc(d.district || "—")}</td>
            <td>${esc(d.donation_date)}</td>
            <td>${bgroup(d.result.abod)}</td>
            <td>${badge(d.result.hiv)}</td><td>${badge(d.result.hbv)}</td>
            <td>${badge(d.result.hcv)}</td><td>${badge(d.result.syphilis)}</td>
            <td>${esc(d.result.approved_by || "")}</td>
          </tr>`).join("")}
        </tbody></table>` : '<p class="empty">Hakuna majibu yaliyoidhinishwa</p>'}
    </div>`;
}

/* ---------------- init ---------------- */

document.getElementById("loginForm").addEventListener("submit", doLogin);
document.getElementById("btnLogout").addEventListener("click", doLogout);

restoreSession().then(ok => { if (ok) enterApp(); });
