"""Script to generate synthetic sample expense reports (CSV & Excel)."""

import os
import pandas as pd

def create_sample_datasets():
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample_data")
    os.makedirs(data_dir, exist_ok=True)

    # 1. Dataset with Flagged Items (Demonstrating all audit rules)
    flagged_records = [
        {
            "transaction_id": "EXP-101",
            "employee_id": "EMP-101",
            "date": "2026-10-10",
            "category": "Meals",
            "description": "Client luncheon discussion",
            "amount": 850.0,
            "receipt_attached": "Yes",
        },
        {
            "transaction_id": "EXP-102",
            "employee_id": "EMP-102",
            "date": "2026-10-11",
            "category": "Meals",
            "description": "Executive team celebration dinner",
            "amount": 2850.0,  # Exceeds Meals limit of 1500
            "receipt_attached": "Yes",
        },
        {
            "transaction_id": "EXP-103",
            "employee_id": "EMP-103",
            "date": "2026-10-12",
            "category": "Travel",
            "description": "Round-trip flight to Delhi office",
            "amount": 8500.0,
            "receipt_attached": "Yes",
        },
        {
            "transaction_id": "EXP-104",
            "employee_id": "EMP-104",
            "date": "2026-10-13",
            "category": "Software",
            "description": "Monthly developer IDE license",
            "amount": 800.0,
            "receipt_attached": "Yes",
        },
        {
            "transaction_id": "EXP-105",
            "employee_id": "EMP-104",
            "date": "2026-10-13",
            "category": "Software",
            "description": "Monthly developer IDE license",
            "amount": 800.0,  # Exact duplicate of EXP-104
            "receipt_attached": "Yes",
        },
        {
            "transaction_id": "EXP-106",
            "employee_id": "EMP-105",
            "date": "2026-10-14",
            "category": "Meals",
            "description": "Working project team lunch",
            "amount": 1250.0,
            "receipt_attached": "No",  # Missing receipt (> 500)
        },
        {
            "transaction_id": "EXP-107",
            "employee_id": "EMP-101",
            "date": "2026-10-14",
            "category": "Office Supplies",
            "description": "Notebooks and pens for workshop",
            "amount": 420.0,  # Valid under threshold
            "receipt_attached": "Yes",
        },
        {
            "transaction_id": "EXP-108",
            "employee_id": "",  # Missing employee_id
            "date": "2026-10-15",
            "category": "Travel",
            "description": "",  # Missing description
            "amount": 1400.0,
            "receipt_attached": "Yes",
        },
        {
            "transaction_id": "EXP-109",
            "employee_id": "EMP-106",
            "date": "2026-10-15",
            "category": "Travel",
            "description": "Fuel reimbursement credit adjustment",
            "amount": -350.0,  # Negative amount
            "receipt_attached": "Yes",
        },
        {
            "transaction_id": "EXP-110",
            "employee_id": "EMP-107",
            "date": "2026-10-16",
            "category": "Entertainment",
            "description": "VIP client hospitality event tickets",
            "amount": 3800.0,  # Exceeds Entertainment limit of 2500
            "receipt_attached": "Yes",
        },
        {
            "transaction_id": "EXP-111",
            "employee_id": "EMP-103",
            "date": "2026-10-13",  # 1 day from EXP-103
            "category": "Travel",
            "description": "Summit conference airfare rebooking",
            "amount": 8500.0,  # Near duplicate amount and employee
            "receipt_attached": "Yes",
        },
        {
            "transaction_id": "EXP-112",
            "employee_id": "EMP-108",
            "date": "2026-10-17",
            "category": "Travel",
            "description": "Airport transfer express taxi",
            "amount": 950.0,
            "receipt_attached": "No",  # Missing receipt (> 500)
        },
        {
            "transaction_id": "EXP-113",
            "employee_id": "EMP-102",
            "date": "2026-10-18",
            "category": "Lodging",
            "description": "3 nights hotel stay during client conference",
            "amount": 13800.0,  # Within lodging limit of 15000
            "receipt_attached": "Yes",
        },
        {
            "transaction_id": "EXP-114",
            "employee_id": "EMP-109",
            "date": "2027-05-15",  # Future date
            "category": "Travel",
            "description": "Next year annual leadership conference",
            "amount": 4200.0,
            "receipt_attached": "Yes",
        },
        {
            "transaction_id": "EXP-115",
            "employee_id": "EMP-110",
            "date": "2026-10-19",
            "category": "Office Supplies",
            "description": "Ergonomic dual-monitor desk mount",
            "amount": 2100.0,  # Within 3000 limit
            "receipt_attached": "Yes",
        },
        {
            "transaction_id": "EXP-116",
            "employee_id": "EMP-105",
            "date": "2026-10-20",
            "category": "Software",
            "description": "Cloud database staging cluster tier",
            "amount": 7200.0,  # Within 8000 limit
            "receipt_attached": "Yes",
        },
    ]

    df_flagged = pd.DataFrame(flagged_records)
    flagged_csv = os.path.join(data_dir, "sample_expenses_flagged.csv")
    flagged_xlsx = os.path.join(data_dir, "sample_expenses_flagged.xlsx")
    df_flagged.to_csv(flagged_csv, index=False)
    df_flagged.to_excel(flagged_xlsx, index=False)
    print(f"Generated {flagged_csv} and {flagged_xlsx}")

    # 2. Dataset with 100% Clean Records (Passing all checks)
    clean_records = [
        {
            "transaction_id": "EXP-201",
            "employee_id": "EMP-201",
            "date": "2026-10-01",
            "category": "Meals",
            "description": "Lunch with prospective vendor partner",
            "amount": 920.0,
            "receipt_attached": "Yes",
        },
        {
            "transaction_id": "EXP-202",
            "employee_id": "EMP-202",
            "date": "2026-10-02",
            "category": "Travel",
            "description": "Train ticket to regional branch office",
            "amount": 1650.0,
            "receipt_attached": "Yes",
        },
        {
            "transaction_id": "EXP-203",
            "employee_id": "EMP-203",
            "date": "2026-10-03",
            "category": "Software",
            "description": "Team project management subscription",
            "amount": 4500.0,
            "receipt_attached": "Yes",
        },
        {
            "transaction_id": "EXP-204",
            "employee_id": "EMP-204",
            "date": "2026-10-04",
            "category": "Office Supplies",
            "description": "Whiteboards and markers for sprint room",
            "amount": 1200.0,
            "receipt_attached": "Yes",
        },
        {
            "transaction_id": "EXP-205",
            "employee_id": "EMP-205",
            "date": "2026-10-05",
            "category": "Lodging",
            "description": "Corporate discount hotel single room",
            "amount": 8900.0,
            "receipt_attached": "Yes",
        },
        {
            "transaction_id": "EXP-206",
            "employee_id": "EMP-201",
            "date": "2026-10-06",
            "category": "Meals",
            "description": "Breakfast during airport layover",
            "amount": 350.0,
            "receipt_attached": "No",  # < 500, exempt from receipt
        },
        {
            "transaction_id": "EXP-207",
            "employee_id": "EMP-206",
            "date": "2026-10-07",
            "category": "Travel",
            "description": "Client site taxi fare round trip",
            "amount": 780.0,
            "receipt_attached": "Yes",
        },
        {
            "transaction_id": "EXP-208",
            "employee_id": "EMP-207",
            "date": "2026-10-08",
            "category": "Office Supplies",
            "description": "Printer ink cartridges for finance department",
            "amount": 2450.0,
            "receipt_attached": "Yes",
        },
        {
            "transaction_id": "EXP-209",
            "employee_id": "EMP-208",
            "date": "2026-10-09",
            "category": "Software",
            "description": "SSL digital certificate renewal",
            "amount": 2100.0,
            "receipt_attached": "Yes",
        },
        {
            "transaction_id": "EXP-210",
            "employee_id": "EMP-209",
            "date": "2026-10-10",
            "category": "Entertainment",
            "description": "Client networking coffee meeting",
            "amount": 650.0,
            "receipt_attached": "Yes",
        },
    ]

    df_clean = pd.DataFrame(clean_records)
    clean_csv = os.path.join(data_dir, "sample_expenses_clean.csv")
    clean_xlsx = os.path.join(data_dir, "sample_expenses_clean.xlsx")
    df_clean.to_csv(clean_csv, index=False)
    df_clean.to_excel(clean_xlsx, index=False)
    print(f"Generated {clean_csv} and {clean_xlsx}")

if __name__ == "__main__":
    create_sample_datasets()
