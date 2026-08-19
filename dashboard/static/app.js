const API_BASE = "";

// ── Colors ─────────────────────────────────────────────────────
const COLORS = {
    accent:  "#126B5B",
    positive:"#147A4B",
    negative:"#B44335",
    warning: "#A66A16",
    purple:  "#6C5A8C",
    text2:   "#52635E",
    text3:   "#7B8984",
    surface: "#FBFAF6",
    border:  "rgba(25,44,40,0.12)",
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
function fmtQty(v) { return v != null ? Number(v).toLocaleString("pt-BR", {maximumFractionDigits: 6}) : "—"; }
function fmtDate(v) {
    if (!v) return "—";
    const dateOnly = String(v).slice(0, 10).split("-");
    if (dateOnly.length === 3) return `${dateOnly[2]}/${dateOnly[1]}/${dateOnly[0]}`;
    return "—";
}
function safe(v) {
    return String(v ?? "—").replace(/[&<>'"]/g, ch => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"
    })[ch]);
}

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
        document.querySelectorAll(".tab-btn").forEach(b => {
            b.setAttribute("aria-selected", String(b === btn));
            b.tabIndex = b === btn ? 0 : -1;
        });
        btn.classList.add("active");
        document.getElementById("tab-" + btn.dataset.tab).classList.add("active");
        carregarTab(btn.dataset.tab);
    });
});

let tabsLoaded = { inicio: false, posicoes: false, notas: false, proventos: false, rentabilidade: false, analise: false, teses: false };

function carregarTab(tab) {
    if (tabsLoaded[tab]) return;
    tabsLoaded[tab] = true;
    switch (tab) {
        case "inicio": carregarInicio(); break;
        case "posicoes": carregarPosicoes(); break;
        case "notas": carregarNotas(); break;
        case "proventos": carregarProventos(); break;
        case "rentabilidade": carregarRentabilidade(); break;
        case "analise": carregarAnalise(); break;
        case "teses": carregarTeses(); break;
    }
}

// ── Início ──────────────────────────────────────────────────────
async function carregarInicio() {
    await carregarQualidade();
    await carregarStatus();
    await carregarEvolucao();
    await carregarDistribuicao();
    await carregarTop5();
}

const NOTE_STATUS = {
    Imported: { label: "Importada", className: "note-status-imported" },
    Manual: { label: "Manual", className: "note-status-manual" },
    Processing: { label: "Processando", className: "note-status-processing" },
    Error: { label: "Erro", className: "note-status-error" },
};

function renderNote(item) {
    const status = NOTE_STATUS[item.status] || NOTE_STATUS.Error;
    const title = item.note_number ? `Nota ${safe(item.note_number)}` : "Tentativa de importacao";
    const operations = item.operations || [];
    const operationRows = operations.map(op => `
        <tr>
            <td class="asset-cell"><strong>${safe(op.ticker)}</strong><small>${safe(op.description)}</small></td>
            <td>${safe(op.side)}</td><td>${safe(op.market)}</td>
            <td class="numeric">${fmtQty(op.quantity)}</td>
            <td class="numeric">${fmtBRL(op.unit_price)}</td>
            <td class="numeric">${fmtBRL(op.total_value)}</td>
        </tr>`).join("");
    const details = operations.length ? `
        <div class="note-details">
            <div class="note-financials">
                <span>Operacoes<strong>${fmtBRL(item.net_operations)}</strong></span>
                <span>Custos<strong>${fmtBRL(item.total_costs)}</strong></span>
                <span>Liquidacao<strong>${fmtBRL(item.settlement_value)}</strong></span>
            </div>
            <div class="table-wrap"><table><thead><tr><th>Ativo</th><th>Operacao</th><th>Mercado</th><th>Quantidade</th><th>Preco</th><th>Valor</th></tr></thead><tbody>${operationRows}</tbody></table></div>
        </div>` : `<p class="note-message">${safe(item.status_message || "Nenhuma operacao consolidada registrada.")}</p>`;
    return `
        <details class="note-card">
            <summary class="note-summary">
                <span><strong>${title}</strong><small>${safe(item.broker || "Corretora nao informada")}</small></span>
                <span class="status-chip ${status.className}"><i></i>${status.label}</span>
                <span class="note-date">${item.trade_date ? "Pregao " + fmtDate(item.trade_date) : "Tentativa " + fmtDate(item.attempted_at)}</span>
                <span class="note-total">${fmtBRL(item.settlement_value)}</span>
            </summary>
            ${details}
        </details>`;
}

