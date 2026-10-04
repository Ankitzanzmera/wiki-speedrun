let selectedAlgo = "bfs";
let pollTimer = null;
let currentJobId = null;
let lastGraph = null;
let network = null;

const $ = (id) => document.getElementById(id);

async function checkHealth() {
  try {
    const r = await fetch("/api/health");
    $("healthDot").style.color = r.ok ? "#22c55e" : "#ef4444";
  } catch { $("healthDot").style.color = "#ef4444"; }
}

// ---- algorithm picker
document.querySelectorAll(".algo").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".algo").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    selectedAlgo = btn.dataset.algo;
  });
});

// ---- sliders
$("maxPages").addEventListener("input", (e) => ($("maxPagesOut").textContent = e.target.value));
$("maxDepth").addEventListener("input", (e) => ($("maxDepthOut").textContent = e.target.value));

$("swapBtn").addEventListener("click", () => {
  const s = $("startInput").value;
  $("startInput").value = $("targetInput").value;
  $("targetInput").value = s;
  syncOpenLinks();
});

// Resolve a source/target field to a Wikipedia article URL for the ↗ preview.
// Accepts full URLs or plain titles.
function toArticleUrl(raw) {
  const v = (raw || "").trim();
  if (!v) return null;
  if (/^https?:\/\//i.test(v)) return v;
  const title = v.replace(/^\/wiki\//, "").replace(/ /g, "_");
  return "https://en.wikipedia.org/wiki/" + encodeURIComponent(title).replace(/%2F/g, "/");
}

function syncOpenLinks() {
  const s = toArticleUrl($("startInput").value);
  const t = toArticleUrl($("targetInput").value);
  if (s) $("startOpen").href = s;
  if (t) $("targetOpen").href = t;
}
$("startInput").addEventListener("input", syncOpenLinks);
$("targetInput").addEventListener("input", syncOpenLinks);

const RANDOM_PAIRS = [
  ["Potato", "Barack Obama"],
  ["Pizza", "Quantum mechanics"],
  ["Chess", "Elon Musk"],
  ["Cat", "Roman Empire"],
  ["Coffee", "Artificial intelligence"],
  ["Beatles", "Black hole"],
];
$("randomBtn").addEventListener("click", () => {
  const [a, b] = RANDOM_PAIRS[Math.floor(Math.random() * RANDOM_PAIRS.length)];
  $("startInput").value = a;
  $("targetInput").value = b;
  syncOpenLinks();
});

// ---- autocomplete via Wikipedia API (direct from browser)
async function attachSuggest(inputEl, boxEl) {
  let timer;
  inputEl.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const q = inputEl.value.trim();
      if (q.length < 2 || /^https?:\/\//i.test(q)) { boxEl.innerHTML = ""; return; }
      try {
        const url = `https://en.wikipedia.org/w/api.php?action=opensearch&search=${encodeURIComponent(q)}&limit=6&namespace=0&format=json&origin=*`;
        const r = await fetch(url);
        const data = await r.json();
        boxEl.innerHTML = "";
        (data[1] || []).forEach((title) => {
          const d = document.createElement("div");
          d.textContent = title;
          d.onclick = () => { inputEl.value = title; boxEl.innerHTML = ""; };
          boxEl.appendChild(d);
        });
      } catch { /* offline -> ignore */ }
    }, 250);
  });
  document.addEventListener("click", (e) => {
    if (!boxEl.contains(e.target) && e.target !== inputEl) boxEl.innerHTML = "";
  });
}
attachSuggest($("startInput"), $("startSuggest"));
attachSuggest($("targetInput"), $("targetSuggest"));

// ---- search lifecycle
$("searchBtn").addEventListener("click", startSearch);
$("cancelBtn").addEventListener("click", cancelSearch);
$("copyBtn").addEventListener("click", () => {
  const items = [...document.querySelectorAll("#pathList a")].map((a) => a.href);
  if (items.length) navigator.clipboard.writeText(items.join("\n"));
});
$("pathOnlyToggle").addEventListener("change", () => renderGraph(true));
$("fitBtn").addEventListener("click", () => { if (network) network.fit({ animation: true }); });
$("expandBtn").addEventListener("click", () => {
  const card = $("graphCard");
  card.classList.toggle("expanded");
  $("expandBtn").textContent = card.classList.contains("expanded") ? "⛶ Collapse" : "⛶ Expand";
  if (network) setTimeout(() => { network.redraw(); network.fit(); }, 60);
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    const card = $("graphCard");
    if (card.classList.contains("expanded")) {
      card.classList.remove("expanded");
      $("expandBtn").textContent = "⛶ Expand";
    }
  }
});

