"""
Fetches all menu items from the active rule version and prints menuName → itemCode mapping.
"""
import asyncio
import httpx

API_URL = "http://127.0.0.1:8000/api/v1/menu-items/version/rv_rest_001_004"

async def extract():
    async with httpx.AsyncClient(timeout=30.0) as client:
        res  = await client.get(API_URL)
        data = res.json()

    items = data if isinstance(data, list) else (data.get("data") or data.get("results") or [])

    print(f"\n{'menuName':<35} {'itemCode'}")
    print("-" * 70)
    for item in items:
        print(f"{item.get('menuName', ''):<35} {item.get('itemCode', '')}")

    print(f"\nTotal: {len(items)} items")

if __name__ == "__main__":
    asyncio.run(extract())
