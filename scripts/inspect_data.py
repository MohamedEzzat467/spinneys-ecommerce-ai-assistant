import pandas as pd
import os

base_dir = r"D:\Mohamed\Matirial\POWE PI"
files = {
    'tx_1997': os.path.join(base_dir, 'Combine', 'MavenMarket_Transactions_1997.csv'),
    'tx_1998': os.path.join(base_dir, 'Combine', 'MavenMarket_Transactions_1998.csv'),
    'returns': os.path.join(base_dir, 'MavenMarket_Returns_1997-1998.csv'),
    'products': os.path.join(base_dir, 'MavenMarket_Products.csv'),
    'customers': os.path.join(base_dir, 'MavenMarket_Customers.csv'),
    'stores': os.path.join(base_dir, 'MavenMarket_Stores.csv'),
    'regions': os.path.join(base_dir, 'MavenMarket_Regions (1).csv'),
    'calendar': os.path.join(base_dir, 'MavenMarket_Calendar.csv'),
    'hr': os.path.join(base_dir, 'HR Attrition Case Study.xlsx')
}

for name, path in files.items():
    print(f"\n==================== {name} ====================")
    if name == 'hr':
        xl = pd.ExcelFile(path)
        print(f"Sheet names: {xl.sheet_names}")
        df = pd.read_excel(path, sheet_name='HR-Employee')
        print(f"Shape: {df.shape}")
        print("Columns:", list(df.columns))
        print("Sample head:\n", df.head(2))
    else:
        df = pd.read_csv(path, nrows=5)
        print("Columns:", list(df.columns))
        print("Sample head:\n", df.head(2))
