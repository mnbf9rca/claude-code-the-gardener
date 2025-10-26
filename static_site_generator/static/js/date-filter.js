/**
 * Shared date filter initialization
 * Call initDateFilter(callback) where callback(fromTime, toTime) is called when the filter changes
 */
function initDateFilter(onFilterChange) {
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

    function applyTimeRange() {
        const fromExpr = fromInput.value.trim();
        const toExpr = toInput.value.trim();

        const fromTime = parseTimeExpression(fromExpr);
        const toTime = parseTimeExpression(toExpr);

        // Clear active preset buttons if manually edited
        presetBtns.forEach(b => {
            if (b.dataset.from !== fromExpr || b.dataset.to !== toExpr) {
                b.classList.remove('active');
            }
        });

        // Call the callback with the parsed times
        onFilterChange(fromTime, toTime);
    }
}
