import requests
import re
import logging
from bs4 import BeautifulSoup

# Configure logging
logger = logging.getLogger(__name__)

def get_website_text_content(url: str) -> str:
    """
    This function takes a url and returns the main text content of the website.
    The text content is extracted using trafilatura and easier to understand.
    
    Args:
        url: The URL to fetch
        
    Returns:
        str: The extracted text content
    """
    try:
        # Send a request to the website
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            logger.error(f"Failed to fetch URL {url}, status code: {response.status_code}")
            return ""
        
        # Use BeautifulSoup to parse the HTML if trafilatura is not available
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find the main content
        main_content = soup.find('div', class_='main-container') or soup.find('main') or soup.body
        if main_content:
            return main_content.get_text(separator="\n", strip=True)
        return soup.get_text(separator="\n", strip=True)
    except Exception as e:
        logger.error(f"Error fetching URL {url}: {str(e)}")
        return ""

def version_compare(v1, v2):
    """Compare two version strings"""
    def normalize(v):
        return [int(x) for x in re.sub(r'[^0-9]', '.', v).split('.') if x]
    
    v1_parts = normalize(v1)
    v2_parts = normalize(v2)
    
    for i in range(max(len(v1_parts), len(v2_parts))):
        v1_part = v1_parts[i] if i < len(v1_parts) else 0
        v2_part = v2_parts[i] if i < len(v2_parts) else 0
        if v1_part > v2_part:
            return 1
        elif v1_part < v2_part:
            return -1
    return 0

def generate_version_range(from_version, to_version):
    """Generate a list of version numbers between from_version and to_version, inclusive"""
    # Ensure from_version is less than to_version
    if version_compare(from_version, to_version) > 0:
        from_version, to_version = to_version, from_version
    
    # Convert versions to integers
    try:
        from_v = int(from_version)
        to_v = int(to_version)
        
        # Generate the range
        return [str(v) for v in range(from_v, to_v + 1)]
    except ValueError:
        # Fallback for non-numeric versions
        logger.warning(f"Non-numeric versions provided: {from_version} to {to_version}")
        return [from_version, to_version]

def scrape_trino_release_page(version):
    """
    Scrape a Trino release page and extract changes categorized by Connector and General
    
    Args:
        version (str): The Trino version to scrape (e.g., "406")
        
    Returns:
        dict: A dictionary with two keys: 'connector_changes' and 'general_changes',
              each containing a list of change items
    """
    base_url = "https://trino.io/docs/current/release"
    release_url = f"{base_url}/release-{version}.html"
    
    try:
        # Fetch the release page
        response = requests.get(release_url, timeout=10)
        if response.status_code != 200:
            logger.warning(f"Failed to fetch release page for version {version}: {response.status_code}")
            return {"connector_changes": [], "general_changes": []}
        
        # Parse the HTML
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find all sections in the release notes
        result = {
            "version": version,
            "connector_changes": [],
            "general_changes": []
        }
        
        # Find all h2 and h3 headings to locate sections
        headings = soup.find_all(['h2', 'h3'])
        
        current_section = None
        connector_section = False
        
        for heading in headings:
            heading_text = heading.get_text().strip().lower()
            
            # Identify connector-related sections
            if 'connector' in heading_text or heading_text.endswith('connector'):
                connector_section = True
                current_section = heading
            # Major section headings
            elif heading.name == 'h2':
                connector_section = False
                current_section = heading
            
            # If we have a current section, find the changes under it
            if current_section:
                # Find the next unordered list after this heading
                next_element = heading.find_next()
                while next_element and next_element.name != 'ul' and next_element.name not in ['h2', 'h3']:
                    next_element = next_element.find_next()
                
                # If we found a ul before the next heading, process its list items
                if next_element and next_element.name == 'ul':
                    changes = []
                    for li in next_element.find_all('li', recursive=False):
                        change_text = li.get_text().strip()
                        if change_text:
                            changes.append({
                                "version": version,
                                "category": heading_text,
                                "text": change_text
                            })
                    
                    # Add to the appropriate category
                    if connector_section:
                        result["connector_changes"].extend(changes)
                    else:
                        result["general_changes"].extend(changes)
        
        return result
    
    except Exception as e:
        logger.error(f"Error scraping release page for version {version}: {str(e)}")
        return {"connector_changes": [], "general_changes": []}

def get_all_changes_between_versions(from_version, to_version):
    """
    Get all changes between two Trino versions, categorized by Connector and General/Other
    
    Args:
        from_version (str): The starting version (lower bound)
        to_version (str): The ending version (upper bound)
        
    Returns:
        dict: A dictionary with all changes categorized
    """
    # Ensure from_version is less than to_version
    if version_compare(from_version, to_version) > 0:
        from_version, to_version = to_version, from_version
    
    # Generate the list of versions to check
    versions = generate_version_range(from_version, to_version)
    
    # Initialize result structure
    result = {
        "from_version": from_version,
        "to_version": to_version,
        "versions_checked": versions,
        "connector_changes": [],
        "general_changes": []
    }
    
    # Process each version
    for version in versions:
        logger.info(f"Scraping release page for Trino version {version}")
        version_changes = scrape_trino_release_page(version)
        
        if version_changes["connector_changes"]:
            result["connector_changes"].extend(version_changes["connector_changes"])
        
        if version_changes["general_changes"]:
            result["general_changes"].extend(version_changes["general_changes"])
    
    return result