async function carregarNotas() {
    try {
        const res = await fetch(`${API_BASE}/api/notas`);
        if (!res.ok) throw new Error(res.status);
        const data = await res.json();
        document.getElementById("notes-total").textContent = fmtInt(data.summary.total);
        document.getElementById("notes-imported").textContent = fmtInt(data.summary.imported);
        document.getElementById("notes-manual").textContent = fmtInt(data.summary.manual);
        document.getElementById("notes-pending").textContent = fmtInt(data.summary.processing + data.summary.error);
        const groups = data.groups || [];
        document.getElementById("notes-empty").classList.toggle("hidden", groups.length > 0);
        document.getElementById("notes-groups").innerHTML = groups.map(group => `
            <section class="notes-group">
                <div class="section-heading"><div><p class="eyebrow">DATA DE REFERENCIA</p><h2>${fmtDate(group.date)}</h2></div><span>${fmtInt(group.items.length)} registros</span></div>
                <div>${group.items.map(renderNote).join("")}</div>
            </section>`).join("");
    } catch {
        registrarErro("notas de negociacao");
    }
}

async function carregarTeses() {
    try {
        const res = await fetch(`${API_BASE}/api/teses/inventario`);
        if (!res.ok) throw new Error(res.status);
        const d = await res.json();
        const coverage = document.getElementById("thesis-coverage");
        coverage.dataset.loaded = "true";
        document.getElementById("thesis-open").textContent = fmtInt(d.coverage.open_positions);
        document.getElementById("thesis-inventoried").textContent = fmtInt(d.coverage.inventoried_positions);
        document.getElementById("thesis-complete").textContent = fmtInt(d.coverage.complete_theses);
        document.getElementById("thesis-gaps").textContent = fmtInt(d.coverage.explicit_gaps);
        document.getElementById("thesis-count").textContent = `${fmtInt(d.positions.length)} ativos`;
        document.querySelector("#table-theses tbody").innerHTML = d.positions.map(item => `
            <tr class="${item.has_complete_thesis ? "" : "row-pending"}">
                <td class="asset-cell"><strong>${safe(item.ticker)}</strong><small>${safe(item.name)}</small></td>
                <td><span class="asset-type">${safe(item.asset_type || "—")}</span><small>${safe(item.sector || "Nao classificado")}</small></td>
                <td>${safe(item.thesis_origin)}</td>
                <td><span class="status-chip status-sem_cotacao"><i></i>${item.has_complete_thesis ? "Publicada" : "Rascunho"}</span></td>
                <td>${safe(item.thesis_summary)}</td>
                <td>${safe((item.risks || []).join("; "))}</td>
                <td><button class="button-secondary thesis-review" data-ticker="${safe(item.ticker)}">${item.has_complete_thesis ? "Ver" : "Revisar"}</button></td>
            </tr>`).join("");
        document.querySelectorAll(".thesis-review").forEach(button => {
            button.addEventListener("click", () => abrirRevisaoTese(
                d.positions.find(item => item.ticker === button.dataset.ticker)
            ));
        });
    } catch {
        registrarErro("teses da carteira");
    }
}

function linhas(text) {
    return String(text || "").split("\n").map(item => item.trim()).filter(Boolean);
}

let thesisProposalController = null;

