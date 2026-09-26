let currentJobId = null;
let originalFiles = [];
let repairedFiles = [];
let visibleIssues = [];
let currentIssueFilter = "all";
let currentFileMode = "original";
let currentActionableCount = 0;
let beforeErrorCount = null;
let systemStatus = null;

const $ = (id) => document.getElementById(id);

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || payload.ok === false) {
    throw new Error(payload.error || `Request failed: ${response.status}`);
  }
  return payload;
}

function toast(message) {
  const node = $("toast");
  node.textContent = message;
  node.classList.add("visible");
  window.clearTimeout(toast.timer);
  toast.timer = window.setTimeout(() => node.classList.remove("visible"), 3600);
}

function formatRate(value) {
  if (value === null || value === undefined || value === "") return "-";
  const number = Number(value);
  if (Number.isNaN(number)) return "-";
  return `${Math.round(number * 1000) / 10}%`;
}

function formatScore(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(3) : "-";
}

function severityOf(issue) {
  return issue.severity || issue.type || "error";
}

function setBusy(button, busy, label) {
  if (busy) {
    button.dataset.originalText = button.textContent;
    button.textContent = label;
    button.disabled = true;
    return;
  }
  button.textContent = button.dataset.originalText || button.textContent;
  button.disabled = false;
}

function selectedProvider() {
  return $("providerSelect").value;
}

function providerConfigured() {
  const provider = selectedProvider();
  return Boolean(systemStatus?.providers?.[provider]?.configured);
}

function updateRepairButton() {
  const button = $("repairButton");
  const enabled = Boolean(currentJobId && currentActionableCount > 0 && providerConfigured());
  button.disabled = !enabled;
  if (!providerConfigured()) {
    button.title = "The selected provider's API key is not configured";
  } else if (currentActionableCount === 0) {
    button.title = "There are no XML-safe errors to repair";
  } else {
    button.title = "";
  }
}

function updateProviderUi() {
  const provider = selectedProvider();
  const providerState = systemStatus?.providers?.[provider];
  if (providerState?.model) $("modelName").value = providerState.model;
  const api = $("apiStatus");
  if (providerState?.configured) {
    api.textContent = `${providerLabel(provider)} API configured`;
    api.className = "status-item ok";
  } else {
    api.textContent = `${providerLabel(provider)} API not configured`;
    api.className = "status-item warn";
  }
  updateRepairButton();
}

function providerLabel(provider) {
  return { deepseek: "DeepSeek", openai: "OpenAI", anthropic: "Anthropic" }[provider] || provider;
}

async function loadStatus() {
  try {
    systemStatus = await requestJson("/api/status");
    updateProviderUi();
  } catch (error) {
    $("apiStatus").textContent = "Service status unavailable";
    $("apiStatus").className = "status-item warn";
  }
}

function switchTab(id) {
  document.querySelectorAll(".tab").forEach((tab) => {
    const active = tab.dataset.tab === id;
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-selected", String(active));
  });
  document.querySelectorAll(".tab-view").forEach((view) => {
    const active = view.id === id;
    view.classList.toggle("active", active);
    view.hidden = !active;
  });
}

function renderIssueList() {
  const list = $("issueList");
  const issues = currentIssueFilter === "all"
    ? visibleIssues
    : visibleIssues.filter((issue) => severityOf(issue) === currentIssueFilter);
  list.innerHTML = "";
  if (!issues.length) {
    list.className = "result-list empty-state";
    list.textContent = visibleIssues.length ? "No issues match the current filter." : "The static checker found no issues.";
    return;
  }
  list.className = "result-list";
  issues.forEach((issue) => {
    const severity = severityOf(issue);
    const repairability = issue.repairability || (severity === "error" ? "xml_safe" : "review");
    const article = document.createElement("article");
    article.className = "result-row issue-row";
    article.innerHTML = `
      <div class="row-marker ${escapeHtml(severity)}"></div>
      <div class="row-main">
        <div class="row-title">
          <strong>${escapeHtml(issue.code || issue.type || "UNKNOWN")}</strong>
          <span class="badge ${escapeHtml(severity)}">${escapeHtml(severity)}</span>
          <span class="badge neutral">${escapeHtml(repairability)}</span>
        </div>
        <p>${escapeHtml(issue.display_message || issue.message || "")}</p>
        <code>${escapeHtml(issue.relative_file || issue.file || "")} · ${escapeHtml(issue.selector || "")}</code>
        ${issue.display_fix_hint || issue.fix_hint ? `<small>${escapeHtml(issue.display_fix_hint || issue.fix_hint)}</small>` : ""}
      </div>`;
    list.appendChild(article);
  });
}

