#!/usr/bin/env python3
"""
JinShi News Query Client

Queries JinShi (金十) financial news via the Chambroad AGI API.
Automatically handles AES key encryption for the request.

Usage:
    python query.py                                    # Last 2 days
    python query.py --start "2026-03-17" --end "2026-03-18"
    python query.py --start "2026-03-17 17:00:00" --end "2026-03-18 23:00:00"
    python query.py --output news.json
"""

import argparse
import base64
import json
import sys
from datetime import datetime

from Crypto.Cipher import AES
import requests


# ── Configuration ──────────────────────────────────────────────
API_URL = "<JINSHI_WORKFLOW_API_URL>"
AUTH_TOKEN = "Bearer app-oeuqZ4yZEruWNNBl4krOrhlk"
SECRET_KEY_B64 = "K3nlUWKurKarvRWICc9PPA=="
TIMEOUT = 60  # seconds


def decrypt_secret_key() -> bytes:
    """Decode the Base64-encoded AES secret key."""
    return base64.b64decode(SECRET_KEY_B64)


def aes_encrypt_timestamp() -> str:
    """
    Encrypt the current timestamp using AES-128-CBC with PKCS7 padding and zero IV.
    
    Returns Base64-encoded string of (IV + ciphertext).
    """
    # Format current time
    plaintext = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    plaintext_bytes = plaintext.encode("utf-8")
    
    # PKCS7 padding
    key = decrypt_secret_key()
    block_size = AES.block_size  # 16 bytes
    padding_len = block_size - (len(plaintext_bytes) % block_size)
    padded = plaintext_bytes + bytes([padding_len] * padding_len)
    
    # AES-128-CBC encrypt with zero IV
    iv = b'\x00' * 16
    cipher = AES.new(key, AES.MODE_CBC, iv)
    ciphertext = cipher.encrypt(padded)
    
    # Prepend IV to ciphertext as required by the API
    combined = iv + ciphertext
    
    # Return Base64-encoded result
    return base64.b64encode(combined).decode("utf-8")


def build_request(startdate: str = None, enddate: str = None) -> dict:
    """Build the API request payload."""
    inputs = {
        "type": "数据查询",
        "key": aes_encrypt_timestamp(),
    }
    
    if startdate:
        inputs["startdate"] = startdate
    if enddate:
        inputs["enddate"] = enddate
    
    return {
        "inputs": inputs,
        "response_mode": "blocking",
        "user": "jinshi-news-query-skill",
    }


def query_news(startdate: str = None, enddate: str = None, output: str = None) -> dict:
    """
    Execute the news query.
    
    Args:
        startdate: Optional start date (e.g. "2026-03-17" or "2026-03-17 17:00:00")
        enddate: Optional end date (e.g. "2026-03-18" or "2026-03-18 23:00:00")
        output: Optional output file path
    
    Returns:
        Parsed JSON response dict
    """
    payload = build_request(startdate, enddate)
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": AUTH_TOKEN,
    }
    
    print(f"[*] Querying JinShi news...", file=sys.stderr)
    if startdate:
        print(f"    Start: {startdate}", file=sys.stderr)
    if enddate:
        print(f"    End:   {enddate}", file=sys.stderr)
    if not startdate and not enddate:
        print(f"    Range: Last 2 days (default)", file=sys.stderr)
    
    response = requests.post(API_URL, json=payload, headers=headers, timeout=TIMEOUT)
    response.raise_for_status()
    
    result = response.json()
    
    if output:
        with open(output, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"[*] Response saved to: {output}", file=sys.stderr)
    
    return result


def main():
    parser = argparse.ArgumentParser(description="Query JinShi (金十) news data")
    parser.add_argument("--start", dest="startdate", help="Start date (e.g. '2026-03-17' or '2026-03-17 17:00:00')")
    parser.add_argument("--end", dest="enddate", help="End date (e.g. '2026-03-18' or '2026-03-18 23:00:00')")
    parser.add_argument("--output", "-o", help="Output file path (JSON)")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON to stdout")
    
    args = parser.parse_args()
    
    try:
        result = query_news(
            startdate=args.startdate,
            enddate=args.enddate,
            output=args.output,
        )
        
        # Always print response to stdout
        if args.pretty:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(json.dumps(result, ensure_ascii=False))
            
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Request failed: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()