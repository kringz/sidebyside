// Main JavaScript file for Trino Comparison Tool

// Global loading indicator functions
function showLoading(message = 'Loading...') {
    // Create the loading overlay if it doesn't exist
    let overlay = document.querySelector('.spinner-overlay');
    
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.className = 'spinner-overlay';
        
        const spinnerContainer = document.createElement('div');
        spinnerContainer.className = 'spinner-container';
        
        const spinner = document.createElement('div');
        spinner.className = 'spinner-border text-primary';
        spinner.setAttribute('role', 'status');
        
        const spinnerSr = document.createElement('span');
        spinnerSr.className = 'visually-hidden';
        spinnerSr.textContent = 'Loading...';
        
        const messageElement = document.createElement('div');
        messageElement.className = 'spinner-message';
        messageElement.id = 'loading-message';
        
        spinner.appendChild(spinnerSr);
        spinnerContainer.appendChild(spinner);
        spinnerContainer.appendChild(messageElement);
        overlay.appendChild(spinnerContainer);
        
        document.body.appendChild(overlay);
    }
    
    // Set the loading message
    document.getElementById('loading-message').textContent = message;
    
    // Show the overlay
    overlay.classList.add('show');
}

function hideLoading() {
    const overlay = document.querySelector('.spinner-overlay');
    if (overlay) {
        overlay.classList.remove('show');
    }
}

// Button loading state functions
function setButtonLoading(button, isLoading) {
    if (isLoading) {
        button.disabled = true;
        button.classList.add('btn-loading');
        button.dataset.originalText = button.textContent;
        button.innerHTML = '&nbsp;'; // Create space for the spinner
    } else {
        button.disabled = false;
        button.classList.remove('btn-loading');
        if (button.dataset.originalText) {
            button.textContent = button.dataset.originalText;
            delete button.dataset.originalText;
        }
    }
}

document.addEventListener('DOMContentLoaded', function() {
    // Auto-close alerts after 5 seconds
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        setTimeout(() => {
            const closeButton = alert.querySelector('.btn-close');
            if (closeButton) {
                closeButton.click();
            }
        }, 5000);
    });
    
    // Make sure the catalog checkboxes are properly styled and visible
    const catalogCheckboxes = document.querySelectorAll('input[name="enabled_catalogs"]');
    if (catalogCheckboxes.length > 0) {
        catalogCheckboxes.forEach(checkbox => {
            // Make sure the checkbox is visible
            checkbox.style.opacity = "1";
            checkbox.style.position = "static";
            checkbox.style.width = "20px";
            checkbox.style.height = "20px";
            checkbox.style.marginRight = "8px";
            checkbox.style.cursor = "pointer";
            checkbox.parentElement.style.opacity = "1";
        });
    }
    
    // Toggle catalog configuration sections based on checkbox state
    const formCheckboxes = document.querySelectorAll('.form-check-input[type="checkbox"]');
    formCheckboxes.forEach(checkbox => {
        checkbox.addEventListener('change', function() {
            const cardBody = this.closest('.card').querySelector('.card-body');
            if (cardBody) {
                if (this.checked) {
                    cardBody.style.display = 'block';
                } else {
                    cardBody.style.display = 'none';
                }
            }
        });
        
        // Initial state
        const cardBody = checkbox.closest('.card').querySelector('.card-body');
        if (cardBody && !checkbox.checked) {
            cardBody.style.display = 'none';
        }
    });
    
    // Example query click handler (already implemented in query.html)
    
    // Add loading indicators for form submissions
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        form.addEventListener('submit', function(event) {
            // Skip for forms with data-no-loading attribute
            if (this.getAttribute('data-no-loading') === 'true') {
                return;
            }
            
            // Check if the form has a data-loading-message attribute
            let message = this.getAttribute('data-loading-message');
            
            // If not, determine message based on form action
            if (!message) {
                message = 'Processing...';
                
                if (this.action.includes('save_catalog_config')) {
                    message = 'Saving catalog configuration...';
                } else if (this.action.includes('save_configuration')) {
                    message = 'Saving cluster configuration...';
                } else if (this.action.includes('reset_config')) {
                    message = 'Resetting to default configuration...';
                } else if (this.action.includes('start_clusters')) {
                    message = 'Starting Trino clusters... This may take a moment.';
                } else if (this.action.includes('stop_clusters')) {
                    message = 'Stopping Trino clusters...';
                } else if (this.action.includes('restart_clusters')) {
                    message = 'Restarting Trino clusters... This may take a moment.';
                } else if (this.action.includes('run_query')) {
                    message = 'Executing query...';
                } else if (this.action.includes('run_benchmark')) {
                    message = 'Running benchmark... This may take several minutes.';
                }
            }
            
            // Get the submit button
            const submitButton = this.querySelector('button[type="submit"]');
            if (submitButton) {
                setButtonLoading(submitButton, true);
            }
            
            // Show loading overlay
            showLoading(message);
        });
    });
    
    // Add loading indicators for action buttons (non-form buttons)
    const actionButtons = document.querySelectorAll('a.btn, button.btn:not([type="submit"])');
    actionButtons.forEach(button => {
        // Skip buttons with data-no-loading attribute
        if (button.getAttribute('data-no-loading') === 'true') {
            return;
        }
        
        button.addEventListener('click', function(event) {
            // Skip if this is just a toggle button or has a specific role
            if (this.getAttribute('data-bs-toggle') || this.getAttribute('role')) {
                return;
            }
            
            // If this is a link to a different page, show loading
            if (this.tagName === 'A' && this.getAttribute('href') && !this.getAttribute('href').startsWith('#')) {
                // Check if the button has a data-loading-message attribute
                let message = this.getAttribute('data-loading-message');
                
                // If not, determine loading message based on the href
                if (!message) {
                    message = 'Loading...';
                    
                    if (this.href.includes('query_page')) {
                        message = 'Loading query interface...';
                    } else if (this.href.includes('history')) {
                        message = 'Loading query history...';
                    } else if (this.href.includes('benchmarks')) {
                        message = 'Loading benchmark playground...';
                    } else if (this.href.includes('version_compatibility')) {
                        message = 'Loading version compatibility information...';
                    } else if (this.href.includes('breaking_changes')) {
                        message = 'Loading breaking changes information...';
                    }
                }
                
                setButtonLoading(this, true);
                showLoading(message);
            }
        });
    });
});
