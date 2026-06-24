"""
setup_smartreorder_db.py

Creates:
    smartreorder.db

Tables:
    product
    supplier
"""

import sqlite3
import os

DB = os.path.join(
    os.path.dirname(__file__),
    "smartreorder.db"
)

if os.path.exists(DB):
    os.remove(DB)

con = sqlite3.connect(DB)
cur = con.cursor()

cur.execute("""
CREATE TABLE product (
    product_id TEXT PRIMARY KEY,
    product_name TEXT NOT NULL,
    on_hand_qty INTEGER NOT NULL,
    safety_stock INTEGER NOT NULL,
    avg_daily_sales INTEGER NOT NULL
)
""")

cur.execute("""
CREATE TABLE supplier (
    supplier_id TEXT PRIMARY KEY,
    supplier_name TEXT NOT NULL,
    unit_price REAL NOT NULL,
    lead_time_days INTEGER NOT NULL,
    reliability REAL NOT NULL,
    ship_speed TEXT NOT NULL
)
""")

# Rainfall / Flooding Scenario

cur.executemany(
    "INSERT INTO product VALUES (?,?,?,?,?)",
    [
        ("P1", "Bottled Water", 160, 250, 80),
        ("P2", "Cola", 700, 250, 100),
        ("P3", "Sports Drink", 140, 180, 50),
    ]
)

cur.executemany(
    "INSERT INTO supplier VALUES (?,?,?,?,?,?)",
    [
        ("S10", "FastBev", 1.15, 2, 0.98, "express"),
        ("S20", "ValueBev", 0.95, 6, 0.91, "standard"),
        ("S30", "BulkBev", 0.85, 11, 0.87, "freight"),
    ]
)

con.commit()
con.close()

print(
    "Created smartreorder.db "
    "(PRODUCT=3 rows, SUPPLIER=3 rows)"
)