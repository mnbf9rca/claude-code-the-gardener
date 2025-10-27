// Chart.js configuration for sensor and analytics visualization

// Global variables to store chart instances and data
let allData = null;
let chartInstances = {};

document.addEventListener('DOMContentLoaded', async function() {
    try {
        // Load sensor data
        const response = await fetch('../data/sensor_data.json');
        allData = await response.json();

        // Initialize charts with all data
        renderCharts(allData);

        // Setup date range filter
        setupDateRangeFilter();

    } catch (error) {
        console.error('Error loading sensor data:', error);
    }
});

// Helper to show error feedback for invalid time expressions
function showTimeExpressionError(message) {
    let errorElem = document.getElementById('time-expression-error');
    if (!errorElem) {
        errorElem = document.createElement('div');
        errorElem.id = 'time-expression-error';
        errorElem.style.color = 'var(--color-error, #e63946)';
        errorElem.style.marginTop = '8px';
        errorElem.style.fontSize = '0.9em';
        // Insert after the time filter controls if present
        const filterControls = document.querySelector('.time-filter-controls');
        if (filterControls && filterControls.parentNode) {
            filterControls.parentNode.insertBefore(errorElem, filterControls.nextSibling);
        } else {
            // Fallback: insert at top of page
            const main = document.querySelector('main') || document.body;
            main.insertBefore(errorElem, main.firstChild);
        }
    }
    errorElem.textContent = message;
}

// Helper to clear error feedback
function clearTimeExpressionError() {
    const errorElem = document.getElementById('time-expression-error');
    if (errorElem) {
        errorElem.textContent = '';
    }
}

function setupDateRangeFilter() {
    const presetBtns = document.querySelectorAll('.preset-btn');
    const applyBtn = document.getElementById('apply-time-range');
    const fromInput = document.getElementById('time-from');
    const toInput = document.getElementById('time-to');

    // Preset buttons
    presetBtns.forEach(btn => {
        btn.addEventListener('click', function() {
            presetBtns.forEach(b => b.classList.remove('active'));
            this.classList.add('active');

            const fromExpr = this.dataset.from;
            const toExpr = this.dataset.to;

            fromInput.value = fromExpr;
            toInput.value = toExpr;

            // Auto-apply
            applyTimeRange();
        });
    });

    // Apply button
    applyBtn.addEventListener('click', applyTimeRange);

    // Enter key in inputs
    fromInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') applyTimeRange();
    });
    toInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') applyTimeRange();
    });

    // Function expression instead of declaration (avoid hoisting issues in blocks)
    const applyTimeRange = () => {
        const fromExpr = fromInput.value.trim();
        const toExpr = toInput.value.trim();

        // Clear any previous errors
        clearTimeExpressionError();

        // Parse with error callbacks
        const fromTime = parseTimeExpression(fromExpr, showTimeExpressionError);
        const toTime = parseTimeExpression(toExpr, showTimeExpressionError);

        // Clear active preset buttons if manually edited
        presetBtns.forEach(b => {
            if (b.dataset.from !== fromExpr || b.dataset.to !== toExpr) {
                b.classList.remove('active');
            }
        });

        // If both are null/empty, show all data
        if (fromTime === null && toTime === null) {
            applyFilter('all');
            return;
        }

        // Apply custom range
        const minTime = fromTime || 0;
        const maxTime = toTime || Date.now() + 86400000;

        applyFilter('custom', minTime, maxTime);
    };
}

function applyFilter(range, customStart, customEnd) {
    if (!allData) return;

    const now = Date.now();
    let minTime, maxTime;

    if (range === 'all') {
        minTime = 0;
        maxTime = now + 86400000; // Add 1 day buffer
    } else if (range === 'custom') {
        minTime = customStart;
        maxTime = customEnd;
    }

    // Filter all datasets
    const filteredData = {
        moisture: allData.moisture.filter(d => d.unix >= minTime && d.unix <= maxTime),
        light: allData.light.filter(d => d.unix >= minTime && d.unix <= maxTime),
        water: allData.water.filter(d => d.unix >= minTime && d.unix <= maxTime),
        cost: allData.cost?.filter(d => d.unix >= minTime && d.unix <= maxTime) || [],
        tokens: allData.tokens?.filter(d => d.unix >= minTime && d.unix <= maxTime) || [],
        thoughts: allData.thoughts?.filter(d => d.unix >= minTime && d.unix <= maxTime) || [],
        actions: allData.actions?.filter(d => d.unix >= minTime && d.unix <= maxTime) || [],
    };

    // Destroy existing charts
    Object.values(chartInstances).forEach(chart => chart.destroy());
    chartInstances = {};

    // Render with filtered data
    renderCharts(filteredData, minTime, maxTime);
}

