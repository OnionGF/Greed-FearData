(() => {
  const scoreEl = document.getElementById("score");
  const levelEl = document.getElementById("level");
  const sourceEl = document.getElementById("source-line");
  const updatedEl = document.getElementById("updated");
  const factorsEl = document.getElementById("factors");
  const phoneUrlEl = document.getElementById("phone-url");
  const refreshBtn = document.getElementById("refresh");
  const canvas = document.getElementById("spark");
  const gaugeArc = document.getElementById("gauge-arc");
  const needle = document.getElementById("needle");
  const ARC_LEN = 289; // approx π * 92

  let market = "US";
  let loading = false;

  function setGauge(score) {
    const t = Math.max(0, Math.min(100, Number(score) || 0)) / 100;
    gaugeArc.style.strokeDashoffset = String(ARC_LEN * (1 - t));
    // -90deg at 0, +90deg at 100
    const deg = -90 + 180 * t;
    needle.style.transform = `rotate(${deg}deg)`;
  }

  function drawSpark(history) {
    const ctx = canvas.getContext("2d");
    const dpr = window.devicePixelRatio || 1;
    const cssW = canvas.clientWidth || 320;
    const cssH = 120;
    canvas.width = Math.floor(cssW * dpr);
    canvas.height = Math.floor(cssH * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, cssW, cssH);

    if (!history || history.length < 2) {
      ctx.fillStyle = "rgba(138,154,144,0.8)";
      ctx.font = "12px Sora, sans-serif";
      ctx.fillText("暂无历史序列", 16, cssH / 2);
      return;
    }

    const pad = 14;
    const xs = history.map((_, i) => pad + (i * (cssW - pad * 2)) / (history.length - 1));
    const ys = history.map((h) => {
      const v = h.score;
      return cssH - pad - (v / 100) * (cssH - pad * 2);
    });

    const grad = ctx.createLinearGradient(0, 0, cssW, 0);
    grad.addColorStop(0, "#3ec7ff");
    grad.addColorStop(0.5, "#d4e36a");
    grad.addColorStop(1, "#ffb347");

    ctx.beginPath();
    xs.forEach((x, i) => {
      if (i === 0) ctx.moveTo(x, ys[i]);
      else ctx.lineTo(x, ys[i]);
    });
    ctx.strokeStyle = grad;
    ctx.lineWidth = 2.5;
    ctx.lineJoin = "round";
    ctx.stroke();

    // soft fill
    ctx.lineTo(xs[xs.length - 1], cssH);
    ctx.lineTo(xs[0], cssH);
    ctx.closePath();
    const fill = ctx.createLinearGradient(0, 0, 0, cssH);
    fill.addColorStop(0, "rgba(212,227,106,0.18)");
    fill.addColorStop(1, "rgba(212,227,106,0)");
    ctx.fillStyle = fill;
    ctx.fill();
  }

  function renderFactors(factors) {
    factorsEl.innerHTML = factors
      .map(
        (f) => `
      <li class="factor">
        <div class="factor-top">
          <span class="factor-name">${f.name}</span>
          <span class="factor-score">${Number(f.score).toFixed(0)}</span>
        </div>
        <div class="bar"><i style="width:${Math.max(0, Math.min(100, f.score))}%"></i></div>
        <p class="factor-detail">${f.detail || ""}</p>
      </li>`
      )
      .join("");
  }

  async function loadMeta() {
    try {
      const res = await fetch("/api/meta");
      const meta = await res.json();
      phoneUrlEl.textContent = meta.phone_url;
      const qr = document.getElementById("qr");
      if (qr) qr.src = `/api/qr.png?port=${meta.port}&t=${Date.now()}`;
    } catch (_) {
      /* ignore */
    }
  }

  async function load() {
    if (loading) return;
    loading = true;
    refreshBtn.disabled = true;
    sourceEl.textContent = "拉取中…";
    try {
      const res = await fetch(`/api/fear-greed?market=${market}`);
      if (!res.ok) throw new Error("bad response");
      const data = await res.json();
      scoreEl.textContent = data.score;
      levelEl.textContent = data.level;
      levelEl.dataset.level = data.level_key;
      setGauge(data.score);
      const srcMap = {
        futu: `${data.market} · 富途 OpenD`,
        public: `${data.market} · 公开行情（云端可用）`,
        demo: `${data.market} · 演示数据`,
      };
      const src = srcMap[data.source] || `${data.market} · ${data.source}`;
      sourceEl.textContent = src;
      updatedEl.textContent = data.updated_at;
      renderFactors(data.factors || []);
      drawSpark(data.history || []);
    } catch (err) {
      sourceEl.textContent = "加载失败，请检查服务";
      console.error(err);
    } finally {
      loading = false;
      refreshBtn.disabled = false;
    }
  }

  document.querySelectorAll(".mkt").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".mkt").forEach((b) => {
        b.classList.toggle("is-active", b === btn);
        b.setAttribute("aria-selected", b === btn ? "true" : "false");
      });
      market = btn.dataset.market;
      load();
    });
  });

  refreshBtn.addEventListener("click", load);
  window.addEventListener("resize", () => {
    // redraw spark with last data via reload-lite: keep simple
  });

  loadMeta();
  load();
  // 自动刷新：5 分钟
  setInterval(load, 5 * 60 * 1000);
})();