function renderReport(report, phase = "before") {
  visibleIssues = report.issues || [];
  $("errorCount").textContent = report.error_count ?? 0;
  $("warningCount").textContent = report.warning_count ?? 0;
  $("infoCount").textContent = report.info_count ?? 0;
  $("totalCount").textContent = report.total_issue_count ?? visibleIssues.length;
  currentActionableCount = Number(report.actionable_error_count ?? visibleIssues.filter(
    (issue) => severityOf(issue) === "error" && (issue.repairability || "xml_safe") === "xml_safe",
  ).length);
  $("actionableCount").textContent = currentActionableCount;
  $("reviewCount").textContent = report.review_required_count ?? visibleIssues.filter(
    (issue) => issue.requires_review || (issue.repairability && issue.repairability !== "xml_safe"),
  ).length;
  if (phase === "before") {
    beforeErrorCount = Number(report.error_count || 0);
    $("beforeErrorCount").textContent = beforeErrorCount;
    $("afterErrorCount").textContent = "-";
    $("repairRate").textContent = "-";
  } else {
    $("afterErrorCount").textContent = report.error_count ?? "-";
  }
  renderIssueList();
  updateRepairButton();
}

function renderDocuments(documents, query) {
  $("knowledgeCount").textContent = documents?.length || 0;
  $("ragQuery").textContent = query ? query.slice(0, 150) : "No XML-safe errors";
  const list = $("docList");
  list.innerHTML = "";
  if (!documents?.length) {
    list.className = "result-list empty-state";
    list.textContent = "No external knowledge was injected for the current issues.";
    return;
  }
  list.className = "result-list";
  documents.forEach((doc, index) => {
    const article = document.createElement("article");
    article.className = "result-row knowledge-row";
    article.innerHTML = `
      <div class="rank">${index + 1}</div>
      <div class="row-main">
        <div class="row-title">
          <strong>${escapeHtml(doc.title_en || doc.doc_id)}</strong>
          <span class="badge neutral">${escapeHtml(doc.issue_code || "mapped")}</span>
        </div>
        <p>${escapeHtml(doc.summary_en || "")}</p>
        <code>${escapeHtml(doc.doc_id || "")} · hybrid ${formatScore(doc.hybrid_score)} · ${escapeHtml(doc.reason || "retrieved")}</code>
      </div>`;
    list.appendChild(article);
  });
}

function renderTrace(payload) {
  const list = $("traceList");
  const trace = payload.trace || {};
  const rounds = trace.rounds || [];
  const safety = payload.safety_report || [];
  list.innerHTML = "";
  list.className = "result-list";

  const summary = document.createElement("article");
  summary.className = "trace-summary";
  summary.innerHTML = `
    <div><span>Stop Reason</span><strong>${escapeHtml(trace.stop_reason || "-")}</strong></div>
    <div><span>Accepted Rounds</span><strong>${trace.accepted_rounds ?? 0}</strong></div>
    <div><span>Rejected Attempts</span><strong>${trace.rejected_attempts ?? 0}</strong></div>
    <div><span>Safety Findings</span><strong>${safety.length}</strong></div>`;
  list.appendChild(summary);

  rounds.forEach((round) => {
    const article = document.createElement("article");
    article.className = "result-row trace-row";
    article.innerHTML = `
      <div class="round-number">R${escapeHtml(round.round)}</div>
      <div class="row-main">
        <div class="row-title"><strong>${round.accepted ? "Committed" : "Not committed"}</strong><span class="badge ${round.accepted ? "ok" : "warning"}">${round.accepted ? "accepted" : "rejected"}</span></div>
        <p>Error ${escapeHtml(round.before_error_count)} → ${escapeHtml(round.after_error_count ?? round.before_error_count)} · ${escapeHtml(round.attempt_count)} model attempt(s)</p>
        <code>repairable=${escapeHtml(round.repairable_issue_count)} · deferred=${escapeHtml(round.deferred_issue_count)} · rejected=${escapeHtml(round.rejected_count)}</code>
      </div>`;
    list.appendChild(article);
  });

  if (!rounds.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state inline-empty";
    empty.textContent = "The pipeline ended without entering a model repair round.";
    list.appendChild(empty);
  }
}

