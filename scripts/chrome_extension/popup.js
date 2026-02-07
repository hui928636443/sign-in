const FAILED_REPORT_PATH = "failed_sites.json";
const STORAGE_KEYS = {
  baseAccounts: "manual_patch_base_accounts",
  resultAccounts: "manual_patch_result_accounts",
  failedReportOverrideEnabled: "manual_patch_failed_report_override_enabled",
  failedReportOverridePayload: "manual_patch_failed_report_override_payload",
  failedReportOverrideFileName: "manual_patch_failed_report_override_file_name",
};

const statusEl = document.getElementById("status");
const failedMetaEl = document.getElementById("failedMeta");
const failedPreviewEl = document.getElementById("failedPreview");
const importFailedBtn = document.getElementById("importFailedBtn");
const failedFileInputEl = document.getElementById("failedFileInput");
const openMergeToolBtn = document.getElementById("openMergeToolBtn");
const baseAccountsEl = document.getElementById("baseAccounts");
const resultJsonEl = document.getElementById("resultJson");
const extractSummaryEl = document.getElementById("extractSummary");

const refreshBtn = document.getElementById("refreshBtn");
const openFailedBtn = document.getElementById("openFailedBtn");
const extractBtn = document.getElementById("extractBtn");
const copyBtn = document.getElementById("copyBtn");

let failedSites = [];

function setStatus(message) {
  statusEl.textContent = message;
}

function storageGet(keys) {
  return new Promise((resolve) => {
    chrome.storage.local.get(keys, resolve);
  });
}

function storageSet(payload) {
  return new Promise((resolve) => {
    chrome.storage.local.set(payload, resolve);
  });
}

function storageRemove(keys) {
  return new Promise((resolve) => {
    chrome.storage.local.remove(keys, resolve);
  });
}

function safeJsonParse(text, fallback) {
  try {
    return JSON.parse(text);
  } catch {
    return fallback;
  }
}

function normalizeProvider(value) {
  return String(value || "").trim().toLowerCase();
}

function normalizeFailedSite(site) {
  return {
    provider: normalizeProvider(site.provider),
    account_name: String(site.account_name || "").trim(),
    api_user: String(site.api_user || "").trim(),
    site_url: String(site.site_url || "").trim(),
    login_url: String(site.login_url || "").trim(),
    oauth_login_url: String(site.oauth_login_url || "").trim(),
    reason: String(site.reason || "").trim(),
  };
}

function normalizeFailedReport(report, defaultSource = "unknown") {
  const failed = Array.isArray(report?.failed_sites) ? report.failed_sites : [];
  return {
    generated_at: report?.generated_at || new Date().toISOString(),
    source: String(report?.source || defaultSource),
    failed_count: failed.length,
    failed_sites: failed,
  };
}

function parseDomainFromUrl(rawUrl) {
  try {
    return new URL(rawUrl).hostname;
  } catch {
    return "";
  }
}

function normalizeAccountRecord(input) {
  if (!input || typeof input !== "object") return null;
  const provider = normalizeProvider(input.provider || "");
  const apiUser = String(input.api_user || "").trim();
  if (!provider || !apiUser) return null;

  const name = String(input.name || `${provider}_${apiUser}`).trim() || `${provider}_${apiUser}`;
  const session = String(input.cookies?.session || "").trim();
  return {
    name,
    provider,
    cookies: { session },
    api_user: apiUser,
  };
}

function parseAccountsJsonArray(raw, sourceLabel = "账号配置") {
  const parsed = safeJsonParse(raw, null);
  if (!Array.isArray(parsed)) {
    throw new Error(`${sourceLabel} 不是 JSON 数组`);
  }
  return parsed.map(normalizeAccountRecord).filter(Boolean);
}

function dedupeByKey(items, keyFn) {
  const map = new Map();
  items.forEach((item) => {
    const key = keyFn(item);
    if (key) {
      map.set(key, item);
    }
  });
  return Array.from(map.values());
}

