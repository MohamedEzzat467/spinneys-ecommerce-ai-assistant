"""Quick dry-run: fetch + impute + clean (no embedding) to verify product count."""
import sys, os
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from dotenv import load_dotenv
load_dotenv(ROOT / '.env')

from scripts.ingest import get_connection, fetch_products, impute_and_normalize_brands, clean_products

print('Step 1: Fetching from MySQL (LEFT JOIN)...')
conn = get_connection()
raw = fetch_products(conn)
conn.close()
print(f'  Raw rows fetched: {len(raw):,}')

print('\nStep 2: Brand imputation + normalization...')
imp = impute_and_normalize_brands(raw)

print('\nStep 3: Cleaning (dedup + filters)...')
clean = clean_products(imp)

named   = (clean["brand"] != "Generic / Unbranded").sum()
generic = (clean["brand"] == "Generic / Unbranded").sum()

print(f'\n{"="*50}')
print(f'  Final product count : {len(clean):,}')
print(f'  Named brand         : {named:,} ({named/len(clean)*100:.1f}%)')
print(f'  Generic/Unbranded   : {generic:,} ({generic/len(clean)*100:.1f}%)')
print(f'{"="*50}')

print('\n  Top 10 brands after normalization:')
print(clean["brand"].value_counts().head(10).to_string())

print(f'\n  Target >25,000: {"✅ ACHIEVED" if len(clean) >= 25000 else "❌ NOT MET"}')
