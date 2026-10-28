(() => {
  const tabsEl = document.getElementById("tabs");
  const tbody = document.getElementById("tbody");
  const updatedEl = document.getElementById("updated");
  const fearEl = document.getElementById("stat-fear");
  const neuEl = document.getElementById("stat-neutral");
  const greedEl = document.getElementById("stat-greed");

  let currentTab = "1";
  let rows = [];
  let sort = { prop: "code", order: "asc" };

  function rowClass(score) {
    if (score <= -60) return "item-value-low";
    if (score >= 60) return "item-value-high";
    return "item-value-mid";
  }

  function renderTabs(tabs) {
    tabsEl.innerHTML = tabs
      .map(
        (t) =>
          `<button type="button" class="tab${t.value === currentTab ? " is-active" : ""}" data-value="${t.value}">${t.label}</button>`
      )
      .join("");
    tabsEl.querySelectorAll(".tab").forEach((btn) => {
      btn.addEventListener("click", () => {
        currentTab = btn.dataset.value;
        tabsEl.querySelectorAll(".tab").forEach((b) => b.classList.toggle("is-active", b === btn));
        load();
      });
    });
  }

  function sortedRows() {
    const copy = [...rows];
    const { prop, order } = sort;
    copy.sort((a, b) => {
      let av = a[prop];
      let bv = b[prop];
      if (prop === "score" || prop === "price") {
        av = parseFloat(av);
        bv = parseFloat(bv);
        if (Number.isNaN(av)) av = -Infinity;
        if (Number.isNaN(bv)) bv = -Infinity;
      } else {
        av = String(av || "");
        bv = String(bv || "");
      }
      if (av < bv) return order === "asc" ? -1 : 1;
      if (av > bv) return order === "asc" ? 1 : -1;
      return 0;
    });
    return copy;
  }

  function renderTable() {
    const list = sortedRows();
    if (!list.length) {
      tbody.innerHTML = `<tr><td colspan="5" class="empty">无数据</td></tr>`;
      return;
    }
    tbody.innerHTML = list
      .map((r) => {
        const codeShort = String(r.code || "").replace(/^US\./, "").replace(/^HK\./, "");
        return `<tr class="${rowClass(r.score)}">
          <td>${codeShort}</td>
          <td>${r.name}</td>
          <td>${r.score}</td>
          <td>${r.price}</td>
          <td>${r.scale}</td>
        </tr>`;
      })
      .join("");
  }

  async function load() {
    tbody.innerHTML = `<tr><td colspan="5" class="empty">加载中...</td></tr>`;
    try {
      const res = await fetch(`/api/etf?etf_type=${encodeURIComponent(currentTab)}`);
      const data = await res.json();
      if (data.tabs) renderTabs(data.tabs);
      rows = data.items || [];
      updatedEl.textContent = data.updated_at || "—";
      const s = data.statics || {};
      fearEl.textContent = `恐慌${s.fear || 0}个`;
      neuEl.textContent = `中性${s.neutral || 0}个`;
      greedEl.textContent = `贪婪${s.greed || 0}个`;
      const foot = document.getElementById("footnote");
      if (foot) {
        const src = data.source || "";
        foot.textContent = src.includes("local") || src.includes("futu")
          ? "≥60 贪婪，≤-60 恐慌。分数为本地反推算法（区间位置+MA60+RSI），不依赖会员；约 30 秒刷新。"
          : "≥60 情绪贪婪，≤-60 情绪恐慌。仅供参考，不构成投资建议。";
      }
      if (data.source) {
        updatedEl.textContent = `${data.updated_at || "—"} · ${data.source}`;
      }
      renderTable();
    } catch (e) {
      console.error(e);
      tbody.innerHTML = `<tr><td colspan="5" class="empty">加载失败</td></tr>`;
    }
  }

  document.querySelectorAll(".etf-table th[data-sort]").forEach((th) => {
    th.addEventListener("click", () => {
      const prop = th.dataset.sort;
      if (sort.prop === prop) sort.order = sort.order === "asc" ? "desc" : "asc";
      else {
        sort.prop = prop;
        sort.order = prop === "score" ? "desc" : "asc";
      }
      renderTable();
    });
  });

  load();
  // 实时刷新：30 秒
  setInterval(load, 30 * 1000);
})();
