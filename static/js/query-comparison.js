/**
 * Query Plan Comparison Utilities
 * This file contains functions to highlight differences between two query plans
 */

// Colors for highlighting different types of changes
const HIGHLIGHT_COLORS = {
    versionDiff: 'rgba(0, 123, 255, 0.2)',    // Blue background for version differences
    timingDiff: 'rgba(255, 193, 7, 0.2)',     // Yellow background for timing differences
    structureDiff: 'rgba(220, 53, 69, 0.2)',  // Red background for structural differences
    estimateDiff: 'rgba(40, 167, 69, 0.2)'    // Green background for estimate differences
};

// Class names for highlights
const HIGHLIGHT_CLASSES = {
    versionDiff: 'highlight-version-diff',
    timingDiff: 'highlight-timing-diff',
    structureDiff: 'highlight-structure-diff',
    estimateDiff: 'highlight-estimate-diff'
};

/**
 * Initialize the query plan comparison highlighting
 */
function initQueryPlanComparison() {
    console.log("Initializing query plan comparison");
    
    // Add CSS for highlighting
    addHighlightStyles();
    
    // Get the query plan text elements for both clusters
    const cluster1Plans = document.querySelectorAll('.cluster1-explain-plan');
    const cluster2Plans = document.querySelectorAll('.cluster2-explain-plan');
    
    if (cluster1Plans.length > 0 && cluster2Plans.length > 0) {
        console.log("Found query plans, highlighting differences");
        
        // If we have explain plans, process them
        // (typically just one cell for each cluster)
        if (cluster1Plans.length === cluster2Plans.length) {
            for (let i = 0; i < cluster1Plans.length; i++) {
                highlightPlanDifferences(cluster1Plans[i], cluster2Plans[i]);
            }
        } else {
            console.warn("Unequal number of plan elements between clusters");
            // Still try to highlight the first one of each
            if (cluster1Plans[0] && cluster2Plans[0]) {
                highlightPlanDifferences(cluster1Plans[0], cluster2Plans[0]);
            }
        }
    } else {
        console.log("Could not find both query plans");
    }
}

/**
 * Add CSS styles for highlighting to the page
 */
function addHighlightStyles() {
    const styleEl = document.createElement('style');
    styleEl.textContent = `
        .${HIGHLIGHT_CLASSES.versionDiff} {
            background-color: ${HIGHLIGHT_COLORS.versionDiff};
            padding: 2px;
            border-radius: 3px;
        }
        .${HIGHLIGHT_CLASSES.timingDiff} {
            background-color: ${HIGHLIGHT_COLORS.timingDiff};
            padding: 2px;
            border-radius: 3px;
        }
        .${HIGHLIGHT_CLASSES.structureDiff} {
            background-color: ${HIGHLIGHT_COLORS.structureDiff};
            padding: 2px;
            border-radius: 3px;
        }
        .${HIGHLIGHT_CLASSES.estimateDiff} {
            background-color: ${HIGHLIGHT_COLORS.estimateDiff};
            padding: 2px;
            border-radius: 3px;
        }
    `;
    document.head.appendChild(styleEl);
}

/**
 * Highlight differences between two query plans
 */