async function abrirRevisaoTese(item) {
    if (!item) return;
    if (thesisProposalController) thesisProposalController.abort();
    thesisProposalController = new AbortController();
    const requestController = thesisProposalController;
    resetarFormularioTese();
    document.getElementById("thesis-ticker").value = item.ticker;
    document.getElementById("thesis-dialog-title").textContent = `Revisar ${item.ticker}`;
    document.getElementById("thesis-dialog").showModal();
    const meta = document.getElementById("thesis-proposal-meta");
    meta.textContent = "Gerando proposta a partir dos dados do sistema...";
    try {
        const response = await fetch(`/api/teses/${encodeURIComponent(item.ticker)}/proposta`, {
            signal: requestController.signal,
        });
        if (!response.ok) throw new Error(response.status);
        const proposal = await response.json();
        if (requestController !== thesisProposalController
            || document.getElementById("thesis-ticker").value !== item.ticker
            || !document.getElementById("thesis-dialog").open) return;
        document.getElementById("thesis-summary").value = proposal.summary;
        document.getElementById("thesis-horizon").value = proposal.horizon;
        document.getElementById("thesis-risks").value = (proposal.risks || []).join("\n");
        document.getElementById("thesis-triggers").value = (proposal.review_triggers || []).join("\n");
        meta.textContent = `Confianca ${proposal.confidence} · dados de ${proposal.evidence_date || "data indisponivel"} · proposta automatica, nao recomendacao.`;
    } catch (exception) {
        if (exception.name === "AbortError") return;
        if (document.getElementById("thesis-ticker").value !== item.ticker) return;
        document.getElementById("thesis-summary").value = item.thesis_summary || "";
        document.getElementById("thesis-risks").value = (item.risks || []).join("\n");
        document.getElementById("thesis-triggers").value = (item.review_triggers || []).join("\n");
        meta.textContent = "Proposta quantitativa indisponivel; exibindo o rascunho basico.";
    }
}

function resetarFormularioTese() {
    document.getElementById("thesis-form").reset();
    document.getElementById("thesis-origin").value = "TESE_ATUAL_RECONSTRUIDA";
    document.getElementById("thesis-decision").value = "";
    document.getElementById("thesis-decision").required = false;
    document.getElementById("thesis-decision-wrapper").classList.add("hidden");
    document.getElementById("thesis-form-error").textContent = "";
    document.getElementById("thesis-proposal-meta").textContent = "";
}

document.getElementById("thesis-close").addEventListener("click", () => {
    if (thesisProposalController) thesisProposalController.abort();
    document.getElementById("thesis-dialog").close();
});

document.getElementById("thesis-origin").addEventListener("change", event => {
    const contemporary = event.target.value === "TESE_CONTEMPORANEA";
    document.getElementById("thesis-decision-wrapper").classList.toggle("hidden", !contemporary);
    document.getElementById("thesis-decision").required = contemporary;
});

document.getElementById("thesis-form").addEventListener("submit", async event => {
    event.preventDefault();
    const ticker = document.getElementById("thesis-ticker").value;
    const origin = document.getElementById("thesis-origin").value;
    const localDecision = document.getElementById("thesis-decision").value;
    const payload = {
        origin,
        summary: document.getElementById("thesis-summary").value,
        horizon: document.getElementById("thesis-horizon").value,
        risks: linhas(document.getElementById("thesis-risks").value),
        review_triggers: linhas(document.getElementById("thesis-triggers").value),
        decision_at: origin === "TESE_CONTEMPORANEA" && localDecision
            ? new Date(localDecision).toISOString() : null,
    };
    const error = document.getElementById("thesis-form-error");
    error.textContent = "";
    try {
        const res = await fetch(`/api/teses/${encodeURIComponent(ticker)}/publicar`, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(payload),
        });
        if (!res.ok) {
            const body = await res.json();
            throw new Error(body.detail || `Erro ${res.status}`);
        }
        document.getElementById("thesis-dialog").close();
        tabsLoaded.teses = false;
        await carregarTeses();
        tabsLoaded.teses = true;
    } catch (exception) {
        error.textContent = exception.message;
    }
});

