const API_BASE = "";

// ── Colors ─────────────────────────────────────────────────────
const COLORS = {
    accent:  "#5EC8F8",
    positive:"#4ADE80",
    negative:"#EF5350",
    warning: "#FFA726",
    purple:  "#A78BFA",
    text2:   "#8EA2BE",
    text3:   "#546A84",
    surface: "#0E1E30",
    border:  "rgba(255,255,255,0.07)",
};

// ── Error handling ─────────────────────────────────────────────
const errors = new Set();
function registrarErro(componente) {
    errors.add(componente);
    const bar = document.getElementById("erro");
    bar.textContent = `Erro ao carregar: ${[...errors].join(", ")}`;
    bar.classList.remove("hidden");
}

// ── Formatting ──────────────────────────────────────────────────
function fmtBRL(v) { return v != null ? "R$ " + v.toLocaleString("pt-BR", {minimumFractionDigits: 2, maximumFractionDigits: 2}) : "—"; }
function fmtPct(v) { return v != null ? (v >= 0 ? "+" : "") + v.toFixed(2) + "%" : "—"; }
function fmtPctPlain(v) { return v != null ? v.toFixed(2) + "%" : "—"; }
function fmtInt(v) { return v != null ? v.toLocaleString("pt-BR") : "—"; }

// ── Chart defaults ──────────────────────────────────────────────
Chart.defaults.color = COLORS.text2;
Chart.defaults.borderColor = COLORS.border;
Chart.defaults.font.family = "'Inter', system-ui, sans-serif";
Chart.defaults.font.size = 11;

// ── Tabs ────────────────────────────────────────────────────────
document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
        document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
        document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
        btn.classList.add("active");
        document.getElementById("tab-" + btn.dataset.tab).classList.add("active");
        carregarTab(btn.dataset.tab);
    });
});

let tabsLoaded = { inicio: false, posicoes: false, proventos: false, rentabilidade: false, analise: false };

function carregarTab(tab) {
    if (tabsLoaded[tab]) return;
    tabsLoaded[tab] = true;
    switch (tab) {
        case "inicio": carregarInicio(); break;
        case "posicoes": carregarPosicoes(); break;
        case "proventos": carregarProventos(); break;
        case "rentabilidade": carregarRentabilidade(); break;
        case "analise": carregarAnalise(); break;
    }
}

// ── Início ──────────────────────────────────────────────────────
async function carregarInicio() {
    await carregarStatus();
    await carregarEvolucao();
    await carregarDistribuicao();
    await carregarTop5();
}

async function carregarStatus() {
    try {
        const res = await fetch(`${API_BASE}/api/status`);
        if (!res.ok) throw new Error(res.status);
        const d = await res.json();

        document.getElementById("kpi-patrimonio").textContent = fmtBRL(d.patrimonio);
        document.getElementById("kpi-patrimonio").classList.remove("skeleton");
        document.getElementById("kpi-lucro").textContent = fmtBRL(d.lucro);
        document.getElementById("kpi-lucro").classList.remove("skeleton");
        document.getElementById("kpi-twr").textContent = fmtPct(d.twr_90d);
        document.getElementById("kpi-twr").classList.remove("skeleton");
        document.getElementById("kpi-prov-ano").textContent = fmtBRL(d.proventos_ano);
        document.getElementById("kpi-prov-ano").classList.remove("skeleton");
        document.getElementById("kpi-prov-mes").textContent = fmtBRL(d.proventos_mes);
        document.getElementById("kpi-prov-mes").classList.remove("skeleton");

        const rentEl = document.getElementById("kpi-rent");
        rentEl.textContent = fmtPct(d.rentabilidade_pct);
        rentEl.className = "kpi-delta " + (d.rentabilidade_pct >= 0 ? "positive" : "negative");

        document.getElementById("phase-label").textContent = "📊 Carteira";
    } catch {
        registrarErro("status");
    }
}

