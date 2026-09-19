from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import mysql.connector
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DB_NAME = os.getenv("MYSQL_DATABASE", "medsupplyai")
DB_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "localhost"),
    "port": int(os.getenv("MYSQL_PORT", "3306")),
    "user": os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASSWORD", ""),
    "database": DB_NAME,
    "autocommit": False,
}


def get_connection(with_database: bool = True):
    config = DB_CONFIG.copy()
    if not with_database:
        config.pop("database", None)
    return mysql.connector.connect(**config)


def _column_names(cursor, table: str) -> set[str]:
    cursor.execute(f"SHOW COLUMNS FROM `{table}`")
    return {row[0] for row in cursor.fetchall()}


def _add_column_if_missing(cursor, table: str, column: str, definition: str) -> None:
    if column not in _column_names(cursor, table):
        cursor.execute(f"ALTER TABLE `{table}` ADD COLUMN `{column}` {definition}")


def create_database() -> None:
    """Create/upgrade the database without dropping existing V1 data."""
    server = get_connection(with_database=False)
    cur = server.cursor()
    cur.execute(
        f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` "
        "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
    )
    cur.close()
    server.commit()
    server.close()

    conn = get_connection()
    cur = conn.cursor()

    # Existing V1 inventory table compatibility.
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS inventory (
            id INT AUTO_INCREMENT PRIMARY KEY,
            medicine_name VARCHAR(150) NOT NULL,
            category VARCHAR(100) NOT NULL,
            quantity INT NOT NULL DEFAULT 0,
            minimum_stock INT NOT NULL DEFAULT 20,
            maximum_stock INT NOT NULL DEFAULT 100,
            expiry_date DATE NOT NULL,
            supplier VARCHAR(150),
            supplier_lead_days INT DEFAULT 5,
            unit_price DECIMAL(10,2) DEFAULT 0,
            criticality VARCHAR(30) DEFAULT 'Routine',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    for name, definition in [
        ("maximum_stock", "INT NOT NULL DEFAULT 100"),
        ("supplier", "VARCHAR(150) NULL"),
        ("supplier_lead_days", "INT NULL DEFAULT 5"),
        ("unit_price", "DECIMAL(10,2) NULL DEFAULT 0"),
        ("criticality", "VARCHAR(30) NULL DEFAULT 'Routine'"),
    ]:
        _add_column_if_missing(cur, "inventory", name, definition)

    # Existing supplier table compatibility.
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS suppliers (
            supplier_id INT AUTO_INCREMENT PRIMARY KEY,
            supplier_name VARCHAR(150) NOT NULL,
            contact VARCHAR(50),
            lead_time_days INT NOT NULL DEFAULT 5,
            supplier_code VARCHAR(50),
            country VARCHAR(100),
            address VARCHAR(255),
            data_status VARCHAR(30) DEFAULT 'DEMO',
            source_url VARCHAR(500),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    for name, definition in [
        ("supplier_code", "VARCHAR(50) NULL"),
        ("country", "VARCHAR(100) NULL"),
        ("address", "VARCHAR(255) NULL"),
        ("data_status", "VARCHAR(30) DEFAULT 'DEMO'"),
        ("source_url", "VARCHAR(500) NULL"),
    ]:
        _add_column_if_missing(cur, "suppliers", name, definition)

    # Existing consumption tables used by the V1 application.
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS consumption_history (
            id INT AUTO_INCREMENT PRIMARY KEY,
            medicine_id INT NOT NULL,
            usage_date DATE NOT NULL,
            quantity_used INT NOT NULL,
            INDEX idx_consumption_medicine_date (medicine_id, usage_date)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS stock_transactions (
            id INT AUTO_INCREMENT PRIMARY KEY,
            medicine_id INT NOT NULL,
            transaction_type VARCHAR(20) NOT NULL,
            quantity INT NOT NULL,
            transaction_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            notes VARCHAR(255),
            INDEX idx_stock_tx_medicine_date (medicine_id, transaction_date)
        )
        """
    )
    # Migrate the pre-V2 table when it already exists without the V2 notes field.
    _add_column_if_missing(cur, "stock_transactions", "notes", "VARCHAR(255) NULL")
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS procurement (
            procurement_id INT AUTO_INCREMENT PRIMARY KEY,
            medicine_id INT NOT NULL,
            recommended_quantity INT NOT NULL,
            recommendation_date DATE NOT NULL,
            status VARCHAR(30) DEFAULT 'Pending'
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS medicines (
            medicine_id INT AUTO_INCREMENT PRIMARY KEY,
            medicine_name VARCHAR(100) NOT NULL,
            category VARCHAR(100),
            criticality ENUM('Low','Medium','High') NOT NULL DEFAULT 'Low',
            emergency_reserve INT DEFAULT 0
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS usage_records (
            usage_id INT AUTO_INCREMENT PRIMARY KEY,
            medicine_id INT NOT NULL,
            quantity_used INT NOT NULL,
            usage_date DATE NOT NULL
        )
        """
    )

    # V2 normalized/provenance tables.
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS medicine_profiles (
            profile_id INT AUTO_INCREMENT PRIMARY KEY,
            inventory_id INT NOT NULL UNIQUE,
            generic_name VARCHAR(150),
            brand_name VARCHAR(150),
            strength VARCHAR(100),
            dosage_form VARCHAR(100),
            storage_instruction VARCHAR(255),
            manufacturer VARCHAR(200),
            manufacturing_site VARCHAR(255),
            product_identifier VARCHAR(100),
            gtin VARCHAR(30),
            emergency_reserve INT NOT NULL DEFAULT 0,
            data_status VARCHAR(30) NOT NULL DEFAULT 'DEMO',
            source_name VARCHAR(150),
            source_url VARCHAR(500),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_profile_inventory
                FOREIGN KEY (inventory_id) REFERENCES inventory(id)
                ON DELETE CASCADE
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS storage_locations (
            location_id INT AUTO_INCREMENT PRIMARY KEY,
            location_code VARCHAR(50) NOT NULL UNIQUE,
            location_name VARCHAR(150) NOT NULL,
            location_type VARCHAR(50) NOT NULL,
            temperature_min_c DECIMAL(5,2),
            temperature_max_c DECIMAL(5,2),
            humidity_max_rh DECIMAL(5,2),
            monitoring_enabled BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS medicine_batches (
            batch_id INT AUTO_INCREMENT PRIMARY KEY,
            inventory_id INT NOT NULL,
            batch_number VARCHAR(100) NOT NULL,
            manufacture_date DATE,
            expiry_date DATE NOT NULL,
            quantity_received INT NOT NULL DEFAULT 0,
            quantity_current INT NOT NULL DEFAULT 0,
            received_date DATE,
            supplier_id INT,
            storage_location_id INT,
            origin_country VARCHAR(100),
            origin_site VARCHAR(255),
            quality_status VARCHAR(40) DEFAULT 'RELEASED',
            data_status VARCHAR(30) NOT NULL DEFAULT 'DEMO',
            source_name VARCHAR(150),
            source_url VARCHAR(500),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_inventory_batch (inventory_id, batch_number),
            INDEX idx_batch_expiry (expiry_date),
            INDEX idx_batch_inventory (inventory_id),
            CONSTRAINT fk_batch_inventory
                FOREIGN KEY (inventory_id) REFERENCES inventory(id)
                ON DELETE CASCADE,
            CONSTRAINT fk_batch_supplier
                FOREIGN KEY (supplier_id) REFERENCES suppliers(supplier_id)
                ON DELETE SET NULL,
            CONSTRAINT fk_batch_location
                FOREIGN KEY (storage_location_id) REFERENCES storage_locations(location_id)
                ON DELETE SET NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS supply_chain_events (
            event_id INT AUTO_INCREMENT PRIMARY KEY,
            batch_id INT NOT NULL,
            event_type VARCHAR(60) NOT NULL,
            event_time DATETIME NOT NULL,
            location_name VARCHAR(255),
            actor_name VARCHAR(200),
            document_ref VARCHAR(100),
            notes VARCHAR(500),
            data_status VARCHAR(30) NOT NULL DEFAULT 'DEMO',
            source_name VARCHAR(150),
            source_url VARCHAR(500),
            INDEX idx_event_batch_time (batch_id, event_time),
            CONSTRAINT fk_event_batch
                FOREIGN KEY (batch_id) REFERENCES medicine_batches(batch_id)
                ON DELETE CASCADE
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS temperature_logs (
            log_id INT AUTO_INCREMENT PRIMARY KEY,
            location_id INT NOT NULL,
            logged_at DATETIME NOT NULL,
            temperature_c DECIMAL(5,2),
            humidity_rh DECIMAL(5,2),
            status VARCHAR(30),
            source_name VARCHAR(150),
            source_url VARCHAR(500),
            INDEX idx_temp_location_time (location_id, logged_at),
            CONSTRAINT fk_temp_location
                FOREIGN KEY (location_id) REFERENCES storage_locations(location_id)
                ON DELETE CASCADE
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS procurement_orders (
            order_id INT AUTO_INCREMENT PRIMARY KEY,
            order_number VARCHAR(50) NOT NULL UNIQUE,
            supplier_id INT,
            created_at DATETIME NOT NULL,
            expected_delivery DATE,
            status VARCHAR(40) NOT NULL DEFAULT 'DRAFT',
            priority VARCHAR(30) NOT NULL DEFAULT 'NORMAL',
            total_value DECIMAL(12,2) NOT NULL DEFAULT 0,
            notes VARCHAR(500),
            CONSTRAINT fk_po_supplier
                FOREIGN KEY (supplier_id) REFERENCES suppliers(supplier_id)
                ON DELETE SET NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS procurement_order_items (
            order_item_id INT AUTO_INCREMENT PRIMARY KEY,
            order_id INT NOT NULL,
            inventory_id INT NOT NULL,
            quantity INT NOT NULL,
            unit_price DECIMAL(10,2) NOT NULL DEFAULT 0,
            CONSTRAINT fk_poi_order
                FOREIGN KEY (order_id) REFERENCES procurement_orders(order_id)
                ON DELETE CASCADE,
            CONSTRAINT fk_poi_inventory
                FOREIGN KEY (inventory_id) REFERENCES inventory(id)
                ON DELETE RESTRICT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            audit_id INT AUTO_INCREMENT PRIMARY KEY,
            event_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            entity_type VARCHAR(50) NOT NULL,
            entity_id INT,
            action VARCHAR(50) NOT NULL,
            details VARCHAR(1000),
            actor VARCHAR(100) DEFAULT 'system'
        )
        """
    )

    # Compatibility migration for databases created by earlier V2 builds.
    # Existing rows are preserved; missing fields are added as nullable/defaulted.
    table_columns = {
        "medicine_profiles": [
            ("generic_name", "VARCHAR(150) NULL"), ("brand_name", "VARCHAR(150) NULL"),
            ("strength", "VARCHAR(100) NULL"), ("dosage_form", "VARCHAR(100) NULL"),
            ("storage_instruction", "VARCHAR(255) NULL"), ("manufacturer", "VARCHAR(200) NULL"),
            ("manufacturing_site", "VARCHAR(255) NULL"), ("product_identifier", "VARCHAR(100) NULL"),
            ("gtin", "VARCHAR(30) NULL"), ("emergency_reserve", "INT NOT NULL DEFAULT 0"),
            ("data_status", "VARCHAR(30) NOT NULL DEFAULT 'DEMO'"), ("source_name", "VARCHAR(150) NULL"),
            ("source_url", "VARCHAR(500) NULL"),
        ],
        "storage_locations": [
            ("location_code", "VARCHAR(50) NULL"), ("location_name", "VARCHAR(150) NULL"),
            ("location_type", "VARCHAR(50) NULL"), ("temperature_min_c", "DECIMAL(5,2) NULL"),
            ("temperature_max_c", "DECIMAL(5,2) NULL"), ("humidity_max_rh", "DECIMAL(5,2) NULL"),
            ("monitoring_enabled", "BOOLEAN NOT NULL DEFAULT FALSE"),
        ],
        "medicine_batches": [
            ("inventory_id", "INT NULL"), ("batch_number", "VARCHAR(100) NULL"),
            ("manufacture_date", "DATE NULL"), ("expiry_date", "DATE NULL"),
            ("quantity_received", "INT NOT NULL DEFAULT 0"), ("quantity_current", "INT NOT NULL DEFAULT 0"),
            ("received_date", "DATE NULL"), ("supplier_id", "INT NULL"), ("storage_location_id", "INT NULL"),
            ("origin_country", "VARCHAR(100) NULL"), ("origin_site", "VARCHAR(255) NULL"),
            ("quality_status", "VARCHAR(40) DEFAULT 'RELEASED'"), ("data_status", "VARCHAR(30) NOT NULL DEFAULT 'DEMO'"),
            ("source_name", "VARCHAR(150) NULL"), ("source_url", "VARCHAR(500) NULL"),
        ],
        "supply_chain_events": [
            ("batch_id", "INT NULL"), ("event_type", "VARCHAR(60) NULL"), ("event_time", "DATETIME NULL"),
            ("location_name", "VARCHAR(255) NULL"), ("actor_name", "VARCHAR(200) NULL"),
            ("document_ref", "VARCHAR(100) NULL"), ("notes", "VARCHAR(500) NULL"),
            ("data_status", "VARCHAR(30) NOT NULL DEFAULT 'DEMO'"), ("source_name", "VARCHAR(150) NULL"),
            ("source_url", "VARCHAR(500) NULL"),
        ],
        "temperature_logs": [
            ("location_id", "INT NULL"), ("logged_at", "DATETIME NULL"), ("temperature_c", "DECIMAL(5,2) NULL"),
            ("humidity_rh", "DECIMAL(5,2) NULL"), ("status", "VARCHAR(30) NULL"),
            ("source_name", "VARCHAR(150) NULL"), ("source_url", "VARCHAR(500) NULL"),
        ],
        "procurement_orders": [
            ("order_number", "VARCHAR(50) NULL"), ("supplier_id", "INT NULL"),
            ("created_at", "DATETIME NULL"), ("expected_delivery", "DATE NULL"),
            ("status", "VARCHAR(40) NOT NULL DEFAULT 'DRAFT'"), ("priority", "VARCHAR(30) NOT NULL DEFAULT 'NORMAL'"),
            ("total_value", "DECIMAL(12,2) NOT NULL DEFAULT 0"), ("notes", "VARCHAR(500) NULL"),
        ],
        "procurement_order_items": [
            ("order_id", "INT NULL"), ("inventory_id", "INT NULL"), ("quantity", "INT NOT NULL DEFAULT 0"),
            ("unit_price", "DECIMAL(10,2) NOT NULL DEFAULT 0"),
        ],
        "audit_log": [
            ("event_time", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"), ("entity_type", "VARCHAR(50) NULL"),
            ("entity_id", "INT NULL"), ("action", "VARCHAR(50) NULL"), ("details", "VARCHAR(1000) NULL"),
            ("actor", "VARCHAR(100) DEFAULT 'system'"),
        ],
    }
    for table, columns in table_columns.items():
        for column_name, definition in columns:
            _add_column_if_missing(cur, table, column_name, definition)

    # Seed a default storage layout only if absent.
    cur.execute("SELECT COUNT(*) FROM storage_locations")
    if cur.fetchone()[0] == 0:
        cur.executemany(
            """
            INSERT INTO storage_locations
            (location_code, location_name, location_type, monitoring_enabled)
            VALUES (%s,%s,%s,%s)
            """,
            [
                ("PHARM-A", "Central Pharmacy Store", "AMBIENT", False),
                ("COLD-A", "Cold Storage Unit A", "COLD_CHAIN", True),
            ],
        )

    # Populate supplier master from existing inventory text values when possible.
    cur.execute(
        "SELECT DISTINCT supplier, supplier_lead_days FROM inventory "
        "WHERE supplier IS NOT NULL AND TRIM(supplier) <> ''"
    )
    for supplier_name, lead_days in cur.fetchall():
        cur.execute(
            "SELECT supplier_id FROM suppliers WHERE supplier_name = %s LIMIT 1",
            (supplier_name,),
        )
        exists = cur.fetchone()
        if not exists:
            cur.execute(
                """
                INSERT INTO suppliers (supplier_name, lead_time_days, data_status, source_name)
                VALUES (%s,%s,'DEMO','Existing inventory record')
                """,
                (supplier_name, int(lead_days or 5)),
            )

    # Create a profile for each legacy inventory row if absent.
    cur.execute("SELECT id, medicine_name, category, criticality FROM inventory")
    inventory_rows = cur.fetchall()
    for inv_id, name, category, criticality in inventory_rows:
        cur.execute("SELECT profile_id FROM medicine_profiles WHERE inventory_id=%s", (inv_id,))
        if cur.fetchone() is None:
            reserve = 0
            if str(criticality).lower() == "critical":
                reserve = 10
            cur.execute(
                """
                INSERT INTO medicine_profiles
                (inventory_id, generic_name, dosage_form, emergency_reserve,
                 data_status, source_name)
                VALUES (%s,%s,%s,%s,'DEMO','Legacy inventory seed')
                """,
                (inv_id, name, category, reserve),
            )

    # One traceability batch per legacy inventory item, explicitly marked demo.
    cur.execute("SELECT location_id FROM storage_locations WHERE location_code='PHARM-A' LIMIT 1")
    ambient_location = cur.fetchone()[0]
    cur.execute("SELECT location_id FROM storage_locations WHERE location_code='COLD-A' LIMIT 1")
    cold_location = cur.fetchone()[0]

    cur.execute(
        """
        SELECT id, medicine_name, quantity, expiry_date, supplier, supplier_lead_days
        FROM inventory
        """
    )
    rows = cur.fetchall()
    for inv_id, name, qty, expiry, supplier_name, lead_days in rows:
        cur.execute(
            "SELECT batch_id FROM medicine_batches WHERE inventory_id=%s LIMIT 1",
            (inv_id,),
        )
        batch = cur.fetchone()
        if batch is None:
            supplier_id = None
            if supplier_name:
                cur.execute(
                    "SELECT supplier_id FROM suppliers WHERE supplier_name=%s LIMIT 1",
                    (supplier_name,),
                )
                supplier = cur.fetchone()
                supplier_id = supplier[0] if supplier else None
            location_id = cold_location if "insulin" in name.lower() else ambient_location
            batch_number = f"DEMO-{int(inv_id):04d}"
            cur.execute(
                """
                INSERT INTO medicine_batches
                (inventory_id, batch_number, manufacture_date, expiry_date,
                 quantity_received, quantity_current, received_date,
                 supplier_id, storage_location_id, quality_status,
                 data_status, source_name)
                VALUES (%s,%s,%s,%s,%s,%s,CURDATE(),%s,%s,'RELEASED','DEMO','Legacy inventory seed')
                """,
                (inv_id, batch_number, None, expiry, qty, qty, supplier_id, location_id),
            )
            batch_id = cur.lastrowid
            cur.execute(
                """
                INSERT INTO supply_chain_events
                (batch_id, event_type, event_time, location_name, notes,
                 data_status, source_name)
                VALUES (%s,'HOSPITAL_RECEIPT',NOW(),%s,'Legacy demo traceability event. Origin not recorded.','DEMO','Legacy inventory seed')
                """,
                (batch_id, "Cold Storage Unit A" if "insulin" in name.lower() else "Central Pharmacy Store"),
            )

    conn.commit()
    cur.close()
    conn.close()