async function carregarQualidade() {
    try {
        const res = await fetch(`${API_BASE}/api/qualidade`);
        if (!res.ok) throw new Error(res.status);
        const d = await res.json();
        document.getElementById("quality-quote").textContent = d.ultima_cotacao || "Sem dados";
        document.getElementById("quality-snapshot").textContent = d.ultimo_snapshot || "Sem dados";
        document.getElementById("quality-coverage").textContent =
            `${d.posicoes - d.posicoes_sem_cotacao}/${d.posicoes} posições com cotação`;
        const badge = document.getElementById("quality-badge");
        const healthy = d.posicoes > 0 && d.posicoes_sem_cotacao === 0 && d.posicoes_sem_cadastro === 0;
        badge.textContent = healthy ? "Cobertura completa" : "Atenção necessária";
        badge.className = `quality-badge ${healthy ? "quality-ok" : "quality-warning"}`;

        const list = document.getElementById("quality-limitations");
        list.replaceChildren(...d.limitacoes.map(item => {
            const li = document.createElement("li");
            li.textContent = item;
            return li;
        }));
    } catch {
        registrarErro("qualidade dos dados");
    }
}

async function carregarSaudeCarteira() {
    try {
        const res = await fetch(`${API_BASE}/api/saude-carteira`);
        if (!res.ok) throw new Error(res.status);
        const d = await res.json();
        const score = document.getElementById("health-score");
        score.textContent = d.score ?? "—";
        score.dataset.level = d.score >= 80 ? "good" : d.score >= 60 ? "medium" : "high";
        document.getElementById("health-classification").textContent = d.classification;
        document.getElementById("health-summary").textContent = d.summary;
        document.getElementById("health-confidence").textContent = `Confiabilidade: ${d.confidence}`;
        document.getElementById("health-pillars").innerHTML = d.pillars.map(p => `
            <div class="health-pillar"><div><span>${safe(p.label)}</span><strong>${p.score}/100</strong></div>
            <div class="health-track"><i style="width:${p.score}%"></i></div></div>`).join("");
        const m = d.metrics;
        document.getElementById("health-metrics").innerHTML = [
            ["Ativos efetivos", m.effective_assets ?? "—"],
            ["Maior posição", m.largest_position_pct != null ? fmtPctPlain(m.largest_position_pct) : "—"],
            ["Maior setor", m.largest_sector_pct != null ? `${safe(m.largest_sector)} · ${fmtPctPlain(m.largest_sector_pct)}` : "—"],
            ["Volatilidade estimada", m.annualized_volatility_pct != null ? fmtPctPlain(m.annualized_volatility_pct) : "—"],
            ["Drawdown estimado", m.max_drawdown_pct != null ? fmtPctPlain(m.max_drawdown_pct) : "—"],
        ].map(([label, value]) => `<div><span>${label}</span><strong>${value}</strong></div>`).join("");
        document.getElementById("health-alerts").innerHTML = d.alerts.map(a =>
            `<li class="health-alert health-alert-${safe(a.level)}">${safe(a.text)}</li>`).join("");
        document.getElementById("health-methodology").textContent = d.methodology || "";
    } catch {
        registrarErro("saúde da carteira");
    }
}

async function carregarStatus() {
    try {
        const res = await fetch(`${API_BASE}/api/status`);
        if (!res.ok) throw new Error(res.status);
        const d = await res.json();

        document.getElementById("kpi-patrimonio").textContent = d.patrimonio == null ? "Cobertura incompleta" : fmtBRL(d.patrimonio);
        document.getElementById("kpi-patrimonio").classList.remove("skeleton");
        document.getElementById("kpi-lucro").textContent = d.lucro == null ? "Indisponivel" : fmtBRL(d.lucro);
        document.getElementById("kpi-lucro").classList.remove("skeleton");
        document.getElementById("kpi-twr").textContent = d.twr_90d == null ? "Indisponível" : fmtPct(d.twr_90d);
        document.getElementById("kpi-twr").classList.remove("skeleton");
        document.getElementById("kpi-prov-ano").textContent = d.proventos_ano == null ? "Indisponivel" : fmtBRL(d.proventos_ano);
        document.getElementById("kpi-prov-ano").classList.remove("skeleton");
        document.getElementById("kpi-prov-mes").textContent = d.proventos_mes == null ? "Indisponivel" : fmtBRL(d.proventos_mes);
        document.getElementById("kpi-prov-mes").classList.remove("skeleton");

        const rentEl = document.getElementById("kpi-rent");
        rentEl.textContent = d.rentabilidade_pct == null ? "Cobertura incompleta" : fmtPct(d.rentabilidade_pct);
        rentEl.className = "kpi-delta " + (d.rentabilidade_pct == null ? "" : d.rentabilidade_pct >= 0 ? "positive" : "negative");

        document.getElementById("phase-label").textContent = "📊 Carteira";
    } catch {
        registrarErro("status");
    }
}

