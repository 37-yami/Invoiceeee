// 学生报销管家:原生 JS,无依赖
"use strict";

const CATEGORIES = ["高铁/铁路", "机票", "酒店住宿", "网约车",
                    "出租车/客运", "餐饮", "其他"];
const S = {
  code: localStorage.getItem("bx-code") || "",
  selected: new Set(),   // 票据库勾选的 id
  library: [],
};

const $ = (id) => document.getElementById(id);

function api(path, opts = {}) {
  const headers = Object.assign({}, opts.headers || {});
  if (S.code) headers["X-Access-Code"] = S.code;
  if (opts.body && !(opts.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }
  return fetch(path, Object.assign({}, opts, { headers })).then(async (r) => {
    if (r.status === 401) { showCodeDialog(); throw new Error("需要访问码"); }
    const ct = r.headers.get("Content-Type") || "";
    if (!ct.includes("application/json")) {
      if (!r.ok) throw new Error("请求失败 " + r.status);
      return r;  // 文件响应,调用方自行取 blob
    }
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || ("请求失败 " + r.status));
    return data;
  });
}
const imgUrl = (id) =>
  `/image/${id}` + (S.code ? `?code=${encodeURIComponent(S.code)}` : "");

function msg(id, text, isError) {
  const el = $(id);
  el.textContent = text || "";
  el.classList.toggle("error", !!isError);
}
function btn(text, onclick, cls) {
  const b = document.createElement("button");
  b.textContent = text;
  b.onclick = onclick;
  if (cls) b.classList.add(cls);
  return b;
}

// ---- 访问码 ----
function showCodeDialog() { $("code-dialog").hidden = false; }
$("code-submit").onclick = () => {
  S.code = $("code-input").value.trim();
  localStorage.setItem("bx-code", S.code);
  $("code-dialog").hidden = true;
  boot();
};

// ---- 页签 ----
document.querySelectorAll("nav#tabs button").forEach((b) => {
  b.onclick = () => {
    document.querySelectorAll("nav#tabs button").forEach((x) =>
      x.classList.toggle("active", x === b));
    document.querySelectorAll("section.tab").forEach((s) =>
      s.classList.toggle("active", s.id === "tab-" + b.dataset.tab));
    const t = b.dataset.tab;
    if (t === "upload") loadPending();
    if (t === "library") loadLibrary();
    if (t === "report") renderReport();
    if (t === "settings") loadSettings();
  };
});

// ---- 上传 ----
$("upload-btn").onclick = upload;
$("file-input").onchange = upload;
const dz = $("drop-zone");
dz.ondragover = (e) => { e.preventDefault(); dz.classList.add("drag"); };
dz.ondragleave = () => dz.classList.remove("drag");
dz.ondrop = (e) => {
  e.preventDefault();
  dz.classList.remove("drag");
  uploadFiles(e.dataTransfer.files);
};
function upload() {
  uploadFiles($("file-input").files);
  $("file-input").value = "";
}
function uploadFiles(files) {
  if (!files || !files.length) return;
  const fd = new FormData();
  for (const f of files) {
    if (/image\/(jpe?g|png|webp)/.test(f.type)) fd.append("files", f);
  }
  if (!fd.has("files")) { msg("upload-msg", "未选择图片", true); return; }
  const cat = $("upload-category").value;
  if (cat) fd.append("category", cat);
  msg("upload-msg", "上传中…");
  api("/api/upload", { method: "POST", body: fd })
    .then((d) => {
      const rows = d.invoices || [];
      const dups = rows.filter((r) => r.dup_flag).length;
      msg("upload-msg", `已上传 ${rows.length} 张` +
          (dups ? `,疑似重复 ${dups} 张(可强制保留)` : ""));
      loadPending();
    })
    .catch((e) => msg("upload-msg", e.message, true));
}

