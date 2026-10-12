"""
End-to-end smoke test against a *running* stack (backend :8000, frontend :5173).

Logs in as every demo role (from `seed_demo`), checks what each role may and may not
access, and confirms seeded images are served. Standard library only.

Usage (from backend/):  .venv\\Scripts\\python scripts\\smoke_test.py
"""

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta

API = os.environ.get("API_URL", "http://127.0.0.1:8000/api/v1")
FRONTEND = os.environ.get("FRONTEND_URL", "http://127.0.0.1:5173")

ACCOUNTS = {
    "SUPER_ADMIN": ("superadmin@medicine.demo", "SuperAdmin@123"),
    "ADMIN": ("admin@medicine.demo", "Admin@123"),
    "SALES_MANAGER": ("manager@medicine.demo", "Manager@123"),
    "SALES_EXECUTIVE": ("sales1@medicine.demo", "Sales@123"),
    "DOCTOR": ("doctor1@medicine.demo", "Doctor@123"),
    "PATIENT": ("patient1@medicine.demo", "Patient@123"),
}

# endpoint -> set of roles expected to get HTTP 200 (everyone else must get 403)
ACCESS_MATRIX = {
    "/auth/me/": set(ACCOUNTS),
    "/products/": set(ACCOUNTS),
    "/doctors/": set(ACCOUNTS),
    "/consultations/": set(ACCOUNTS),
    "/patients/": set(ACCOUNTS),  # scoped: sales roles simply get an empty list
    "/clinical/summary/": set(ACCOUNTS),
    "/leads/": {"SUPER_ADMIN", "ADMIN", "SALES_MANAGER", "SALES_EXECUTIVE"},
    "/followups/": {"SUPER_ADMIN", "ADMIN", "SALES_MANAGER", "SALES_EXECUTIVE"},
    "/campaigns/": {"SUPER_ADMIN", "ADMIN", "SALES_MANAGER", "SALES_EXECUTIVE"},
    "/dashboard/summary/": {"SUPER_ADMIN", "ADMIN", "SALES_MANAGER", "SALES_EXECUTIVE"},
    "/users/": {"SUPER_ADMIN", "ADMIN"},
    "/roles/": {"SUPER_ADMIN", "ADMIN"},
    "/patients/me/": {"PATIENT"},  # others: 404 (no patient profile)
    "/doctors/me/": {"DOCTOR"},  # others: 404 (no doctor profile)
    "/notifications/": set(ACCOUNTS),
    "/notifications/unread-count/": set(ACCOUNTS),
    "/documents/": set(ACCOUNTS),  # scoped like patients
    "/vitals/": set(ACCOUNTS),
    "/audit-logs/": {"SUPER_ADMIN", "ADMIN"},
    "/users/assignable/": {"SUPER_ADMIN", "ADMIN", "SALES_MANAGER"},
}
NOT_FOUND_FOR_OTHERS = {"/patients/me/", "/doctors/me/"}

# Expected number of patient records each role can see with the seed data.
EXPECTED_PATIENT_COUNTS = {
    "SUPER_ADMIN": 6,
    "ADMIN": 6,
    "SALES_MANAGER": 0,
    "SALES_EXECUTIVE": 0,
    "DOCTOR": 2,
    "PATIENT": 1,
}

failures = []
checks = 0


def request(method, url, token=None, body=None):
    # Python on Windows resolves "localhost" to IPv6 first (~2s stall per call).
    url = url.replace("//localhost:", "//127.0.0.1:")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
            ctype = resp.headers.get("Content-Type", "")
            return resp.status, (json.loads(raw) if raw and "json" in ctype else raw)
    except urllib.error.HTTPError as exc:
        return exc.code, None


def check(condition, label):
    global checks
    checks += 1
    status = "PASS" if condition else "FAIL"
    if not condition:
        failures.append(label)
    print(f"  [{status}] {label}")


