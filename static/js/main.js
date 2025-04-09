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
    
    // Synchronize catalog checkboxes between forms to prevent issues with multiple forms
    const catalogForm = document.getElementById('catalogForm');
    
    if (catalogForm) {
        catalogForm.addEventListener('submit', function(event) {
            event.preventDefault();
            
            // Create a FormData object from the catalog form
            const formData = new FormData(this);
            
            // Submit via AJAX to avoid page reload
            fetch(this.action, {
                method: 'POST',
                body: formData,
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            })
            .then(response => response.json())
            .then(data => {
                // Show success message
                const alertContainer = document.createElement('div');
                alertContainer.className = 'alert alert-success alert-dismissible fade show';
                alertContainer.role = 'alert';
                alertContainer.innerHTML = `
                    Catalog configuration saved successfully!
                    <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
                `;
                
                // Insert at the top of the main content
                const mainContent = document.querySelector('.container');
                mainContent.insertBefore(alertContainer, mainContent.firstChild);
                
                // Auto close after 5 seconds
                setTimeout(() => {
                    const closeButton = alertContainer.querySelector('.btn-close');
                    if (closeButton) {
                        closeButton.click();
                    }
                }, 5000);
            })
            .catch(error => {
                console.error('Error:', error);
                // Show error message
                const alertContainer = document.createElement('div');
                alertContainer.className = 'alert alert-danger alert-dismissible fade show';
                alertContainer.role = 'alert';
                alertContainer.innerHTML = `
                    Error saving catalog configuration.
                    <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
                `;
                
                // Insert at the top of the main content
                const mainContent = document.querySelector('.container');
                mainContent.insertBefore(alertContainer, mainContent.firstChild);
            });
        });
    }
    
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
