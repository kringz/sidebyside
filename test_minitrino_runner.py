import os
import sys
import logging
from test_minitrino import test_minitrino_integration

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    # Get version from command line argument or use default
    version = sys.argv[1] if len(sys.argv) > 1 else '443-e'
    
    logger.info(f"Testing Minitrino integration with Starburst version: {version}")
    
    try:
        # Run the test
        success = test_minitrino_integration(version)
        
        if success:
            logger.info("✅ Test completed successfully!")
        else:
            logger.error("❌ Test failed!")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"❌ Error during test: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main() 