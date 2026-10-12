import pytest
from django.core.management import call_command

from apps.accounts.models import Role, RoleCode, User, UserRole


@pytest.mark.django_db
def test_roles_table_is_seeded_by_migration():
    assert set(Role.objects.values_list("code", flat=True)) == set(RoleCode.values)
    assert Role._meta.db_table == "roles"
    assert UserRole._meta.db_table == "user_roles"


@pytest.mark.django_db
def test_create_user_writes_user_roles_row(doctor):
    assert UserRole.objects.filter(user=doctor, role__code=RoleCode.DOCTOR).count() == 1
    assert doctor.role == RoleCode.DOCTOR
    assert doctor.role_codes == [RoleCode.DOCTOR]


@pytest.mark.django_db
def test_create_superuser_gets_super_admin_role():
    user = User.objects.create_superuser(email="root@test.demo", password="TestPass123!")
    assert user.role == RoleCode.SUPER_ADMIN
    assert user.is_staff and user.is_superuser


@pytest.mark.django_db
def test_multiple_roles_primary_is_highest_privilege(patient):
    patient.add_role(RoleCode.DOCTOR)
    patient = User.objects.get(pk=patient.pk)
    assert patient.role_codes == [RoleCode.DOCTOR, RoleCode.PATIENT]
    assert patient.role == RoleCode.DOCTOR
    assert patient.has_role(RoleCode.PATIENT)


@pytest.mark.django_db
def test_set_roles_replaces_existing(doctor):
    doctor.set_roles([RoleCode.SALES_MANAGER])
    assert list(doctor.user_roles.values_list("role__code", flat=True)) == ["SALES_MANAGER"]
    assert doctor.role == RoleCode.SALES_MANAGER


@pytest.mark.django_db
@pytest.mark.parametrize(
    "email,expected_role",
    [
        ("admin@test.demo", "SUPER_ADMIN"),
        ("ops@test.demo", "ADMIN"),
        ("doctor@test.demo", "DOCTOR"),
        ("patient@test.demo", "PATIENT"),
    ],
)
def test_login_returns_role_and_roles(
    api_client, super_admin, admin_user, doctor, patient, email, expected_role
):
    response = api_client.post(
        "/api/v1/auth/login/", {"email": email, "password": "TestPass123!"}, format="json"
    )
    assert response.status_code == 200
    assert response.data["user"]["role"] == expected_role
    assert response.data["user"]["roles"] == [expected_role]


@pytest.mark.django_db
def test_me_includes_roles(api_client, doctor):
    api_client.force_authenticate(user=doctor)
    response = api_client.get("/api/v1/auth/me/")
    assert response.data["data"]["roles"] == ["DOCTOR"]


# --- role / user management API ---------------------------------------------------------


@pytest.mark.django_db
def test_roles_endpoint_admin_only(api_client, admin_user, doctor):
    api_client.force_authenticate(user=admin_user)
    response = api_client.get("/api/v1/roles/")
    assert response.status_code == 200
    assert len(response.data["data"]) == len(RoleCode.values)

    api_client.force_authenticate(user=doctor)
    assert api_client.get("/api/v1/roles/").status_code == 403


@pytest.mark.django_db
def test_admin_can_create_doctor_user(api_client, admin_user):
    api_client.force_authenticate(user=admin_user)
    response = api_client.post(
        "/api/v1/users/",
        {
            "email": "newdoc@test.demo",
            "first_name": "New",
            "last_name": "Doc",
            "password": "TestPass123!",
            "roles": ["DOCTOR"],
        },
        format="json",
    )
    assert response.status_code == 201, response.data
    assert response.data["data"]["roles"] == ["DOCTOR"]
    user = User.objects.get(email="newdoc@test.demo")
    assert user.check_password("TestPass123!")


