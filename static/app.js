/* =====================================================================
   Snapchat Memories Viewer — Frontend
   ===================================================================== */

// ── State ──────────────────────────────────────────────────────────────
const state = {
  page:           1,
  loading:        false,
  done:           false,
  mediaType:      "",
  dateFrom:       "",
  dateTo:         "",
  monthDayFrom:   null,   // "MM-DD" cross-year filter
  monthDayTo:     null,
  monthFilter:    null,   // "MM" cross-year month filter
  yearFilter:     null,   // integer, specifiek jaar
  availableYears: [],     // [2019, 2020, ..., 2026] ascending
  locLat:         null,
  locLon:         null,
  radiusKm:       5,
  allMemories:    [],
  lbIndex:        -1,
  mapVisible:     false,
  map:            null,
  markerLayer:    null,
};

// ── Boot ───────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", async () => {
  initMap();
  await loadStats();
  await loadDateBounds();
  applyFilters();
  initIntersectionObserver();
  initKeyboard();
});

// ── Stats ──────────────────────────────────────────────────────────────
async function loadStats() {
  const data = await api("/api/stats");
  const el = document.getElementById("stats-badge");
  if (el) {
    el.textContent =
      `${data.total} herinneringen  •  ${data.images} foto's  •  ${data.videos} video's`;
    el.classList.remove("hidden");
  }
}

// ── Date bounds → set min/max on pickers + populate year selector ──────
async function loadDateBounds() {
  const data = await api("/api/date-bounds");
  if (data.min_date) {
    const minDate = data.min_date.slice(0, 10);
    const maxDate = data.max_date.slice(0, 10);
    document.getElementById("date-from").min = minDate;
    document.getElementById("date-from").max = maxDate;
    document.getElementById("date-to").min   = minDate;
    document.getElementById("date-to").max   = maxDate;

    const minYear = parseInt(data.min_date.slice(0, 4));
    const maxYear = new Date().getFullYear();
    state.availableYears = Array.from({ length: maxYear - minYear + 1 }, (_, i) => minYear + i);
    populateYearSelect();
    updateYearNav();
  }
}

function populateYearSelect() {
  const sel = document.getElementById("year-select");
  while (sel.options.length > 1) sel.remove(1);
  for (let i = state.availableYears.length - 1; i >= 0; i--) {
    const opt = document.createElement("option");
    opt.value = state.availableYears[i];
    opt.textContent = state.availableYears[i];
    sel.appendChild(opt);
  }
}

function setYearFromSelect() {
  const val = document.getElementById("year-select").value;
  state.yearFilter   = val ? parseInt(val) : null;
  state.monthDayFrom = null;
  state.monthDayTo   = null;
  state.monthFilter  = null;
  state.dateFrom     = "";
  state.dateTo       = "";
  document.getElementById("date-from").value = "";
  document.getElementById("date-to").value   = "";
  document.querySelectorAll(".quick-btn").forEach(b => b.classList.remove("active"));
  updateYearNav();
  applyFilters();
}

function navYear(dir) {
  // dir: -1 = ouder jaar, +1 = nieuwer jaar
  const years = state.availableYears;
  if (!years.length) return;
  if (state.yearFilter === null) {
    state.yearFilter = dir > 0 ? years[years.length - 1] : years[0];
  } else {
    const idx    = years.indexOf(state.yearFilter);
    const newIdx = idx + dir;
    if (newIdx < 0 || newIdx >= years.length) return;
    state.yearFilter = years[newIdx];
  }
  document.getElementById("year-select").value = state.yearFilter;
  state.monthDayFrom = null;
  state.monthDayTo   = null;
  state.monthFilter  = null;
  state.dateFrom     = "";
  state.dateTo       = "";
  document.getElementById("date-from").value = "";
  document.getElementById("date-to").value   = "";
  document.querySelectorAll(".quick-btn").forEach(b => b.classList.remove("active"));
  updateYearNav();
  applyFilters();
}

function updateYearNav() {
  const years = state.availableYears;
  const prev  = document.getElementById("year-prev");
  const next  = document.getElementById("year-next");
  if (!prev || !next || !years.length) return;
  if (state.yearFilter === null) {
    prev.disabled = false;
    next.disabled = false;
  } else {
    const idx     = years.indexOf(state.yearFilter);
    prev.disabled = idx <= 0;
    next.disabled = idx >= years.length - 1;
  }
}

