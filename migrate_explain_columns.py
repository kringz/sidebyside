import os
import logging
import psycopg2
from app import app

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_explain_columns():
    """Add EXPLAIN plan columns to QueryHistory table"""
    try:
        with app.app_context():
            # Check if DATABASE_URL is configured
            DATABASE_URL = os.environ.get('DATABASE_URL')
            if not DATABASE_URL:
                logger.warning("DATABASE_URL not configured. Migration skipped.")
                return False
            
            logger.info("Running database migration to add EXPLAIN plan columns...")
            
            # Connect directly to the database using psycopg2
            conn = psycopg2.connect(DATABASE_URL)
            conn.autocommit = False  # Use transaction
            cur = conn.cursor()
            
            try:
                # Check if the columns exist
                cur.execute("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'query_history' 
                    AND column_name = 'cluster1_explain'
                """)
                
                if cur.fetchone() is None:
                    logger.info("Adding new columns to query_history table...")
                    
                    # Add the columns if they don't exist
                    cur.execute("ALTER TABLE query_history ADD COLUMN IF NOT EXISTS cluster1_explain TEXT")
                    cur.execute("ALTER TABLE query_history ADD COLUMN IF NOT EXISTS cluster2_explain TEXT")
                    cur.execute("ALTER TABLE query_history ADD COLUMN IF NOT EXISTS cluster1_explain_timing FLOAT")
                    cur.execute("ALTER TABLE query_history ADD COLUMN IF NOT EXISTS cluster2_explain_timing FLOAT")
                    
                    conn.commit()
                    logger.info("Migration complete: Added explain plan columns to query_history table")
                else:
                    logger.info("Columns already exist. No changes needed.")
                    conn.rollback()
                
                return True
                
            except Exception as e:
                conn.rollback()
                logger.error(f"Migration error in SQL execution: {str(e)}")
                return False
                
            finally:
                cur.close()
                conn.close()
                
    except Exception as e:
        logger.error(f"Migration error: {str(e)}")
        return False

if __name__ == "__main__":
    print("Running migration to add EXPLAIN plan columns to QueryHistory table...")
    
    success = migrate_explain_columns()
    
    if success:
        print("Migration completed successfully!")
    else:
        print("Migration failed or was skipped. Check logs for details.")