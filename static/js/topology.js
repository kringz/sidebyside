document.addEventListener('DOMContentLoaded', function() {
    // Initialize Cytoscape instance
    const cy = cytoscape({
        container: document.getElementById('topology-container'),
        style: [
            {
                selector: 'node',
                style: {
                    'background-color': '#666',
                    'label': 'data(label)',
                    'color': '#fff',
                    'text-outline-color': '#222',
                    'text-outline-width': 1,
                    'font-size': 12,
                    'text-valign': 'center',
                    'text-halign': 'center',
                    'text-max-width': '80px',
                    'text-wrap': 'ellipsis'
                }
            },
            {
                selector: 'node[nodeType="coordinator"]',
                style: {
                    'background-color': '#4299e1',
                    'shape': 'rectangle',
                    'width': 50,
                    'height': 50
                }
            },
            {
                selector: 'node[nodeType="worker"]',
                style: {
                    'background-color': '#48bb78',
                    'shape': 'rectangle',
                    'width': 40,
                    'height': 40
                }
            },
            {
                selector: 'node[nodeType="catalog"]',
                style: {
                    'background-color': '#805ad5',
                    'shape': 'round-rectangle',
                    'width': 80,
                    'height': 30
                }
            },
            {
                selector: 'node[nodeType="schema"]',
                style: {
                    'background-color': '#f56565',
                    'shape': 'round-diamond',
                    'width': 25,
                    'height': 25
                }
            },
            {
                selector: 'node[nodeType="table"]',
                style: {
                    'background-color': '#ecc94b',
                    'shape': 'ellipse',
                    'width': 20,
                    'height': 20
                }
            },
            {
                selector: 'edge',
                style: {
                    'width': 2,
                    'line-color': '#999',
                    'curve-style': 'bezier',
                    'target-arrow-shape': 'triangle',
                    'target-arrow-color': '#999',
                    'arrow-scale': 0.8
                }
            },
            {
                selector: 'edge[edgeType="catalog-connection"]',
                style: {
                    'line-color': '#805ad5',
                    'target-arrow-color': '#805ad5'
                }
            },
            {
                selector: 'edge[edgeType="schema-connection"]',
                style: {
                    'line-color': '#f56565',
                    'target-arrow-color': '#f56565'
                }
            },
            {
                selector: 'edge[edgeType="table-connection"]',
                style: {
                    'line-color': '#ecc94b',
                    'target-arrow-color': '#ecc94b'
                }
            },
            {
                selector: 'edge[edgeType="node-connection"]',
                style: {
                    'line-color': '#4299e1',
                    'target-arrow-color': '#4299e1',
                    'line-style': 'dashed'
                }
            },
            {
                selector: ':selected',
                style: {
                    'border-width': 3,
                    'border-color': '#ff0',
                    'border-opacity': 0.8
                }
            }
        ],
        
        // Initial layout settings
        layout: {
            name: 'cose',
            idealEdgeLength: 100,
            nodeOverlap: 20,
            refresh: 20,
            fit: true,
            padding: 30,
            randomize: false,
            componentSpacing: 100,
            nodeRepulsion: 4500,
            edgeElasticity: 100,
            nestingFactor: 5,
            gravity: 80,
            numIter: 1000,
            initialTemp: 200,
            coolingFactor: 0.95,
            minTemp: 1.0
        }
    });

    // Register for node click events
    cy.on('click', 'node', function(evt) {
        const node = evt.target;
        const nodeData = node.data();
        
        let detailsHtml = `<div class="p-2">
            <h6>${nodeData.label}</h6>
            <hr class="my-2">
            <p><strong>Type:</strong> ${capitalizeFirstLetter(nodeData.nodeType)}</p>`;
            
        // Add different details based on node type
        if (nodeData.nodeType === 'coordinator' || nodeData.nodeType === 'worker') {
            detailsHtml += `
                <p><strong>Cluster:</strong> ${nodeData.cluster}</p>
                <p><strong>Host:</strong> ${nodeData.host || 'localhost'}</p>
                <p><strong>Port:</strong> ${nodeData.port || 'N/A'}</p>
                <p><strong>Version:</strong> ${nodeData.version || 'N/A'}</p>
                <p><strong>Status:</strong> <span class="badge rounded-pill ${nodeData.status === 'Running' ? 'bg-success' : 'bg-danger'}">${nodeData.status || 'Unknown'}</span></p>
            `;
        } else if (nodeData.nodeType === 'catalog') {
            detailsHtml += `
                <p><strong>Type:</strong> ${nodeData.catalogType || 'N/A'}</p>
                <p><strong>Enabled:</strong> <span class="badge rounded-pill ${nodeData.enabled ? 'bg-success' : 'bg-secondary'}">${nodeData.enabled ? 'Yes' : 'No'}</span></p>
                <p><strong>Connected to:</strong> ${nodeData.connectedTo || 'N/A'}</p>
            `;
            if (nodeData.properties) {
                detailsHtml += `<p><strong>Properties:</strong></p><ul>`;
                Object.entries(nodeData.properties).forEach(([key, value]) => {
                    detailsHtml += `<li>${key}: ${value}</li>`;
                });
                detailsHtml += `</ul>`;
            }
        } else if (nodeData.nodeType === 'schema') {
            detailsHtml += `
                <p><strong>Catalog:</strong> ${nodeData.catalog || 'N/A'}</p>
                <p><strong>Tables:</strong> ${nodeData.tableCount || 'Unknown'}</p>
            `;
        } else if (nodeData.nodeType === 'table') {
            detailsHtml += `
                <p><strong>Schema:</strong> ${nodeData.schema || 'N/A'}</p>
                <p><strong>Catalog:</strong> ${nodeData.catalog || 'N/A'}</p>
                <p><strong>Columns:</strong> ${nodeData.columnCount || 'Unknown'}</p>
            `;
        }
        
        detailsHtml += `</div>`;
        document.getElementById('node-details').innerHTML = detailsHtml;
    });

    // Click away from nodes to clear details
    cy.on('click', function(evt) {
        if (evt.target === cy) {
            document.getElementById('node-details').innerHTML = '<p class="text-muted">Click on a node to see details</p>';
        }
    });

    // Handle layout options
    document.querySelectorAll('.layout-option').forEach(option => {
        option.addEventListener('click', function(e) {
            e.preventDefault();
            const layoutName = this.getAttribute('data-layout');
            applyLayout(layoutName);
        });
    });

    // Refresh topology button
    document.getElementById('refreshTopology').addEventListener('click', function() {
        fetchTopologyData();
    });

    // Apply a specific layout
    function applyLayout(layoutName) {
        let layoutOptions = {
            name: layoutName,
            fit: true,
            padding: 30
        };
        
        // Add specific options based on layout type
        if (layoutName === 'cose') {
            layoutOptions = {
                name: 'cose',
                idealEdgeLength: 100,
                nodeOverlap: 20,
                refresh: 20,
                fit: true,
                padding: 30,
                randomize: false,
                componentSpacing: 100,
                nodeRepulsion: 4500,
                edgeElasticity: 100,
                nestingFactor: 5,
                gravity: 80,
                numIter: 1000,
                initialTemp: 200,
                coolingFactor: 0.95,
                minTemp: 1.0
            };
        } else if (layoutName === 'circle') {
            layoutOptions = {
                name: 'circle',
                fit: true,
                padding: 30,
                radius: 200,
                startAngle: 3/2 * Math.PI,
                sweep: 2 * Math.PI,
                clockwise: true
            };
        } else if (layoutName === 'concentric') {
            layoutOptions = {
                name: 'concentric',
                fit: true,
                padding: 30,
                startAngle: 3/2 * Math.PI,
                minNodeSpacing: 50,
                concentric: function(node) {
                    // Determine concentric circle based on node type
                    if (node.data('nodeType') === 'coordinator') return 5;
                    if (node.data('nodeType') === 'worker') return 4;
                    if (node.data('nodeType') === 'catalog') return 3;
                    if (node.data('nodeType') === 'schema') return 2;
                    return 1;
                },
                levelWidth: function() { return 1; }
            };
        } else if (layoutName === 'breadthfirst') {
            layoutOptions = {
                name: 'breadthfirst',
                fit: true,
                padding: 30,
                directed: true,
                spacingFactor: 1.5
            };
        } else if (layoutName === 'grid') {
            layoutOptions = {
                name: 'grid',
                fit: true,
                padding: 30,
                avoidOverlap: true,
                spacingFactor: 1.5
            };
        }

        // Apply the chosen layout
        cy.layout(layoutOptions).run();
    }

    // Fetch topology data from the server
    function fetchTopologyData() {
        fetch('/api/topology')
            .then(response => response.json())
            .then(data => {
                // Clear existing graph
                cy.elements().remove();
                
                // Add nodes and edges from the server data
                cy.add(data.elements);
                
                // Apply layout
                applyLayout('cose');
                
                // Update cluster info
                updateClusterInfo(data.clusterInfo);
            })
            .catch(error => {
                console.error('Error fetching topology data:', error);
                // Show error message in the container
                document.getElementById('topology-container').innerHTML = 
                    `<div class="text-center p-5 text-light">
                        <div class="alert alert-danger">
                            Error loading topology data. Please check if the clusters are running.
                        </div>
                        <button id="retry-btn" class="btn btn-primary">Retry</button>
                    </div>`;
                
                document.getElementById('retry-btn').addEventListener('click', function() {
                    document.getElementById('topology-container').innerHTML = '';
                    fetchTopologyData();
                });
            });
    }

    // Update cluster information display
    function updateClusterInfo(clusterInfo) {
        if (!clusterInfo) return;
        
        if (clusterInfo.cluster1) {
            document.getElementById('cluster1-nodes').textContent = clusterInfo.cluster1.nodeCount || 'Unknown';
            document.getElementById('cluster1-catalogs').textContent = clusterInfo.cluster1.catalogs.join(', ') || 'None';
            
            const statusElement = document.getElementById('cluster1-status');
            statusElement.textContent = clusterInfo.cluster1.running ? 'Running' : 'Stopped';
            statusElement.className = `badge rounded-pill ${clusterInfo.cluster1.running ? 'bg-success' : 'bg-danger'}`;
        }
        
        if (clusterInfo.cluster2) {
            document.getElementById('cluster2-nodes').textContent = clusterInfo.cluster2.nodeCount || 'Unknown';
            document.getElementById('cluster2-catalogs').textContent = clusterInfo.cluster2.catalogs.join(', ') || 'None';
            
            const statusElement = document.getElementById('cluster2-status');
            statusElement.textContent = clusterInfo.cluster2.running ? 'Running' : 'Stopped';
            statusElement.className = `badge rounded-pill ${clusterInfo.cluster2.running ? 'bg-success' : 'bg-danger'}`;
        }
    }

    // Helper function to capitalize first letter
    function capitalizeFirstLetter(string) {
        return string.charAt(0).toUpperCase() + string.slice(1);
    }

    // Initial data load
    fetchTopologyData();
});