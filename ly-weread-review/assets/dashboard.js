// weread-reading-review
(() => {
  const palettes = {
    "米棕暖调": ["#8b5633", "#f6eee3", "#fffaf3"],
    "黛蓝雾灰": ["#3f507b", "#e6ebf3", "#f3f6fd"],
    "抹茶奶油": ["#4e642c", "#e9efdb", "#f7faef"],
    "香芋紫": ["#72548c", "#eee7f5", "#faf5ff"],
    "砖红拿铁": ["#9a4337", "#f4e7df", "#fff7f2"],
    "珊瑚奶油": ["#a24e52", "#f9e6e2", "#fff5f4"],
    "雾蓝银灰": ["#4c6774", "#e5edf0", "#f2f8fb"],
  };
  const hex = /^#[0-9a-f]{6}$/i;
  const css = `
  .wr-review{--ink:#222529;--muted:#535960;background:var(--paper);color:var(--ink);
    border:1px solid var(--tint);border-radius:20px;padding:clamp(16px,4vw,34px);
    font:14px/1.65 system-ui,-apple-system,"PingFang SC",sans-serif;box-sizing:border-box}
  .wr-review *{box-sizing:border-box}
  .wr-review h2,.wr-review h3,.wr-review p{margin:0;color:var(--ink)}
  .wr-review h2{font-size:clamp(24px,4.2vw,37px);line-height:1.25;font-weight:760}
  .wr-review h3{font-weight:730;font-size:17px;line-height:1.4}
  .wr-review .wr-muted{color:var(--muted)}
  .wr-controls{display:flex;align-items:end;gap:10px 14px;flex-wrap:wrap;margin:0 0 23px}
  .wr-controls label{display:grid;gap:3px;font-size:12px;color:var(--muted)}
  .wr-controls select,.wr-controls input{font:inherit;color:var(--ink);background:#fff;border:1px solid #bfc2c6;
    border-radius:7px;height:32px;max-width:100%;padding:0 8px;box-shadow:none}
  .wr-controls input{width:45px;padding:3px}
  .wr-metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(125px,100%),1fr));gap:8px;margin:18px 0}
  .wr-panel,.wr-metric{padding:15px;border:1px solid var(--tint);border-radius:12px;background:#fff;min-width:0}
  .wr-metric{border-top:3px solid var(--accent)}
  .wr-metric strong{display:block;font-size:20px;line-height:1.25;margin-top:5px}
  .wr-panel{margin:10px 0;overflow-wrap:anywhere}
  .wr-panel > p{margin-top:5px}
  .wr-columns{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,265px),1fr));gap:10px}
  .wr-columns .wr-panel{margin:0}
  .wr-bars{display:grid;grid-template-columns:repeat(var(--wr-bar-count),minmax(0,1fr));gap:3px;align-items:end;
    margin:11px 0 4px;padding:0;list-style:none}
  .wr-bars li{display:grid;grid-template-rows:86px auto;justify-items:center;margin:0;padding:0;min-width:0}
  .wr-bars li span:first-child{width:100%;max-width:25px;align-self:end;border-radius:4px 4px 1px 1px;
    height:var(--bar-height);background:var(--accent);border:1px solid rgba(23,31,37,.23)}
  .wr-bars li[data-state=missing] span:first-child{height:3px;background:#d6d9db}
  .wr-bars li[data-state=future] span:first-child{visibility:hidden}
  .wr-bars li span+span{color:var(--muted);font-size:11px;margin-top:4px;height:18px}
  .wr-layout-list{padding:0;margin:6px 0 0;list-style:none}
  .wr-layout-list li{margin:0;padding:8px 0;border-bottom:1px solid var(--tint)}
  .wr-layout-list li:last-child{border-bottom:0}
  .wr-layout-list strong{display:block}
  .wr-review a{color:#173c6e;text-decoration:underline;text-underline-offset:3px}
  .wr-footer{margin-top:14px}
  `;

  function add(parent, tag, label, className) {
    const node = document.createElement(tag);
    if (label !== undefined) node.textContent = label;
    if (className) node.className = className;
    parent.append(node);
    return node;
  }

  function duration(seconds) {
    if (seconds == null) return "未返回";
    if (seconds > 0 && seconds < 60) return seconds + " 秒";
    const minutes = Math.floor(seconds / 60);
    return minutes >= 60 ? Math.floor(minutes / 60) + " 小时 " + minutes % 60 + " 分" : minutes + " 分钟";
  }

  function drawTrend(panel, report) {
    const monthly = report.period.length === 7;
    const [year, month] = report.period.split("-").map(Number);
    const limit = monthly ? new Date(Date.UTC(year, month, 0)).getUTCDate() : 12;
    const last = monthly ? report.through : report.through.slice(0, 7);
    const max = Math.max(1, ...Object.values(report.buckets));
    const list = add(panel, "ul", undefined, "wr-bars");
    list.style.setProperty("--wr-bar-count", limit);
    list.setAttribute("aria-label", "阅读与收听的时长分布");
    for (let index = 1; index <= limit; index++) {
      const key = (monthly ? report.period : report.period.slice(0, 4)) + "-" + String(index).padStart(2, "0");
      const value = report.buckets[key];
      const label = (monthly ? index + " 日" : index + " 月") + " · " + (key > last ? "未到" : duration(value));
      const mark = add(list, "li");
      mark.title = label;
      mark.setAttribute("aria-label", label);
      mark.dataset.state = key > last ? "future" : value == null ? "missing" : "present";
      const bar = add(mark, "span");
      bar.style.setProperty("--bar-height", Math.max(2, Math.round((value || 0) * 86 / max)) + "px");
      add(mark, "span", !monthly || index === 1 || index === limit || index % 5 === 0 ? index : "");
    }
    add(panel, "p", "灰色短线表示微信读书未返回该时段的数据。", "wr-muted");
  }

  function appendList(panel, entries, empty, fill) {
    if (!entries.length) {
      add(panel, "p", empty, "wr-muted");
      return;
    }
    const list = add(panel, "ul", undefined, "wr-layout-list");
    for (const item of entries) fill(add(list, "li"), item);
  }

  function panel(parent, title) {
    const section = add(parent, "section", undefined, "wr-panel");
    add(section, "h3", title);
    return section;
  }

  function drawReport(root, report, openNote) {
    root.replaceChildren();
    const monthly = report.period.length === 7;
    add(root, "h2", report.period + (monthly ? " 月度阅读回顾" : " 年度阅读回顾"));
    const first = report.period + (monthly ? "-01" : "-01-01");
    add(root, "p", first + " 至 " + report.through + (report.partial ? " · 本期进行中" : "") + " · 北京时间", "wr-muted");
    const grid = add(root, "div", undefined, "wr-metrics");
    for (const [label, value] of report.metrics) {
      const card = add(grid, "div", undefined, "wr-metric");
      add(card, "span", label, "wr-muted");
      add(card, "strong", value);
    }
    drawTrend(panel(root, monthly ? "每日阅读" : "每月阅读"), report);
    const columns = add(root, "div", undefined, "wr-columns");
    appendList(panel(columns, "阅读偏好"), report.categories, "本期未返回可展示的偏好分类。", (item, entry) => {
      add(item, "strong", entry.title);
      add(item, "span", duration(entry.seconds), "wr-muted");
    });
    appendList(panel(columns, "阅读与收听排行"), report.ranking, "本期未返回排行条目。", (item, entry) => {
      add(item, "strong", entry.title);
      add(item, "span", [entry.author, duration(entry.seconds)].filter(Boolean).join(" · "), "wr-muted");
    });
    const patterns = panel(root, report.goal ? "目标与待补主题" : "阅读观察与探索方向");
    if (report.goal) add(patterns, "p", "这次的阅读目标：" + report.goal);
    appendList(patterns, report.patterns, "目前没有足够依据给出进一步判断。", (item, entry) => {
      add(item, "strong", entry.label);
      add(item, "span", entry.evidence);
    });
    appendList(panel(root, "推荐阅读"), report.books, "本期暂无核实后的推荐书目。", (item, book) => {
      const title = add(item, "strong");
      const label = "《" + book.title + "》" + (book.author ? " · " + book.author : "");
      if (/^(https?|weread):\/\//i.test(book.url)) {
        const link = add(title, "a", label);
        link.href = book.url;
        link.rel = "noreferrer";
      } else {
        title.textContent = label;
      }
      add(item, "p", book.why);
      add(item, "p", "从这里开始：" + book.start, "wr-muted");
    });
    if (report.plan.length) appendList(panel(root, "未来 30 天计划"), report.plan, "", (item, step) => {
      add(item, "strong", step.start + " 至 " + step.end);
      add(item, "span", step.action);
    });
    const source = add(root, "div", undefined, "wr-footer");
    add(source, "p", "数据来源：微信读书。有效阅读天数按单日满 1 分钟计。", "wr-muted");
    if (openNote) {
      const link = add(source, "a", "打开这期回顾与我的复盘");
      link.href = "#";
      link.addEventListener("click", (event) => {
        event.preventDefault();
        openNote(report.path);
      });
    }
  }

  function mount(container, reports, options = {}) {
    const root = add(container, "div", undefined, "wr-review");
    add(root, "style", css);
    const controls = add(root, "div", undefined, "wr-controls");
    const reportSelect = add(add(controls, "label", "回顾周期"), "select");
    reportSelect.disabled = reports.length === 0;
    if (!reports.length) add(reportSelect, "option", "暂无回顾");
    for (const report of reports) {
      const entry = add(reportSelect, "option", report.period + (report.period.length === 7 ? " 月报" : " 年报"));
      entry.value = report.period;
    }
    const themeSelect = add(add(controls, "label", "看板配色"), "select");
    add(themeSelect, "option", "使用默认").value = "default";
    for (const theme of Object.keys(palettes)) add(themeSelect, "option", theme);
    add(themeSelect, "option", "自选颜色");
    const customGroup = add(controls, "label", "自选颜色");
    const colorPicker = add(customGroup, "input");
    colorPicker.type = "color";
    colorPicker.value = "#8b5633";
    const defaultTheme = options.theme || "米棕暖调";
    const key = options.storageKey;
    let saved;
    try { saved = key ? localStorage.getItem(key) : null; } catch (_) { /* 隐私模式可现场换色。 */ }
    themeSelect.value = saved && palettes[saved] ? saved : saved && hex.test(saved) ? "自选颜色" : "default";
    if (saved && hex.test(saved)) colorPicker.value = saved;
    else if (hex.test(defaultTheme)) colorPicker.value = defaultTheme;
    const setTheme = (persist) => {
      const picked = themeSelect.value;
      const theme = picked === "自选颜色" ? colorPicker.value : picked === "default" ? defaultTheme : picked;
      const [accent, tint, paper] = palettes[theme] || [hex.test(theme) ? theme : "#8b5633", "#e8e8e9", "#f7f7f6"];
      root.style.setProperty("--accent", accent);
      root.style.setProperty("--tint", tint);
      root.style.setProperty("--paper", paper);
      customGroup.style.display = picked === "自选颜色" ? "" : "none";
      if (persist && key) {
        try {
          if (picked === "default") localStorage.removeItem(key);
          else localStorage.setItem(key, theme);
        } catch (_) { /* 保留当前预览。 */ }
      }
    };
    themeSelect.addEventListener("change", () => setTheme(true));
    colorPicker.addEventListener("input", () => setTheme(true));
    setTheme(false);
    const reportArea = add(root, "div");
    function show() {
      const current = reports.find(report => report.period === reportSelect.value);
      if (current) drawReport(reportArea, current, options.openNote);
      else add(reportArea, "p", "生成第一份月报或年报后，它会出现在这里。");
    }
    reportSelect.addEventListener("change", show);
    show();
  }

  async function openObsidian() {
    const current = dv.current().file;
    const sourceFiles = dv.app.vault.getMarkdownFiles().filter(file =>
      file.parent.path === current.folder &&
      /^\d{4}(?:-\d{2})? 微信读书(月度|年度)回顾\.md$/.test(file.name));
    const reports = [];
    const failed = [];
    for (const file of sourceFiles) {
      const note = await dv.app.vault.cachedRead(file);
      const encoded = note.match(/<!-- weread-review-payload:([A-Za-z0-9+/=]+) -->/)?.[1];
      if (!encoded) continue;
      try {
        const bytes = Uint8Array.from(atob(encoded), letter => letter.charCodeAt(0));
        const report = JSON.parse(new TextDecoder().decode(bytes));
        if (report.period !== file.name.split(" ")[0]) throw new Error("报告周期不一致");
        reports.push({ ...report, path: file.path });
      } catch (_) {
        failed.push(file.name);
      }
    }
    reports.sort((left, right) => right.through.localeCompare(left.through) ||
      right.period.length - left.period.length);
    mount(dv.container, reports, {
      theme: input.theme,
      storageKey: "weread-theme:" + dv.app.vault.getName() + ":" + current.folder,
      openNote: path => dv.app.workspace.openLinkText(path, current.path),
    });
    if (failed.length) add(dv.container, "p", "无法读取以下看板数据，可直接打开原报告：" + failed.join("、"));
  }

  if (typeof dv === "undefined") {
    window.mountWeReadReview = mount;
  } else {
    void openObsidian().catch(() => add(dv.container, "p", "加载看板失败。请从下方目录打开报告。"));
  }
})();
