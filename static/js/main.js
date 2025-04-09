// Main JavaScript file for Trino Comparison Tool

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
});
