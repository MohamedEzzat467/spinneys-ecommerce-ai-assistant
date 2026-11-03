import os, sys, warnings
warnings.filterwarnings('ignore')
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / '.env')

import pymysql

conn = pymysql.connect(
    host='localhost', port=3306, user='root', password='1234',
    database='spinneys_database', charset='utf8mb4',
    cursorclass=pymysql.cursors.DictCursor, connect_timeout=30
)

sql = """
SELECT COUNT(*) AS n FROM (
    SELECT p.id FROM catalog_product p
    INNER JOIN catalog_productname pn ON pn.product_id=p.id AND pn.language='English'
    LEFT JOIN catalog_productattributes pa ON pa.product_id=p.id AND pa.language='English'
    LEFT JOIN JSON_TABLE(
        COALESCE(pa.attributes,'[]'),
        '$[*]'
        COLUMNS(
            attr_code   VARCHAR(100) PATH '$.code',
            brand_value TEXT         PATH '$.value'
        )
    ) AS jt ON jt.attr_code='product_brand_id'
    WHERE p.default_price>0
    GROUP BY p.id
) sub
"""

with conn.cursor() as cur:
    cur.execute(sql)
    result = cur.fetchone()
conn.close()
print(f"Products fetchable with LEFT JOIN (no brand filter): {result['n']:,}")
print("Target: > 25,000")
