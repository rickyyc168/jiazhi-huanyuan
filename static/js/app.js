/* ============================================================
   股票多维度分析系统 - 前端逻辑
   ============================================================ */

// 全局状态
let analysisData = null;
let weights = {
    fundamental: 30,
    technical: 20,
    sentiment: 15,
    news: 15,
    institutional: 20
};

// 图表实例
const charts = {};

// ============================================================
// 核心功能
// ============================================================

async function analyze() {
    const input = document.getElementById('stockInput').value.trim();
    if (!input) {
        alert('请输入股票代码');
        return;
    }

    const btn = document.getElementById('searchBtn');
    btn.querySelector('.btn-text').style.display = 'none';
    btn.querySelector('.btn-loading').style.display = 'inline';
    btn.disabled = true;

    try {
        const resp = await fetch(`/api/analyze?code=${encodeURIComponent(input)}&days=180`);
        const data = await resp.json();

        if (data.error) {
            alert(data.error);
            return;
        }

        analysisData = data;
        document.getElementById('resultArea').style.display = 'block';
        renderStockInfo(data.stock);
        renderModuleCharts(data);
        await recalcFit();
        
        // 滚动到结果
        document.getElementById('resultArea').scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (e) {
        alert('分析失败: ' + e.message);
    } finally {
        btn.querySelector('.btn-text').style.display = 'inline';
        btn.querySelector('.btn-loading').style.display = 'none';
        btn.disabled = false;
    }
}

function quickSelect(code) {
    document.getElementById('stockInput').value = code;
    analyze();
}

// ============================================================
// 渲染函数
// ============================================================

function renderStockInfo(stock) {
    document.getElementById('stockName').textContent = `${stock.name} (${stock.code})`;
    document.getElementById('stockPrice').textContent = stock.current_price.toFixed(2);
    
    const changeEl = document.getElementById('stockChange');
    const pct = stock.change_pct;
    changeEl.textContent = `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%`;
    changeEl.className = `stock-change ${pct >= 0 ? 'up' : 'down'}`;
    
    document.getElementById('stockSource').textContent = `数据源: ${stock.source}`;
}

function renderModuleCharts(data) {
    const moduleKeys = ['fundamental', 'technical', 'sentiment', 'news', 'institutional'];
    const colors = {
        fundamental: '#3b82f6',
        technical: '#10b981',
        sentiment: '#f59e0b',
        news: '#8b5cf6',
        institutional: '#06b6d4'
    };

    moduleKeys.forEach(key => {
        const module = data.modules[key];
        const chartId = `chart_${key}`;
        const dom = document.getElementById(chartId);
        
        if (charts[chartId]) {
            charts[chartId].dispose();
        }
        
        const chart = echarts.init(dom, 'dark');
        charts[chartId] = chart;

        chart.setOption({
            backgroundColor: 'transparent',
            grid: { top: 30, right: 20, bottom: 30, left: 50 },
            tooltip: {
                trigger: 'axis',
                backgroundColor: 'rgba(17, 24, 39, 0.95)',
                borderColor: '#2a3a52',
                textStyle: { color: '#e8edf5' }
            },
            xAxis: {
                type: 'category',
                data: data.dates,
                axisLabel: { 
                    color: '#8b97a8', 
                    fontSize: 11,
                    rotate: 30,
                    interval: Math.floor(data.dates.length / 6)
                },
                axisLine: { lineStyle: { color: '#2a3a52' } }
            },
            yAxis: {
                type: 'value',
                min: 0,
                max: 100,
                axisLabel: { color: '#8b97a8' },
                splitLine: { lineStyle: { color: '#1a2332' } }
            },
            series: [{
                data: module.scores,
                type: 'line',
                smooth: true,
                lineStyle: { width: 2, color: colors[key] },
                areaStyle: {
                    color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                        { offset: 0, color: colors[key] + '40' },
                        { offset: 1, color: colors[key] + '05' }
                    ])
                },
                symbol: 'none'
            }]
        });
    });
}

async function recalcFit() {
    if (!analysisData) return;

    const normalizedWeights = {};
    const total = Object.values(weights).reduce((a, b) => a + b, 0);
    if (total === 0) {
        alert('权重不能全部为0');
        return;
    }

    for (const [key, val] of Object.entries(weights)) {
        normalizedWeights[key] = val / total;
    }

    try {
        const resp = await fetch('/api/fit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                modules: analysisData.modules,
                weights: normalizedWeights,
                price_changes: analysisData.price_changes
            })
        });

        const result = await resp.json();
        if (!result.success) {
            alert('拟合计算失败');
            return;
        }

        renderCompositeChart(result);
        renderFitResult(result);
        renderFitMetrics(result);
    } catch (e) {
        alert('拟合计算失败: ' + e.message);
    }
}

