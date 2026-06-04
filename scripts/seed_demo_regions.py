"""
Seed 5 real Indian monitoring regions into the Sentinel API.

Regions:
  1. Tumkur Solar Corridor  — Karnataka (major solar park zone)
  2. Bellary Iron Ore Belt  — Karnataka (mining + construction)
  3. Sundarbans Delta       — West Bengal (deforestation + flooding)
  4. Bhuj Rann              — Gujarat (post-earthquake reconstruction, flooding)
  5. Chilika Lake Catchment — Odisha (flood, deforestation)
"""
import sys
import httpx

API_BASE = "http://localhost:8000/api"

REGIONS = [
    {
        "name": "Tumkur Solar Corridor",
        "geom": {
            "type": "Polygon",
            "coordinates": [[
                [76.9, 13.2],
                [77.4, 13.2],
                [77.4, 13.7],
                [76.9, 13.7],
                [76.9, 13.2],
            ]],
        },
        "detection_types": ["solar", "construction"],
        "cadence": 24,
        "owner_email": "admin@sentinel.app",
    },
    {
        "name": "Bellary Iron Ore Belt",
        "geom": {
            "type": "Polygon",
            "coordinates": [[
                [76.7, 14.8],
                [77.2, 14.8],
                [77.2, 15.3],
                [76.7, 15.3],
                [76.7, 14.8],
            ]],
        },
        "detection_types": ["construction", "deforestation", "fire"],
        "cadence": 24,
        "owner_email": "admin@sentinel.app",
    },
    {
        "name": "Sundarbans Delta",
        "geom": {
            "type": "Polygon",
            "coordinates": [[
                [88.3, 21.5],
                [89.0, 21.5],
                [89.0, 22.1],
                [88.3, 22.1],
                [88.3, 21.5],
            ]],
        },
        "detection_types": ["deforestation", "flood"],
        "cadence": 12,
        "owner_email": "admin@sentinel.app",
    },
    {
        "name": "Bhuj Rann of Kutch",
        "geom": {
            "type": "Polygon",
            "coordinates": [[
                [69.5, 23.2],
                [70.2, 23.2],
                [70.2, 23.7],
                [69.5, 23.7],
                [69.5, 23.2],
            ]],
        },
        "detection_types": ["construction", "flood"],
        "cadence": 24,
        "owner_email": "admin@sentinel.app",
    },
    {
        "name": "Chilika Lake Catchment",
        "geom": {
            "type": "Polygon",
            "coordinates": [[
                [85.1, 19.6],
                [85.6, 19.6],
                [85.6, 20.0],
                [85.1, 20.0],
                [85.1, 19.6],
            ]],
        },
        "detection_types": ["flood", "deforestation", "construction"],
        "cadence": 24,
        "owner_email": "admin@sentinel.app",
    },
]


def seed():
    created = []
    errors = []

    for region in REGIONS:
        try:
            resp = httpx.post(f"{API_BASE}/regions/", json=region, timeout=15)
            if resp.status_code == 201:
                data = resp.json()
                created.append(data)
                print(f"  Created: {data['name']} (id={data['id']})")
            else:
                errors.append((region["name"], resp.status_code, resp.text[:200]))
                print(f"  FAILED {region['name']}: {resp.status_code} {resp.text[:200]}")
        except httpx.ConnectError:
            print(f"\nERROR: Cannot connect to API at {API_BASE}")
            print("Make sure the API is running: docker compose up api")
            sys.exit(1)

    print(f"\n{'='*50}")
    print(f"Seeded {len(created)}/{len(REGIONS)} regions successfully.")
    if errors:
        print(f"Errors:")
        for name, code, msg in errors:
            print(f"  {name}: {code} — {msg}")

    return created


if __name__ == "__main__":
    print("Seeding demo regions into Sentinel API...")
    print(f"Target: {API_BASE}\n")
    seed()