let chartEvolucao = null;
function agruparFechamentosMensais(historico) {
    const meses = new Map();
    historico.forEach(registro => {
        const chave = registro.data.slice(0, 7);
        meses.set(chave, registro);
    });
    return Array.from(meses.entries()).map(([mes, registro]) => ({
        label: new Intl.DateTimeFormat("pt-BR", {
            month: "short",
            year: "2-digit",
            timeZone: "UTC",
        }).format(new Date(`${mes}-01T00:00:00Z`)),
        valor: registro.valor_total,
    }));
}

async function carregarEvolucao() {
    try {
        const res = await fetch(`${API_BASE}/api/rentabilidade?dias=365`);
        if (!res.ok) throw new Error(res.status);
        const d = await res.json();
        if (!d.historico.length) return;

        const mensal = agruparFechamentosMensais(d.historico);
        const labels = mensal.map(r => r.label);
        const valores = mensal.map(r => r.valor);

        const ctx = document.getElementById("chart-evolucao").getContext("2d");
        if (chartEvolucao) chartEvolucao.destroy();
        chartEvolucao = new Chart(ctx, {
            type: "bar",
            data: {
                labels,
                datasets: [{
                    label: "Patrimônio",
                    data: valores,
                    backgroundColor: "rgba(94,200,248,0.72)",
                    borderColor: COLORS.accent,
                    borderWidth: 1,
                    borderRadius: 5,
                    maxBarThickness: 48,
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
                <td><strong>${safe(r.ticker)}</strong></td>
                <td>${safe(r.nome)}</td>
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
let positionData = null;

async function carregarPosicoes() {
    await carregarFiltros();
    await atualizarPosicoes();
    ["filtro-tipo", "filtro-setor", "filtro-status"].forEach(id =>
        document.getElementById(id).addEventListener("change", renderPosicoes)
    );
    document.getElementById("filtro-busca").addEventListener("input", renderPosicoes);
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
    try {
        const res = await fetch(`${API_BASE}/api/posicoes`);
        if (!res.ok) throw new Error(res.status);
        positionData = await res.json();
        document.getElementById("phase-label").textContent = "Posicao atual";
        document.getElementById("pos-count").textContent = positionData.quantidade_posicoes;
        document.getElementById("pos-coverage").textContent = `${positionData.posicoes_com_cotacao} com cotacao`;
        document.getElementById("pos-cost").textContent = fmtBRL(positionData.custo_total);
        document.getElementById("pos-market").textContent = fmtBRL(positionData.total_carteira);
        document.getElementById("pos-pending").textContent = positionData.posicoes_sem_cotacao;
        const updates = positionData.posicoes.map(r => r.atualizado_em).filter(Boolean).sort();
        document.getElementById("position-updated").textContent = updates.length ? fmtDate(updates.at(-1)) : "Sem data";
        renderPosicoes();
    } catch {
        registrarErro("posicoes");
    }
}

function renderPosicoes() {
    if (!positionData) return;
    const tipo = document.getElementById("filtro-tipo").value;
    const setor = document.getElementById("filtro-setor").value;
    const status = document.getElementById("filtro-status").value;
    const busca = document.getElementById("filtro-busca").value.trim().toLocaleUpperCase("pt-BR");

    const rows = positionData.posicoes.filter(r => {
        const matchesText = !busca || `${r.ticker} ${r.nome || ""}`.toLocaleUpperCase("pt-BR").includes(busca);
        const matchesType = tipo === "Todos" || r.tipo === tipo;
        const matchesSector = setor === "Todos" || r.setor === setor;
        const matchesStatus = status === "todos" || (status === "ok" ? r.status === "ok" : r.status !== "ok");
        return matchesText && matchesType && matchesSector && matchesStatus;
    });

    document.querySelector("#table-posicoes tbody").innerHTML = rows.map(r => {
        const statusLabel = r.status === "ok" ? "Conferido" : r.status === "sem_cadastro" ? "Sem cadastro" : "Sem cotacao";
        const resultClass = r.lucro_prejuizo == null ? "" : r.lucro_prejuizo >= 0 ? "positive" : "negative";
        return `
            <tr class="${r.status === "ok" ? "" : "row-pending"}">
                <td data-label="Status"><span class="status-chip status-${safe(r.status)}"><i></i>${statusLabel}</span></td>
                <td data-label="Ativo"><div class="asset-cell"><strong>${safe(r.ticker)}</strong><small>${safe(r.nome)}</small></div></td>
                <td data-label="Classe"><span class="asset-type">${safe(r.tipo)}</span></td>
                <td data-label="Quantidade" class="numeric">${fmtQty(r.quantidade_total)}</td>
                <td data-label="Preco medio" class="numeric">${fmtBRL(r.preco_medio)}</td>
                <td data-label="Custo" class="numeric">${fmtBRL(r.custo_total)}</td>
                <td data-label="Preco atual" class="numeric"><strong>${fmtBRL(r.preco_atual)}</strong><small>${fmtDate(r.data_cotacao)}</small></td>
                <td data-label="Valor coberto" class="numeric">${fmtBRL(r.saldo_atual)}</td>
                <td data-label="Resultado" class="numeric ${resultClass}">${fmtBRL(r.lucro_prejuizo)}<small>${fmtPctPlain(r.rentabilidade_pct)}</small></td>
                <td data-label="Peso" class="numeric">${fmtPctPlain(r.pct_carteira)}</td>
                <td data-label="Atualizacao">${fmtDate(r.atualizado_em)}</td>
            </tr>`;
    }).join("");

    document.getElementById("position-result-count").textContent = `${rows.length} de ${positionData.quantidade_posicoes}`;
    document.getElementById("caption-posicoes").textContent = positionData.cobertura_completa
        ? "Cobertura completa para todas as posicoes exibidas."
        : `${positionData.posicoes_sem_cotacao} posicoes permanecem sem valor de mercado; o total coberto nao e o patrimonio completo.`;
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
        document.getElementById("prov-12m").textContent = d.total_12m == null ? "Indisponivel" : fmtBRL(d.total_12m);
        document.getElementById("prov-12m").classList.remove("skeleton");
        document.getElementById("prov-ano").textContent = d.total_ano == null ? "Indisponivel" : fmtBRL(d.total_ano);
        document.getElementById("prov-ano").classList.remove("skeleton");
        document.getElementById("prov-mes").textContent = d.total_mes == null ? "Indisponivel" : fmtBRL(d.total_mes);
        document.getElementById("prov-mes").classList.remove("skeleton");

        // Chart
        const ctx = document.getElementById("chart-proventos").getContext("2d");
        if (chartProventos) chartProventos.destroy();

        if (meses == 1) {
            document.getElementById("prov-chart-title").textContent = "📊 Proventos por Ativo (último mês)";
            const byTicker = {};
            d.proventos.forEach(p => { byTicker[p.ticker] = (byTicker[p.ticker] || 0) + p.valor_por_cota; });
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
                byMonth[ym] = (byMonth[ym] || 0) + p.valor_por_cota;
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
                <td><strong>${safe(p.ticker)}</strong></td>
                <td>${new Date(p.data_pgto).toLocaleDateString("pt-BR")}</td>
                <td>${fmtBRL(p.valor_por_cota)}</td>
                <td>${safe(p.tipo)}</td>
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
        document.getElementById("rent-twr").textContent = fmtPct(d.variacao_patrimonio_pct);
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
                <td><strong>${safe(r.ticker)}</strong></td>
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
                <td><strong>${safe(r.ticker)}</strong></td>
                <td>${r.bazin > 0 ? "R$ " + r.bazin.toFixed(2) : "—"}</td>
                <td>${r.graham > 0 ? "R$ " + r.graham.toFixed(2) : "—"}</td>
            </tr>
        `).join("");

    } catch {
        registrarErro("análise");
    }
}

// ── Init ────────────────────────────────────────────────────────
carregarPosicoes();
carregarSaudeCarteira();
tabsLoaded.posicoes = true;
