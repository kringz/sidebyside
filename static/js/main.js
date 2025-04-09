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
    
    // Toggle catalog configuration sections based on checkbox state
    const catalogCheckboxes = document.querySelectorAll('.form-check-input[type="checkbox"]');
    catalogCheckboxes.forEach(checkbox => {
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