function highlightPlanDifferences(plan1Element, plan2Element) {
    const plan1Lines = plan1Element.innerText.split('\n');
    const plan2Lines = plan2Element.innerText.split('\n');
    
    // Create new HTML for the plans with highlighted differences
    let highlightedPlan1HTML = '';
    let highlightedPlan2HTML = '';
    
    // Process each line
    const maxLines = Math.max(plan1Lines.length, plan2Lines.length);
    for (let i = 0; i < maxLines; i++) {
        const line1 = i < plan1Lines.length ? plan1Lines[i] : '';
        const line2 = i < plan2Lines.length ? plan2Lines[i] : '';
        
        if (line1 === line2) {
            // Lines are identical
            highlightedPlan1HTML += `${escapeHTML(line1)}\n`;
            highlightedPlan2HTML += `${escapeHTML(line2)}\n`;
        } else {
            // Lines are different, determine type of difference
            const diffType = determineDifferenceType(line1, line2);
            const highlightClass = HIGHLIGHT_CLASSES[diffType];
            
            highlightedPlan1HTML += `<span class="${highlightClass}">${escapeHTML(line1)}</span>\n`;
            highlightedPlan2HTML += `<span class="${highlightClass}">${escapeHTML(line2)}</span>\n`;
        }
    }
    
    // Update the plan elements with highlighted content
    plan1Element.innerHTML = highlightedPlan1HTML;
    plan2Element.innerHTML = highlightedPlan2HTML;
    
    // Add a legend for the highlights
    addHighlightLegend();
}

/**
 * Determine the type of difference between two lines
 */
function determineDifferenceType(line1, line2) {
    // Check for version differences
    if (line1.includes('version:') || line2.includes('version:')) {
        return 'versionDiff';
    }
    
    // Check for timing/performance differences
    if (line1.includes('seconds') || line2.includes('seconds') ||
        line1.includes('ms)') || line2.includes('ms)')) {
        return 'timingDiff';
    }
    
    // Check for estimate differences
    if (line1.includes('Estimates:') || line2.includes('Estimates:') ||
        line1.includes('rows:') || line2.includes('rows:') ||
        line1.includes('memory:') || line2.includes('memory:') ||
        (line1.match(/\(\d+B\)/) || line2.match(/\(\d+B\)/))) {
        return 'estimateDiff';
    }
    
    // Check for plan structure differences related to operators or execution details
    const structureKeywords = ['Fragment', 'Output', 'Layout:', 'partitioning:', 'distributed', 'join'];
    for (const keyword of structureKeywords) {
        if (line1.includes(keyword) || line2.includes(keyword)) {
            return 'structureDiff';
        }
    }
    
    // Default to structure differences
    return 'structureDiff';
}

/**
 * Add a legend explaining the highlight colors
 */
function addHighlightLegend() {
    // Check if legend already exists
    if (document.querySelector('.highlight-legend')) {
        return; // Legend already added
    }
    
    const legendDiv = document.createElement('div');
    legendDiv.className = 'highlight-legend card mt-2';
    
    legendDiv.innerHTML = `
        <div class="card-header">
            <h6 class="mb-0">Highlight Legend</h6>
        </div>
        <div class="card-body">
            <div class="d-flex flex-wrap gap-3">
                <div>
                    <span class="${HIGHLIGHT_CLASSES.versionDiff} px-2 me-1">Version</span>
                    <small>Version differences</small>
                </div>
                <div>
                    <span class="${HIGHLIGHT_CLASSES.timingDiff} px-2 me-1">Timing</span>
                    <small>Execution time differences</small>
                </div>
                <div>
                    <span class="${HIGHLIGHT_CLASSES.structureDiff} px-2 me-1">Structure</span>
                    <small>Query plan structure differences</small>
                </div>
                <div>
                    <span class="${HIGHLIGHT_CLASSES.estimateDiff} px-2 me-1">Estimates</span>
                    <small>Row/memory estimate differences</small>
                </div>
            </div>
        </div>
    `;
    
    // Add the legend after the query plan comparison section
    const planContainer = document.querySelector('.card-header.bg-dark');
    
    if (planContainer && planContainer.closest('.card')) {
        const container = planContainer.closest('.card');
        container.parentNode.insertBefore(legendDiv, container.nextSibling);
    } else {
        // Fallback: Add legend to the end of the content area
        const contentArea = document.querySelector('.card-body') || document.body;
        contentArea.appendChild(legendDiv);
    }
}

/**
 * Escape HTML special characters
 */
function escapeHTML(str) {
    return str
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

// Run the initialization when the DOM is fully loaded
document.addEventListener('DOMContentLoaded', function() {
    initQueryPlanComparison();
});