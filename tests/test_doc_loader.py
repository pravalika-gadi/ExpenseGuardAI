"""Unit tests for doc_loader universal document & screenshot parser."""

import io
import json
import pytest
from PIL import Image, ImageDraw
import doc_loader


def test_parse_json_records():
    data = [
        {
            "transaction_id": "TX-JSON-1",
            "employee_id": "EMP-01",
            "date": "2026-10-15",
            "category": "Meals",
            "description": "Client dinner",
            "amount": 1250.0,
            "receipt_attached": True,
        }
    ]
    stream = io.StringIO(json.dumps(data))
    df = doc_loader.load_single_file(stream, "test_file.json")
    assert len(df) == 1
    assert df.iloc[0]["transaction_id"] == "TX-JSON-1"
    assert df.iloc[0]["amount"] == 1250.0


def test_parse_csv_records():
    csv_text = (
        "transaction_id,employee_id,date,category,description,amount,receipt_attached\n"
        "TX-CSV-1,EMP-02,2026-10-16,Travel,Cab ride,450.0,True\n"
    )
    stream = io.StringIO(csv_text)
    df = doc_loader.load_single_file(stream, "test_file.csv")
    assert len(df) == 1
    assert df.iloc[0]["transaction_id"] == "TX-CSV-1"


def test_parse_image_ocr():
    img = Image.new("RGB", (400, 200), color="white")
    draw = ImageDraw.Draw(img)
    draw.text((20, 20), "UBER TRIP RECEIPT", fill="black")
    draw.text((20, 50), "Date: 2026-10-18", fill="black")
    draw.text((20, 80), "Total: INR 750.00", fill="black")

    byte_stream = io.BytesIO()
    img.save(byte_stream, format="PNG")
    byte_stream.seek(0)

    df = doc_loader.load_single_file(byte_stream, "uber_receipt.png")
    assert len(df) == 1
    assert bool(df.iloc[0]["receipt_attached"]) is True
    assert df.iloc[0]["amount"] > 0
    assert df.iloc[0]["category"] == "Travel"