def main():
    print(f"API: {API}")
    status, _ = request("GET", f"{API}/public/products/")
    check(status == 200, "backend reachable (public product catalogue)")

    try:
        with urllib.request.urlopen(FRONTEND, timeout=10) as resp:
            check(resp.status == 200, f"frontend reachable at {FRONTEND}")
    except OSError:
        check(False, f"frontend reachable at {FRONTEND}")

    status, _ = request("POST", f"{API}/auth/login/", body={"email": "x@y.z", "password": "bad"})
    check(status == 401, "invalid login rejected (401)")

    tokens = {}
    for role, (email, password) in ACCOUNTS.items():
        print(f"\n== {role} ({email})")
        status, data = request(
            "POST", f"{API}/auth/login/", body={"email": email, "password": password}
        )
        check(status == 200, "login succeeds")
        if status != 200:
            continue
        tokens[role] = data["access"]
        check(data["user"]["role"] == role, f"login reports role {role}")
        check(role in data["user"]["roles"], "roles list contains role")

        for path, allowed in ACCESS_MATRIX.items():
            status, _ = request("GET", f"{API}{path}", tokens[role])
            if role in allowed:
                check(status == 200, f"GET {path} -> 200 (got {status})")
            else:
                expected = 404 if path in NOT_FOUND_FOR_OTHERS else 403
                check(status == expected, f"GET {path} -> {expected} (got {status})")

        status, data = request("GET", f"{API}/patients/", tokens[role])
        if status == 200:
            count = data["data"]["count"]
            check(
                count == EXPECTED_PATIENT_COUNTS[role],
                f"sees {EXPECTED_PATIENT_COUNTS[role]} patient(s) (got {count})",
            )

    print("\n== write permissions")
    if "PATIENT" in tokens:
        status, _ = request(
            "POST",
            f"{API}/consultations/",
            tokens["PATIENT"],
            {
                "patient_id": "00000000-0000-0000-0000-000000000000",
                "scheduled_at": "2030-01-01T10:00:00Z",
            },
        )
        check(status == 403, "patient cannot create consultations (403)")
    if "DOCTOR" in tokens:
        status, data = request("GET", f"{API}/products/", tokens["DOCTOR"])
        product_id = data["data"]["results"][0]["id"]
        status, _ = request(
            "PATCH", f"{API}/products/{product_id}/", tokens["DOCTOR"], {"pack_size": "x"}
        )
        check(status == 403, "doctor cannot edit products (403)")
        status, data = request("GET", f"{API}/consultations/?status=SCHEDULED", tokens["DOCTOR"])
        consult = data["data"]["results"][0]
        status, _ = request(
            "PATCH",
            f"{API}/consultations/{consult['id']}/",
            tokens["DOCTOR"],
            {"recommendations": consult["recommendations"]},
        )
        check(status == 200, "doctor can update own consultation (200)")
    if "ADMIN" in tokens:
        status, data = request("GET", f"{API}/users/?role=SUPER_ADMIN", tokens["ADMIN"])
        super_id = data["data"]["results"][0]["id"]
        status, _ = request(
            "POST", f"{API}/users/{super_id}/roles/", tokens["ADMIN"], {"roles": ["PATIENT"]}
        )
        check(status == 403, "admin cannot change a super admin's roles (403)")
        status, data = request("GET", f"{API}/roles/", tokens["ADMIN"])
        check(len(data["data"]) == 6, "roles table has 6 roles")

    print("\n== booking flow (patient books, doctor cancels to free the slot)")
    if "PATIENT" in tokens and "DOCTOR" in tokens:
        status, data = request("GET", f"{API}/doctors/", tokens["PATIENT"])
        doctor = next(
            d for d in data["data"]["results"] if d["user"]["email"] == ACCOUNTS["DOCTOR"][0]
        )
        booked = None
        for days_ahead in range(20, 40):
            day = (date.today() + timedelta(days=days_ahead)).isoformat()
            status, data = request(
                "GET", f"{API}/doctors/{doctor['id']}/slots/?date={day}", tokens["PATIENT"]
            )
            free = [s for s in data["data"]["slots"] if s["available"]]
            if free:
                status, booked = request(
                    "POST",
                    f"{API}/consultations/book/",
                    tokens["PATIENT"],
                    {
                        "doctor_id": doctor["user"]["id"],
                        "scheduled_at": free[0]["start"],
                        "mode": "VIDEO",
                        "chief_complaint": "Smoke test booking",
                    },
                )
                break
        check(status == 201 and booked is not None, f"patient books an open slot (got {status})")
        if booked:
            consult_id = booked["data"]["id"]
            status, data = request("GET", f"{API}/notifications/?page_size=5", tokens["DOCTOR"])
            titles = [n["title"] for n in data["data"]["results"]]
            check("New consultation booked" in titles, "doctor receives booking notification")
            status, _ = request(
                "POST",
                f"{API}/consultations/{consult_id}/prescription/",
                tokens["PATIENT"],
                {"items": []},
            )
            check(status == 403, "patient cannot write prescriptions (403)")
            status, data = request(
                "POST",
                f"{API}/consultations/{consult_id}/prescription/",
                tokens["DOCTOR"],
                {"items": [{"medicine": "Smoke test medicine", "dosage": "1"}]},
            )
            check(
                status == 200 and len(data["data"]["prescription_items"]) == 1,
                "doctor saves prescription",
            )
            status, _ = request(
                "PATCH",
                f"{API}/consultations/{consult_id}/",
                tokens["DOCTOR"],
                {"status": "CANCELLED"},
            )
            check(status == 200, "doctor cancels the smoke-test booking")
            # Leave no trace in the demo data (admins may delete consultations).
            status, _ = request("DELETE", f"{API}/consultations/{consult_id}/", tokens["ADMIN"])
            check(status == 204, "admin deletes the smoke-test booking (204)")

    print("\n== seeded clinical data")
    if "PATIENT" in tokens:
        status, data = request("GET", f"{API}/vitals/", tokens["PATIENT"])
        check(
            data["data"]["count"] >= 10, f"patient has vitals history (got {data['data']['count']})"
        )
        status, data = request("GET", f"{API}/documents/", tokens["PATIENT"])
        docs = data["data"]["results"]
        check(len(docs) >= 2, f"patient has documents (got {len(docs)})")
        pdf = next((d for d in docs if d["file"].endswith(".pdf")), None)
        if pdf:
            status, body = request("GET", pdf["file"])
            check(
                status == 200 and isinstance(body, bytes) and body[:4] == b"%PDF",
                "lab report served as PDF",
            )
    status, data = request("GET", f"{API}/public/doctors/")
    check(
        status == 200 and len(data) >= 3 and "registration_number" not in data[0],
        "public doctor list is safe",
    )

    print("\n== images")
    status, data = request("GET", f"{API}/public/products/")
    media = data["results"][0]["media"] if isinstance(data, dict) and "results" in data else []
    if not media and isinstance(data, dict):
        media = data.get("data", {}).get("results", [{}])[0].get("media", [])
    check(len(media) >= 3, f"product has >= 3 images (got {len(media)})")
    if media:
        status, body = request("GET", media[0]["file"])
        check(
            status == 200 and isinstance(body, bytes) and body[:4] == b"\x89PNG",
            "product image served as PNG",
        )
    if "PATIENT" in tokens:
        status, data = request("GET", f"{API}/doctors/", tokens["PATIENT"])
        photo = data["data"]["results"][0]["photo"]
        status, body = request("GET", photo)
        check(
            status == 200 and isinstance(body, bytes) and body[:4] == b"\x89PNG",
            "doctor photo served as PNG",
        )

    print(f"\n{checks - len(failures)}/{checks} checks passed")
    if failures:
        print("FAILED:")
        for label in failures:
            print(f"  - {label}")
        sys.exit(1)


if __name__ == "__main__":
    main()
