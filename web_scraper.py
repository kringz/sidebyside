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

def scrape_trino_release_page(version, timeout=5):
    """
    Scrape a Trino release page and extract changes categorized by Connector and General
    
    Args:
        version (str): The Trino version to scrape (e.g., "406")
        timeout (int): Request timeout in seconds to prevent hanging
        
    Returns:
        dict: A dictionary with two keys: 'connector_changes' and 'general_changes',
              each containing a list of change items
    """
    base_url = "https://trino.io/docs/current/release"
    release_url = f"{base_url}/release-{version}.html"
    
    logger.info(f"Scraping Trino release page: {release_url}")
    
    try:
        # Fetch the release page with a short timeout to prevent hanging
        response = requests.get(release_url, timeout=timeout)
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
        logger.info(f"Found {len(headings)} headings in release page for version {version}")
        
        current_section = None
        connector_section = False
        
        for heading in headings:
            heading_text = heading.get_text().strip().lower()
            logger.debug(f"Processing heading: {heading.name} - {heading_text}")
            
            # Identify connector-related sections
            if 'connector' in heading_text or heading_text.endswith('connector'):
                connector_section = True
                current_section = heading
                logger.debug(f"Identified connector section: {heading_text}")
            # Major section headings
            elif heading.name == 'h2':
                connector_section = False
                current_section = heading
                logger.debug(f"Identified general section: {heading_text}")
            
            # If we have a current section, find the changes under it
            if current_section:
                # Find the next unordered list after this heading
                next_element = heading.find_next()
                while next_element and next_element.name != 'ul' and next_element.name not in ['h2', 'h3']:
                    next_element = next_element.find_next()
                
                # If we found a ul before the next heading, process its list items
                if next_element and next_element.name == 'ul':
                    changes = []
                    list_items = next_element.find_all('li', recursive=False)
                    logger.debug(f"Found {len(list_items)} list items under section {heading_text}")
                    
                    for li in list_items:
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
                        logger.debug(f"Added {len(changes)} connector changes for section {heading_text}")
                    else:
                        result["general_changes"].extend(changes)
                        logger.debug(f"Added {len(changes)} general changes for section {heading_text}")
        
        logger.info(f"Completed scraping for version {version}. Found {len(result['connector_changes'])} connector changes and {len(result['general_changes'])} general changes")
        return result
    
    except Exception as e:
        logger.error(f"Error scraping release page for version {version}: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return {"connector_changes": [], "general_changes": []}

def fetch_all_trino_versions():
    """
    Fetch all available Trino versions from the official release notes page.
    
    Returns:
        list: A list of dictionaries containing version information, ordered by version number (descending)
    """
    release_url = "https://trino.io/docs/current/release.html"
    logger.info(f"Fetching all Trino versions from {release_url}")
    
    try:
        # Fetch the release page
        response = requests.get(release_url, timeout=10)
        if response.status_code != 200:
            logger.warning(f"Failed to fetch release page: {response.status_code}")
            return []
        
        # Parse the HTML
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Add debug information
        logger.debug(f"Response length: {len(response.text)} bytes")
        
        # Debug: first 500 chars of the response
        logger.debug(f"First 500 chars of response: {response.text[:500]}")
        
        # Debug: check main content sections
        sections = soup.find_all('section')
        logger.debug(f"Found {len(sections)} sections")
        
        # Use a simpler approach - extract version numbers from any line with 'Release XXX'
        versions = []
        lines = response.text.split('\n')
        version_pattern = re.compile(r'Release (\d+)')
        
        for line in lines:
            if 'Release' in line and 'href' in line:
                logger.debug(f"Found potential version line: {line}")
                match = version_pattern.search(line)
                if match:
                    version_number = match.group(1)
                    logger.debug(f"Extracted version number: {version_number}")
                    versions.append({
                        "version": version_number,
                        "name": f"Release {version_number}"
                    })
        
        # Remove duplicates while preserving order
        seen = set()
        unique_versions = []
        for v in versions:
            if v["version"] not in seen:
                seen.add(v["version"])
                unique_versions.append(v)
        
        # Sort versions in descending order
        unique_versions.sort(key=lambda x: int(x["version"]), reverse=True)
        
        logger.info(f"Found {len(unique_versions)} Trino versions")
        
        # If we still have no versions, use a fallback approach with manual extraction
        if not unique_versions:
            logger.warning("Using fallback approach with hardcoded regex")
            # Extract all digits following "Release"
            fallback_pattern = re.compile(r'Release\s+(\d+)')
            matches = fallback_pattern.findall(response.text)
            logger.debug(f"Fallback found {len(matches)} matches: {matches[:10]}")
            
            for v in matches:
                unique_versions.append({
                    "version": v,
                    "name": f"Release {v}"
                })
                
            # Sort again after fallback
            unique_versions.sort(key=lambda x: int(x["version"]), reverse=True)
            logger.info(f"Fallback found {len(unique_versions)} Trino versions")
        
        return unique_versions
    
    except Exception as e:
        logger.error(f"Error fetching Trino versions: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return []

def get_all_changes_between_versions(from_version, to_version, max_versions=20):
    """
    Get all changes between two Trino versions, categorized by Connector and General/Other
    
    Args:
        from_version (str): The starting version (lower bound)
        to_version (str): The ending version (upper bound)
        max_versions (int): Maximum number of versions to process to prevent timeouts
        
    Returns:
        dict: A dictionary with all changes categorized
    """
    # Enhanced debug logging
    logger.info(f"Getting changes between Trino versions {from_version} and {to_version}")
    
    # Ensure from_version is less than to_version
    if version_compare(from_version, to_version) > 0:
        logger.info(f"Swapping from_version and to_version as {from_version} is newer than {to_version}")
        from_version, to_version = to_version, from_version
    
    # Generate the list of versions to check
    versions = generate_version_range(from_version, to_version)
    logger.info(f"Generated version range: {versions}")
    
    # Limit the number of versions to process to prevent timeouts
    if len(versions) > max_versions:
        logger.warning(f"Too many versions requested ({len(versions)}). Limiting to {max_versions} versions.")
        # Take versions at regular intervals to get a representative sample
        if len(versions) > 1:
            step = max(1, len(versions) // max_versions)
            versions = versions[::step]
            # Always include the first and last version
            if versions[-1] != to_version:
                versions.append(to_version)
        logger.info(f"Limited version range: {versions}")
    
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
        try:
            version_changes = scrape_trino_release_page(version)
            
            logger.info(f"Found {len(version_changes['connector_changes'])} connector changes and {len(version_changes['general_changes'])} general changes for version {version}")
            
            if version_changes["connector_changes"]:
                result["connector_changes"].extend(version_changes["connector_changes"])
            
            if version_changes["general_changes"]:
                result["general_changes"].extend(version_changes["general_changes"])
        except Exception as e:
            logger.error(f"Error scraping version {version}: {str(e)}")
            # Continue with next version instead of failing completely
            continue
    
    logger.info(f"Total changes found: {len(result['connector_changes'])} connector changes, {len(result['general_changes'])} general changes")
    
    # Debug: print first change if there are any
    if result['connector_changes']:
        logger.info(f"Sample connector change: {result['connector_changes'][0]}")
    if result['general_changes']:
        logger.info(f"Sample general change: {result['general_changes'][0]}")
        
    return result