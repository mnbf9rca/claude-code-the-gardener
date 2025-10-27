// Annotation system for marking interesting events
// Uses localStorage for persistence across page loads

const STORAGE_KEY = 'gardener_annotations';

function loadAnnotations() {
    try {
        const stored = localStorage.getItem(STORAGE_KEY);
        return stored ? JSON.parse(stored) : {};
    } catch (e) {
        console.error('Error loading annotations:', e);
        return {};
    }
}

function saveAnnotations(annotations) {
    try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(annotations));
    } catch (e) {
        console.error('Error saving annotations:', e);
    }
}

function exportAnnotations() {
    const annotations = loadAnnotations();
    const dataStr = JSON.stringify(annotations, null, 2);
    const blob = new Blob([dataStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);

    const a = document.createElement('a');
    a.href = url;
    a.download = 'gardener_annotations.json';
    a.click();

    URL.revokeObjectURL(url);
}

function importAnnotations(file) {
    const reader = new FileReader();
    reader.onload = function(e) {
        try {
            const importedAnnotations = JSON.parse(e.target.result);
            const existingAnnotations = loadAnnotations();

            // Warn if overwriting existing annotations
            if (Object.keys(existingAnnotations).length > 0) {
                const action = window.confirm(
                    `You have ${Object.keys(existingAnnotations).length} existing annotation(s). ` +
                    `Click OK to overwrite them, or Cancel to merge (imported annotations will take precedence).`
                );

                if (action) {
                    // Overwrite
                    localStorage.setItem(STORAGE_KEY, JSON.stringify(importedAnnotations));
                } else {
                    // Merge: imported takes precedence
                    const merged = { ...existingAnnotations, ...importedAnnotations };
                    localStorage.setItem(STORAGE_KEY, JSON.stringify(merged));
                }
            } else {
                // No existing annotations, just import
                localStorage.setItem(STORAGE_KEY, JSON.stringify(importedAnnotations));
            }

            location.reload();
        } catch (error) {
            alert('Error importing annotations: ' + error.message);
        }
    };
    reader.readAsText(file);
}

// Initialize annotation buttons
document.addEventListener('DOMContentLoaded', function() {
    const annotateBtns = document.querySelectorAll('.annotate-btn');

    annotateBtns.forEach(btn => {
        btn.addEventListener('click', function() {
            const {eventId} = this.dataset;
            const note = prompt('Add your note:');

            if (note) {
                const annotations = loadAnnotations();
                annotations[eventId] = {
                    note: note,
                    timestamp: new Date().toISOString()
                };
                saveAnnotations(annotations);

                // Visual feedback
                this.textContent = '✓ Noted';
                this.style.background = '#e8f5e9';
            }
        });
    });

    // Load existing annotations and mark buttons
    const annotations = loadAnnotations();
    annotateBtns.forEach(btn => {
        const {eventId} = btn.dataset;
        if (annotations[eventId]) {
            btn.textContent = '✓ Noted';
            btn.style.background = '#e8f5e9';
        }
    });
});

// Export annotation controls (if needed)
window.gardenerAnnotations = {
    export: exportAnnotations,
    import: importAnnotations,
    load: loadAnnotations
};