function renderCharts(data, forceMinTime, forceMaxTime) {
    try {

        // Find min and max timestamps across all datasets for synchronized x-axes
        const allTimestamps = [
            ...data.moisture.map(d => d.unix),
            ...data.light.map(d => d.unix),
            ...(data.cost || []).map(d => d.unix),
            ...(data.tokens || []).map(d => d.unix),
            ...(data.thoughts || []).map(d => d.unix),
            ...(data.actions || []).map(d => d.unix),
        ].filter(t => t); // Remove any undefined/null values

        const minTime = forceMinTime !== undefined ? forceMinTime : (allTimestamps.length > 0 ? Math.min(...allTimestamps) : Date.now() - 86400000);
        const maxTime = forceMaxTime !== undefined ? forceMaxTime : (allTimestamps.length > 0 ? Math.max(...allTimestamps) : Date.now());

        // Common x-axis configuration for all charts
        const commonXAxis = {
            type: 'time',
            time: {
                unit: 'hour',
                displayFormats: {
                    hour: 'MMM d, HH:mm'
                }
            },
            min: minTime,
            max: maxTime,
            ticks: {
                maxRotation: 45,
                minRotation: 45,
                font: { size: 10 }
            }
        };

        // Common chart options
        const commonOptions = {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false,
            },
            plugins: {
                legend: {
                    display: true,
                    labels: { font: { size: 10 } }
                }
            }
        };

        // Moisture Chart
        const moistureCtx = document.getElementById('moisture-chart');
        if (moistureCtx && data.moisture.length > 0) {
            chartInstances.moisture = new Chart(moistureCtx, {
                type: 'line',
                data: {
                    datasets: [{
                        label: 'Moisture Level',
                        data: data.moisture.map(d => ({ x: d.unix, y: d.value })),
                        borderColor: '#4c9bf5',
                        backgroundColor: 'rgba(76, 155, 245, 0.1)',
                        borderWidth: 2,
                        pointRadius: 0,
                        tension: 0.4
                    }]
                },
                options: {
                    ...commonOptions,
                    scales: {
                        x: commonXAxis,
                        y: {
                            title: { display: true, text: 'Sensor Value', font: { size: 11 } },
                            ticks: { font: { size: 10 } }
                        }
                    }
                }
            });
        }

        // Light Chart
        const lightCtx = document.getElementById('light-chart');
        if (lightCtx && data.light.length > 0) {
            chartInstances.light = new Chart(lightCtx, {
                type: 'bar',
                data: {
                    datasets: [{
                        label: 'Duration (min)',
                        data: data.light.map(d => ({ x: d.unix, y: d.duration_minutes })),
                        backgroundColor: '#ffd60a',
                        borderWidth: 0
                    }]
                },
                options: {
                    ...commonOptions,
                    scales: {
                        x: commonXAxis,
                        y: {
                            title: { display: true, text: 'Minutes', font: { size: 11 } },
                            ticks: { font: { size: 10 } }
                        }
                    }
                }
            });
        }

        // Cost Chart
        const costCtx = document.getElementById('cost-chart');
        if (costCtx && data.cost && data.cost.length > 0) {
            chartInstances.cost = new Chart(costCtx, {
                type: 'line',
                data: {
                    datasets: [{
                        label: 'Cumulative Cost',
                        data: data.cost.map(d => ({ x: d.unix, y: d.cumulative_cost })),
                        borderColor: '#e63946',
                        backgroundColor: 'rgba(230, 57, 70, 0.1)',
                        borderWidth: 2,
                        pointRadius: 0,
                        tension: 0.4,
                        fill: true
                    }]
                },
                options: {
                    ...commonOptions,
                    scales: {
                        x: commonXAxis,
                        y: {
                            title: { display: true, text: 'USD ($)', font: { size: 11 } },
                            ticks: {
                                font: { size: 10 },
                                callback: function(value) {
                                    return '$' + value.toFixed(2);
                                }
                            }
                        }
                    }
                }
            });
        }

        // Tokens Chart - simple stacked bars per conversation
        const tokensCtx = document.getElementById('tokens-chart');
        if (tokensCtx && data.tokens && data.tokens.length > 0) {
            chartInstances.tokens = new Chart(tokensCtx, {
                type: 'bar',
                data: {
                    datasets: [
                        {
                            label: 'Input',
                            data: data.tokens.map(d => ({ x: d.unix, y: d.input })),
                            backgroundColor: 'rgba(76, 155, 245, 0.8)',
                            stack: 'tokens',
                            barThickness: 4,
                            maxBarThickness: 8
                        },
                        {
                            label: 'Output',
                            data: data.tokens.map(d => ({ x: d.unix, y: d.output })),
                            backgroundColor: 'rgba(46, 204, 113, 0.8)',
                            stack: 'tokens',
                            barThickness: 4,
                            maxBarThickness: 8
                        },
                        {
                            label: 'Cache Read',
                            data: data.tokens.map(d => ({ x: d.unix, y: d.cache_read })),
                            backgroundColor: 'rgba(155, 89, 182, 0.8)',
                            stack: 'tokens',
                            barThickness: 4,
                            maxBarThickness: 8
                        },
                        {
                            label: 'Cache Create',
                            data: data.tokens.map(d => ({ x: d.unix, y: d.cache_creation })),
                            backgroundColor: 'rgba(241, 196, 15, 0.8)',
                            stack: 'tokens',
                            barThickness: 4,
                            maxBarThickness: 8
                        }
                    ]
                },
                options: {
                    ...commonOptions,
                    scales: {
                        x: {
                            ...commonXAxis,
                            stacked: true,
                            offset: false
                        },
                        y: {
                            stacked: true,
                            title: { display: true, text: 'Tokens', font: { size: 11 } },
                            ticks: {
                                font: { size: 10 },
                                callback: function(value) {
                                    if (value >= 1000000) {
                                        return (value / 1000000).toFixed(1) + 'M';
                                    } else if (value >= 1000) {
                                        return (value / 1000).toFixed(0) + 'k';
                                    }
                                    return value;
                                }
                            }
                        }
                    }
                }
            });
        }

        // Thoughts Chart
        const thoughtsCtx = document.getElementById('thoughts-chart');
        if (thoughtsCtx && data.thoughts && data.thoughts.length > 0) {
            chartInstances.thoughts = new Chart(thoughtsCtx, {
                type: 'line',
                data: {
                    datasets: [{
                        label: 'Cumulative Thoughts',
                        data: data.thoughts.map(d => ({ x: d.unix, y: d.cumulative })),
                        borderColor: '#9b59b6',
                        backgroundColor: 'rgba(155, 89, 182, 0.1)',
                        borderWidth: 2,
                        pointRadius: 0,
                        tension: 0.4,
                        fill: true
                    }]
                },
                options: {
                    ...commonOptions,
                    scales: {
                        x: commonXAxis,
                        y: {
                            title: { display: true, text: 'Count', font: { size: 11 } },
                            ticks: { font: { size: 10 } }
                        }
                    }
                }
            });
        }

        // Actions Chart
        const actionsCtx = document.getElementById('actions-chart');
        if (actionsCtx && data.actions && data.actions.length > 0) {
            chartInstances.actions = new Chart(actionsCtx, {
                type: 'line',
                data: {
                    datasets: [{
                        label: 'Cumulative Actions',
                        data: data.actions.map(d => ({ x: d.unix, y: d.cumulative })),
                        borderColor: '#2ecc71',
                        backgroundColor: 'rgba(46, 204, 113, 0.1)',
                        borderWidth: 2,
                        pointRadius: 0,
                        tension: 0.4,
                        fill: true
                    }]
                },
                options: {
                    ...commonOptions,
                    scales: {
                        x: commonXAxis,
                        y: {
                            title: { display: true, text: 'Count', font: { size: 11 } },
                            ticks: { font: { size: 10 } }
                        }
                    }
                }
            });
        }

    } catch (error) {
        console.error('Error rendering charts:', error);
    }
}