function activeFiles() {
  return currentFileMode === "repaired" && repairedFiles.length ? repairedFiles : originalFiles;
}

function renderFiles() {
  const files = activeFiles();
  const select = $("fileSelect");
  select.innerHTML = "";
  if (!files.length) {
    $("filePreview").textContent = "No XML files are available for display.";
    return;
  }
  files.forEach((file, index) => {
    const option = document.createElement("option");
    option.value = String(index);
    option.textContent = file.path;
    select.appendChild(option);
  });
  select.value = "0";
  $("filePreview").textContent = files[0].content;
}

function setFileMode(mode) {
  if (mode === "repaired" && !repairedFiles.length) return;
  currentFileMode = mode;
  document.querySelectorAll("#fileMode button").forEach((button) => {
    button.classList.toggle("selected", button.dataset.mode === mode);
  });
  renderFiles();
}

function resetRepairOutput() {
  repairedFiles = [];
  currentFileMode = "original";
  $("fileMode").querySelector('[data-mode="repaired"]').disabled = true;
  $("downloadButton").className = "download-button disabled";
  $("downloadButton").setAttribute("aria-disabled", "true");
  $("downloadButton").href = "#";
  $("afterErrorCount").textContent = "-";
  $("repairRate").textContent = "-";
  $("modelCalls").textContent = "-";
  $("traceList").className = "result-list empty-state";
  $("traceList").textContent = "Repair rounds, accepted or rejected attempts, and the stop reason appear here.";
}

async function handleCheck(event) {
  event.preventDefault();
  const button = $("checkButton");
  setBusy(button, true, "Checking…");
  $("pipelineState").textContent = "CHECKING";
  $("pipelineState").className = "running";
  try {
    const form = new FormData();
    const file = $("fileInput").files[0];
    if (file) form.append("file", file);
    form.append("xml_text", $("xmlText").value);
    form.append("filename", file ? file.name : "upload.xml");
    const payload = await requestJson("/api/check", { method: "POST", body: form });
    currentJobId = payload.job.job_id;
    originalFiles = payload.files || [];
    resetRepairOutput();
    $("jobLabel").textContent = `JOB ${currentJobId}`;
    $("pipelineState").textContent = currentActionableCount > 0 ? "READY" : "REVIEW";
    $("pipelineState").className = "ready";
    renderReport(payload.report, "before");
    renderDocuments(payload.documents, payload.rag_display_query || payload.rag_query);
    renderFiles();
    switchTab("issuesView");
    $("pipelineState").textContent = currentActionableCount > 0 ? "READY" : "REVIEW";
    toast("Check complete. Only XML-safe errors enter automated repair.");
  } catch (error) {
    $("pipelineState").textContent = "FAILED";
    $("pipelineState").className = "failed";
    toast(error.message);
  } finally {
    setBusy(button, false);
    updateRepairButton();
  }
}