// ── Filters ────────────────────────────────────────────────────────────
function applyFilters() {
  state.dateFrom  = document.getElementById("date-from").value;
  state.dateTo    = document.getElementById("date-to").value;
  state.page      = 1;
  state.done      = false;
  state.allMemories = [];
  document.getElementById("grid").innerHTML = "";
  document.getElementById("empty").classList.add("hidden");
  loadPage();
}

function clearFilters() {
  document.getElementById("date-from").value = "";
  document.getElementById("date-to").value   = "";
  state.monthDayFrom = null;
  state.monthDayTo   = null;
  state.monthFilter  = null;
  state.yearFilter   = null;
  state.locLat       = null;
  state.locLon       = null;
  state.radiusKm     = 5;
  const sel = document.getElementById("year-select");
  if (sel) sel.value = "";
  updateYearNav();
  document.querySelectorAll(".quick-btn").forEach(b => b.classList.remove("active"));
  setMediaType("", false);
  applyFilters();
}

function setMediaType(type, doApply = true) {
  state.mediaType = type;
  document.getElementById("btn-all").classList.toggle("active",   type === "");
  document.getElementById("btn-image").classList.toggle("active", type === "image");
  document.getElementById("btn-video").classList.toggle("active", type === "video");
  if (doApply) applyFilters();
}

function setQuickDate(range) {
  const now = new Date();
  document.querySelectorAll(".quick-btn").forEach(b => b.classList.remove("active"));
  event.target.classList.add("active");

  // Reset date pickers en cross-year state
  state.dateFrom     = "";
  state.dateTo       = "";
  state.monthDayFrom = null;
  state.monthDayTo   = null;
  state.monthFilter  = null;
  state.yearFilter   = null;
  document.getElementById("date-from").value = "";
  document.getElementById("date-to").value   = "";
  const sel = document.getElementById("year-select");
  if (sel) sel.value = "";
  updateYearNav();

  const mm = String(now.getMonth() + 1).padStart(2, "0");
  const dd = String(now.getDate()).padStart(2, "0");

  if (range === "today") {
    // Dezelfde dag in alle jaren: bijv. "03-18"
    state.monthDayFrom = `${mm}-${dd}`;
    state.monthDayTo   = `${mm}-${dd}`;
  } else if (range === "week") {
    // Dezelfde week-periode in alle jaren
    const weekAgo = new Date(now);
    weekAgo.setDate(weekAgo.getDate() - 6);
    const wmm = String(weekAgo.getMonth() + 1).padStart(2, "0");
    const wdd = String(weekAgo.getDate()).padStart(2, "0");
    state.monthDayFrom = `${wmm}-${wdd}`;
    state.monthDayTo   = `${mm}-${dd}`;
  } else if (range === "month") {
    // Dezelfde maand in alle jaren
    state.monthFilter = mm;
  } else if (range === "year") {
    // Dit jaar (exacte jaarfilter)
    state.yearFilter = now.getFullYear();
    if (sel) sel.value = state.yearFilter;
    updateYearNav();
  } else if (range === "lastyear") {
    state.yearFilter = now.getFullYear() - 1;
    if (sel) sel.value = state.yearFilter;
    updateYearNav();
  }

  applyFilters();
}

// ── API helper ─────────────────────────────────────────────────────────
async function api(url) {
  const resp = await fetch(url);
  return resp.json();
}

// ── Grid loading ───────────────────────────────────────────────────────
async function loadPage() {
  if (state.loading || state.done) return;
  state.loading = true;

  const loadingEl = document.getElementById("loading");
  loadingEl.classList.remove("hidden");

  const params = new URLSearchParams({ page: state.page, per_page: 50 });
  if (state.dateFrom)      params.set("date_from",      state.dateFrom);
  if (state.dateTo)        params.set("date_to",        state.dateTo);
  if (state.monthDayFrom)  params.set("month_day_from", state.monthDayFrom);
  if (state.monthDayTo)    params.set("month_day_to",   state.monthDayTo);
  if (state.monthFilter)   params.set("month",          state.monthFilter);
  if (state.yearFilter)    params.set("year",           state.yearFilter);
  if (state.mediaType)     params.set("media_type",     state.mediaType);
  if (state.locLat !== null) {
    params.set("lat",       state.locLat);
    params.set("lon",       state.locLon);
    params.set("radius_km", state.radiusKm);
  }

  try {
    const data = await api(`/api/memories?${params}`);
    const items = data.items || [];

    if (items.length === 0 && state.page === 1) {
      document.getElementById("empty").classList.remove("hidden");
    }
    if (items.length < 50) {
      state.done = true;
    }

    const startIndex = state.allMemories.length;
    state.allMemories.push(...items);
    renderItems(items, startIndex);
    state.page++;
  } catch (e) {
    console.error("Fout bij laden:", e);
  } finally {
    state.loading = false;
    loadingEl.classList.add("hidden");
  }
}

