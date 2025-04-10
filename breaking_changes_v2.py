from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import traceback
import logging
import requests
import re
import sys
from web_scraper import scrape_trino_release_page, get_all_changes_between_versions, version_compare, fetch_all_trino_versions

# Configure logging
logger = logging.getLogger(__name__)

# Import models if available
try:
    from models import db, TrinoVersion
except ImportError:
    logger.warning("Models not available, running in standalone mode")
    db = None
    TrinoVersion = None

def register_breaking_changes_routes(app):
    # Create a test function to fetch versions 
    @app.route('/test_fetch_versions')
    def test_fetch_versions():
        try:
            logger.info("TEST: Explicitly fetching all Trino versions")
            versions = fetch_all_trino_versions()
            logger.info(f"TEST: Successfully fetched {len(versions)} versions")
            logger.info(f"TEST: First 10 versions: {versions[:10]}")
            return jsonify({
                'success': True,
                'versions': versions
            })
        except Exception as e:
            logger.error(f"TEST: Error fetching versions: {str(e)}")
            logger.error(traceback.format_exc())
            return jsonify({
                'success': False,
                'error': str(e)
            })
    
    @app.route('/breaking_changes')
    def breaking_changes():
        """Page for displaying changes for all releases between two Trino versions"""
        # Get all available versions if database is configured
        versions = []
        if db and TrinoVersion:
            try:
                versions = TrinoVersion.query.order_by(TrinoVersion.version.desc()).all()
            except Exception as e:
                logger.error(f"Error querying versions: {str(e)}")
                
        # If no versions in database or database not configured, fetch all available versions from the Trino website
        if not versions:
            try:
                logger.info("Fetching all available Trino versions from official website")
                versions = fetch_all_trino_versions()
                logger.info(f"Successfully fetched {len(versions)} versions from Trino website")
                
                # Print the first 5 versions to debug
                logger.info(f"First 5 versions: {versions[:5] if len(versions) >= 5 else versions}")
                
                # If versions is empty, raise an exception to fall back to the default
                if not versions:
                    raise ValueError("No versions fetched from website")
                    
            except Exception as e:
                logger.error(f"Error fetching Trino versions: {str(e)}")
                logger.error(traceback.format_exc())
                # Fallback to default version range if fetch fails
                default_versions = range(400, 475)
                versions = [{"version": str(v)} for v in default_versions]
        
        # Create a new template file that directly injects the versions into JavaScript
        return create_breaking_changes_page(versions, app, '/compare_versions')
    
    @app.route('/compare_versions', methods=['POST'])
    def compare_versions():
        """API endpoint to compare changes between two Trino versions"""
        from_version = request.form.get('from_version')
        to_version = request.form.get('to_version')
        
        if not from_version or not to_version:
            return jsonify({
                'success': False,
                'message': 'Both from_version and to_version are required'
            })
        
        try:
            # Fetch all changes between versions
            changes = get_all_changes_between_versions(from_version, to_version)
            
            return jsonify({
                'success': True,
                'from_version': changes['from_version'],
                'to_version': changes['to_version'],
                'versions_checked': changes['versions_checked'],
                'total_versions': len(changes['versions_checked']),
                'connector_changes': changes['connector_changes'],
                'general_changes': changes['general_changes'],
                'processed_count': len(set([change.get('version') for change in changes['connector_changes'] + changes['general_changes']]))
            })
            
        except Exception as e:
            logger.error(f"Error comparing versions: {str(e)}")
            logger.error(traceback.format_exc())
            return jsonify({
                'success': False,
                'message': f"Error comparing versions: {str(e)}"
            })
    
    def get_all_changes_between_versions(from_version, to_version):
        """Get all changes between two Trino versions by scraping release docs for every version in the range"""
        # Ensure from is lower than to for correct ordering
        if from_version > to_version:
            from_version, to_version = to_version, from_version  # Swap
        
        logger.info(f"Fetching changes between Trino v{from_version} and v{to_version}")
        
        # Get a range of versions to check
        # Default range to check if we can't infer range
        versions_to_check = list(range(int(from_version), int(to_version) + 1))
        versions_to_check = [str(v) for v in versions_to_check]
        
        # Initialize result containers 
        connector_changes = []
        general_changes = []
        
        # Fetch changes for each version in range
        for version in versions_to_check:
            try:
                # Scrape the release notes page for this version
                logger.info(f"Scraping changes for version {version}")
                version_changes = fetch_trino_version_changes(version)
                
                # Add the changes to our results
                if version_changes:
                    if 'connector_changes' in version_changes:
                        connector_changes.extend(version_changes['connector_changes'])
                    if 'general_changes' in version_changes:
                        general_changes.extend(version_changes['general_changes'])
            except Exception as e:
                logger.error(f"Error fetching changes for version {version}: {str(e)}")
        
        # Return all changes
        return {
            'from_version': from_version,
            'to_version': to_version,
            'versions_checked': versions_to_check,
            'connector_changes': connector_changes,
            'general_changes': general_changes,
        }