function renderFailedSites(report) {
  const normalized = normalizeFailedReport(report);
  const sites = normalized.failed_sites.map(normalizeFailedSite);
  failedSites = dedupeByKey(sites, (x) => `${x.provider}_${x.account_name}_${x.api_user}`);

  const generatedAt = normalized.generated_at
    ? String(normalized.generated_at).replace("T", " ").slice(0, 19)
    : "未知";
  const source = normalized.source ? ` | 来源 ${normalized.source}` : "";
  failedMetaEl.textContent = `失败 ${failedSites.length} 个 | 生成时间 ${generatedAt}${source}`;

  if (!failedSites.length) {
    failedPreviewEl.textContent = "暂无失败站点";
    return;
  }

  const lines = failedSites.slice(0, 8).map((site, idx) => {
    return `${idx + 1}. ${site.provider} / ${site.account_name || "未命名"}\n   ${site.reason || "无失败原因"}`;
  });
  if (failedSites.length > 8) {
    lines.push(`... 还有 ${failedSites.length - 8} 个`);
  }
  failedPreviewEl.textContent = lines.join("\n");
}

async function loadFailedReport() {
  const url = `${chrome.runtime.getURL(FAILED_REPORT_PATH)}?t=${Date.now()}`;
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`读取失败清单失败: HTTP ${response.status}`);
  }
  const report = normalizeFailedReport(await response.json(), "local");
  renderFailedSites(report);
}

async function importFailedReportFromFile(file) {
  const raw = await file.text();
  const parsed = safeJsonParse(raw, null);
  if (!parsed || !Array.isArray(parsed.failed_sites)) {
    throw new Error("导入失败：文件不是有效的 failed_sites.json 格式");
  }

  const report = normalizeFailedReport(parsed, "email_import");
  renderFailedSites(report);

  await storageSet({
    [STORAGE_KEYS.failedReportOverrideEnabled]: true,
    [STORAGE_KEYS.failedReportOverridePayload]: JSON.stringify(report),
    [STORAGE_KEYS.failedReportOverrideFileName]: file.name,
  });

  setStatus(`已导入失败清单：${file.name}（${failedSites.length} 个）。`);
}

async function clearImportedFailedReport() {
  await storageRemove([
    STORAGE_KEYS.failedReportOverrideEnabled,
    STORAGE_KEYS.failedReportOverridePayload,
    STORAGE_KEYS.failedReportOverrideFileName,
  ]);
}

async function restoreImportedFailedReport() {
  const data = await storageGet([
    STORAGE_KEYS.failedReportOverrideEnabled,
    STORAGE_KEYS.failedReportOverridePayload,
    STORAGE_KEYS.failedReportOverrideFileName,
  ]);

  if (!data[STORAGE_KEYS.failedReportOverrideEnabled]) {
    return false;
  }

  const payload = String(data[STORAGE_KEYS.failedReportOverridePayload] || "").trim();
  if (!payload) {
    return false;
  }

  const parsed = safeJsonParse(payload, null);
  if (!parsed || !Array.isArray(parsed.failed_sites)) {
    return false;
  }

  renderFailedSites(normalizeFailedReport(parsed, "email_import"));
  const fileName = String(data[STORAGE_KEYS.failedReportOverrideFileName] || "导入文件");
  setStatus(`已加载导入失败清单：${fileName}。可点“刷新失败清单”切回本地文件。`);
  return true;
}

function pickOpenUrl(site) {
  return site.login_url || site.oauth_login_url || site.site_url || "";
}