// ---- 票据编辑器(待确认与票据库共用) ----
function editorRow(inv, afterSave) {
  const box = document.createElement("div");
  box.className = "item";

  const img = document.createElement("img");
  img.className = "thumb";
  img.loading = "lazy";
  img.src = imgUrl(inv.id);
  img.onclick = () => window.open(img.src, "_blank");
  box.appendChild(img);

  const wrap = document.createElement("div");
  const fields = document.createElement("div");
  fields.className = "fields";
  const mk = (labelText, key, type) => {
    const l = document.createElement("label");
    l.textContent = labelText;
    let input;
    if (key === "category") {
      input = document.createElement("select");
      for (const c of ["unknown", ...CATEGORIES]) {
        const o = document.createElement("option");
        o.value = c;
        o.textContent = c === "unknown" ? "(待选择)" : c;
        input.appendChild(o);
      }
      input.value = inv.category || "unknown";
    } else {
      input = document.createElement("input");
      if (type === "number") {
        input.type = "number"; input.step = "0.01"; input.min = "0";
      }
      if (type === "date") input.type = "date";
      input.value = inv[key] ?? "";
    }
    input.dataset.key = key;
    l.appendChild(input);
    fields.appendChild(l);
  };
  mk("类别", "category");
  mk("金额(元)", "amount", "number");
  mk("日期", "invoice_date", "date");
  mk("商户/行程", "merchant");
  mk("发票号", "invoice_no");
  mk("备注", "note");
  wrap.appendChild(fields);

  const ops = document.createElement("div");
  ops.className = "ops";
  if (inv.dup_flag) {
    const badge = document.createElement("span");
    badge.className = "badge dup";
    badge.textContent = `疑似重复 #${inv.dup_of}`;
    ops.appendChild(badge);
    ops.appendChild(btn("强制保留", () =>
      api(`/api/invoices/${inv.id}/force-keep`, { method: "POST" })
        .then(afterSave)
        .catch((e) => alert(e.message))));
  }
  if (inv.status === "confirmed") {
    const ok = document.createElement("span");
    ok.className = "badge ok";
    ok.textContent = "已确认";
    ops.appendChild(ok);
  }
  const collect = () => {
    const body = {};
    box.querySelectorAll("[data-key]").forEach((el) => {
      const k = el.dataset.key;
      body[k] = k === "amount"
        ? (el.value === "" ? null : parseFloat(el.value))
        : el.value;
    });
    return body;
  };
  const put = (extra) => api(`/api/invoices/${inv.id}`, {
    method: "PUT",
    body: JSON.stringify(Object.assign(collect(), extra || {})),
  });
  ops.appendChild(btn("保存", () =>
    put().then(afterSave).catch((e) => alert(e.message))));
  ops.appendChild(btn("确认归档", () =>
    put({ status: "confirmed" })
      .then(afterSave)
      .catch((e) => alert(e.message)), "primary"));
  ops.appendChild(btn("删除", () => {
    if (window.confirm(`删除票据 #${inv.id}?原图移入回收站。`)) {
      api(`/api/invoices/${inv.id}`, { method: "DELETE" })
        .then(afterSave)
        .catch((e) => alert(e.message));
    }
  }, "danger"));
  wrap.appendChild(ops);
  box.appendChild(wrap);
  return box;
}

// ---- 待确认 ----
function loadPending() {
  return api("/api/invoices?status=pending").then((rows) => {
    $("pending-count").textContent = rows.length ? `(${rows.length})` : "";
    const list = $("pending-list");
    list.innerHTML = "";
    if (!rows.length) {
      list.innerHTML = '<p class="muted">无待确认票据。</p>';
      return;
    }
    rows.sort((a, b) => a.id - b.id)
      .forEach((inv) => list.appendChild(editorRow(inv, loadPending)));
  }).catch((e) => msg("upload-msg", e.message, true));
}

