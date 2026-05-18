/* Facilito SPA — vanilla JS */
const App = (() => {

  // ── State ────────────────────────────────────────────────────────────────
  let state = {
    facilitator: null,
    session: null,
    sessions: [],
    practices: [],
    participants: [],
    specialPractices: [],
    teams: [],
    clients: [],
    mascots: [],
    currentMascot: null,
    mobileAgentOpen: false,
    chatHistory: [],      // mirrored locally for display
  };

  // ── API helpers ──────────────────────────────────────────────────────────
  async function api(method, path, body) {
    const opts = { method, headers: { "Content-Type": "application/json" } };
    if (body) opts.body = JSON.stringify(body);
    const r = await fetch(path, opts);
    if (!r.ok) { const t = await r.text(); throw new Error(t); }
    if (r.status === 204) return null;
    return r.json();
  }
  const get  = p       => api("GET",    p);
  const post = (p, b)  => api("POST",   p, b);
  const patch = (p, b) => api("PATCH",  p, b);
  const del  = p       => api("DELETE", p);

  // ── Screen management ────────────────────────────────────────────────────
  function show(id) {
    document.querySelectorAll(".screen").forEach(s => s.classList.remove("active"));
    document.getElementById("screen-" + id).classList.add("active");
  }
  function breadcrumb(text) {
    document.getElementById("breadcrumb").textContent = text;
  }

  // ── Init ─────────────────────────────────────────────────────────────────
  async function init() {
    // Load mascot
    const mascots = await get("/api/mascots").catch(() => []);
    state.mascots = mascots;
    if (mascots.length) {
      state.currentMascot = mascots[Math.floor(Math.random() * mascots.length)];
      const avatarSrc = "/mascotte/" + encodeURIComponent(state.currentMascot);
      document.getElementById("agent-avatar").src = avatarSrc;
      document.getElementById("agent-avatar-mobile").src = avatarSrc;
    }

    // Load special practices
    state.specialPractices = await get("/api/practices/special").catch(() => []);
    const sel = document.getElementById("select-special");
    sel.innerHTML = "";
    state.specialPractices.forEach(sp => {
      const o = document.createElement("option");
      o.value = sp.id;
      o.textContent = `${sp.titre} (${sp.duration_default} min)`;
      sel.appendChild(o);
    });

    await loadFacilitators();

    // Auto-resize textareas
    ["chat-input", "chat-input-mobile"].forEach(id => {
      const el = document.getElementById(id);
      if (!el) return;
      el.addEventListener("input", () => { el.style.height = "auto"; el.style.height = el.scrollHeight + "px"; });
      el.addEventListener("keydown", e => {
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          id === "chat-input" ? sendChat() : sendChatMobile();
        }
      });
    });

    addAgentMessage("Bonjour ! Je suis votre assistant facilitateur. Sélectionnez ou créez un facilitateur pour commencer.");
  }

  // ── Facilitators ─────────────────────────────────────────────────────────
  async function loadFacilitators() {
    const list = await get("/api/facilitators");
    const el = document.getElementById("facilitator-list");
    if (!list.length) {
      el.innerHTML = `<div class="empty-state"><div class="icon">👤</div><p>Aucun facilitateur. Créez-en un pour commencer.</p></div>`;
      return;
    }
    el.innerHTML = list.map(f => `
      <div class="card" onclick="App.openFacilitator(${f.id}, '${esc(f.name)}')">
        <h3>${esc(f.name)}</h3>
        <p class="meta">Cliquer pour voir les sessions</p>
      </div>`).join("");
  }

  function showNewFacilitator() { document.getElementById("form-new-facilitator").style.display = ""; }
  function hideNewFacilitator() { document.getElementById("form-new-facilitator").style.display = "none"; }

  async function createFacilitator() {
    const name = document.getElementById("input-facilitator-name").value.trim();
    if (!name) return;
    await post("/api/facilitators", { name });
    document.getElementById("input-facilitator-name").value = "";
    hideNewFacilitator();
    await loadFacilitators();
  }

  async function openFacilitator(id, name) {
    state.facilitator = { id, name };
    breadcrumb(`${name}`);
    document.getElementById("sessions-title").textContent = `Sessions — ${name}`;
    show("sessions");
    await loadSessions();
  }

  // ── Facilitators nav ─────────────────────────────────────────────────────
  async function showFacilitators() {
    show("facilitators");
    breadcrumb("");
    await loadFacilitators();
  }

  // ── Sessions ──────────────────────────────────────────────────────────────
  async function loadSessions() {
    const list = await get(`/api/facilitators/${state.facilitator.id}/sessions`);
    state.sessions = list;
    const el = document.getElementById("session-list");
    if (!list.length) {
      el.innerHTML = `<div class="empty-state"><div class="icon">📋</div><p>Aucune session. Créez-en une !</p></div>`;
      return;
    }
    el.innerHTML = list.map(s => `
      <div class="card" onclick="App.openSession(${s.id})">
        <h3>${esc(s.title)}</h3>
        <p class="meta">${s.date || "Date non définie"} · <span class="badge badge-${s.status}">${statusLabel(s.status)}</span></p>
      </div>`).join("");
  }

  function showNewSession() { document.getElementById("form-new-session").style.display = ""; }
  function hideNewSession()  { document.getElementById("form-new-session").style.display = "none"; }

  async function createSession() {
    const title = document.getElementById("input-session-title").value.trim();
    if (!title) return;
    const date = document.getElementById("input-session-date").value || null;
    const objective = document.getElementById("input-session-objective").value.trim() || null;
    const s = await post("/api/sessions", { facilitator_id: state.facilitator.id, title, date, objective });
    hideNewSession();
    await openSession(s.id);
  }

  async function openSession(id) {
    const ctx = await get(`/api/sessions/${id}`);
    state.session = ctx;
    state.practices = ctx.practices || [];
    state.participants = ctx.participants || [];
    breadcrumb(`${state.facilitator ? state.facilitator.name + " › " : ""}${ctx.title}`);
    show("session");
    renderSessionMeta(ctx);
    renderParticipants();
    renderPractices();
    await loadTeamsForSession();
  }

  function renderSessionMeta(ctx) {
    document.getElementById("session-meta-title").textContent = ctx.title;
    document.getElementById("session-meta-badge").textContent = statusLabel(ctx.status);
    document.getElementById("session-meta-badge").className = `badge badge-${ctx.status}`;
    document.getElementById("session-status-select").value = ctx.status;
    const row = document.getElementById("session-meta-row");
    row.innerHTML = `
      <div class="meta-item"><strong>Date</strong><span class="editable" onclick="App.editSessionField('date')">${ctx.date || "—"}</span></div>
      <div class="meta-item"><strong>Objectif</strong><span class="editable" onclick="App.editSessionField('objective')">${esc(ctx.objective || "—")}</span></div>
      <div class="meta-item"><strong>Facilitateur</strong>${esc(ctx.facilitator ? ctx.facilitator.name : "—")}</div>`;
  }

  async function updateSessionStatus(status) {
    const ctx = await patch(`/api/sessions/${state.session.id}`, { status });
    state.session = ctx;
    renderSessionMeta(ctx);
  }

  async function editSessionField(field) {
    const labels = { title: "Titre", date: "Date (YYYY-MM-DD)", objective: "Objectif" };
    const current = state.session[field] || "";
    const val = prompt(`${labels[field]} :`, current);
    if (val === null) return;
    const ctx = await patch(`/api/sessions/${state.session.id}`, { [field]: val });
    state.session = ctx;
    renderSessionMeta(ctx);
  }

  // ── Participants ──────────────────────────────────────────────────────────
  function renderParticipants() {
    const list = state.participants;
    const el = document.getElementById("participant-list");
    document.getElementById("participants-count").textContent = list.length ? `(${list.length})` : "";
    if (!list.length) { el.innerHTML = `<li style="color:var(--muted);font-size:.85rem;padding:6px">Aucun participant pour l'instant.</li>`; return; }
    el.innerHTML = list.map(p => `
      <li class="participant-item">
        <span class="p-name">${esc(p.first_name)} ${esc(p.last_name)}</span>
        <span class="p-role">${esc(p.role || p.email || "")}</span>
        <button class="btn-icon" onclick="App.removeParticipant(${p.id})" title="Retirer">✕</button>
      </li>`).join("");
  }

  async function addParticipant() {
    const fn = document.getElementById("p-first").value.trim();
    const ln = document.getElementById("p-last").value.trim();
    if (!ln) { alert("Le nom est obligatoire."); return; }
    const email = document.getElementById("p-email").value.trim() || undefined;
    const role  = document.getElementById("p-role").value.trim() || undefined;
    try {
      const p = await post(`/api/sessions/${state.session.id}/participants`, { first_name: fn || "—", last_name: ln, email, role });
      state.participants.push(p);
      ["p-first","p-last","p-email","p-role"].forEach(id => document.getElementById(id).value = "");
      renderParticipants();
    } catch(e) {
      alert("Erreur lors de l'ajout : " + e.message);
    }
  }

  async function removeParticipant(pid) {
    await del(`/api/sessions/${state.session.id}/participants/${pid}`);
    state.participants = state.participants.filter(p => p.id !== pid);
    renderParticipants();
  }

  async function loadTeamsForSession() {
    const teams = await get("/api/teams");
    state.teams = teams;
    const sel = document.getElementById("select-team");
    sel.innerHTML = `<option value="">— Choisir une équipe —</option>` +
      teams.map(t => `<option value="${t.id}">${esc(t.name)}</option>`).join("");
  }

  async function addTeam() {
    const tid = parseInt(document.getElementById("select-team").value);
    if (!tid) return;
    const result = await post(`/api/sessions/${state.session.id}/teams`, { team_id: tid });
    // Reload participants
    const updated = await get(`/api/sessions/${state.session.id}/participants`);
    state.participants = updated;
    renderParticipants();
  }

  // ── Practices ─────────────────────────────────────────────────────────────
  function renderPractices() {
    const list = state.practices;
    const el = document.getElementById("practice-list");
    const total = list.reduce((s, p) => s + p.duration_minutes, 0);
    document.getElementById("total-duration").textContent = `Durée totale : ${total} min`;
    if (!list.length) { el.innerHTML = `<li style="color:var(--muted);font-size:.85rem;padding:8px">Aucune pratique. Demandez à l'agent d'en suggérer !</li>`; return; }
    el.innerHTML = list.map((p, i) => `
      <li class="practice-item" data-id="${p.id}">
        <span class="p-pos">${i + 1}</span>
        <span class="p-title">${esc(p.titre)}</span>
        <span class="p-source">${p.source === "special" ? "Spécial" : p.icone_code || "RAG"}</span>
        <span class="p-dur">
          <input type="number" min="1" max="480" value="${p.duration_minutes}"
            onchange="App.updateDuration(${p.id}, this.value)" style="width:56px;text-align:center;padding:4px 6px;border:1px solid var(--border);border-radius:6px"/>
          <span style="font-size:.8rem;color:var(--muted)">min</span>
        </span>
        <span class="practice-actions">
          ${i > 0 ? `<button class="btn-icon" onclick="App.movePractice(${p.id},'up')" title="Monter">▲</button>` : '<button class="btn-icon" disabled style="opacity:.3">▲</button>'}
          ${i < list.length - 1 ? `<button class="btn-icon" onclick="App.movePractice(${p.id},'down')" title="Descendre">▼</button>` : '<button class="btn-icon" disabled style="opacity:.3">▼</button>'}
          <button class="btn-icon" onclick="App.removePractice(${p.id})" title="Supprimer" style="color:var(--red)">✕</button>
        </span>
      </li>`).join("");
  }

  async function updateDuration(rowId, val) {
    const dur = parseInt(val);
    if (!dur || dur < 1) return;
    await patch(`/api/sessions/${state.session.id}/practices/${rowId}`, { duration_minutes: dur });
    state.practices = state.practices.map(p => p.id === rowId ? { ...p, duration_minutes: dur } : p);
    const total = state.practices.reduce((s, p) => s + p.duration_minutes, 0);
    document.getElementById("total-duration").textContent = `Durée totale : ${total} min`;
  }

  async function movePractice(rowId, direction) {
    // FLIP — snapshot positions before re-render
    const before = {};
    document.querySelectorAll("#practice-list .practice-item").forEach(el => {
      before[el.dataset.id] = el.getBoundingClientRect().top;
    });

    const result = await patch(`/api/sessions/${state.session.id}/practices/${rowId}`, { direction });
    if (!Array.isArray(result)) return;
    state.practices = result;
    renderPractices();

    // Animate from old positions to new ones
    requestAnimationFrame(() => {
      document.querySelectorAll("#practice-list .practice-item").forEach(el => {
        const id = el.dataset.id;
        if (before[id] !== undefined) {
          const delta = before[id] - el.getBoundingClientRect().top;
          if (Math.abs(delta) > 1) {
            el.animate(
              [{ transform: `translateY(${delta}px)` }, { transform: "translateY(0)" }],
              { duration: 320, easing: "cubic-bezier(.25,.46,.45,.94)" }
            );
          }
        }
      });
      // Pulse-highlight the moved item
      const movedEl = document.querySelector(`#practice-list .practice-item[data-id="${rowId}"]`);
      if (movedEl) {
        movedEl.classList.add("practice-pulse");
        movedEl.addEventListener("animationend", () => movedEl.classList.remove("practice-pulse"), { once: true });
      }
    });
  }

  async function removePractice(rowId) {
    const el = document.querySelector(`#practice-list .practice-item[data-id="${rowId}"]`);
    if (el) {
      const h = el.getBoundingClientRect().height;
      el.style.overflow = "hidden";
      await el.animate([
        { opacity: 1, height: h + "px", marginBottom: "8px", transform: "translateX(0)" },
        { opacity: 0, height: "0",      marginBottom: "0",   transform: "translateX(-28px)" },
      ], { duration: 260, easing: "ease-in", fill: "forwards" }).finished;
    }
    await del(`/api/sessions/${state.session.id}/practices/${rowId}`);
    state.practices = state.practices.filter(p => p.id !== rowId);
    renderPractices();
  }

  function _animateNewPractices(newIds) {
    if (!newIds.size) return;
    requestAnimationFrame(() => {
      newIds.forEach(id => {
        const el = document.querySelector(`#practice-list .practice-item[data-id="${id}"]`);
        if (el) {
          el.classList.add("practice-entering");
          el.addEventListener("animationend", () => el.classList.remove("practice-entering"), { once: true });
        }
      });
    });
  }

  function showSpecialPracticeMenu()  { document.getElementById("special-practice-menu").style.display = ""; }
  function hideSpecialPracticeMenu() { document.getElementById("special-practice-menu").style.display = "none"; }

  async function addSpecialPractice() {
    const id = document.getElementById("select-special").value;
    const sp = state.specialPractices.find(p => p.id === id);
    if (!sp) return;
    const p = await post(`/api/sessions/${state.session.id}/practices`, {
      practice_id: sp.id, titre: sp.titre,
      duration_minutes: sp.duration_default, source: "special",
    });
    state.practices.push(p);
    renderPractices();
    _animateNewPractices(new Set([p.id]));
    hideSpecialPracticeMenu();
  }

  async function refreshSessionTotal() {
    const pracs = await get(`/api/sessions/${state.session.id}/practices`);
    state.practices = pracs;
    renderPractices();
  }

  // ── Clients & Teams ───────────────────────────────────────────────────────
  async function showClients() {
    show("clients");
    breadcrumb("Clients & Équipes");
    await loadClients();
    await loadTeamsPage();
  }

  async function loadClients() {
    const list = await get("/api/clients");
    state.clients = list;
    const el = document.getElementById("client-list");
    el.innerHTML = list.length
      ? list.map(c => `<div class="card"><h3>${esc(c.name)}</h3></div>`).join("")
      : `<div class="empty-state"><p>Aucun client.</p></div>`;

    // Also refresh team-client select
    const sel = document.getElementById("select-team-client");
    sel.innerHTML = `<option value="">— Client (optionnel) —</option>` +
      list.map(c => `<option value="${c.id}">${esc(c.name)}</option>`).join("");
  }

  async function createClient() {
    const name = document.getElementById("input-client-name").value.trim();
    if (!name) return;
    await post("/api/clients", { name });
    document.getElementById("input-client-name").value = "";
    await loadClients();
  }

  async function loadTeamsPage() {
    const list = await get("/api/teams");
    state.teams = list;
    const el = document.getElementById("team-list");
    el.innerHTML = list.length
      ? list.map(t => `<div class="card"><h3>${esc(t.name)}</h3><p class="meta">${t.client_id ? "Client #" + t.client_id : "Sans client"}</p></div>`).join("")
      : `<div class="empty-state"><p>Aucune équipe.</p></div>`;
  }

  async function createTeam() {
    const name = document.getElementById("input-team-name").value.trim();
    if (!name) return;
    const cid = parseInt(document.getElementById("select-team-client").value) || null;
    await post("/api/teams", { name, client_id: cid });
    document.getElementById("input-team-name").value = "";
    await loadTeamsPage();
  }

  function showTab(tab) {
    document.getElementById("tab-clients").style.display = tab === "clients" ? "" : "none";
    document.getElementById("tab-teams").style.display   = tab === "teams"   ? "" : "none";
    document.querySelectorAll(".tab-btn").forEach((b, i) =>
      b.classList.toggle("active", (i === 0 && tab === "clients") || (i === 1 && tab === "teams")));
  }

  // ── Dashboard ─────────────────────────────────────────────────────────────
  let _activeLogFilters = new Set(["llm", "rag", "db", "resolution"]);

  async function showDashboard() {
    show("dashboard");
    breadcrumb("Tableau de bord");
    await refreshDashboard();
  }

  async function refreshDashboard() {
    const [kpis, cfg] = await Promise.all([
      get("/api/dashboard/kpis"),
      get("/api/dashboard/config"),
    ]);
    renderKPIs(kpis);
    document.getElementById("cost-in").value  = cfg.cost_in;
    document.getElementById("cost-out").value = cfg.cost_out;
    await refreshLogs();
  }

  function renderKPIs(kpis) {
    const defs = [
      { key: "auto_resolution",   label: "Taux résolution auto",  fmt: v => v + " %",   target: ">90 %",  good: v => v >= 90 },
      { key: "avg_response_time", label: "Temps moyen traitement", fmt: v => v + " s",   target: "<1,5 s", good: v => v < 1.5 },
      { key: "avg_satisfaction",  label: "Satisfaction utilisateur", fmt: v => "★ " + v, target: ">4",     good: v => v >= 4 },
      { key: "avg_cost",          label: "Coût par transaction",   fmt: v => "$" + v,    target: "<0,10 $",good: v => v < 0.1 },
      { key: "fallback_rate",     label: "Taux de fallback RAG",   fmt: v => v + " %",   target: "<5 %",   good: v => v < 5 },
    ];
    const grid = document.getElementById("kpi-grid");
    grid.innerHTML = defs.map(d => {
      const raw = kpis[d.key];
      let valHtml;
      if (raw === null || raw === undefined) {
        valHtml = `<div class="kpi-na">N/A</div>`;
      } else {
        const cls = d.good(raw) ? "" : (raw < 0 ? "bad" : "warn");
        valHtml = `<div class="kpi-value ${cls}">${d.fmt(raw)}</div>`;
      }
      return `<div class="kpi-card">
        <div class="kpi-name">${d.label}</div>
        ${valHtml}
        <div class="kpi-target">Cible : ${d.target}</div>
      </div>`;
    }).join("");
  }

  async function saveCostConfig() {
    const cost_in  = parseFloat(document.getElementById("cost-in").value);
    const cost_out = parseFloat(document.getElementById("cost-out").value);
    if (isNaN(cost_in) || isNaN(cost_out)) return;
    await post("/api/dashboard/config", { cost_in, cost_out });
    await refreshDashboard();
  }

  function toggleLogFilter(type, btn) {
    if (_activeLogFilters.has(type)) {
      _activeLogFilters.delete(type);
      btn.classList.remove("active");
    } else {
      _activeLogFilters.add(type);
      btn.classList.add("active");
    }
    _applyLogFilters();
  }

  function _applyLogFilters() {
    document.querySelectorAll(".log-entry").forEach(el => {
      el.style.display = _activeLogFilters.has(el.dataset.type) ? "" : "none";
    });
  }

  async function refreshLogs() {
    const logs = await get("/api/dashboard/logs?limit=300");
    const viewer = document.getElementById("log-viewer");
    if (!logs.length) { viewer.innerHTML = `<div style="color:#6c7086;padding:10px">Aucun log.</div>`; return; }
    viewer.innerHTML = logs.map(l => {
      let payloadHtml = "";
      if (l.payload) {
        try {
          const pretty = JSON.stringify(JSON.parse(l.payload), null, 2);
          payloadHtml = `<div class="log-payload">${esc(pretty)}</div>`;
        } catch {
          payloadHtml = `<div class="log-payload">${esc(l.payload)}</div>`;
        }
      }
      return `<div class="log-entry" data-type="${l.event_type}" onclick="this.classList.toggle('expanded')">
        <span class="log-ts">${l.timestamp}</span>
        <span class="log-type">[${l.event_type.toUpperCase()}]</span>
        <span class="log-summary">${esc(l.summary || "")}</span>
        ${payloadHtml}
      </div>`;
    }).join("");
    _applyLogFilters();
  }

  // ── Chat / Agent ──────────────────────────────────────────────────────────
  function addAgentMessage(text, isMobile) {
    const msg = { role: "agent", text };
    _appendBubble("agent", text, "chat-messages");
    _appendBubble("agent", text, "chat-messages-mobile");
  }

  function _appendBubble(role, text, containerId) {
    const el = document.getElementById(containerId);
    if (!el) return;
    const div = document.createElement("div");
    div.className = `chat-bubble ${role}`;
    div.innerHTML = text.replace(/\n/g, "<br>");
    el.appendChild(div);
    el.scrollTop = el.scrollHeight;
  }

  function _appendTyping(containerId) {
    const el = document.getElementById(containerId);
    if (!el) return null;
    const div = document.createElement("div");
    div.className = "chat-bubble agent chat-typing";
    div.textContent = "…";
    el.appendChild(div);
    el.scrollTop = el.scrollHeight;
    return div;
  }

  async function _sendMessage(message) {
    if (!message.trim()) return;
    _appendBubble("user", esc(message), "chat-messages");
    _appendBubble("user", esc(message), "chat-messages-mobile");

    const tid1 = _appendTyping("chat-messages");
    const tid2 = _appendTyping("chat-messages-mobile");

    const sessionId = state.session ? state.session.id : 0;
    let reply = "";
    try {
      const data = await post("/api/agent/chat", { session_id: sessionId, message });
      reply = data.reply || "Pas de réponse.";

      // If agent modified session data, refresh
      if (data.tool_results && data.tool_results.length) {
        const modifyingTools = ["add_practice","remove_practice","reorder_practice","update_practice_duration",
          "add_participant_to_session","create_participant","add_team_to_session","update_session"];
        const changed = data.tool_results.some(t => modifyingTools.includes(t.tool));

        // Snapshot current practice IDs before refresh (for enter animations)
        const oldPracticeIds = new Set((state.practices || []).map(p => p.id));

        // If agent created a session, navigate to it automatically
        const createdSession = data.tool_results.find(t => t.tool === "create_session" && t.result && t.result.id);
        if (createdSession) {
          const newSession = createdSession.result;
          if (!state.facilitator && newSession.facilitator_id) {
            state.facilitator = await get(`/api/facilitators/${newSession.facilitator_id}`);
          }
          await openSession(newSession.id);
          if (state.facilitator) await loadSessions();
        } else if (changed && state.session) {
          await openSession(state.session.id);
        }

        // Animate newly added practices
        if (state.practices && state.practices.length) {
          const newIds = new Set(state.practices.filter(p => !oldPracticeIds.has(p.id)).map(p => p.id));
          _animateNewPractices(newIds);
        }
      }
    } catch (e) {
      reply = "Erreur : " + e.message;
    }

    if (tid1) tid1.remove();
    if (tid2) tid2.remove();
    _appendBubble("agent", reply, "chat-messages");
    _appendBubble("agent", reply, "chat-messages-mobile");
    _appendRating("chat-messages", state.session ? state.session.id : 0);
    _appendRating("chat-messages-mobile", state.session ? state.session.id : 0);
  }

  function _appendRating(containerId, sessionId) {
    const el = document.getElementById(containerId);
    if (!el) return;
    const row = document.createElement("div");
    row.className = "rating-row";
    row.dataset.rated = "0";
    for (let i = 1; i <= 5; i++) {
      const s = document.createElement("span");
      s.className = "star";
      s.textContent = "★";
      s.dataset.val = i;
      s.onclick = () => _submitRating(row, sessionId, i);
      s.onmouseover = () => { if (row.dataset.rated === "0") _highlightStars(row, i); };
      s.onmouseout  = () => { if (row.dataset.rated === "0") _highlightStars(row, 0); };
      row.appendChild(s);
    }
    el.appendChild(row);
    el.scrollTop = el.scrollHeight;
  }

  function _highlightStars(row, upTo) {
    row.querySelectorAll(".star").forEach(s => s.classList.toggle("lit", parseInt(s.dataset.val) <= upTo));
  }

  async function _submitRating(row, sessionId, rating) {
    if (row.dataset.rated !== "0") return;
    row.dataset.rated = rating;
    _highlightStars(row, rating);
    row.style.pointerEvents = "none";
    const done = document.createElement("span");
    done.className = "rating-done";
    done.textContent = " Merci !";
    row.appendChild(done);
    await post("/api/dashboard/rate", { session_id: sessionId, rating }).catch(() => {});
  }

  async function sendChat() {
    const inp = document.getElementById("chat-input");
    const msg = inp.value.trim();
    inp.value = "";
    inp.style.height = "auto";
    await _sendMessage(msg);
  }

  async function sendChatMobile() {
    const inp = document.getElementById("chat-input-mobile");
    const msg = inp.value.trim();
    inp.value = "";
    inp.style.height = "auto";
    await _sendMessage(msg);
  }

  function toggleMobileAgent() {
    state.mobileAgentOpen = !state.mobileAgentOpen;
    const panel = document.getElementById("agent-panel-mobile");
    panel.style.display = state.mobileAgentOpen ? "flex" : "none";
  }

  // ── PDF ───────────────────────────────────────────────────────────────────
  function exportPDF() {
    if (!state.session) return;
    window.open(`/api/sessions/${state.session.id}/export/pdf`, "_blank");
  }

  // ── Utilities ─────────────────────────────────────────────────────────────
  function esc(str) {
    return String(str ?? "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
  }
  function statusLabel(s) {
    return { draft: "Brouillon", confirmed: "Confirmé", finished: "Terminé" }[s] || s;
  }

  // ── Public API ────────────────────────────────────────────────────────────
  document.addEventListener("DOMContentLoaded", init);

  return {
    showNewFacilitator, hideNewFacilitator, createFacilitator,
    showFacilitators, openFacilitator,
    showNewSession, hideNewSession, createSession, openSession,
    updateSessionStatus, editSessionField,
    addParticipant, removeParticipant, addTeam,
    updateDuration, movePractice, removePractice,
    showSpecialPracticeMenu, hideSpecialPracticeMenu, addSpecialPractice,
    showClients, createClient, createTeam, showTab,
    showDashboard, refreshDashboard, saveCostConfig, toggleLogFilter,
    sendChat, sendChatMobile, toggleMobileAgent,
    exportPDF,
  };
})();
