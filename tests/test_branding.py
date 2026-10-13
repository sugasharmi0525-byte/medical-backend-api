import pytest

from apps.audit.models import AuditLog
from apps.branding.models import SiteTheme


@pytest.mark.django_db
def test_public_theme_needs_no_login_and_defaults_to_green(api_client):
    response = api_client.get("/api/v1/public/theme/")
    assert response.status_code == 200
    data = response.data["data"]
    assert data["preset"] == "MEDICINE_GREEN"
    assert data["primary_color"] == "#0F9D78"


@pytest.mark.django_db
@pytest.mark.parametrize("fixture", ["admin_user", "doctor", "patient", "sales_manager"])
def test_only_super_admin_can_manage_theme(api_client, request, fixture):
    api_client.force_authenticate(user=request.getfixturevalue(fixture))
    assert api_client.get("/api/v1/theme/").status_code == 403
    assert (
        api_client.patch("/api/v1/theme/", {"preset": "ROSE_PLUM"}, format="json").status_code
        == 403
    )
    assert api_client.delete("/api/v1/theme/").status_code == 403


@pytest.mark.django_db
def test_super_admin_applies_preset(api_client, super_admin):
    api_client.force_authenticate(user=super_admin)
    response = api_client.patch("/api/v1/theme/", {"preset": "ROSE_PLUM"}, format="json")
    assert response.status_code == 200
    theme = SiteTheme.load()
    assert theme.preset == "ROSE_PLUM"
    assert theme.primary_color == "#D9467A"
    assert theme.heading_font == "Fraunces"
    assert theme.updated_by == super_admin
    assert "presets" in response.data["data"]
    assert AuditLog.objects.filter(action="THEME_UPDATED").exists()
    # Every visitor now receives the new theme.
    public = api_client.get("/api/v1/public/theme/").data["data"]
    assert public["primary_color"] == "#D9467A"


@pytest.mark.django_db
def test_editing_a_value_switches_to_custom(api_client, super_admin):
    api_client.force_authenticate(user=super_admin)
    api_client.patch("/api/v1/theme/", {"preset": "LAVENDER_CALM"}, format="json")
    response = api_client.patch("/api/v1/theme/", {"primary_color": "#aa3366"}, format="json")
    assert response.status_code == 200
    theme = SiteTheme.load()
    assert theme.preset == "CUSTOM"
    assert theme.primary_color == "#AA3366"
    assert theme.heading_font == "Quicksand"  # untouched fields are kept


@pytest.mark.django_db
def test_invalid_values_rejected(api_client, super_admin):
    api_client.force_authenticate(user=super_admin)
    assert (
        api_client.patch("/api/v1/theme/", {"primary_color": "pink"}, format="json").status_code
        == 400
    )
    assert (
        api_client.patch(
            "/api/v1/theme/", {"heading_font": "Comic Sans"}, format="json"
        ).status_code
        == 400
    )
    assert api_client.patch("/api/v1/theme/", {"preset": "NEON"}, format="json").status_code == 400


@pytest.mark.django_db
def test_reset_restores_default(api_client, super_admin):
    api_client.force_authenticate(user=super_admin)
    api_client.patch("/api/v1/theme/", {"preset": "PEACH_TEAL"}, format="json")
    response = api_client.delete("/api/v1/theme/")
    assert response.status_code == 200
    theme = SiteTheme.load()
    assert theme.preset == "MEDICINE_GREEN" and theme.primary_color == "#0F9D78"
    assert AuditLog.objects.filter(action="THEME_RESET").exists()


@pytest.mark.django_db
def test_repair_branding_redraws_only_seeded_brand_images(settings, tmp_path):
    from django.core.files.base import ContentFile
    from django.core.files.storage import default_storage
    from django.core.management import call_command

    from apps.clinical.models import DocumentType, MedicalDocument
    from apps.products.models import Product, ProductMedia

    settings.MEDIA_ROOT = tmp_path
    call_command("seed_demo")
    shot = ProductMedia.objects.get(product__slug="medicine-stress-ease", sort_order=0)
    report = MedicalDocument.objects.filter(document_type=DocumentType.LAB_REPORT).first()
    upload = ProductMedia.objects.create(
        product=Product.objects.get(slug="medicine-stress-ease"),
        file=default_storage.save("products/client-photo.png", ContentFile(b"real")),
        sort_order=5,
    )
    before = {"shot": shot.file.name, "report": report.file.name, "upload": upload.file.name}

    call_command("repair_branding", images=True)

    shot.refresh_from_db()
    report.refresh_from_db()
    upload.refresh_from_db()
    # Redrawn under a new name (old one removed), so browsers can't show a cached copy.
    for key, obj in (("shot", shot), ("report", report)):
        assert obj.file.name != before[key]
        assert default_storage.exists(obj.file.name)
        assert not default_storage.exists(before[key])
    assert upload.file.name == before["upload"]
    assert default_storage.open(upload.file.name).read() == b"real"
