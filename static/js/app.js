const STATUSES = ["Wishlist", "Applied", "Screening", "Interviewing", "Offer", "Accepted", "Rejected", "Withdrawn"];

let state = {
  applications: [],
  counts: {},
  status: "",
  q: "",
  sort: "created_desc",
  currentDetailId: null,
};

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

function toast(msg) {
  const el = $("#toast");
  el.textContent = msg;
  el.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { el.hidden = true; }, 2500);
}

function fmtMoney(app) {
  if (!app.salary_min && !app.salary_max) return null;
  const cur = app.salary_currency || "";
  const period = app.salary_period ? `/${app.salary_period.toLowerCase()}` : "";
  if (app.salary_min && app.salary_max && app.salary_min !== app.salary_max) {
    return `${cur} ${Math.round(app.salary_min).toLocaleString()}–${Math.round(app.salary_max).toLocaleString()}${period}`;
  }
  const val = app.salary_min || app.salary_max;
  return `${cur} ${Math.round(val).toLocaleString()}${period}`;
}

function initials(name) {
  if (!name) return "?";
  return name.trim().split(/\s+/).slice(0, 2).map(w => w[0]).join("").toUpperCase();
}

function populateStatusSelects() {
  const filter = $("#statusFilter");
  const detail = $("#f_status");
  STATUSES.forEach(s => {
    filter.insertAdjacentHTML("beforeend", `<option value="${s}">${s}</option>`);
    detail.insertAdjacentHTML("beforeend", `<option value="${s}">${s}</option>`);
  });
}

async function fetchApplications() {
  const params = new URLSearchParams();
  if (state.status) params.set("status", state.status);
  if (state.q) params.set("q", state.q);
  if (state.sort) params.set("sort", state.sort);
  const res = await fetch(`/api/applications?${params}`);
  const data = await res.json();
  state.applications = data.applications;
  state.counts = data.counts;
  renderStats();
  renderCards();
}

function renderStats() {
  const total = Object.values(state.counts).reduce((a, b) => a + b, 0);
  const bar = $("#statsBar");
  let html = `<div class="stat-chip ${state.status === "" ? "active" : ""}" data-status="">All <strong>${total}</strong></div>`;
  STATUSES.forEach(s => {
    if (!state.counts[s]) return;
    html += `<div class="stat-chip ${state.status === s ? "active" : ""}" data-status="${s}">${s} <strong>${state.counts[s]}</strong></div>`;
  });
  bar.innerHTML = html;
  bar.querySelectorAll(".stat-chip").forEach(chip => {
    chip.addEventListener("click", () => {
      state.status = chip.dataset.status;
      $("#statusFilter").value = state.status;
      fetchApplications();
    });
  });
}