function renderItems(items, startIndex) {
  const grid = document.getElementById("grid");
  items.forEach((mem, i) => {
    const idx = startIndex + i;
    const div = document.createElement("div");
    div.className = "thumb";
    div.dataset.index = idx;
    div.onclick = () => openLightbox(idx);

    if (mem.media_type === "video") {
      if (mem.poster) {
        const img = document.createElement("img");
        img.src = `${window.MEDIA_BASE}/${mem.poster}`;
        img.loading = "lazy";
        img.alt = "";
        div.appendChild(img);
      } else {
        // Geen poster: toon donkere placeholder (voorkomt blauwe browser-default)
        const placeholder = document.createElement("div");
        placeholder.style.cssText = "width:100%;height:100%;background:#1a1a2e;";
        div.appendChild(placeholder);
      }
      // Altijd zichtbaar gecentreerd play-icoon
      div.insertAdjacentHTML("beforeend", `
        <div class="play-overlay">
          <div class="play-circle">
            <svg viewBox="0 0 24 24" style="width:16px;height:16px;fill:white;margin-left:2px;">
              <path d="M8 5v14l11-7z"/>
            </svg>
          </div>
        </div>`);
    } else {
      const img = document.createElement("img");
      img.src = `${window.MEDIA_BASE}/${mem.filename}`;
      img.loading = "lazy";
      img.alt = "";
      div.appendChild(img);
    }

    // Overlay info bar
    const info = document.createElement("div");
    info.className = "overlay-info";

    const dateLabel = document.createElement("span");
    dateLabel.className = "date-label";
    dateLabel.textContent = formatDate(mem.date_utc);
    info.appendChild(dateLabel);

    if (mem.media_type === "video") {
      info.insertAdjacentHTML("beforeend",
        `<svg class="video-icon w-3 h-3 fill-current" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>`);
    }
    div.appendChild(info);

    // GPS dot
    if (mem.latitude) {
      const dot = document.createElement("div");
      dot.className = "loc-dot";
      div.appendChild(dot);
    }

    grid.appendChild(div);
  });
}

function formatDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleDateString("nl-NL", { day: "2-digit", month: "short", year: "numeric" });
}

function formatDateFull(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleString("nl-NL", {
    weekday: "long", day: "numeric", month: "long", year: "numeric",
    hour: "2-digit", minute: "2-digit"
  });
}

// ── Infinite scroll ────────────────────────────────────────────────────
function initIntersectionObserver() {
  const sentinel = document.getElementById("sentinel");
  const observer = new IntersectionObserver(entries => {
    if (entries[0].isIntersecting) loadPage();
  }, { rootMargin: "200px" });
  observer.observe(sentinel);
}

// ── Lightbox ───────────────────────────────────────────────────────────
function openLightbox(idx) {
  state.lbIndex = idx;
  renderLightbox();
  document.getElementById("lightbox").classList.remove("hidden");
  document.body.style.overflow = "hidden";
}

function closeLightbox() {
  document.getElementById("lightbox").classList.add("hidden");
  document.getElementById("lb-content").innerHTML = "";
  document.body.style.overflow = "";
}

function lightboxNav(dir) {
  const newIdx = state.lbIndex + dir;
  if (newIdx < 0 || newIdx >= state.allMemories.length) return;
  // Load more if near end
  if (newIdx >= state.allMemories.length - 5) loadPage();
  state.lbIndex = newIdx;
  renderLightbox();
}