async function openAllFailedSites() {
  if (!failedSites.length) {
    setStatus("失败清单为空，先刷新。");
    return;
  }

  const urls = dedupeByKey(
    failedSites.map(pickOpenUrl).filter(Boolean),
    (x) => x
  );

  if (!urls.length) {
    setStatus("失败清单里没有可打开的 URL。");
    return;
  }

  for (const url of urls) {
    await chrome.tabs.create({ url, active: false });
    await new Promise((resolve) => setTimeout(resolve, 180));
  }

  setStatus(`已打开 ${urls.length} 个失败站点，请逐个人工登录。`);
}

async function getSessionByDomain(domain) {
  return new Promise((resolve) => {
    chrome.cookies.getAll({ domain }, (cookies) => {
      const hit = cookies.find((c) => c.name === "session" && c.value);
      resolve(hit ? hit.value : "");
    });
  });
}

async function getApiUserFromOpenTab(domain) {
  const tabs = await chrome.tabs.query({ url: [`*://${domain}/*`, `*://*.${domain}/*`] });
  if (!tabs.length) return "";

  try {
    const results = await chrome.scripting.executeScript({
      target: { tabId: tabs[0].id },
      func: () => {
        const keys = ["user", "newapi_user", "profile"]; 
        for (const k of keys) {
          const v = localStorage.getItem(k);
          if (!v) continue;
          try {
            const obj = JSON.parse(v);
            if (obj && (obj.id || obj.api_user || obj.user_id)) {
              return String(obj.id || obj.api_user || obj.user_id);
            }
          } catch {}
        }
        return "";
      },
    });
    return String(results?.[0]?.result || "").trim();
  } catch {
    return "";
  }
}

function parseBaseAccounts() {
  const raw = baseAccountsEl.value.trim();
  if (!raw) return [];
  return parseAccountsJsonArray(raw, "当前 NEWAPI_ACCOUNTS");
}

function mergeAccountPair(existing, incoming) {
  const incomingSession = String(incoming?.cookies?.session || "").trim();
  const existingSession = String(existing?.cookies?.session || "").trim();
  return {
    name: String(incoming?.name || existing?.name || "").trim(),
    provider: normalizeProvider(incoming?.provider || existing?.provider),
    cookies: { session: incomingSession || existingSession },
    api_user: String(incoming?.api_user || existing?.api_user || "").trim(),
  };
}

function mergeAccounts(baseAccounts, newAccounts) {
  const map = new Map();
  const upsert = (item) => {
    const normalized = normalizeAccountRecord(item);
    if (!normalized) return;
    const key = `${normalized.provider}_${normalized.api_user}`;
    const existing = map.get(key);
    if (!existing) {
      map.set(key, normalized);
      return;
    }
    map.set(key, mergeAccountPair(existing, normalized));
  };

  baseAccounts.forEach(upsert);
  newAccounts.forEach(upsert);

  return Array.from(map.values()).sort((a, b) => {
    const byProvider = a.provider.localeCompare(b.provider);
    if (byProvider !== 0) return byProvider;
    return String(a.api_user).localeCompare(String(b.api_user));
  });
}