function renderCards() {
  const grid = $("#cardsGrid");
  const empty = $("#emptyState");
  if (!state.applications.length) {
    grid.innerHTML = "";
    empty.hidden = false;
    return;
  }
  empty.hidden = true;

  grid.innerHTML = state.applications.map(app => {
    const logo = app.company_logo
      ? `<img src="${app.company_logo}" alt="" onerror="this.parentElement.textContent='${initials(app.company)}'">`
      : initials(app.company);
    const money = fmtMoney(app);
    const chips = [app.work_mode, app.employment_type, app.location].filter(Boolean);
    const stars = app.rating ? "★".repeat(app.rating) + "☆".repeat(5 - app.rating) : "";
    const dateLabel = app.applied_date ? `Applied ${app.applied_date}` : `Added ${(app.created_at || "").slice(0, 10)}`;

    return `
      <article class="card" data-id="${app.id}">
        <div class="card-top">
          <div class="card-logo">${logo}</div>
          <div class="card-title-block">
            <p class="card-title">${escapeHtml(app.title || "Untitled role")}</p>
            <p class="card-company">${escapeHtml(app.company || "Unknown company")}</p>
          </div>
        </div>
        ${chips.length ? `<div class="card-meta">${chips.map(c => `<span class="chip">${escapeHtml(c)}</span>`).join("")}</div>` : ""}
        ${money ? `<div class="card-salary">💰 ${escapeHtml(money)}</div>` : ""}
        <div class="card-bottom">
          <select class="status-select status-${app.status}" data-id="${app.id}">
            ${STATUSES.map(s => `<option value="${s}" ${s === app.status ? "selected" : ""}>${s}</option>`).join("")}
          </select>
          <span class="card-rating">${stars}</span>
        </div>
        <div class="card-date">${dateLabel}${app.deadline ? ` · Deadline ${app.deadline}` : ""}</div>
      </article>
    `;
  }).join("");

  grid.querySelectorAll(".card").forEach(card => {
    card.addEventListener("click", (e) => {
      if (e.target.closest(".status-select")) return;
      openDetail(Number(card.dataset.id));
    });
  });
  grid.querySelectorAll(".status-select").forEach(sel => {
    sel.addEventListener("click", e => e.stopPropagation());
    sel.addEventListener("change", async () => {
      await fetch(`/api/applications/${sel.dataset.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: sel.value }),
      });
      sel.className = `status-select status-${sel.value}`;
      fetchApplications();
    });
  });
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str ?? "";
  return div.innerHTML;
}

// ---------- Add modal ----------
function openModal(id) { $(`#${id}`).hidden = false; }
function closeModal(id) { $(`#${id}`).hidden = true; }

$$("[data-close]").forEach(btn => {
  btn.addEventListener("click", () => closeModal(btn.dataset.close));
});
$$(".modal-backdrop").forEach(backdrop => {
  backdrop.addEventListener("click", (e) => {
    if (e.target === backdrop) backdrop.hidden = true;
  });
});

$("#addBtn").addEventListener("click", () => {
  $("#addUrlInput").value = "";
  $("#addStatus").hidden = true;
  openModal("addModal");
  $("#addUrlInput").focus();
});

$("#addUrlInput").addEventListener("keydown", (e) => {
  if (e.key === "Enter") submitAdd();
});
$("#addSubmitBtn").addEventListener("click", submitAdd);

async function submitAdd() {
  const url = $("#addUrlInput").value.trim();
  if (!url) return;
  const statusEl = $("#addStatus");
  statusEl.hidden = false;
  statusEl.className = "scrape-status loading";
  statusEl.textContent = "Fetching and analyzing the job page…";
  $("#addSubmitBtn").disabled = true;

  try {
    const res = await fetch("/api/applications", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Failed to add");

    statusEl.className = `scrape-status ${data.scrape_status || "ok"}`;
    statusEl.textContent = data.scrape_message || "Added.";

    await fetchApplications();
    setTimeout(() => {
      closeModal("addModal");
      openDetail(data.id);
    }, 700);
  } catch (err) {
    statusEl.className = "scrape-status failed";
    statusEl.textContent = err.message;
  } finally {
    $("#addSubmitBtn").disabled = false;
  }
}

// ---------- Detail modal ----------
async function openDetail(id) {
  const res = await fetch(`/api/applications/${id}`);
  if (!res.ok) { toast("Could not load application"); return; }
  const app = await res.json();
  state.currentDetailId = id;

  $("#detailTitle").textContent = app.title || "Application";
  const fieldMap = {
    title: "f_title", company: "f_company", url: "f_url", location: "f_location",
    work_mode: "f_work_mode", employment_type: "f_employment_type", source: "f_source",
    tags: "f_tags", description: "f_description", salary_min: "f_salary_min",
    salary_max: "f_salary_max", salary_currency: "f_salary_currency", salary_period: "f_salary_period",
    status: "f_status", date_posted: "f_date_posted", deadline: "f_deadline",
    applied_date: "f_applied_date", rating: "f_rating", next_action: "f_next_action",
    next_action_date: "f_next_action_date", contact_name: "f_contact_name",
    contact_email: "f_contact_email", contact_phone: "f_contact_phone",
    resume_version: "f_resume_version", notes: "f_notes",
  };
  Object.entries(fieldMap).forEach(([key, id]) => {
    $(`#${id}`).value = app[key] ?? "";
  });
  $("#f_referral").checked = !!app.referral;
  $("#f_cover_letter_used").checked = !!app.cover_letter_used;
  $("#openLinkBtn").href = app.url;

  const notice = $("#detailScrapeNotice");
  if (app.scrape_status && app.scrape_status !== "ok") {
    notice.hidden = false;
    notice.className = `scrape-status ${app.scrape_status}`;
    notice.textContent = app.scrape_message || "";
  } else {
    notice.hidden = true;
  }

  renderTimeline(app.events || []);
  openModal("detailModal");
}

function renderTimeline(events) {
  const list = $("#timelineList");
  if (!events.length) {
    list.innerHTML = `<p class="hint">No events yet.</p>`;
    return;
  }
  list.innerHTML = events.map(ev => `
    <div class="timeline-item">
      <span class="t-date">${ev.event_date || ""}</span>
      <span><span class="t-type">${escapeHtml(ev.event_type)}</span>${escapeHtml(ev.description || "")}</span>
      <button class="t-del" data-eid="${ev.id}">✕</button>
    </div>
  `).join("");
  list.querySelectorAll(".t-del").forEach(btn => {
    btn.addEventListener("click", async () => {
      await fetch(`/api/events/${btn.dataset.eid}`, { method: "DELETE" });
      openDetail(state.currentDetailId);
    });
  });
}

$("#addEventBtn").addEventListener("click", async () => {
  const description = $("#eventDescription").value.trim();
  if (!description) return;
  await fetch(`/api/applications/${state.currentDetailId}/events`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      event_type: $("#eventType").value,
      event_date: $("#eventDate").value || null,
      description,
    }),
  });
  $("#eventDescription").value = "";
  openDetail(state.currentDetailId);
});

$("#saveBtn").addEventListener("click", async () => {
  const id = state.currentDetailId;
  const payload = {
    title: $("#f_title").value, company: $("#f_company").value, url: $("#f_url").value,
    location: $("#f_location").value, work_mode: $("#f_work_mode").value,
    employment_type: $("#f_employment_type").value, source: $("#f_source").value,
    tags: $("#f_tags").value, description: $("#f_description").value,
    salary_min: $("#f_salary_min").value || null, salary_max: $("#f_salary_max").value || null,
    salary_currency: $("#f_salary_currency").value, salary_period: $("#f_salary_period").value,
    status: $("#f_status").value, date_posted: $("#f_date_posted").value || null,
    deadline: $("#f_deadline").value || null, applied_date: $("#f_applied_date").value || null,
    rating: $("#f_rating").value || null, next_action: $("#f_next_action").value,
    next_action_date: $("#f_next_action_date").value || null,
    contact_name: $("#f_contact_name").value, contact_email: $("#f_contact_email").value,
    contact_phone: $("#f_contact_phone").value, resume_version: $("#f_resume_version").value,
    notes: $("#f_notes").value, referral: $("#f_referral").checked ? 1 : 0,
    cover_letter_used: $("#f_cover_letter_used").checked ? 1 : 0,
  };
  const res = await fetch(`/api/applications/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (res.ok) {
    toast("Saved");
    closeModal("detailModal");
    fetchApplications();
  } else {
    toast("Failed to save");
  }
});

$("#deleteBtn").addEventListener("click", async () => {
  if (!confirm("Delete this application? This cannot be undone.")) return;
  await fetch(`/api/applications/${state.currentDetailId}`, { method: "DELETE" });
  closeModal("detailModal");
  fetchApplications();
  toast("Deleted");
});

$("#rescrapeBtn").addEventListener("click", async () => {
  $("#rescrapeBtn").disabled = true;
  $("#rescrapeBtn").textContent = "Analyzing…";
  try {
    await fetch(`/api/applications/${state.currentDetailId}/rescrape`, { method: "POST" });
    await openDetail(state.currentDetailId);
    toast("Re-analyzed link");
  } finally {
    $("#rescrapeBtn").disabled = false;
    $("#rescrapeBtn").textContent = "Re-analyze Link";
  }
});

$("#exportBtn").addEventListener("click", () => {
  const params = new URLSearchParams();
  if (state.status) params.set("status", state.status);
  if (state.q) params.set("q", state.q);
  if (state.sort) params.set("sort", state.sort);
  window.location = `/api/export/pdf?${params}`;
});

// ---------- Toolbar ----------
let searchDebounce;
$("#searchInput").addEventListener("input", (e) => {
  clearTimeout(searchDebounce);
  searchDebounce = setTimeout(() => {
    state.q = e.target.value.trim();
    fetchApplications();
  }, 300);
});
$("#statusFilter").addEventListener("change", (e) => {
  state.status = e.target.value;
  fetchApplications();
});
$("#sortSelect").addEventListener("change", (e) => {
  state.sort = e.target.value;
  fetchApplications();
});

// ---------- Init ----------
populateStatusSelects();
fetchApplications();