@pytest.mark.django_db
def test_admin_cannot_grant_admin_roles(api_client, admin_user, patient):
    api_client.force_authenticate(user=admin_user)
    response = api_client.post(
        "/api/v1/users/",
        {"email": "x@test.demo", "password": "TestPass123!", "roles": ["SUPER_ADMIN"]},
        format="json",
    )
    assert response.status_code == 403
    response = api_client.post(
        f"/api/v1/users/{patient.id}/roles/", {"roles": ["ADMIN"]}, format="json"
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_super_admin_can_change_roles(api_client, super_admin, patient):
    api_client.force_authenticate(user=super_admin)
    response = api_client.post(
        f"/api/v1/users/{patient.id}/roles/", {"roles": ["PATIENT", "DOCTOR"]}, format="json"
    )
    assert response.status_code == 200
    assert response.data["data"]["roles"] == ["DOCTOR", "PATIENT"]
    assert UserRole.objects.get(user=patient, role__code="DOCTOR").assigned_by == super_admin


@pytest.mark.django_db
def test_super_admin_cannot_drop_own_super_admin_role(api_client, super_admin):
    api_client.force_authenticate(user=super_admin)
    response = api_client.post(
        f"/api/v1/users/{super_admin.id}/roles/", {"roles": ["ADMIN"]}, format="json"
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_users_filter_by_role(api_client, admin_user, doctor, other_doctor, patient):
    api_client.force_authenticate(user=admin_user)
    response = api_client.get("/api/v1/users/?role=DOCTOR")
    emails = {row["email"] for row in response.data["data"]["results"]}
    assert emails == {"doctor@test.demo", "doctor2@test.demo"}


@pytest.mark.django_db
@pytest.mark.parametrize("fixture", ["doctor", "patient", "sales_executive"])
def test_non_admins_cannot_manage_users(api_client, request, fixture):
    api_client.force_authenticate(user=request.getfixturevalue(fixture))
    assert api_client.get("/api/v1/users/").status_code == 403


# --- CRM access by role -------------------------------------------------------------------


CRM_ENDPOINTS = [
    "/api/v1/leads/",
    "/api/v1/followups/",
    "/api/v1/campaigns/",
    "/api/v1/dashboard/summary/",
    "/api/v1/reports/leads/",
]


@pytest.mark.django_db
@pytest.mark.parametrize("fixture", ["doctor", "patient"])
@pytest.mark.parametrize("url", CRM_ENDPOINTS)
def test_doctors_and_patients_blocked_from_crm(api_client, request, fixture, url):
    api_client.force_authenticate(user=request.getfixturevalue(fixture))
    assert api_client.get(url).status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("fixture", ["super_admin", "admin_user", "sales_manager"])
@pytest.mark.parametrize("url", CRM_ENDPOINTS)
def test_crm_roles_can_read_crm(api_client, request, fixture, url):
    api_client.force_authenticate(user=request.getfixturevalue(fixture))
    assert api_client.get(url).status_code == 200


@pytest.mark.django_db
def test_admin_can_edit_products_but_doctor_cannot(api_client, admin_user, doctor, product):
    api_client.force_authenticate(user=admin_user)
    url = f"/api/v1/products/{product.id}/"
    assert api_client.patch(url, {"pack_size": "2 packs"}, format="json").status_code == 200
    api_client.force_authenticate(user=doctor)
    assert api_client.get(url).status_code == 200
    assert api_client.patch(url, {"pack_size": "3 packs"}, format="json").status_code == 403


@pytest.mark.django_db
def test_lead_cannot_be_assigned_to_patient(api_client, super_admin, patient, product):
    from apps.leads.models import Lead

    lead = Lead.objects.create(first_name="A", phone="9000000000", product=product)
    api_client.force_authenticate(user=super_admin)
    response = api_client.post(
        f"/api/v1/leads/{lead.id}/assign/", {"assigned_to": str(patient.id)}, format="json"
    )
    assert response.status_code == 400


# --- seed command -------------------------------------------------------------------------


@pytest.mark.django_db
def test_seed_demo_creates_every_role_and_is_idempotent(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    call_command("seed_demo")
    call_command("seed_demo")
    for code in RoleCode.values:
        assert User.objects.filter(roles__code=code).exists(), code
    superadmin = User.objects.get(email="superadmin@medicine.demo")
    assert superadmin.check_password("SuperAdmin@123")
    assert superadmin.is_superuser
    assert User.objects.get(email="doctor1@medicine.demo").doctor_profile.photo
    assert User.objects.get(email="patient1@medicine.demo").patient_profile.assigned_doctor
    assert UserRole.objects.count() == 15
    # Demo images go to the configured storage (the database by default).
    from apps.media_files.models import StoredFile

    on_disk = list(tmp_path.rglob("*.png"))
    assert StoredFile.objects.filter(name__endswith=".png").exists() or on_disk