async function startSearch() {
  const start = $("startInput").value.trim();
  const target = $("targetInput").value.trim();
  const err = $("formError");
  err.hidden = true;
  if (!start || !target) {
    err.textContent = "Enter both a start and a target article.";
    err.hidden = false;
    return;
  }
  $("searchBtn").disabled = true;
  $("cancelBtn").disabled = false;
  $("resultCard").hidden = true;
  $("graphCard").hidden = true;
  $("graphCard").classList.remove("expanded");
  $("expandBtn").textContent = "⛶ Expand";
  $("nodeDetail").hidden = true;
  $("progressCard").hidden = false;
  $("logFeed").innerHTML = "";
  $("copyBtn").disabled = true;

  const body = {
    start, target,
    algorithm: selectedAlgo,
    max_pages: parseInt($("maxPages").value, 10),
    max_depth: parseInt($("maxDepth").value, 10),
  };
  $("progressTitle").textContent = `Searching (${selectedAlgo})…`;
  try {
    const r = await fetch("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) {
      const e = await r.json().catch(() => ({}));
      throw new Error(e.detail || `Server error ${r.status}`);
    }
    const data = await r.json();
    currentJobId = data.job_id;
    clearInterval(pollTimer);
    pollTimer = setInterval(poll, 800);
    poll();
  } catch (e) {
    err.textContent = e.message;
    err.hidden = false;
    $("searchBtn").disabled = false;
    $("cancelBtn").disabled = true;
  }
}

async function poll() {
  if (!currentJobId) return;
  try {
    const r = await fetch(`/api/jobs/${currentJobId}?graph=true`);
    const job = await r.json();
    updateProgress(job);
    if (["done", "error", "cancelled"].includes(job.status)) {
      clearInterval(pollTimer);
      $("searchBtn").disabled = false;
      $("cancelBtn").disabled = true;
      if (job.status === "done") showResult(job);
      else if (job.status === "error") {
        const err = $("formError");
        err.textContent = job.error || "Search failed.";
        err.hidden = false;
        $("progressTitle").textContent = "Search failed";
        if (job.graph && job.graph.nodes.length) {
          lastGraph = job.graph;
          renderGraph(false);
          $("graphCard").hidden = false;
        }
      } else {
        $("progressTitle").textContent = "Search cancelled";
      }
    }
  } catch (e) {
    console.warn("poll failed", e);
  }
}

function updateProgress(job) {
  $("statVisited").textContent = job.pages_visited;
  $("statQueue").textContent = job.queue_size;
  $("statCurrent").textContent = job.current_title || "—";
  $("statCurrent").title = job.current_url || "";
  $("elapsedBadge").textContent = `${job.elapsed.toFixed(1)}s`;
  const pct = Math.min(100, (job.pages_visited / 800) * 100);
  $("progressBar").style.width = job.status === "done" ? "100%" : `${pct}%`;
  if (job.status === "running") $("progressTitle").textContent = `Searching (${job.algorithm})…`;
  const feed = $("logFeed");
  feed.innerHTML = job.logs.map((l) => `<div>${escapeHtml(l)}</div>`).join("");
  feed.scrollTop = feed.scrollHeight;
  lastGraph = job.graph || lastGraph;
}

function showResult(job) {
  $("progressTitle").textContent = "Path found ✓";
  $("resultCard").hidden = false;
  const s = job.stats;
  $("resultStats").innerHTML = `
    <div class="stat"><span class="stat-num">${s.clicks} clicks</span><span class="stat-label">path length (${s.path_length} articles)</span></div>
    <div class="stat"><span class="stat-num">${s.pages_visited}</span><span class="stat-label">pages visited</span></div>
    <div class="stat"><span class="stat-num">${s.time_taken}s</span><span class="stat-label">time taken</span></div>`;
  const list = $("pathList");
  list.innerHTML = "";
  job.path.forEach((url, i) => {
    const title = job.path_titles[i];
    const li = document.createElement("li");
    if (i > 0 && i < job.path.length - 1) li.className = "path-mid";
    li.innerHTML = `<span class="step">${i}</span><a href="${url}" target="_blank" rel="noopener">${escapeHtml(title)}</a>`;
    list.appendChild(li);
  });
  $("copyBtn").disabled = false;
  renderGraph(false);
  $("graphCard").hidden = false;
  $("resultCard").scrollIntoView({ behavior: "smooth" });
}