async function extractFailedCookiesAndBuildSecret() {
  if (!failedSites.length) {
    setStatus("失败清单为空，先刷新。");
    return;
  }

  let baseAccounts = [];
  try {
    baseAccounts = parseBaseAccounts();
  } catch (e) {
    setStatus(`解析当前 NEWAPI_ACCOUNTS 失败: ${e.message}`);
    return;
  }

  const extracted = [];
  const missed = [];

  for (const site of failedSites) {
    const openUrl = pickOpenUrl(site) || site.site_url;
    const domain = parseDomainFromUrl(openUrl || site.site_url);
    if (!domain || !site.provider) {
      missed.push(`${site.provider || "unknown"}/${site.account_name || "unknown"}: 缺少域名或 provider`);
      continue;
    }

    const session = await getSessionByDomain(domain);
    if (!session) {
      missed.push(`${site.provider}/${site.account_name || "unknown"}: 未找到 session cookie`);
      continue;
    }

    const apiUserFromPage = await getApiUserFromOpenTab(domain);
    const apiUser = apiUserFromPage || site.api_user;
    if (!apiUser) {
      missed.push(`${site.provider}/${site.account_name || "unknown"}: 缺少 api_user`);
      continue;
    }

    extracted.push({
      name: site.account_name || `${site.provider}_${apiUser}`,
      provider: site.provider,
      cookies: { session },
      api_user: String(apiUser),
    });
  }

  const merged = mergeAccounts(baseAccounts, extracted);
  resultJsonEl.value = JSON.stringify(merged, null, 2);

  const lines = [];
  lines.push(`提取成功 ${extracted.length} 个，失败 ${missed.length} 个。`);
  if (missed.length) {
    lines.push("未成功项:");
    missed.slice(0, 12).forEach((x) => lines.push(`- ${x}`));
    if (missed.length > 12) {
      lines.push(`- ... 还有 ${missed.length - 12} 个`);
    }
  }

  extractSummaryEl.textContent = lines.join("\n");
  setStatus(`完成：已生成 NEWAPI_ACCOUNTS（共 ${merged.length} 条）。`);

  await storageSet({
    [STORAGE_KEYS.baseAccounts]: baseAccountsEl.value,
    [STORAGE_KEYS.resultAccounts]: resultJsonEl.value,
  });
}

async function copyResult() {
  const text = resultJsonEl.value.trim();
  if (!text) {
    setStatus("没有可复制的结果 JSON。");
    return;
  }
  await navigator.clipboard.writeText(text);
  setStatus("已复制生成结果，可直接粘贴到 GitHub Secret: NEWAPI_ACCOUNTS。");
}

async function restoreDraft() {
  const data = await storageGet([STORAGE_KEYS.baseAccounts, STORAGE_KEYS.resultAccounts]);
  if (data[STORAGE_KEYS.baseAccounts]) {
    baseAccountsEl.value = data[STORAGE_KEYS.baseAccounts];
  }
  if (data[STORAGE_KEYS.resultAccounts]) {
    resultJsonEl.value = data[STORAGE_KEYS.resultAccounts];
  }
}

refreshBtn.addEventListener("click", async () => {
  try {
    await loadFailedReport();
    await clearImportedFailedReport();
    setStatus("失败清单刷新成功（已切回本地 failed_sites.json）。");
  } catch (e) {
    setStatus(e.message);
  }
});

importFailedBtn.addEventListener("click", () => {
  failedFileInputEl.value = "";
  failedFileInputEl.click();
});

failedFileInputEl.addEventListener("change", async () => {
  const file = failedFileInputEl.files?.[0];
  if (!file) return;

  importFailedBtn.disabled = true;
  try {
    await importFailedReportFromFile(file);
  } catch (e) {
    setStatus(e.message || "导入失败清单失败。");
  } finally {
    importFailedBtn.disabled = false;
    failedFileInputEl.value = "";
  }
});

openMergeToolBtn.addEventListener("click", async () => {
  const url = chrome.runtime.getURL("merge.html");
  await chrome.tabs.create({ url, active: true });
  setStatus("已打开独立 JSON 合并去重工具（新标签页）。");
});

openFailedBtn.addEventListener("click", async () => {
  await openAllFailedSites();
});

extractBtn.addEventListener("click", async () => {
  extractBtn.disabled = true;
  try {
    await extractFailedCookiesAndBuildSecret();
  } finally {
    extractBtn.disabled = false;
  }
});

copyBtn.addEventListener("click", async () => {
  await copyResult();
});

(async function init() {
  await restoreDraft();
  const restored = await restoreImportedFailedReport();
  if (restored) {
    return;
  }
  try {
    await loadFailedReport();
    setStatus("已加载失败站点清单。按顺序：打开站点 -> 人工登录 -> 提取生成。 ");
  } catch (e) {
    setStatus(`${e.message}。请先 pull 最新仓库。`);
  }
})();