def create_breaking_changes_page(versions, app, compare_endpoint):
    """Create a custom HTML page with versions directly injected into JavaScript"""
    # Get configured versions from application config
    config = app.config.get('CURRENT_CONFIG', {})
    
    # Set default comparison to be between the two configured clusters
    cluster1_version = config.get('cluster1', {}).get('version', '406')
    cluster2_version = config.get('cluster2', {}).get('version', '405')
    
    # Convert versions to JSON string to inject into JavaScript
    import json
    
    # Handle different types of version objects
    processed_versions = []
    for v in versions:
        if isinstance(v, dict) and "version" in v:
            # Web scraper produces dictionaries with version key
            processed_versions.append({
                "version": v["version"],
                "name": f"Release {v['version']}"
            })
        elif hasattr(v, 'version'):
            # Database model has a version attribute
            processed_versions.append({
                "version": v.version,
                "name": f"Release {v.version}" 
            })
        else:
            # Fallback for any other type
            version_str = str(v)
            processed_versions.append({
                "version": version_str,
                "name": f"Release {version_str}"
            })
    
    # Log the processed versions
    logger.info(f"Processed {len(processed_versions)} versions for JavaScript injection")
    if processed_versions:
        logger.info(f"First 5 processed versions: {processed_versions[:5]}")
    
    versions_json = json.dumps(processed_versions)
    
    # Create a new HTML page with versions embedded in JavaScript
    html_content = """
    {% extends "layout.html" %}
    
    {% block title %}Trino Version Changes Comparison{% endblock %}
    
    {% block scripts %}
    <script>
    // Debug output for available versions
    console.log("Direct version count: {{ versions_count }}");
    
    // Store versions in JavaScript variable
    const trino_versions = {{ versions_json|safe }};
    console.log("First 10 versions:", trino_versions.slice(0, 10).map(v => v.version));
    
    // Completely override the global loading functions to prevent any spinner from appearing
    window.showLoading = function() { 
        console.log("Loading function disabled"); 
        return false; 
    };
    window.hideLoading = function() { 
        console.log("Hide loading function disabled"); 
        return false; 
    };
    // Override the setButtonLoading function to prevent any button spinners
    window.setButtonLoading = function() {
        console.log("Button loading disabled");
        return false;
    };
    
    // Remove any existing spinner elements
    $(document).ready(function() {
        // Populate version dropdowns from JavaScript
        populateVersionDropdowns();
        
        // Immediately remove all spinner elements
        $('.spinner-overlay').hide();
        $('.spinner-container').hide();
        $('.spinner-overlay').remove();
        $('.spinner-container').remove();
        
        // Add custom CSS to hide any spinner that might be dynamically added
        $('<style>')
            .prop('type', 'text/css')
            .html(`
                .spinner-overlay, .spinner-container { 
                    display: none !important; 
                    visibility: hidden !important;
                    opacity: 0 !important;
                    z-index: -1000 !important;
                }
            `)
            .appendTo('head');
            
        // Force remove on any form submission
        $('form').on('submit', function() {
            $('.spinner-overlay').remove();
            $('.spinner-container').remove();
            return true;
        });
    });
    
    // Function to populate version dropdowns
    function populateVersionDropdowns() {
        const fromVersionSelect = document.getElementById('from_version');
        const toVersionSelect = document.getElementById('to_version');
        
        // Clear existing options
        fromVersionSelect.innerHTML = '';
        toVersionSelect.innerHTML = '';
        
        // Add options for each version
        trino_versions.forEach(version => {
            const fromOption = document.createElement('option');
            fromOption.value = version.version;
            fromOption.textContent = version.version;
            if (version.version === '{{ cluster1_version }}') {
                fromOption.selected = true;
            }
            
            const toOption = document.createElement('option');
            toOption.value = version.version;
            toOption.textContent = version.version;
            if (version.version === '{{ cluster2_version }}') {
                toOption.selected = true;
            }
            
            fromVersionSelect.appendChild(fromOption);
            toVersionSelect.appendChild(toOption);
        });
    }
    </script>
    {% endblock %}
    
    {% block header_css %}
    <style>
        /* Override any spinning behavior for our button */
        #compare-versions-btn.btn-loading:before {
            display: none !important;
        }
        
        #compare-versions-btn {
            /* Ensure our custom styles always take precedence */
            position: relative !important;
            padding-left: 1rem !important;
            padding-right: 1rem !important;
        }
        
        /* Prevent any global button styling from affecting our button */
        #compare-versions-btn:after,
        #compare-versions-btn:before {
            display: none !important;
        }
        
        .version-select-container {
            max-width: 800px;
            margin: 0 auto;
        }
        #results-content {
            margin-top: 30px;
        }
        .change-item p {
            white-space: pre-wrap;
        }
        .code {
            font-family: monospace;
            background-color: #f5f5f5;
            padding: 2px 4px;
            border-radius: 3px;
        }
    </style>
    {% endblock %}
    
    {% block header_scripts %}
    <!-- Font Awesome for icons -->
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.4/css/all.min.css">
    {% endblock %}
    
    {% block content %}
    <div class="container-fluid py-4">
        <div class="row">
            <div class="col-12">
                <div class="card shadow">
                    <div class="card-header bg-primary text-white">
                        <h5 class="card-title mb-0">
                            <i class="fas fa-exchange-alt me-2"></i>
                            Trino Version Changes Comparison
                        </h5>
                    </div>
                    <div class="card-body">
                        <div class="version-select-container">
                            <form id="version-comparison-form" action="{{ compare_endpoint }}" method="post">
                                <div class="alert alert-info mb-4">
                                    <i class="fas fa-info-circle me-2"></i>
                                    Compare changes between two Trino versions to see what's new, changed, or removed.
                                </div>
                                
                                <div class="row g-3 align-items-center">
                                    <div class="col-5">
                                        <div class="form-group">
                                            <label for="from_version" class="form-label">From Version</label>
                                            <select class="form-select" id="from_version" name="from_version" required>
                                                <!-- Options will be populated by JavaScript -->
                                            </select>
                                        </div>
                                    </div>
                                    <div class="col-2 text-center" style="padding-top: 30px;">
                                        <i class="fas fa-arrow-right fa-2x"></i>
                                    </div>
                                    <div class="col-5">
                                        <div class="form-group">
                                            <label for="to_version" class="form-label">To Version</label>
                                            <select class="form-select" id="to_version" name="to_version" required>
                                                <!-- Options will be populated by JavaScript -->
                                            </select>
                                        </div>
                                    </div>
                                </div>
                                
                                <div class="d-grid mt-3">
                                    <button type="submit" class="btn btn-primary" id="compare-versions-btn">
                                        <i class="fas fa-sync-alt me-2"></i>
                                        Compare Versions
                                    </button>
                                </div>
                            </form>
                        </div>
                        
                        <div class="alert alert-info mt-4" id="version-range-info" style="display: none;">
                            <i class="fas fa-info-circle me-2"></i>
                            Showing changes for versions <span id="version-range-text"></span>
                        </div>
                        
                        <div id="comparison-results" class="mt-4">                    
                        <div id="results-content" style="display: none;">
                            <ul class="nav nav-tabs" id="resultTabs" role="tablist">
                                <li class="nav-item" role="presentation">
                                    <button class="nav-link active" id="connector-tab" data-bs-toggle="tab" data-bs-target="#connector" type="button" role="tab" aria-controls="connector" aria-selected="true">
                                        <i class="fas fa-plug me-1"></i> Connector Changes <span id="connector-count" class="badge bg-primary ms-1">0</span>
                                    </button>
                                </li>
                                <li class="nav-item" role="presentation">
                                    <button class="nav-link" id="general-tab" data-bs-toggle="tab" data-bs-target="#general" type="button" role="tab" aria-controls="general" aria-selected="false">
                                        <i class="fas fa-cogs me-1"></i> General Changes <span id="general-count" class="badge bg-secondary ms-1">0</span>
                                    </button>
                                </li>
                            </ul>
                            
                            <div class="tab-content p-3 border border-top-0 rounded-bottom" id="resultTabsContent">
                                <!-- Connector Changes Tab -->
                                <div class="tab-pane fade show active" id="connector" role="tabpanel" aria-labelledby="connector-tab">
                                    <div class="d-flex justify-content-between mb-3">
                                        <div>
                                            <div class="input-group">
                                                <span class="input-group-text"><i class="fas fa-search"></i></span>
                                                <input type="text" id="connector-search" class="form-control" placeholder="Search connector changes...">
                                            </div>
                                        </div>
                                        <div>
                                            <button id="connector-expand-all" class="btn btn-sm btn-outline-primary me-2">
                                                <i class="fas fa-expand-alt me-1"></i> Expand All
                                            </button>
                                            <button id="connector-collapse-all" class="btn btn-sm btn-outline-secondary">
                                                <i class="fas fa-compress-alt me-1"></i> Collapse All
                                            </button>
                                        </div>
                                    </div>
                                    
                                    <div class="alert alert-info mb-3" id="no-connector-changes" style="display: none;">
                                        <i class="fas fa-info-circle me-2"></i> No connector changes found between these versions.
                                    </div>
                                    
                                    <div id="connector-changes-list" class="accordion"></div>
                                </div>
                                
                                <!-- General Changes Tab -->
                                <div class="tab-pane fade" id="general" role="tabpanel" aria-labelledby="general-tab">
                                    <div class="d-flex justify-content-between mb-3">
                                        <div>
                                            <div class="input-group">
                                                <span class="input-group-text"><i class="fas fa-search"></i></span>
                                                <input type="text" id="general-search" class="form-control" placeholder="Search general changes...">
                                            </div>
                                        </div>
                                        <div>
                                            <button id="general-expand-all" class="btn btn-sm btn-outline-primary me-2">
                                                <i class="fas fa-expand-alt me-1"></i> Expand All
                                            </button>
                                            <button id="general-collapse-all" class="btn btn-sm btn-outline-secondary">
                                                <i class="fas fa-compress-alt me-1"></i> Collapse All
                                            </button>
                                        </div>
                                    </div>
                                    
                                    <div class="alert alert-info mb-3" id="no-general-changes" style="display: none;">
                                        <i class="fas fa-info-circle me-2"></i> No general changes found between these versions.
                                    </div>
                                    
                                    <div id="general-changes-list" class="accordion"></div>
                                </div>
                            </div>
                        </div>
                        
                        <div id="error-message" class="alert alert-danger mt-3" style="display: none;">
                            <i class="fas fa-exclamation-circle me-2"></i> <span id="error-text"></span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    {% endblock %}
    
    {% block custom_scripts %}
    <script>
    $(document).ready(function() {
        // Handle form submission - completely rebuilt without any loading overlay
        $('#version-comparison-form').on('submit', function(e) {
            e.preventDefault();
            
            // Make doubly sure no spinner appears
            $('.spinner-overlay').remove();
            $('.spinner-container').remove();
            
            // Get the submit button directly by ID to avoid any global button handling
            const compareButton = $('#compare-versions-btn');
            
            // Just disable without changing the content
            compareButton.prop('disabled', true);
            // Ensure button is NEVER in loading state
            compareButton.removeClass('btn-loading');
            
            // Hide content areas
            $('#results-content').hide();
            $('#error-message').hide();
            $('#version-range-info').hide();
            
            // Show loading message directly in the UI (not a modal)
            $('#comparison-results').prepend('<div id="inline-loading" class="alert alert-info"><i class="fas fa-sync fa-spin me-2"></i> Loading comparison results...</div>');
            
            // Get selected versions
            const fromVersion = $('#from_version').val();
            const toVersion = $('#to_version').val();
            
            console.log("Form submitted with versions:", fromVersion, "to", toVersion);
            
            // Submit form via AJAX
            $.ajax({
                url: $(this).attr('action'),
                type: 'POST',
                data: $(this).serialize(),
                dataType: 'json',
                success: function(response) {
                    // Auto-submit it
                    console.log("Auto-submitting form...");
                    $('#version-comparison-form').trigger('submit');
                    
                    // Debug info
                    console.log("Response received:", response);
                    
                    // Remove the inline loading message
                    $('#inline-loading').remove();
                    
                    // Restore the submit button to its original state
                    compareButton.html('<i class="fas fa-sync-alt me-2"></i>Compare Versions');
                    compareButton.prop('disabled', false);
                    compareButton.removeClass('btn-loading');
                    
                    if (!response.success) {
                        $('#error-text').text(response.message || 'An error occurred while comparing versions.');
                        $('#error-message').show();
                        return;
                    }
                    
                    // Show success info
                    console.log("Successfully received data:");
                    console.log("- Connector changes:", response.connector_changes ? response.connector_changes.length : 0);
                    console.log("- General changes:", response.general_changes ? response.general_changes.length : 0);
                    
                    // Update version range info with details
                    $('#version-range-text').html(`${response.from_version} to ${response.to_version}`);
                    $('#version-range-info').show();
                    
                    // Reset counters and clear content
                    $('#connector-count').text('0');
                    $('#general-count').text('0');
                    $('#connector-changes-list').empty();
                    $('#general-changes-list').empty();
                    
                    // PROCESS CONNECTOR CHANGES
                    if (response.connector_changes && response.connector_changes.length > 0) {
                        console.log("Processing connector changes:", response.connector_changes.length);
                        $('#connector-count').text(response.connector_changes.length);
                        $('#no-connector-changes').hide();
                        
                        // Group changes by connector category
                        const connectorGroups = {};
                        for (let i = 0; i < response.connector_changes.length; i++) {
                            const change = response.connector_changes[i];
                            if (!connectorGroups[change.category]) {
                                connectorGroups[change.category] = [];
                            }
                            connectorGroups[change.category].push(change);
                        }
                        
                        console.log("Connector groups:", Object.keys(connectorGroups));
                        
                        // Render connector changes by group
                        let accordionIndex = 0;
                        for (const category in connectorGroups) {
                            const changes = connectorGroups[category];
                            const categoryName = category.replace('#', '').trim();
                            const categoryTitle = categoryName.charAt(0).toUpperCase() + categoryName.slice(1);
                            
                            // Create accordion group for this connector
                            const accordionItem = $('<div class="accordion-item"></div>');
                            const headerId = `connector-heading-${accordionIndex}`;
                            const collapseId = `connector-collapse-${accordionIndex}`;
                            
                            // Create header
                            const header = $(`
                                <h2 class="accordion-header" id="${headerId}">
                                    <button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" 
                                            data-bs-target="#${collapseId}" aria-expanded="false" aria-controls="${collapseId}">
                                        <strong>${categoryTitle}</strong> <span class="badge bg-primary ms-2">${changes.length}</span>
                                    </button>
                                </h2>
                            `);
                            
                            // Create body
                            const body = $(`
                                <div id="${collapseId}" class="accordion-collapse collapse" aria-labelledby="${headerId}" data-bs-parent="#connector-changes-list">
                                    <div class="accordion-body">
                                    </div>
                                </div>
                            `);
                            
                            // Add changes to body
                            const bodyContent = body.find('.accordion-body');
                            for (let j = 0; j < changes.length; j++) {
                                const change = changes[j];
                                const changeItem = $(`
                                    <div class="change-item mb-3" data-version="${change.version}">
                                        <div class="d-flex align-items-start">
                                            <div class="flex-grow-1">
                                                <div class="mb-1">
                                                    <span class="badge bg-info">v${change.version}</span>
                                                </div>
                                                <p>${change.text}</p>
                                            </div>
                                        </div>
                                    </div>
                                `);
                                
                                bodyContent.append(changeItem);
                                if (j < changes.length - 1) {
                                    bodyContent.append('<hr>');
                                }
                            }
                            
                            accordionItem.append(header);
                            accordionItem.append(body);
                            $('#connector-changes-list').append(accordionItem);
                            
                            accordionIndex++;
                        }
                    } else {
                        $('#no-connector-changes').show();
                    }
                    
                    // PROCESS GENERAL CHANGES
                    if (response.general_changes && response.general_changes.length > 0) {
                        console.log("Processing general changes:", response.general_changes.length);
                        $('#general-count').text(response.general_changes.length);
                        $('#no-general-changes').hide();
                        
                        // Group changes by category
                        const generalGroups = {};
                        for (let i = 0; i < response.general_changes.length; i++) {
                            const change = response.general_changes[i];
                            if (!generalGroups[change.category]) {
                                generalGroups[change.category] = [];
                            }
                            generalGroups[change.category].push(change);
                        }
                        
                        // Render general changes by group
                        let accordionIndex = 0;
                        for (const category in generalGroups) {
                            const changes = generalGroups[category];
                            const categoryName = category.replace('#', '').trim();
                            const categoryTitle = categoryName.charAt(0).toUpperCase() + categoryName.slice(1);
                            
                            // Create accordion group for this category
                            const accordionItem = $('<div class="accordion-item"></div>');
                            const headerId = `general-heading-${accordionIndex}`;
                            const collapseId = `general-collapse-${accordionIndex}`;
                            
                            // Create header
                            const header = $(`
                                <h2 class="accordion-header" id="${headerId}">
                                    <button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" 
                                            data-bs-target="#${collapseId}" aria-expanded="false" aria-controls="${collapseId}">
                                        <strong>${categoryTitle}</strong> <span class="badge bg-primary ms-2">${changes.length}</span>
                                    </button>
                                </h2>
                            `);
                            
                            // Create body
                            const body = $(`
                                <div id="${collapseId}" class="accordion-collapse collapse" aria-labelledby="${headerId}" data-bs-parent="#general-changes-list">
                                    <div class="accordion-body">
                                    </div>
                                </div>
                            `);
                            
                            // Add changes to body
                            const bodyContent = body.find('.accordion-body');
                            for (let j = 0; j < changes.length; j++) {
                                const change = changes[j];
                                const changeItem = $(`
                                    <div class="change-item mb-3" data-version="${change.version}">
                                        <div class="d-flex align-items-start">
                                            <div class="flex-grow-1">
                                                <div class="mb-1">
                                                    <span class="badge bg-info">v${change.version}</span>
                                                </div>
                                                <p>${change.text}</p>
                                            </div>
                                        </div>
                                    </div>
                                `);
                                
                                bodyContent.append(changeItem);
                                if (j < changes.length - 1) {
                                    bodyContent.append('<hr>');
                                }
                            }
                            
                            accordionItem.append(header);
                            accordionItem.append(body);
                            $('#general-changes-list').append(accordionItem);
                            
                            accordionIndex++;
                        }
                    } else {
                        $('#no-general-changes').show();
                    }
                    
                    // Show the results container
                    $('#results-content').show();
                },
                error: function(xhr, status, error) {
                    // Remove the inline loading message
                    $('#inline-loading').remove();
                    
                    // Restore the submit button to its original state
                    compareButton.html('<i class="fas fa-sync-alt me-2"></i>Compare Versions');
                    compareButton.prop('disabled', false);
                    compareButton.removeClass('btn-loading');
                    
                    // Display error message
                    $('#error-text').text(`Error: ${error || 'An unknown error occurred.'}`);
                    $('#error-message').show();
                }
            });
        });
        
        // Connector search functionality
        $('#connector-search').on('keyup', function() {
            const searchTerm = $(this).val().toLowerCase();
            $('#connector-changes-list .change-item').each(function() {
                const text = $(this).text().toLowerCase();
                if (text.includes(searchTerm)) {
                    $(this).show();
                    $(this).prev('hr').show();
                    $(this).next('hr').show();
                } else {
                    $(this).hide();
                    $(this).prev('hr').hide();
                    $(this).next('hr').hide();
                }
            });
        });
        
        // General search functionality
        $('#general-search').on('keyup', function() {
            const searchTerm = $(this).val().toLowerCase();
            $('#general-changes-list .change-item').each(function() {
                const text = $(this).text().toLowerCase();
                if (text.includes(searchTerm)) {
                    $(this).show();
                    $(this).prev('hr').show();
                    $(this).next('hr').show();
                } else {
                    $(this).hide();
                    $(this).prev('hr').hide();
                    $(this).next('hr').hide();
                }
            });
        });
        
        // Expand/Collapse All for connector changes
        $('#connector-expand-all').on('click', function() {
            $('#connector-changes-list .accordion-button.collapsed').click();
        });
        
        $('#connector-collapse-all').on('click', function() {
            $('#connector-changes-list .accordion-button:not(.collapsed)').click();
        });
        
        // Expand/Collapse All for general changes
        $('#general-expand-all').on('click', function() {
            $('#general-changes-list .accordion-button.collapsed').click();
        });
        
        $('#general-collapse-all').on('click', function() {
            $('#general-changes-list .accordion-button:not(.collapsed)').click();
        });
    });
    </script>
    {% endblock %}
    """
    
    # Render the template string with parameters
    from flask import render_template_string
    return render_template_string(
        html_content,
        versions_count=len(versions),
        versions_json=versions_json,
        cluster1_version=cluster1_version,
        cluster2_version=cluster2_version,
        url_for=app.jinja_env.globals['url_for']
    )


    # Fixed endpoint route
    @app.route('/compare_versions_v2', methods=['POST'])
    def compare_versions_v2():
        """API endpoint to compare changes between two Trino versions"""
        from_version = request.form.get('from_version')
        to_version = request.form.get('to_version')
        
        if not from_version or not to_version:
            return jsonify({
                'success': False,
                'message': 'Both from_version and to_version are required'
            })
        
        try:
            # Fetch all changes between versions
            changes = get_all_changes_between_versions(from_version, to_version)
            
            return jsonify({
                'success': True,
                'from_version': changes['from_version'],
                'to_version': changes['to_version'],
                'versions_checked': changes['versions_checked'],
                'total_versions': len(changes['versions_checked']),
                'connector_changes': changes['connector_changes'],
                'general_changes': changes['general_changes'],
                'processed_count': len(set([change.get('version') for change in changes['connector_changes'] + changes['general_changes']]))
            })
            
        except Exception as e:
            logger.error(f"Error comparing versions: {str(e)}")
            logger.error(traceback.format_exc())
            return jsonify({
                'success': False,
                'message': f"Error comparing versions: {str(e)}"
            })