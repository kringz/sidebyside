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

// Function to handle image pull progress updates
function setupImagePullTracking() {
    // Track active pulls
    const activePulls = new Set();
    
    // Create or update a progress bar for a specific version
    function createOrUpdateProgressBar(version, progress, bytesDownloaded, totalBytes, isDemoMode) {
        const progressBarsContainer = document.getElementById('imagePullProgressBars');
        if (!progressBarsContainer) {
            console.error('Progress bars container not found!');
            return;
        }
        
        let progressBarContainer = document.getElementById(`progress-${version}`);
        
        // Format display text to show MB downloaded
        let displayText;
        if (bytesDownloaded !== undefined && totalBytes !== undefined && 
            bytesDownloaded !== null && totalBytes !== null && totalBytes > 0) {
            const downloadedMB = (bytesDownloaded / (1024 * 1024)).toFixed(1);
            const totalMB = (totalBytes / (1024 * 1024)).toFixed(1);
            
            // If in demo mode, make it clear this is simulated
            if (isDemoMode) {
                displayText = `${Math.floor(progress * 100)}% (${downloadedMB} MB / ${totalMB} MB) - SIMULATION`;
            } else {
                displayText = `${Math.floor(progress * 100)}% (${downloadedMB} MB / ${totalMB} MB)`;
            }
            console.log(`Progress bar text for ${version}: ${displayText}`);
        } else {
            displayText = `${Math.floor(progress * 100)}%`;
            if (isDemoMode) {
                displayText += ' - SIMULATION';
            }
        }
        
        if (!progressBarContainer) {
            // Create new progress bar if it doesn't exist
            progressBarContainer = document.createElement('div');
            progressBarContainer.id = `progress-${version}`;
            progressBarContainer.className = 'mb-3';
            
            const label = document.createElement('div');
            label.className = 'mb-1';
            label.innerHTML = `<strong>Trino ${version}:</strong> <span class="progress-percent">${displayText}</span>`;
            
            const progressBarWrapper = document.createElement('div');
            progressBarWrapper.className = 'progress';
            
            const progressBar = document.createElement('div');
            progressBar.className = 'progress-bar progress-bar-striped progress-bar-animated';
            progressBar.role = 'progressbar';
            progressBar.style.width = '0%';
            progressBar.setAttribute('aria-valuenow', '0');
            progressBar.setAttribute('aria-valuemin', '0');
            progressBar.setAttribute('aria-valuemax', '100');
            
            progressBarWrapper.appendChild(progressBar);
            progressBarContainer.appendChild(label);
            progressBarContainer.appendChild(progressBarWrapper);
            progressBarsContainer.appendChild(progressBarContainer);
        }
        
        // Update progress bar
        const progressBar = progressBarContainer.querySelector('.progress-bar');
        const percentText = progressBarContainer.querySelector('.progress-percent');
        const percentValue = Math.floor(progress * 100);
        
        progressBar.style.width = `${percentValue}%`;
        progressBar.setAttribute('aria-valuenow', percentValue);
        percentText.textContent = displayText;
        
        // If progress is complete, mark it as success after a delay
        if (progress >= 1) {
            setTimeout(() => {
                progressBar.classList.remove('progress-bar-animated');
                progressBar.classList.add('bg-success');
                activePulls.delete(version);
                
                // If no more active pulls, hide the progress section after a delay
                if (activePulls.size === 0) {
                    setTimeout(() => {
                        document.getElementById('imagePullProgress').classList.add('d-none');
                    }, 2000);
                }
            }, 500);
        }
    }
    
    // Function to handle image pull requests
    function pullTrinoImage(version = null) {
        // Show the progress section
        document.getElementById('imagePullProgress').classList.remove('d-none');
        
        // Create form data
        const formData = new FormData();
        if (version) {
            formData.append('version', version);
            activePulls.add(version);
            createOrUpdateProgressBar(version, 0);
        } else {
            // If pulling all images, get the configured versions
            const cluster1Version = document.querySelector('[data-version]')?.getAttribute('data-version');
            const cluster2Version = document.querySelectorAll('[data-version]')[1]?.getAttribute('data-version');
            
            if (cluster1Version) {
                activePulls.add(cluster1Version);
                createOrUpdateProgressBar(cluster1Version, 0);
            }
            if (cluster2Version && cluster2Version !== cluster1Version) {
                activePulls.add(cluster2Version);
                createOrUpdateProgressBar(cluster2Version, 0);
            }
        }
        
        // Post to the server
        fetch('/pull_trino_images', {
            method: 'POST',
            body: formData,
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // Success - progress is already tracked by the progress bars
                console.log('Pull request successful:', data.message);
                
                // Check if this is demo mode
                if (data.demo) {
                    // Update the UI to clearly show this is a simulation
                    const progressHeader = document.querySelector('#imagePullProgress .card-header h5');
                    if (progressHeader) {
                        progressHeader.innerHTML = '<i class="fas fa-info-circle me-2"></i> DEMO MODE - No actual downloads';
                        progressHeader.classList.add('text-warning');
                    }
                    
                    // Add demo mode indicator to progress bars
                    const progressBars = document.querySelectorAll('#imagePullProgressBars .mb-3');
                    progressBars.forEach(bar => {
                        const label = bar.querySelector('.mb-1');
                        if (label) {
                            label.innerHTML += ' <span class="badge bg-warning">DEMO</span>';
                        }
                    });
                    
                    console.log('Running in DEMO mode - this is a simulation');
                }
                
                // Start polling for progress updates
                startProgressPolling();
            } else {
                // Error - show alert
                console.error('Pull request failed:', data.message);
                alert(`Error: ${data.message}`);
                
                // Hide progress for failed versions
                if (version) {
                    const progressBar = document.getElementById(`progress-${version}`);
                    if (progressBar) {
                        progressBar.querySelector('.progress-bar').classList.remove('progress-bar-animated');
                        progressBar.querySelector('.progress-bar').classList.add('bg-danger');
                        activePulls.delete(version);
                    }
                }
            }
            
            // Update progress based on data from response
            if (data.progress_details) {
                // Use detailed progress information if available
                Object.entries(data.progress_details).forEach(([version, detail]) => {
                    createOrUpdateProgressBar(
                        version,
                        detail.progress,
                        detail.current_bytes,
                        detail.total_bytes,
                        detail.demo
                    );
                });
            } else if (data.progress) {
                // Fallback to simple progress
                Object.entries(data.progress).forEach(([version, progress]) => {
                    createOrUpdateProgressBar(version, progress);
                });
            }
        })
        .catch(error => {
            console.error('Error pulling Trino images:', error);
            alert('An error occurred while pulling Trino images. Please check the console for details.');
        });
    }
    
    // Polling function to check image pull progress
    let pollInterval = null;
    function startProgressPolling() {
        // Clear any existing interval
        if (pollInterval) {
            clearInterval(pollInterval);
        }
        
        console.log("Starting progress polling for versions:", Array.from(activePulls));
        
        // Make sure the progress container exists and is visible
        if (!document.getElementById('imagePullProgress')) {
            console.log('Creating progress container');
            
            // Create container if missing
            const progressContainer = document.createElement('div');
            progressContainer.id = 'imagePullProgress';
            progressContainer.className = 'row mb-3';
            
            const colDiv = document.createElement('div');
            colDiv.className = 'col-12';
            
            const cardDiv = document.createElement('div');
            cardDiv.className = 'card';
            
            const cardHeader = document.createElement('div');
            cardHeader.className = 'card-header';
            cardHeader.innerHTML = '<h5 class="mb-0"><i class="fas fa-spinner fa-spin me-2"></i> Pulling Trino Images</h5>';
            
            const cardBody = document.createElement('div');
            cardBody.className = 'card-body';
            
            const progressBars = document.createElement('div');
            progressBars.id = 'imagePullProgressBars';
            
            // Assemble the structure
            cardBody.appendChild(progressBars);
            cardDiv.appendChild(cardHeader);
            cardDiv.appendChild(cardBody);
            colDiv.appendChild(cardDiv);
            progressContainer.appendChild(colDiv);
            
            // Insert into the page
            document.body.appendChild(progressContainer);
            
            // Try to move it to a better position if possible
            setTimeout(() => {
                const imageSection = document.querySelector('.card-body.border-top');
                if (imageSection && imageSection.parentNode) {
                    imageSection.parentNode.insertBefore(progressContainer, imageSection.nextSibling);
                }
            }, 100);
        }
        
        // Ensure progress element is visible
        document.getElementById('imagePullProgress').classList.remove('d-none');
        
        // Set up new polling interval (every 1 second)
        pollInterval = setInterval(() => {
            // If no active pulls, stop polling
            if (activePulls.size === 0) {
                console.log("No active pulls, stopping polling");
                clearInterval(pollInterval);
                return;
            }
            
            // Fetch the current progress
            fetch('/check_pull_progress')
                .then(response => response.json())
                .then(data => {
                    console.log("Received progress data:", data);
                    
                    // Update progress bars with the latest data
                    if (data.progress) {
                        let allComplete = true;
                        
                        if (data.progress_details) {
                            // Use detailed progress information including bytes
                            Object.entries(data.progress_details).forEach(([version, detail]) => {
                                // Log detailed progress information
                                console.log(`Progress for ${version}: ${detail.progress * 100}% (${Math.round(detail.current_bytes / (1024 * 1024))} MB / ${Math.round(detail.total_bytes / (1024 * 1024))} MB)`);
                                
                                if (activePulls.has(version)) {
                                    // Ensure progress element is visible
                                    const progressContainer = document.getElementById('imagePullProgress');
                                    if (progressContainer) {
                                        progressContainer.classList.remove('d-none');
                                    }
                                    
                                    // Update the progress bar with byte information
                                    createOrUpdateProgressBar(
                                        version, 
                                        detail.progress, 
                                        detail.current_bytes, 
                                        detail.total_bytes,
                                        detail.demo
                                    );
                                    
                                    // Check if this pull is still in progress
                                    if (detail.progress < 1) {
                                        allComplete = false;
                                    }
                                }
                            });
                        } else {
                            // Fallback to simple progress information
                            Object.entries(data.progress).forEach(([version, progress]) => {
                                console.log(`Progress for ${version}: ${progress * 100}%`);
                                
                                if (activePulls.has(version)) {
                                    // Ensure progress element is visible
                                    document.getElementById('imagePullProgress').classList.remove('d-none');
                                    
                                    // Update the progress bar
                                    createOrUpdateProgressBar(version, progress);
                                    
                                    // Check if this pull is still in progress
                                    if (progress < 1) {
                                        allComplete = false;
                                    }
                                }
                            });
                        }
                        
                        // If all pulls are complete, stop polling
                        if (allComplete && activePulls.size > 0) {
                            console.log("All pulls complete, stopping polling");
                            clearInterval(pollInterval);
                            
                            // Refresh the page after a delay to show the new images
                            setTimeout(() => {
                                console.log("Refreshing page to show new images");
                                window.location.reload();
                            }, 3000);
                        }
                    } else {
                        console.log("No progress data received");
                    }
                })
                .catch(error => {
                    console.error('Error checking pull progress:', error);
                    clearInterval(pollInterval);
                });
        }, 1000);
    }
    
    // Setup event listeners for pull buttons
    const pullAllImagesBtn = document.getElementById('pullAllImagesBtn');
    if (pullAllImagesBtn) {
        pullAllImagesBtn.addEventListener('click', function() {
            pullTrinoImage();
        });
    }
    
    const pullVersionBtns = document.querySelectorAll('.pull-version-btn');
    pullVersionBtns.forEach(btn => {
        btn.addEventListener('click', function() {
            const version = this.getAttribute('data-version');
            pullTrinoImage(version);
        });
    });
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
    
    // Set up image pull tracking functionality
    setupImagePullTracking();
    
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