function renderLightbox() {
  const mem = state.allMemories[state.lbIndex];
  if (!mem) return;

  const content = document.getElementById("lb-content");
  content.innerHTML = "";

  if (mem.media_type === "video") {
    const video = document.createElement("video");
    video.src = `${window.MEDIA_BASE}/${mem.filename}`;
    video.controls = true;
    video.autoplay = true;
    content.appendChild(video);
  } else {
    const img = document.createElement("img");
    img.src = `${window.MEDIA_BASE}/${mem.filename}`;
    img.alt = "";
    content.appendChild(img);
  }

  const infoEl = document.getElementById("lb-info");
  let info = formatDateFull(mem.date_utc);
  if (mem.latitude) info += ` · ${mem.latitude.toFixed(4)}, ${mem.longitude.toFixed(4)}`;
  infoEl.textContent = info;

  // Download-link bijwerken
  const dlBtn = document.getElementById("lb-download");
  if (dlBtn) {
    dlBtn.href = `${window.MEDIA_BASE}/${mem.filename}`;
    dlBtn.download = mem.filename;
  }

  // Show/hide nav arrows
  document.getElementById("lb-prev").style.display = state.lbIndex > 0 ? "" : "none";
  document.getElementById("lb-next").style.display =
    state.lbIndex < state.allMemories.length - 1 ? "" : "none";
}

function initKeyboard() {
  document.addEventListener("keydown", e => {
    const lb = document.getElementById("lightbox");
    if (lb.classList.contains("hidden")) return;
    if (e.key === "Escape")      closeLightbox();
    if (e.key === "ArrowLeft")   lightboxNav(-1);
    if (e.key === "ArrowRight")  lightboxNav(1);
  });
  // Close on backdrop click
  document.getElementById("lightbox").addEventListener("click", e => {
    if (e.target === e.currentTarget) closeLightbox();
  });
}

// ── Map ─────────────────────────────────────────────────────────────────
function initMap() {
  const mapEl = document.getElementById("map");
  if (!mapEl) return;

  state.map = L.map("map", { preferCanvas: true }).setView([52.37, 4.9], 5);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "© OpenStreetMap contributors",
    maxZoom: 19,
  }).addTo(state.map);

  state.markerLayer = L.markerClusterGroup({ chunkedLoading: true });
  state.map.addLayer(state.markerLayer);
}

async function loadMapPoints() {
  if (!state.map) return;
  state.markerLayer.clearLayers();

  const points = await api("/api/map-points");
  points.forEach(p => {
    const marker = L.marker([p.latitude, p.longitude]);
    const thumb  = p.poster
      ? `<img src="${window.MEDIA_BASE}/${p.poster}" style="width:120px;height:120px;object-fit:cover;border-radius:4px;">`
      : (p.filename && !p.filename.endsWith(".mp4")
        ? `<img src="${window.MEDIA_BASE}/${p.filename}" style="width:120px;height:120px;object-fit:cover;border-radius:4px;">`
        : `<div style="width:120px;height:60px;display:flex;align-items:center;justify-content:center;background:#1f2937;border-radius:4px;color:#9ca3af;font-size:12px;">Video</div>`);

    marker.bindPopup(`
      <div style="text-align:center">
        ${thumb}
        <div style="font-size:11px;margin-top:4px;color:#9ca3af">${formatDate(p.date_utc)}</div>
      </div>
    `);
    marker.on("click", () => {
      const idx = state.allMemories.findIndex(m => m.id === p.id);
      if (idx !== -1) openLightbox(idx);
    });
    state.markerLayer.addLayer(marker);
  });
}

function toggleMap() {
  const panel     = document.getElementById("map-panel");
  const btn       = document.getElementById("map-toggle");
  state.mapVisible = !state.mapVisible;

  if (state.mapVisible) {
    panel.classList.remove("hidden");
    btn.classList.add("bg-snap-yellow", "text-black", "border-snap-yellow");
    btn.classList.remove("bg-gray-800", "text-white", "border-gray-700");
    // Leaflet needs a size invalidation after show
    setTimeout(() => {
      if (state.map) state.map.invalidateSize();
    }, 50);
    loadMapPoints();
  } else {
    panel.classList.add("hidden");
    btn.classList.remove("bg-snap-yellow", "text-black", "border-snap-yellow");
    btn.classList.add("bg-gray-800", "text-white", "border-gray-700");
  }
}