function renderCompositeChart(result) {
    const dom = document.getElementById('compositeChart');
    
    if (charts.composite) {
        charts.composite.dispose();
    }
    
    const chart = echarts.init(dom, 'dark');
    charts.composite = chart;

    // 计算综合评分累计值（从50开始）
    const compositeScores = [50];
    for (let i = 1; i < result.composite_changes.length; i++) {
        compositeScores.push(Math.max(0, Math.min(100, compositeScores[i-1] + result.composite_changes[i])));
    }

    // 计算评分的实际范围
    const scoreMin = Math.min(...compositeScores);
    const scoreMax = Math.max(...compositeScores);
    const scoreRange = scoreMax - scoreMin || 1;
    const scorePadding = scoreRange * 0.1;  // 上下留10%间距

    // 归一化股价到评分的同一范围，让两条线紧贴对比
    const closes = analysisData.closes;
    const minPrice = Math.min(...closes);
    const maxPrice = Math.max(...closes);
    const priceRange = maxPrice - minPrice || 1;
    const normalizedPrices = closes.map(p => 
        ((p - minPrice) / priceRange) * scoreRange + (scoreMin - scorePadding)
    );

    // Y轴范围：取两条线的合并范围
    const allValues = [...compositeScores, ...normalizedPrices];
    const yMin = Math.floor(Math.min(...allValues) - scorePadding);
    const yMax = Math.ceil(Math.max(...allValues) + scorePadding);

    // 存储真实价格用于tooltip
    const realCloses = analysisData.closes;

    chart.setOption({
        backgroundColor: 'transparent',
        grid: { top: 60, right: 40, bottom: 40, left: 60 },
        tooltip: {
            trigger: 'axis',
            backgroundColor: 'rgba(17, 24, 39, 0.95)',
            borderColor: '#2a3a52',
            textStyle: { color: '#e8edf5' },
            formatter: function(params) {
                let html = `<div style="font-weight:600;margin-bottom:6px">${params[0].axisValue}</div>`;
                params.forEach(p => {
                    if (p.seriesName === '真实股价') {
                        // 显示真实价格而非归一化值
                        const idx = p.dataIndex;
                        const realPrice = realCloses[idx];
                        html += `<div>${p.marker} ${p.seriesName}: <b>${realPrice.toFixed(2)}</b></div>`;
                    } else {
                        html += `<div>${p.marker} ${p.seriesName}: <b>${p.value.toFixed(1)}</b></div>`;
                    }
                });
                return html;
            }
        },
        legend: {
            data: ['综合评分曲线', '真实股价'],
            textStyle: { color: '#8b97a8' },
            top: 10
        },
        xAxis: {
            type: 'category',
            data: analysisData.dates,
            axisLabel: { 
                color: '#8b97a8',
                rotate: 30,
                interval: Math.floor(analysisData.dates.length / 8)
            },
            axisLine: { lineStyle: { color: '#2a3a52' } }
        },
        yAxis: {
            type: 'value',
            min: yMin,
            max: yMax,
            axisLabel: { color: '#8b97a8' },
            splitLine: { lineStyle: { color: '#1a2332' } }
        },
        series: [
            {
                name: '综合评分曲线',
                type: 'line',
                data: compositeScores,
                smooth: true,
                lineStyle: { width: 3, color: '#3b82f6' },
                areaStyle: {
                    color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                        { offset: 0, color: '#3b82f630' },
                        { offset: 1, color: '#3b82f605' }
                    ])
                },
                symbol: 'none',
                z: 10
            },
            {
                name: '真实股价',
                type: 'line',
                data: normalizedPrices,
                smooth: true,
                lineStyle: { width: 2, color: '#ef4444', type: 'dashed' },
                symbol: 'none',
                z: 5
            }
        ]
    });

    // 响应式
    window.addEventListener('resize', () => chart.resize());
}

function renderFitResult(result) {
    const el = document.getElementById('fitResult');
    if (result.is_explainable) {
        el.className = 'fit-result explainable';
        el.innerHTML = `✅ 模型可解释市场 | 离散度: ${result.dispersion}% (≤20%阈值) | 相关系数: ${result.correlation}`;
    } else {
        el.className = 'fit-result blackbox';
        el.innerHTML = `⚠️ 存在黑箱因素 | 离散度: ${result.dispersion}% (>20%阈值) | 模型未覆盖部分市场影响因素`;
    }
}

function renderFitMetrics(result) {
    const el = document.getElementById('fitMetrics');
    const metrics = [
        {
            label: '离散度',
            value: `${result.dispersion}%`,
            quality: result.dispersion <= 20 ? 'good' : result.dispersion <= 30 ? 'warn' : 'bad'
        },
        {
            label: '相关系数',
            value: result.correlation.toFixed(4),
            quality: result.correlation > 0.5 ? 'good' : result.correlation > 0.2 ? 'warn' : 'bad'
        },
        {
            label: '平均绝对误差 (MAE)',
            value: result.mae.toFixed(4),
            quality: result.mae < 2 ? 'good' : result.mae < 5 ? 'warn' : 'bad'
        },
        {
            label: '模型解释力',
            value: result.is_explainable ? '✅ 可解释' : '⚠️ 存在黑箱',
            quality: result.is_explainable ? 'good' : 'warn'
        },
        {
            label: '数据点数',
            value: analysisData.dates.length,
            quality: 'good'
        },
        {
            label: '数据源',
            value: analysisData.stock.source,
            quality: 'good'
        }
    ];

    el.innerHTML = metrics.map(m => `
        <div class="metric-card">
            <div class="metric-label">${m.label}</div>
            <div class="metric-value ${m.quality}">${m.value}</div>
        </div>
    `).join('');
}

