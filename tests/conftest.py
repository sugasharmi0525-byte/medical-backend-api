import pytest
from rest_framework.test import APIClient

from apps.accounts.models import RoleCode, User
from apps.campaigns.models import Campaign, CampaignPlatform
from apps.products.models import Product, ProductStatus


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def super_admin(db):
    return User.objects.create_user(
        email="admin@test.demo", password="TestPass123!", role=RoleCode.SUPER_ADMIN, is_staff=True
    )


@pytest.fixture
def sales_manager(db):
    return User.objects.create_user(
        email="manager@test.demo", password="TestPass123!", role=RoleCode.SALES_MANAGER
    )


@pytest.fixture
def sales_executive(db):
    return User.objects.create_user(
        email="exec@test.demo", password="TestPass123!", role=RoleCode.SALES_EXECUTIVE
    )


@pytest.fixture
def product(db):
    return Product.objects.create(
        name="Medicine Neuro Life",
        slug="medicine-neuro-life",
        status=ProductStatus.ACTIVE,
        selling_price=899,
    )


@pytest.fixture
def campaign(db):
    return Campaign.objects.create(
        name="Test Campaign",
        platform=CampaignPlatform.ORGANIC,
        campaign_code="TEST-001",
        start_date="2026-01-01",
    )


@pytest.fixture
def admin_user(db):
    return User.objects.create_user(
        email="ops@test.demo", password="TestPass123!", role=RoleCode.ADMIN
    )


@pytest.fixture
def doctor(db):
    return User.objects.create_user(
        email="doctor@test.demo", password="TestPass123!", role=RoleCode.DOCTOR
    )


@pytest.fixture
def other_doctor(db):
    return User.objects.create_user(
        email="doctor2@test.demo", password="TestPass123!", role=RoleCode.DOCTOR
    )


@pytest.fixture
def patient(db):
    return User.objects.create_user(
        email="patient@test.demo", password="TestPass123!", role=RoleCode.PATIENT
    )


@pytest.fixture
def other_patient(db):
    return User.objects.create_user(
        email="patient2@test.demo", password="TestPass123!", role=RoleCode.PATIENT
    )


@pytest.fixture(autouse=True)
def _messaging_test_settings(settings):
    """Deliver messages inline, log WhatsApp only, and never touch real providers."""
    settings.NOTIFICATIONS_DELIVERY = "sync"
    settings.WHATSAPP_PROVIDER = "console"
    settings.WHATSAPP_TEST_RECIPIENTS = []
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