// ---- 票据库 ----
function loadLibrary() {
  const q = new URLSearchParams();
  [["status", "f-status"], ["category", "f-category"],
   ["date_from", "f-from"], ["date_to", "f-to"], ["q", "f-q"]]
    .forEach(([param, id]) => {
      const v = $(id).value;
      if (v) q.set(param, v);
    });
  return api("/api/invoices?" + q.toString()).then((rows) => {
    S.library = rows;
    const list = $("library-list");
    list.innerHTML = "";
    if (!rows.length) {
      list.innerHTML = '<p class="muted">没有符合条件的票据。</p>';
      updateSummary();
      return;
    }
    rows.forEach((inv) => {
      const row = editorRow(inv, loadLibrary);
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = S.selected.has(inv.id);
      cb.onchange = () => {
        if (cb.checked) S.selected.add(inv.id);
        else S.selected.delete(inv.id);
        updateSummary();
      };
      row.prepend(cb);
      list.appendChild(row);
    });
    updateSummary();
  }).catch((e) => alert(e.message));
}
function updateSummary() {
  const picked = S.library.filter((i) => S.selected.has(i.id));
  const total = picked.reduce((s, i) => s + (Number(i.amount) || 0), 0);
  $("library-summary").textContent = picked.length
    ? `已勾选 ${picked.length} 张,合计 ${total.toFixed(2)} 元。`
    : "勾选票据以生成汇总单。";
}
$("f-apply").onclick = loadLibrary;

// ---- 生成汇总单 ----
function renderReport() {
  $("report-summary").textContent = S.selected.size
    ? `已选 ${S.selected.size} 张票据。填写下方信息后生成。`
    : "尚未勾选票据。";
}
function reportMeta() {
  return {
    name: $("m-name").value.trim(),
    student_id: $("m-sid").value.trim(),
    project: $("m-project").value.trim(),
    date_from: $("m-from").value,
    date_to: $("m-to").value,
    reason: $("m-reason").value.trim(),
  };
}
$("preview-btn").onclick = () => {
  api("/api/report/preview", {
    method: "POST",
    body: JSON.stringify({ ids: [...S.selected] }),
  })
    .then((d) => msg("report-result",
                     `共 ${d.count} 张,合计 ${d.total} 元`))
    .catch((e) => msg("report-result", e.message, true));
};
function downloadReport(kind) {
  api(`/api/report/${kind}`, {
    method: "POST",
    body: JSON.stringify({ ids: [...S.selected], meta: reportMeta() }),
  })
    .then((r) => {
      let name = kind === "docx" ? "报销汇总单.docx" : "报销明细.csv";
      const m = (r.headers.get("Content-Disposition") || "")
        .match(/filename\*=UTF-8''([^;]+)/);
      if (m) name = decodeURIComponent(m[1]);
      return r.blob().then((b) => {
        const a = document.createElement("a");
        a.href = URL.createObjectURL(b);
        a.download = name;
        a.click();
        URL.revokeObjectURL(a.href);
        msg("report-result", `已生成:${name}(工作区 exports/ 目录留有备份)`);
      });
    })
    .catch((e) => msg("report-result", e.message, true));
}
$("docx-btn").onclick = () => downloadReport("docx");
$("csv-btn").onclick = () => downloadReport("csv");

// ---- 设置 ----
function loadSettings() {
  return api("/api/settings").then((s) => {
    $("s-name").value = s.default_name || "";
    $("s-sid").value = s.default_student_id || "";
    $("s-project").value = s.default_project || "";
    $("s-ocr").value = s.ocr_cmd || "";
    if (!$("m-name").value) $("m-name").value = s.default_name || "";
    if (!$("m-sid").value) $("m-sid").value = s.default_student_id || "";
    if (!$("m-project").value) $("m-project").value = s.default_project || "";
  }).catch((e) => msg("settings-msg", e.message, true));
}
$("settings-save").onclick = () => {
  api("/api/settings", {
    method: "PUT",
    body: JSON.stringify({
      default_name: $("s-name").value,
      default_student_id: $("s-sid").value,
      default_project: $("s-project").value,
      ocr_cmd: $("s-ocr").value,
    }),
  })
    .then(() => msg("settings-msg", "已保存"))
    .catch((e) => msg("settings-msg", e.message, true));
};

// ---- 初始化 ----
for (const sel of [$("upload-category"), $("f-category")]) {
  for (const c of CATEGORIES) {
    const o = document.createElement("option");
    o.value = c;
    o.textContent = c;
    sel.appendChild(o);
  }
}
function boot() {
  api("/api/access-info").then((info) => {
    if (info.require_code && !S.code) showCodeDialog();
    return loadPending();
  }).catch(() => {});
}
boot();