// ============================================================
// 权重管理
// ============================================================

function updateWeight(slider, key) {
    weights[key] = parseInt(slider.value);
    document.getElementById(`wv_${key}`).textContent = slider.value + '%';
    updateWeightTotal();
}

function updateWeightTotal() {
    const total = Object.values(weights).reduce((a, b) => a + b, 0);
    const el = document.getElementById('weightTotal');
    el.textContent = total + '%';
    el.style.color = total === 100 ? '#10b981' : '#ef4444';
}

function resetWeights() {
    const defaults = { fundamental: 30, technical: 20, sentiment: 15, news: 15, institutional: 20 };
    for (const [key, val] of Object.entries(defaults)) {
        weights[key] = val;
        document.getElementById(`w_${key}`).value = val;
        document.getElementById(`wv_${key}`).textContent = val + '%';
    }
    updateWeightTotal();
    if (analysisData) recalcFit();
}

// ============================================================
// 初始化
// ============================================================

window.addEventListener('load', () => {
    // 深色主题图表
    echarts.registerTheme('dark', {
        backgroundColor: 'transparent',
        textStyle: { color: '#8b97a8' }
    });
});


// ============================================================
// 搜索联想功能
// ============================================================

let searchTimer = null;
let suggestIndex = -1;
let lastQuery = '';

function initSearchSuggest() {
    const input = document.getElementById('stockInput');
    const box = document.querySelector('.search-box');

    let dropdown = document.getElementById('searchSuggest');
    if (!dropdown) {
        dropdown = document.createElement('div');
        dropdown.id = 'searchSuggest';
        dropdown.className = 'search-suggest';
        box.appendChild(dropdown);
    }

    input.addEventListener('input', function () {
        clearTimeout(searchTimer);
        const q = this.value.trim();

        if (q.length < 1) {
            hideSuggest();
            return;
        }

        searchTimer = setTimeout(() => doSearch(q), 300);
    });

    input.addEventListener('keydown', function (e) {
        const dropdown = document.getElementById('searchSuggest');
        if (!dropdown || !dropdown.classList.contains('active')) return;

        const items = dropdown.querySelectorAll('.suggest-item');
        if (!items.length) return;

        if (e.key === 'ArrowDown') {
            e.preventDefault();
            suggestIndex = Math.min(suggestIndex + 1, items.length - 1);
            updateHighlight(items);
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            suggestIndex = Math.max(suggestIndex - 1, 0);
            updateHighlight(items);
        } else if (e.key === 'Enter') {
            if (suggestIndex >= 0 && items[suggestIndex]) {
                e.preventDefault();
                items[suggestIndex].click();
            }
        } else if (e.key === 'Escape') {
            hideSuggest();
        }
    });

    document.addEventListener('click', function (e) {
        if (!box.contains(e.target)) {
            hideSuggest();
        }
    });
}

function updateHighlight(items) {
    items.forEach((item, i) => {
        item.classList.toggle('highlighted', i === suggestIndex);
    });
    if (items[suggestIndex]) {
        items[suggestIndex].scrollIntoView({ block: 'nearest' });
    }
}

function hideSuggest() {
    const dropdown = document.getElementById('searchSuggest');
    if (dropdown) {
        dropdown.classList.remove('active');
        dropdown.innerHTML = '';
    }
    suggestIndex = -1;
}

async function doSearch(query) {
    if (query === lastQuery) return;
    lastQuery = query;

    const dropdown = document.getElementById('searchSuggest');
    if (!dropdown) return;

    dropdown.innerHTML = '<div class="suggest-loading">🔍 搜索中...</div>';
    dropdown.classList.add('active');
    suggestIndex = -1;

    try {
        const resp = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
        const data = await resp.json();

        if (!data.results || data.results.length === 0) {
            dropdown.innerHTML = '<div class="suggest-empty">未找到相关股票</div>';
            return;
        }

        dropdown.innerHTML = data.results.map((item, i) => `
            <div class="suggest-item" onclick="selectStock('${item.code}', '${item.name}', '${item.suffix}')">
                <div>
                    <span class="suggest-code">${item.code}</span>
                    <span class="suggest-name">${item.name}</span>
                </div>
                <span class="suggest-type">${item.type}</span>
            </div>
        `).join('');
    } catch (err) {
        dropdown.innerHTML = '<div class="suggest-empty">搜索出错，请直接输入代码</div>';
    }
}

function selectStock(code, name, suffix) {
    const input = document.getElementById('stockInput');
    input.value = code + suffix;
    hideSuggest();
    analyze();
}

// 覆盖原有的 quickSelect
const _originalQuickSelect = typeof quickSelect === 'function' ? quickSelect : null;
function quickSelect(codeOrName) {
    const input = document.getElementById('stockInput');
    input.value = codeOrName;
    hideSuggest();
    analyze();
}

document.addEventListener('DOMContentLoaded', initSearchSuggest);
