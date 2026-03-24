"""
Seed script — creates all staff accounts for CraveCall engine.
Run once after server is up:
  python seed_staff.py
"""
import asyncio
import httpx

API_BASE = "http://127.0.0.1:8000/api/v1"

STAFF = [
    {
        "firstName": "Sales",
        "lastName":  "Rep",
        "email":     "sales@cravecall.com",
        "password":  "Staff@1234",
        "role":      "sales_rep",
        "phone":     "+1 617 000 0001",
    },
    {
        "firstName": "Operations",
        "lastName":  "Manager",
        "email":     "ops@cravecall.com",
        "password":  "Staff@1234",
        "role":      "operations_manager",
        "phone":     "+1 617 000 0002",
    },
    {
        "firstName": "Catering",
        "lastName":  "Manager",
        "email":     "catering@cravecall.com",
        "password":  "Staff@1234",
        "role":      "catering_manager",
        "phone":     "+1 617 000 0003",
    },
    {
        "firstName": "Business",
        "lastName":  "Owner",
        "email":     "owner@cravecall.com",
        "password":  "Owner@1234",
        "role":      "business_owner",
        "phone":     "+1 617 000 0004",
    },
    {
        "firstName": "System",
        "lastName":  "Admin",
        "email":     "admin@cravecall.com",
        "password":  "Admin@1234",
        "role":      "admin",
        "phone":     "+1 617 000 0005",
    },
]


async def seed():
    async with httpx.AsyncClient() as client:
        for staff in STAFF:
            res  = await client.post(f"{API_BASE}/auth/signup", json=staff)
            data = res.json()
            if res.status_code == 201:
                print(f"✅ Created: {staff['role']} — {staff['email']}")
            elif res.status_code == 409:
                print(f"⚠️  Already exists: {staff['email']}")
            else:
                print(f"❌ Failed: {staff['email']} — {data.get('detail')}")

    print("\n── Credentials ──────────────────────────")
    print(f"{'Role':<22} {'Email':<30} {'Password'}")
    print("-" * 70)
    for s in STAFF:
        print(f"{s['role']:<22} {s['email']:<30} {s['password']}")


if __name__ == "__main__":
    asyncio.run(seed())