async function handleRepair() {
  if (!currentJobId) return toast("Run a check first.");
  const button = $("repairButton");
  setBusy(button, true, "Repairing…");
  $("pipelineState").textContent = "REPAIRING";
  $("pipelineState").className = "running";
  try {
    const form = new FormData();
    form.append("job_id", currentJobId);
    form.append("provider", selectedProvider());
    form.append("model", $("modelName").value);
    form.append("max_rounds", $("maxRounds").value);
    form.append("max_model_attempts", $("maxAttempts").value);
    const payload = await requestJson("/api/repair", { method: "POST", body: form });
    repairedFiles = payload.files || [];
    originalFiles = payload.original_files || originalFiles;
    $("modelCalls").textContent = payload.job.model_calls ?? 0;
    const after = Number(payload.report?.error_count ?? beforeErrorCount);
    $("afterErrorCount").textContent = after;
    $("repairRate").textContent = beforeErrorCount > 0 ? formatRate((beforeErrorCount - after) / beforeErrorCount) : "-";
    renderReport(payload.report || { issues: [] }, "after");
    renderTrace(payload);
    $("fileMode").querySelector('[data-mode="repaired"]').disabled = !repairedFiles.length;
    if (payload.download_url) {
      $("downloadButton").href = payload.download_url;
      $("downloadButton").className = "download-button";
      $("downloadButton").setAttribute("aria-disabled", "false");
    }
    setFileMode("repaired");
    $("pipelineState").textContent = after === 0 ? "COMPLETED" : "STOPPED";
    $("pipelineState").className = after === 0 ? "completed" : "ready";
    switchTab("traceView");
    toast(payload.job.model_called ? "Repair complete." : "The pipeline ended without calling a model.");
  } catch (error) {
    $("pipelineState").textContent = "FAILED";
    $("pipelineState").className = "failed";
    toast(error.message);
  } finally {
    button.textContent = button.dataset.originalText || "Start Repair";
    updateRepairButton();
  }
}

function clearTask() {
  $("fileInput").value = "";
  $("fileLabel").textContent = "A single XML file or a ZIP containing res";
  $("xmlText").value = "";
  currentJobId = null;
  originalFiles = [];
  repairedFiles = [];
  visibleIssues = [];
  currentActionableCount = 0;
  beforeErrorCount = null;
  ["beforeErrorCount", "afterErrorCount", "actionableCount", "reviewCount", "repairRate", "modelCalls"].forEach((id) => $(id).textContent = "-");
  ["errorCount", "warningCount", "infoCount", "totalCount", "knowledgeCount"].forEach((id) => $(id).textContent = "0");
  $("jobLabel").textContent = "Not started";
  $("pipelineState").textContent = "IDLE";
  $("pipelineState").className = "";
  $("issueList").className = "result-list empty-state";
  $("issueList").textContent = "Run a check to view source-level evidence.";
  $("docList").className = "result-list empty-state";
  $("docList").textContent = "Knowledge is retrieved only for XML-safe errors.";
  resetRepairOutput();
  $("filePreview").textContent = "Select or paste XML, then run a check.";
  updateRepairButton();
  switchTab("issuesView");
}

document.querySelectorAll(".tab").forEach((tab) => tab.addEventListener("click", () => switchTab(tab.dataset.tab)));
document.querySelectorAll("#issueFilters button").forEach((button) => button.addEventListener("click", () => {
  currentIssueFilter = button.dataset.filter;
  document.querySelectorAll("#issueFilters button").forEach((item) => item.classList.toggle("selected", item === button));
  renderIssueList();
}));
document.querySelectorAll("#fileMode button").forEach((button) => button.addEventListener("click", () => setFileMode(button.dataset.mode)));
$("fileSelect").addEventListener("change", (event) => {
  const file = activeFiles()[Number(event.target.value)];
  $("filePreview").textContent = file?.content || "";
});
$("fileInput").addEventListener("change", () => {
  $("fileLabel").textContent = $("fileInput").files[0]?.name || "A single XML file or a ZIP containing res";
});
$("providerSelect").addEventListener("change", updateProviderUi);
$("checkForm").addEventListener("submit", handleCheck);
$("repairButton").addEventListener("click", handleRepair);
$("clearButton").addEventListener("click", clearTask);

loadStatus();
