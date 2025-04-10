document.addEventListener('DOMContentLoaded', function() {
    // Initialize main variables
    let cy = null;
    let autoRefreshInterval = null;
    const AUTO_REFRESH_INTERVAL_MS = 5000;
    
    // Node colors based on node type
    const nodeColors = {
        'coordinator': '#ff9e00',
        'worker': '#00b9ff',
        'catalog': '#4caf50',
        'schema': '#9c27b0',
        'table': '#607d8b'
    };
    
    // Edge colors based on edge type
    const edgeColors = {
        'node-connection': '#888888',
        'catalog-connection': '#4caf50',
        'schema-connection': '#9c27b0',
        'table-connection': '#607d8b'
    };
    
    // Default style for Cytoscape
    const defaultStyle = [
        {
            selector: 'node',
            style: {
                'label': 'data(label)',
                'text-valign': 'center',
                'text-halign': 'center',
                'background-color': '#666',
                'color': '#fff',
                'font-size': '12px',
                'text-wrap': 'wrap',
                'text-max-width': '80px',
                'shape': 'ellipse',
                'width': '50px',
                'height': '50px',
                'border-width': '2px',
                'border-color': '#333'
            }
        },
        {
            selector: 'node[nodeType="coordinator"]',
            style: {
                'shape': 'hexagon',
                'background-color': nodeColors.coordinator,
                'width': '60px',
                'height': '60px',
                'border-color': '#b86e00'
            }
        },
        {
            selector: 'node[nodeType="worker"]',
            style: {
                'shape': 'round-rectangle',
                'background-color': nodeColors.worker,
                'width': '55px',
                'height': '55px',
                'border-color': '#007ab3'
            }
        },
        {
            selector: 'node[nodeType="catalog"]',
            style: {
                'shape': 'diamond',
                'background-color': nodeColors.catalog,
                'width': '50px',
                'height': '50px',
                'border-color': '#2e7c31'
            }
        },
        {
            selector: 'node[nodeType="schema"]',
            style: {
                'shape': 'round-triangle',
                'background-color': nodeColors.schema,
                'width': '45px',
                'height': '45px',
                'border-color': '#681b7a'
            }
        },
        {
            selector: 'node[nodeType="table"]',
            style: {
                'shape': 'rectangle',
                'background-color': nodeColors.table,
                'width': '40px',
                'height': '40px',
                'border-color': '#3b4a52'
            }
        },
        {
            selector: 'edge',
            style: {
                'width': 2,
                'line-color': '#888',
                'curve-style': 'bezier',
                'target-arrow-shape': 'triangle',
                'target-arrow-color': '#888',
                'arrow-scale': 0.8
            }
        },
        {
            selector: 'edge[edgeType="node-connection"]',
            style: {
                'line-color': edgeColors['node-connection'],
                'target-arrow-color': edgeColors['node-connection']
            }
        },
        {
            selector: 'edge[edgeType="catalog-connection"]',
            style: {
                'line-color': edgeColors['catalog-connection'],
                'target-arrow-color': edgeColors['catalog-connection']
            }
        },
        {
            selector: 'edge[edgeType="schema-connection"]',
            style: {
                'line-color': edgeColors['schema-connection'],
                'target-arrow-color': edgeColors['schema-connection']
            }
        },
        {
            selector: 'edge[edgeType="table-connection"]',
            style: {
                'line-color': edgeColors['table-connection'],
                'target-arrow-color': edgeColors['table-connection']
            }
        },
        {
            selector: 'node:selected',
            style: {
                'border-width': '3px',
                'border-color': '#fff',
                'border-opacity': 1
            }
        }
    ];
    
    // Initialize Cytoscape
    function initCytoscape() {
        cy = cytoscape({
            container: document.getElementById('cy'),
            style: defaultStyle,
            layout: {
                name: 'cose-bilkent',
                animate: true,
                randomize: true,
                nodeDimensionsIncludeLabels: true,
                idealEdgeLength: 100,
                nodeRepulsion: 5000,
                edgeElasticity: 0.45,
                nestingFactor: 0.1,
                gravity: 0.25,
                numIter: 2500,
                padding: 20,
                fit: true
            },
            elements: [],
            wheelSensitivity: 0.3
        });
        
        // Register panzoom extension
        cy.panzoom({
            zoomFactor: 0.1,
            zoomDelay: 45,
            minZoom: 0.1,
            maxZoom: 10,
            fitPadding: 50,
            panSpeed: 10,
            panDistance: 10,
            panDragAreaSize: 75,
            panMinPercentSpeed: 0.25,
            panInactiveArea: 8,
            panIndicatorMinOpacity: 0.5,
            zoomOnly: false,
            fitSelector: undefined,
            animateOnFit: function() {
                return false;
            },
            fitAnimationDuration: 200
        });
        
        // Handle node click to display info
        cy.on('tap', 'node', function(event) {
            const node = event.target;
            const nodeData = node.data();
            
            let infoHtml = '<table class="table table-sm table-dark">';
            
            // Basic info for all nodes
            infoHtml += `<tr><td>Type</td><td>${capitalizeFirstLetter(nodeData.nodeType)}</td></tr>`;
            infoHtml += `<tr><td>Name</td><td>${nodeData.label}</td></tr>`;
            
            // Node-type specific info
            if (nodeData.nodeType === 'coordinator') {
                infoHtml += `<tr><td>Version</td><td>${nodeData.version}</td></tr>`;
                infoHtml += `<tr><td>Port</td><td>${nodeData.port}</td></tr>`;
                infoHtml += `<tr><td>Status</td><td>${nodeData.status}</td></tr>`;
            } else if (nodeData.nodeType === 'worker') {
                infoHtml += `<tr><td>Version</td><td>${nodeData.version}</td></tr>`;
                infoHtml += `<tr><td>Status</td><td>${nodeData.status}</td></tr>`;
            } else if (nodeData.nodeType === 'catalog') {
                infoHtml += `<tr><td>Type</td><td>${nodeData.catalogType}</td></tr>`;
                infoHtml += `<tr><td>Host</td><td>${nodeData.properties.host}</td></tr>`;
                infoHtml += `<tr><td>Port</td><td>${nodeData.properties.port}</td></tr>`;
            } else if (nodeData.nodeType === 'schema') {
                infoHtml += `<tr><td>Catalog</td><td>${nodeData.catalog}</td></tr>`;
                infoHtml += `<tr><td>Tables</td><td>${nodeData.tableCount}</td></tr>`;
            } else if (nodeData.nodeType === 'table') {
                infoHtml += `<tr><td>Schema</td><td>${nodeData.schema}</td></tr>`;
                infoHtml += `<tr><td>Catalog</td><td>${nodeData.catalog}</td></tr>`;
                infoHtml += `<tr><td>Columns</td><td>${nodeData.columnCount}</td></tr>`;
            }
            
            infoHtml += '</table>';
            
            // Display the node info
            document.getElementById('node-info').innerHTML = infoHtml;
        });
        
        // Reset node info when background is clicked
        cy.on('tap', function(event) {
            if (event.target === cy) {
                document.getElementById('node-info').innerHTML = '<p class="text-muted">Select a node to view its details</p>';
            }
        });
    }
    
    // Function to apply a different layout
    function applyLayout(layoutName) {
        let layoutOptions = {
            name: layoutName,
            fit: true,
            animate: true,
            padding: 30,
            nodeDimensionsIncludeLabels: true
        };
        
        // Layout-specific options
        if (layoutName === 'cose') {
            layoutOptions = {
                ...layoutOptions,
                idealEdgeLength: 100,
                nodeOverlap: 20,
                nodeRepulsion: function(node) {
                    return 4500;
                },
                edgeElasticity: function(edge) {
                    return 100;
                },
                gravity: 80,
                numIter: 1000
            };
        } else if (layoutName === 'breadthfirst') {
            layoutOptions = {
                ...layoutOptions,
                directed: true,
                spacingFactor: 1.75
            };
        } else if (layoutName === 'concentric') {
            layoutOptions = {
                ...layoutOptions,
                concentric: function(node) {
                    if (node.data('nodeType') === 'coordinator') return 5;
                    if (node.data('nodeType') === 'worker') return 4;
                    if (node.data('nodeType') === 'catalog') return 3;
                    if (node.data('nodeType') === 'schema') return 2;
                    return 1;
                },
                levelWidth: function() {
                    return 1;
                },
                minNodeSpacing: 50
            };
        }
        
        cy.layout(layoutOptions).run();
    }
    
    // Function to fetch topology data
    function fetchTopologyData() {
        fetch('/api/topology')
            .then(response => response.json())
            .then(data => {
                // Check if we have an error
                if (data.error) {
                    console.error('Error fetching topology data:', data.error);
                    return;
                }
                
                // If cytoscape isn't initialized yet, do it now
                if (!cy) {
                    initCytoscape();
                }
                
                // Update the graph with new data
                cy.elements().remove();
                cy.add(data.elements);
                
                // Apply layout (use existing layout setting or default to cose-bilkent)
                const activeLayoutBtn = document.querySelector('.layout-btn.active');
                const layoutName = activeLayoutBtn ? activeLayoutBtn.dataset.layout : 'cose';
                applyLayout(layoutName);
                
                // Update cluster info
                updateClusterInfo(data.clusterInfo);
            })
            .catch(error => {
                console.error('Error:', error);
            });
    }
    
    // Function to update cluster information in the sidebar
    function updateClusterInfo(clusterInfo) {
        // Update Cluster 1 info
        const cluster1 = clusterInfo.cluster1;
        document.getElementById('cluster1-node-count').textContent = cluster1.nodeCount;
        
        if (cluster1.catalogs && cluster1.catalogs.length > 0) {
            document.getElementById('cluster1-catalogs').textContent = cluster1.catalogs.join(', ');
        } else {
            document.getElementById('cluster1-catalogs').textContent = 'None';
        }
        
        // Update Cluster 2 info
        const cluster2 = clusterInfo.cluster2;
        document.getElementById('cluster2-node-count').textContent = cluster2.nodeCount;
        
        if (cluster2.catalogs && cluster2.catalogs.length > 0) {
            document.getElementById('cluster2-catalogs').textContent = cluster2.catalogs.join(', ');
        } else {
            document.getElementById('cluster2-catalogs').textContent = 'None';
        }
    }
    
    // Helper function to capitalize first letter
    function capitalizeFirstLetter(string) {
        return string.charAt(0).toUpperCase() + string.slice(1);
    }
    
    // Set up event listeners
    
    // Layout buttons
    document.querySelectorAll('.layout-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            // Remove active class from all layout buttons
            document.querySelectorAll('.layout-btn').forEach(b => b.classList.remove('active'));
            // Add active class to clicked button
            this.classList.add('active');
            // Apply the selected layout
            applyLayout(this.dataset.layout);
        });
    });
    
    // Show Labels toggle
    document.getElementById('show-labels').addEventListener('change', function() {
        if (cy) {
            if (this.checked) {
                cy.style()
                    .selector('node')
                    .style({
                        'label': 'data(label)'
                    })
                    .update();
            } else {
                cy.style()
                    .selector('node')
                    .style({
                        'label': ''
                    })
                    .update();
            }
        }
    });
    
    // Auto Refresh toggle
    document.getElementById('auto-refresh').addEventListener('change', function() {
        if (this.checked) {
            // Start auto-refresh
            autoRefreshInterval = setInterval(fetchTopologyData, AUTO_REFRESH_INTERVAL_MS);
        } else {
            // Stop auto-refresh
            if (autoRefreshInterval) {
                clearInterval(autoRefreshInterval);
                autoRefreshInterval = null;
            }
        }
    });
    
    // Initial fetch of topology data
    fetchTopologyData();
    
    // Set the first layout button as active
    const firstLayoutBtn = document.querySelector('.layout-btn');
    if (firstLayoutBtn) {
        firstLayoutBtn.classList.add('active');
    }
});