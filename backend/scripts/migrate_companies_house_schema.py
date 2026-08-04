"""
Database Migration Script — Companies House Schema Update
Applies schema updates (new columns & new tables) idempotently for Companies House integration.
"""

import sys
import os
from sqlalchemy import text

# Ensure backend root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils.mysql_client import get_sync_db_session

def run_migration():
    print("[MIGRATION] Starting Companies House schema migration...")
    
    with get_sync_db_session() as conn:
        # 1. Company table updates
        print(" -> Updating 'companies' table...")
        try:
            conn.execute(text("ALTER TABLE companies ADD COLUMN source VARCHAR(100) DEFAULT 'Manual Entry';"))
            conn.execute(text("CREATE INDEX ix_companies_source ON companies (source);"))
        except Exception as e:
            print(f"    (Notice: source column on companies may already exist: {e})")

        try:
            conn.execute(text("ALTER TABLE companies ADD COLUMN company_number VARCHAR(20) DEFAULT '';"))
            conn.execute(text("CREATE INDEX ix_companies_company_number ON companies (company_number);"))
        except Exception as e:
            print(f"    (Notice: company_number column on companies may already exist: {e})")

        # 2. Tender table updates
        print(" -> Updating 'tenders' table...")
        try:
            conn.execute(text("ALTER TABLE tenders ADD COLUMN source VARCHAR(100) DEFAULT 'SAM.gov';"))
            conn.execute(text("CREATE INDEX ix_tenders_source ON tenders (source);"))
        except Exception as e:
            print(f"    (Notice: source column on tenders may already exist: {e})")

        try:
            conn.execute(text("ALTER TABLE tenders ADD COLUMN raw_companies_house_data JSON;"))
        except Exception as e:
            print(f"    (Notice: raw_companies_house_data on tenders may already exist: {e})")

        # 3. Report table updates
        print(" -> Updating 'reports' table...")
        try:
            conn.execute(text("ALTER TABLE reports ADD COLUMN source VARCHAR(100) DEFAULT '';"))
            conn.execute(text("CREATE INDEX ix_reports_source ON reports (source);"))
        except Exception as e:
            print(f"    (Notice: source column on reports may already exist: {e})")

        # 4. Create sic_codes table if not exists
        print(" -> Creating 'sic_codes' table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS sic_codes (
                code VARCHAR(20) PRIMARY KEY,
                title VARCHAR(500) NOT NULL DEFAULT '',
                description TEXT,
                FULLTEXT KEY ft_sic_title_desc (title, description)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """))

        # 5. Create ch_companies table if not exists
        print(" -> Creating 'ch_companies' table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS ch_companies (
                id INT AUTO_INCREMENT PRIMARY KEY,
                company_number VARCHAR(20) NOT NULL UNIQUE,
                title VARCHAR(255) NOT NULL,
                company_status VARCHAR(100) DEFAULT 'active',
                company_type VARCHAR(100) DEFAULT 'ltd',
                date_of_creation VARCHAR(50) DEFAULT '',
                sic_codes JSON,
                registered_office_address JSON,
                raw_data JSON,
                source VARCHAR(100) DEFAULT 'Companies House',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX ix_ch_companies_number (company_number),
                INDEX ix_ch_companies_status (company_status),
                FULLTEXT KEY ft_ch_companies_title (title)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """))

        # 6. Backfill existing records
        print(" -> Backfilling default source values...")
        conn.execute(text("UPDATE companies SET source = 'SAM.gov' WHERE uei IS NOT NULL AND uei != '' AND (source IS NULL OR source = 'Manual Entry');"))
        conn.execute(text("UPDATE tenders SET source = 'SAM.gov' WHERE source IS NULL OR source = '';"))
        conn.commit()

    print("[MIGRATION] Migration completed successfully!")

if __name__ == "__main__":
    run_migration()