let chartEvolucao = null;
async function carregarEvolucao() {
    try {
        const res = await fetch(`${API_BASE}/api/rentabilidade?dias=90`);
        if (!res.ok) throw new Error(res.status);
        const d = await res.json();
        if (!d.historico.length) return;

        const labels = d.historico.map(r => r.data.slice(0, 10));
        const valores = d.historico.map(r => r.valor_total);

        const ctx = document.getElementById("chart-evolucao").getContext("2d");
        if (chartEvolucao) chartEvolucao.destroy();
        chartEvolucao = new Chart(ctx, {
            type: "line",
            data: {
                labels,
                datasets: [{
                    label: "Patrimônio",
                    data: valores,
                    borderColor: COLORS.accent,
                    backgroundColor: "rgba(94,200,248,0.05)",
                    borderWidth: 2,
                    fill: true,
                    tension: 0.3,
                    pointRadius: 0,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { grid: { display: false } },
                    y: { ticks: { callback: v => "R$ " + v.toLocaleString("pt-BR") } }
                },
                interaction: { intersect: false, mode: "index" }
            }
        });
    } catch {
        registrarErro("evolução");
    }
}

let chartDonut = null;
async function carregarDistribuicao() {
    try {
        const res = await fetch(`${API_BASE}/api/distribuicao`);
        if (!res.ok) throw new Error(res.status);
        const d = await res.json();
        if (!d.distribuicao.length) return;

        const ctx = document.getElementById("chart-donut").getContext("2d");
        if (chartDonut) chartDonut.destroy();
        chartDonut = new Chart(ctx, {
            type: "doughnut",
            data: {
                labels: d.distribuicao.map(r => r.tipo),
                datasets: [{
                    data: d.distribuicao.map(r => r.valor),
                    backgroundColor: [COLORS.accent, COLORS.warning, COLORS.negative, COLORS.positive, COLORS.purple],
                    borderColor: COLORS.surface,
                    borderWidth: 3,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: "bottom", labels: { padding: 20, usePointStyle: true } }
                }
            }
        });
    } catch {
        registrarErro("distribuição");
    }
}

async function carregarTop5() {
    try {
        const res = await fetch(`${API_BASE}/api/posicoes`);
        if (!res.ok) throw new Error(res.status);
        const d = await res.json();
        const top5 = d.posicoes.slice(0, 5);

        const tbody = document.querySelector("#table-top5 tbody");
        tbody.innerHTML = top5.map(r => `
            <tr>
                <td><strong>${r.ticker}</strong></td>
                <td>${r.nome || "—"}</td>
                <td>${fmtBRL(r.preco_atual)}</td>
                <td>${fmtBRL(r.saldo_atual)}</td>
                <td class="${r.rentabilidade_pct >= 0 ? 'positive' : 'negative'}">${fmtPctPlain(r.rentabilidade_pct)}</td>
            </tr>
        `).join("");
    } catch {
        registrarErro("top5");
    }
}

// ── Posições ────────────────────────────────────────────────────
async function carregarPosicoes() {
    await carregarFiltros();
    await atualizarPosicoes();
    document.getElementById("filtro-tipo").addEventListener("change", atualizarPosicoes);
    document.getElementById("filtro-setor").addEventListener("change", atualizarPosicoes);
}

async function carregarFiltros() {
    try {
        const res = await fetch(`${API_BASE}/api/filtros`);
        if (!res.ok) throw new Error(res.status);
        const d = await res.json();
        const tipoEl = document.getElementById("filtro-tipo");
        const setorEl = document.getElementById("filtro-setor");
        d.tipos.forEach(t => { const opt = document.createElement("option"); opt.value = t; opt.textContent = t; tipoEl.appendChild(opt); });
        d.setores.forEach(s => { const opt = document.createElement("option"); opt.value = s; opt.textContent = s; setorEl.appendChild(opt); });
    } catch { /* non-critical */ }
}

async function atualizarPosicoes() {
    const tipo = document.getElementById("filtro-tipo").value;
    const setor = document.getElementById("filtro-setor").value;
    const params = new URLSearchParams();
    if (tipo !== "Todos") params.set("tipo", tipo);
    if (setor !== "Todos") params.set("setor", setor);

    try {
        const res = await fetch(`${API_BASE}/api/posicoes?${params}`);
        if (!res.ok) throw new Error(res.status);
        const d = await res.json();

        const tbody = document.querySelector("#table-posicoes tbody");
        tbody.innerHTML = d.posicoes.map(r => `
            <tr>
                <td><strong>${r.ticker}</strong></td>
                <td>${r.nome || "—"}</td>
                <td>${r.tipo || "—"}</td>
                <td>${r.setor || "—"}</td>
                <td>${fmtInt(r.quantidade_total)}</td>
                <td>${fmtBRL(r.preco_medio)}</td>
                <td>${fmtBRL(r.preco_atual)}</td>
                <td class="${r.var_dia_pct >= 0 ? 'positive' : 'negative'}">${fmtPctPlain(r.var_dia_pct)}</td>
                <td class="${r.lucro_prejuizo >= 0 ? 'positive' : 'negative'}">${fmtBRL(r.lucro_prejuizo)}</td>
                <td class="${r.rentabilidade_pct >= 0 ? 'positive' : 'negative'}">${fmtPctPlain(r.rentabilidade_pct)}</td>
                <td>${fmtBRL(r.saldo_atual)}</td>
                <td>${fmtPctPlain(r.pct_carteira)}</td>
            </tr>
        `).join("");

        document.getElementById("caption-posicoes").textContent =
            `${d.posicoes.length} ativos | Saldo total: ${fmtBRL(d.total_saldo)}`;
    } catch {
        registrarErro("posições");
    }
}

// ── Proventos ───────────────────────────────────────────────────
let chartProventos = null;
async function carregarProventos() {
    await atualizarProventos();
    document.getElementById("filtro-meses").addEventListener("change", atualizarProventos);
}

async function atualizarProventos() {
    const meses = document.getElementById("filtro-meses").value;
    try {
        const res = await fetch(`${API_BASE}/api/proventos?meses=${meses}`);
        if (!res.ok) throw new Error(res.status);
        const d = await res.json();

        // KPIs
        document.getElementById("prov-12m").textContent = fmtBRL(d.total_ano);
        document.getElementById("prov-12m").classList.remove("skeleton");
        document.getElementById("prov-ano").textContent = fmtBRL(d.total_ano);
        document.getElementById("prov-ano").classList.remove("skeleton");
        document.getElementById("prov-mes").textContent = fmtBRL(d.total_mes);
        document.getElementById("prov-mes").classList.remove("skeleton");

        // Chart
        const ctx = document.getElementById("chart-proventos").getContext("2d");
        if (chartProventos) chartProventos.destroy();

        if (meses == 1) {
            document.getElementById("prov-chart-title").textContent = "📊 Proventos por Ativo (último mês)";
            const byTicker = {};
            d.proventos.forEach(p => { byTicker[p.ticker] = (byTicker[p.ticker] || 0) + p.valor; });
            const sorted = Object.entries(byTicker).sort((a, b) => a[1] - b[1]);
            chartProventos = new Chart(ctx, {
                type: "bar",
                data: {
                    labels: sorted.map(([k]) => k),
                    datasets: [{ data: sorted.map(([, v]) => v), backgroundColor: COLORS.positive, borderRadius: 4 }]
                },
                options: {
                    indexAxis: "y",
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: { x: { ticks: { callback: v => "R$ " + v.toLocaleString("pt-BR") } } }
                }
            });
        } else {
            document.getElementById("prov-chart-title").textContent = `📊 Proventos Mensais (últimos ${meses} meses)`;
            const byMonth = {};
            d.proventos.forEach(p => {
                const ym = p.data_pgto.slice(0, 7);
                byMonth[ym] = (byMonth[ym] || 0) + p.valor;
            });
            const sorted = Object.entries(byMonth).sort((a, b) => a[0].localeCompare(b[0]));
            chartProventos = new Chart(ctx, {
                type: "bar",
                data: {
                    labels: sorted.map(([k]) => k),
                    datasets: [{ data: sorted.map(([, v]) => v), backgroundColor: COLORS.positive, borderRadius: 4 }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: { y: { ticks: { callback: v => "R$ " + v.toLocaleString("pt-BR") } } }
                }
            });
        }

        // Table
        const tbody = document.querySelector("#table-proventos tbody");
        tbody.innerHTML = d.proventos.map(p => `
            <tr>
                <td><strong>${p.ticker}</strong></td>
                <td>${new Date(p.data_pgto).toLocaleDateString("pt-BR")}</td>
                <td>${fmtBRL(p.valor)}</td>
                <td>${p.tipo || "—"}</td>
            </tr>
        `).join("");
    } catch {
        registrarErro("proventos");
    }
}

// ── Rentabilidade ───────────────────────────────────────────────
let chartRentPat = null, chartRentDia = null;
async function carregarRentabilidade() {
    await atualizarRentabilidade();
    document.getElementById("filtro-dias").addEventListener("change", atualizarRentabilidade);
}

async function atualizarRentabilidade() {
    const dias = document.getElementById("filtro-dias").value;
    try {
        const res = await fetch(`${API_BASE}/api/rentabilidade?dias=${dias}`);
        if (!res.ok) throw new Error(res.status);
        const d = await res.json();
        const h = d.historico;
        if (!h.length) return;

        // KPIs
        document.getElementById("rent-twr").textContent = fmtPct(d.twr);
        document.getElementById("rent-twr").classList.remove("skeleton");
        const ultimo = h[h.length - 1];
        document.getElementById("rent-dia").textContent = fmtPct(ultimo.rentabilidade);
        document.getElementById("rent-dia").classList.remove("skeleton");
        document.getElementById("rent-lucro").textContent = fmtBRL(ultimo.lucro_prejuizo);
        document.getElementById("rent-lucro").classList.remove("skeleton");

        const labels = h.map(r => r.data.slice(0, 10));

        // Chart 1: Evolução do Patrimônio
        const ctx1 = document.getElementById("chart-rent-patrimonio").getContext("2d");
        if (chartRentPat) chartRentPat.destroy();
        chartRentPat = new Chart(ctx1, {
            type: "line",
            data: {
                labels,
                datasets: [{
                    data: h.map(r => r.valor_total),
                    borderColor: COLORS.accent,
                    backgroundColor: "rgba(94,200,248,0.05)",
                    borderWidth: 2, fill: true, tension: 0.3, pointRadius: 0,
                }]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: { x: { grid: { display: false } }, y: { ticks: { callback: v => "R$ " + v.toLocaleString("pt-BR") } } },
                interaction: { intersect: false, mode: "index" }
            }
        });

        // Chart 2: Rentabilidade Diária
        const ctx2 = document.getElementById("chart-rent-diaria").getContext("2d");
        if (chartRentDia) chartRentDia.destroy();
        chartRentDia = new Chart(ctx2, {
            type: "bar",
            data: {
                labels,
                datasets: [{
                    data: h.map(r => r.rentabilidade),
                    backgroundColor: h.map(r => r.rentabilidade >= 0 ? COLORS.positive : COLORS.negative),
                    borderRadius: 2,
                }]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: { y: { ticks: { callback: v => v + "%" } } }
            }
        });
    } catch {
        registrarErro("rentabilidade");
    }
}

// ── Análise ─────────────────────────────────────────────────────
let chartRoePvp = null, chartDyRank = null;
async function carregarAnalise() {
    try {
        const res = await fetch(`${API_BASE}/api/indicadores`);
        if (!res.ok) throw new Error(res.status);
        const d = await res.json();
        const ind = d.indicadores;
        if (!ind.length) return;

        // Data coleta
        if (d.data_coleta) {
            document.getElementById("caption-analise-coleta").textContent =
                `Dados mais recentes: ${new Date(d.data_coleta).toLocaleDateString("pt-BR")}`;
        }

        // Tabela indicadores
        const tbodyInd = document.querySelector("#table-indicadores tbody");
        tbodyInd.innerHTML = ind.map(r => `
            <tr>
                <td><strong>${r.ticker}</strong></td>
                <td>${r.p_l != null ? r.p_l.toFixed(2) : "—"}</td>
                <td>${r.p_vp != null ? r.p_vp.toFixed(2) : "—"}</td>
                <td>${r.roe != null ? r.roe.toFixed(1) + "%" : "—"}</td>
                <td>${r.roic != null ? r.roic.toFixed(1) + "%" : "—"}</td>
                <td>${r.marg_liquida != null ? r.marg_liquida.toFixed(1) + "%" : "—"}</td>
                <td>${r.marg_bruta != null ? r.marg_bruta.toFixed(1) + "%" : "—"}</td>
                <td>${r.dividend_yield != null ? r.dividend_yield.toFixed(2) + "%" : "—"}</td>
                <td>${r.cres_rec_5a != null ? r.cres_rec_5a.toFixed(1) + "%" : "—"}</td>
                <td>${r.div_liq_patrim != null ? r.div_liq_patrim.toFixed(2) : "—"}</td>
                <td>${r.osc_12m != null ? r.osc_12m.toFixed(1) + "%" : "—"}</td>
            </tr>
        `).join("");

        // Chart: ROE vs P/VP
        const scatterData = ind.filter(r => r.roe != null && r.p_vp != null);
        if (scatterData.length) {
            const ctx1 = document.getElementById("chart-roe-pvp").getContext("2d");
            if (chartRoePvp) chartRoePvp.destroy();
            chartRoePvp = new Chart(ctx1, {
                type: "scatter",
                data: {
                    datasets: [{
                        label: "Ativos",
                        data: scatterData.map(r => ({ x: r.p_vp, y: r.roe })),
                        backgroundColor: COLORS.accent,
                        pointRadius: 6,
                    }]
                },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    plugins: {
                        tooltip: {
                            callbacks: {
                                label: ctx => {
                                    const r = scatterData[ctx.dataIndex];
                                    return `${r.ticker}: P/VP=${r.p_vp?.toFixed(2)}, ROE=${r.roe?.toFixed(1)}%`;
                                }
                            }
                        }
                    },
                    scales: {
                        x: { title: { display: true, text: "P/VP" } },
                        y: { title: { display: true, text: "ROE (%)" }, ticks: { callback: v => v + "%" } }
                    }
                }
            });
        }

        // Chart: Ranking DY
        const dyRank = ind.filter(r => r.dividend_yield != null).sort((a, b) => b.dividend_yield - a.dividend_yield).slice(0, 10);
        if (dyRank.length) {
            const ctx2 = document.getElementById("chart-dy-rank").getContext("2d");
            if (chartDyRank) chartDyRank.destroy();
            chartDyRank = new Chart(ctx2, {
                type: "bar",
                data: {
                    labels: dyRank.map(r => r.ticker),
                    datasets: [{
                        data: dyRank.map(r => r.dividend_yield),
                        backgroundColor: COLORS.positive,
                        borderRadius: 4,
                    }]
                },
                options: {
                    indexAxis: "y",
                    responsive: true, maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: { x: { ticks: { callback: v => v + "%" } } }
                }
            });
        }

        // Tabela Bazin/Graham
        const tbodyBg = document.querySelector("#table-bazin-graham tbody");
        tbodyBg.innerHTML = ind.map(r => `
            <tr>
                <td><strong>${r.ticker}</strong></td>
                <td>${r.bazin > 0 ? "R$ " + r.bazin.toFixed(2) : "—"}</td>
                <td>${r.graham > 0 ? "R$ " + r.graham.toFixed(2) : "—"}</td>
            </tr>
        `).join("");

    } catch {
        registrarErro("análise");
    }
}

// ── Init ────────────────────────────────────────────────────────
carregarInicio();
tabsLoaded.inicio = true;