function renderGraph(useToggle) {
  if (!lastGraph || !window.vis) return;
  const pathOnly = useToggle ? $("pathOnlyToggle").checked : $("pathOnlyToggle").checked;
  const pathSet = new Set(lastGraph.path || []);
  let nodes = lastGraph.nodes;
  let edges = lastGraph.edges;
  if (pathOnly && lastGraph.path) {
    const pathIds = new Set(lastGraph.path);
    nodes = nodes.filter((n) => pathIds.has(n.id));
    edges = edges.filter((e) => pathIds.has(e.from) && pathIds.has(e.to));
    // chain path edges explicitly for clean layout
    edges = lastGraph.path.slice(1).map((id, i) => ({ from: lastGraph.path[i], to: id }));
  }
  // Importance = outgoing links in the explored graph (bubble size).
  // Child -> parent map gives depth from the source for the detail pane.
  const outDegree = {};
  const parentOf = {};
  edges.forEach((e) => {
    outDegree[e.from] = (outDegree[e.from] || 0) + 1;
    if (!(e.to in parentOf)) parentOf[e.to] = e.from;
  });
  const startId = lastGraph.start || null;
  const targetId = lastGraph.target || null;
  const labelOf = {};
  nodes.forEach((n) => { labelOf[n.id] = n.label; });
  function depthOf(id) {
    let d = 0, cur = id, guard = 0;
    while (cur !== startId && parentOf[cur] && guard++ < 10000) { cur = parentOf[cur]; d++; }
    return cur === startId ? d : null;
  }
  const visNodes = new vis.DataSet(
    nodes.map((n) => {
      // Connected-Papers style: bubble size reflects importance —
      // here, how many outgoing links the article had in the explored graph.
      const out = outDegree[n.id] || 0;
      const isStart = n.id === startId;
      const isTarget = n.id === targetId;
      const onPath = pathSet.has(n.id);
      let size = 11 + Math.min(15, Math.sqrt(out) * 3.2);
      let color = { background: "#b9c6e8", border: "#64748b", highlight: { background: "#93a5e0", border: "#475569" } };
      let font = { size: 12, face: "Inter", color: "#475569" };
      if (onPath) {
        size = Math.max(size, 24);
        color = { background: "#fbbf24", border: "#b45309", highlight: { background: "#f59e0b", border: "#92400e" } };
        font = { size: 15, face: "Inter", bold: true, color: "#78350f" };
      }
      if (isStart) {
        size = Math.max(size, 28);
        color = { background: "#8b5cf6", border: "#5b21b6", highlight: { background: "#7c3aed", border: "#4c1d95" } };
        font = { size: 15, face: "Inter", bold: true, color: "#2e1065" };
      }
      if (isTarget) {
        size = Math.max(size, 28);
        color = { background: "#34d399", border: "#047857", highlight: { background: "#10b981", border: "#065f46" } };
        font = { size: 15, face: "Inter", bold: true, color: "#064e3b" };
      }
      return {
        id: n.id,
        label: n.label.length > 26 ? n.label.slice(0, 25) + "…" : n.label,
        title: `${n.label} · links to ${out} article${out === 1 ? "" : "s"}`,
        shape: "dot",
        borderWidth: onPath || isStart || isTarget ? 3 : 1.5,
        color, size, font,
      };
    })
  );
  const pathEdgeSet = new Set();
  if (lastGraph.path) {
    for (let i = 1; i < lastGraph.path.length; i++) {
      pathEdgeSet.add(lastGraph.path[i - 1] + "→" + lastGraph.path[i]);
    }
  }
  const visEdges = new vis.DataSet(
    edges.slice(0, 2000).map((e) => {
      const isPath = pathEdgeSet.has(e.from + "→" + e.to);
      return {
        from: e.from,
        to: e.to,
        length: isPath ? 260 : 220,
        width: isPath ? 3.5 : 1.2,
        color: isPath ? { color: "#d97706", highlight: "#b45309" } : { color: "#c3cbe4", highlight: "#818cf8" },
        smooth: { enabled: true, type: "continuous", roundness: 0.4 },
        arrows: "to",
      };
    })
  );
  const container = $("graph");
  if (network) network.destroy();
  network = new vis.Network(container, { nodes: visNodes, edges: visEdges }, {
    // Spread-out force layout so the graph doesn't look compact.
    layout: { improvedLayout: true, randomSeed: 42 },
    physics: {
      enabled: true,
      solver: "barnesHut",
      barnesHut: {
        gravitationalConstant: -14000,
        centralGravity: 0.12,
        springLength: 260,
        springConstant: 0.028,
        damping: 0.085,
        avoidOverlap: 0.6,
      },
      stabilization: { enabled: true, iterations: 250, fit: true },
    },
    nodes: { scaling: { min: 10, max: 34 } },
    interaction: { hover: true, navigationButtons: true, zoomView: true, dragView: true, multiselect: true },
  });
  network.once("stabilized", () => network.fit({ animation: true }));
  network.on("doubleClick", (p) => {
    if (p.nodes.length) window.open(p.nodes[0], "_blank");
  });
  // Connected-Papers style detail pane on single click.
  network.on("click", (p) => {
    if (!p.nodes.length) return;
    const id = p.nodes[0];
    const role = id === startId ? "Source" : id === targetId ? "Target" : pathSet.has(id) ? "Shortest path" : "Explored";
    const out = outDegree[id] || 0;
    const depth = depthOf(id);
    $("ndTitle").textContent = labelOf[id] || id;
    $("ndRole").textContent = role;
    $("ndMeta").textContent = `Links to ${out} article${out === 1 ? "" : "s"} in this graph` + (depth === null ? "" : ` · ${depth} click${depth === 1 ? "" : "s"} from source`);
    $("ndOpen").href = id;
    $("nodeDetail").hidden = false;
  });
}

$("ndClose").addEventListener("click", () => { $("nodeDetail").hidden = true; });

async function cancelSearch() {
  if (!currentJobId) return;
  await fetch(`/api/jobs/${currentJobId}`, { method: "DELETE" });
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}

checkHealth();
setInterval(checkHealth, 15000);
