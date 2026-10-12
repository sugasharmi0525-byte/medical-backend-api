import json
from datetime import datetime, time, timedelta
from unittest import mock

import pytest
from django.core import mail
from django.core.management import call_command
from django.utils import timezone

from apps.accounts.models import RoleCode, User
from apps.clinical.models import Consultation, ConsultationStatus, DoctorProfile, PatientProfile
from apps.notifications.models import (
    ContactPreference,
    MessageEvent,
    MessageTemplate,
    Notification,
    NotificationLog,
    NotificationStatus,
)
from apps.notifications.services import dispatch, normalize_whatsapp_number, send_due_reminders


@pytest.fixture
def real_patient(db):
    """A patient on a deliverable domain who opted in to WhatsApp."""
    user = User.objects.create_user(
        email="asha@example.com",
        password="TestPass123!",
        first_name="Asha",
        phone="9876543210",
        role=RoleCode.PATIENT,
    )
    PatientProfile.objects.create(user=user)
    ContactPreference.objects.create(user=user, whatsapp_enabled=True)
    return user


@pytest.fixture
def real_doctor(db):
    user = User.objects.create_user(
        email="dr.rao@example.com",
        password="TestPass123!",
        first_name="Meera",
        last_name="Rao",
        role=RoleCode.DOCTOR,
    )
    DoctorProfile.objects.create(user=user, specialization="Neurology", registration_number="R-9")
    return user


def _tomorrow_at(hour):
    day = timezone.localdate() + timedelta(days=1)
    return timezone.make_aware(datetime.combine(day, time(hour, 0)))


def test_whatsapp_number_normalisation(settings):
    settings.WHATSAPP_DEFAULT_COUNTRY_CODE = "91"
    assert normalize_whatsapp_number("98765 43210") == "919876543210"
    assert normalize_whatsapp_number("+91-98765-43210") == "919876543210"
    assert normalize_whatsapp_number("09876543210") == "919876543210"
    assert normalize_whatsapp_number("12345") == ""


@pytest.mark.django_db
def test_booking_sends_email_and_whatsapp_to_patient(api_client, real_patient, real_doctor):
    api_client.force_authenticate(user=real_patient)
    response = api_client.post(
        "/api/v1/consultations/book/",
        {
            "doctor_id": str(real_doctor.id),
            "scheduled_at": _tomorrow_at(11).isoformat(),
            "mode": "VIDEO",
        },
        format="json",
    )
    assert response.status_code == 201, response.data

    patient_logs = NotificationLog.objects.filter(
        recipient=real_patient, event=MessageEvent.CONSULTATION_BOOKED
    )
    assert {log.channel for log in patient_logs} == {"EMAIL", "WHATSAPP"}
    assert all(log.status == NotificationStatus.SENT for log in patient_logs)
    whatsapp = patient_logs.get(channel="WHATSAPP")
    assert whatsapp.to_address == "919876543210"
    assert "Dr. Meera Rao" in whatsapp.body

    # Patient email + doctor's new-booking email (doctor has not opted in to WhatsApp).
    subjects = [m.subject for m in mail.outbox]
    assert any(s.startswith("Your consultation is confirmed") for s in subjects)
    assert any(s.startswith("New booking: Asha") for s in subjects)
    patient_mail = next(m for m in mail.outbox if m.to == ["asha@example.com"])
    assert "11:00 AM" in patient_mail.body
    assert "http://localhost:5173/consultations/" in patient_mail.body
    assert patient_mail.alternatives and "Open in portal" in patient_mail.alternatives[0][0]


@pytest.mark.django_db
def test_demo_accounts_are_never_contacted(api_client, patient, doctor):
    DoctorProfile.objects.create(user=doctor, specialization="X", registration_number="R-1")
    ContactPreference.objects.create(
        user=patient, whatsapp_enabled=True, whatsapp_number="9876543210"
    )
    api_client.force_authenticate(user=patient)
    api_client.post(
        "/api/v1/consultations/book/",
        {"doctor_id": str(doctor.id), "scheduled_at": _tomorrow_at(12).isoformat()},
        format="json",
    )
    logs = NotificationLog.objects.filter(recipient=patient)
    assert logs.exists()
    assert set(logs.values_list("status", flat=True)) == {NotificationStatus.SKIPPED}
    assert mail.outbox == []
    # The in-app notification still arrives.
    assert Notification.objects.filter(recipient=patient, category="CONSULTATION").exists()


@pytest.mark.django_db
def test_preferences_control_channels(real_patient):
    prefs = real_patient.contact_preference
    prefs.email_enabled = False
    prefs.whatsapp_enabled = False
    prefs.save()
    logs = dispatch(MessageEvent.WELCOME, user=real_patient, link="/book")
    assert logs == []
    assert mail.outbox == []


@pytest.mark.django_db
def test_inactive_template_is_not_sent(real_patient):
    dispatch(MessageEvent.WELCOME, user=real_patient)  # creates default templates
    MessageTemplate.objects.filter(event=MessageEvent.WELCOME, channel="EMAIL").update(
        is_active=False
    )
    mail.outbox.clear()
    logs = dispatch(MessageEvent.WELCOME, user=real_patient)
    assert [log.channel for log in logs] == ["WHATSAPP"]
    assert mail.outbox == []


@pytest.mark.django_db
def test_cancellation_notifies_patient(api_client, real_patient, real_doctor):
    consultation = Consultation.objects.create(
        patient=real_patient, doctor=real_doctor, scheduled_at=_tomorrow_at(15)
    )
    api_client.force_authenticate(user=real_doctor)
    api_client.patch(
        f"/api/v1/consultations/{consultation.id}/", {"status": "CANCELLED"}, format="json"
    )
    assert (
        NotificationLog.objects.filter(
            recipient=real_patient, event=MessageEvent.CONSULTATION_CANCELLED, status="SENT"
        ).count()
        == 2
    )


@pytest.mark.django_db
def test_due_reminders_sent_once(real_patient, real_doctor, settings):
    settings.REMINDER_HOURS_BEFORE = 24
    soon = Consultation.objects.create(
        patient=real_patient, doctor=real_doctor, scheduled_at=timezone.now() + timedelta(hours=5)
    )
    Consultation.objects.create(
        patient=real_patient, doctor=real_doctor, scheduled_at=timezone.now() + timedelta(days=3)
    )
    Consultation.objects.create(
        patient=real_patient,
        doctor=real_doctor,
        scheduled_at=timezone.now() + timedelta(hours=2),
        status=ConsultationStatus.CANCELLED,
    )
    assert send_due_reminders() == 1
    soon.refresh_from_db()
    assert soon.reminder_sent_at is not None
    assert send_due_reminders() == 0
    assert NotificationLog.objects.filter(event=MessageEvent.CONSULTATION_REMINDER).count() == 2
    assert Notification.objects.filter(
        recipient=real_patient, title="Upcoming consultation"
    ).exists()


@pytest.mark.django_db
def test_reminders_respect_opt_out(real_patient, real_doctor):
    real_patient.contact_preference.reminders_enabled = False
    real_patient.contact_preference.save()
    Consultation.objects.create(
        patient=real_patient, doctor=real_doctor, scheduled_at=timezone.now() + timedelta(hours=3)
    )
    send_due_reminders()
    assert not NotificationLog.objects.filter(event=MessageEvent.CONSULTATION_REMINDER).exists()


@pytest.mark.django_db
def test_send_reminders_command(real_patient, real_doctor, capsys):
    Consultation.objects.create(
        patient=real_patient, doctor=real_doctor, scheduled_at=timezone.now() + timedelta(hours=1)
    )
    call_command("send_reminders")
    assert "Sent 1 reminder" in capsys.readouterr().out


@pytest.mark.django_db
def test_public_enquiry_acknowledged(api_client, product):
    response = api_client.post(
        "/api/v1/public/leads/",
        {
            "first_name": "Divya",
            "phone": "9123456780",
            "email": "divya@example.com",
            "preferred_contact_method": "WHATSAPP",
            "product_id": str(product.id),
            "consent_given": True,
        },
        format="json",
    )
    assert response.status_code == 201
    logs = NotificationLog.objects.filter(event=MessageEvent.ENQUIRY_RECEIVED)
    assert {log.channel for log in logs} == {"EMAIL", "WHATSAPP"}
    assert mail.outbox[0].to == ["divya@example.com"]
    assert "MED-" in mail.outbox[0].subject


@pytest.mark.django_db
def test_registration_opt_in_and_welcome(api_client):
    response = api_client.post(
        "/api/v1/auth/register/",
        {
            "email": "nisha@example.com",
            "password": "Strong!Pass42",
            "first_name": "Nisha",
            "phone": "9988776655",
            "consent_given": True,
            "whatsapp_opt_in": True,
        },
        format="json",
    )
    assert response.status_code == 201, response.data
    user = User.objects.get(email="nisha@example.com")
    assert user.contact_preference.whatsapp_enabled is True
    assert user.contact_preference.whatsapp_opt_in_at is not None
    assert NotificationLog.objects.filter(recipient=user, event="WELCOME").count() == 2


@pytest.mark.django_db
def test_meta_whatsapp_provider_uses_template(settings, real_patient):
    settings.WHATSAPP_PROVIDER = "meta"
    settings.WHATSAPP_ACCESS_TOKEN = "token"
    settings.WHATSAPP_PHONE_NUMBER_ID = "12345"
    dispatch(MessageEvent.WELCOME, user=real_patient)  # create templates
    MessageTemplate.objects.filter(event="WELCOME", channel="WHATSAPP").update(
        whatsapp_template_name="welcome_patient"
    )
    NotificationLog.objects.all().delete()

    sent = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return json.dumps({"messages": [{"id": "wamid.TEST"}]}).encode()

    def fake_urlopen(request, timeout):
        sent["url"] = request.full_url
        sent["payload"] = json.loads(request.data)
        sent["auth"] = request.headers["Authorization"]
        return FakeResponse()

    with mock.patch("urllib.request.urlopen", fake_urlopen):
        dispatch(MessageEvent.WELCOME, user=real_patient, link="/book")

    log = NotificationLog.objects.get(channel="WHATSAPP")
    assert log.status == "SENT" and log.provider_message_id == "wamid.TEST"
    assert sent["url"].endswith("/12345/messages")
    assert sent["auth"] == "Bearer token"
    assert sent["payload"]["template"]["name"] == "welcome_patient"
    params = sent["payload"]["template"]["components"][0]["parameters"]
    assert [p["text"] for p in params] == ["Asha", "http://localhost:5173/book"]


@pytest.mark.django_db
def test_provider_failure_is_recorded(settings, real_patient):
    settings.WHATSAPP_PROVIDER = "meta"
    settings.WHATSAPP_ACCESS_TOKEN = ""
    logs = dispatch(MessageEvent.WELCOME, user=real_patient)
    whatsapp = NotificationLog.objects.get(
        pk=next(log.pk for log in logs if log.channel == "WHATSAPP")
    )
    assert whatsapp.status == "FAILED"
    assert "not configured" in whatsapp.error


# --- API ---------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_contact_preferences_api(api_client, patient):
    api_client.force_authenticate(user=patient)
    response = api_client.get("/api/v1/me/contact-preferences/")
    assert response.data["data"]["whatsapp_enabled"] is False
    bad = api_client.patch(
        "/api/v1/me/contact-preferences/", {"whatsapp_number": "12"}, format="json"
    )
    assert bad.status_code == 400
    ok = api_client.patch(
        "/api/v1/me/contact-preferences/",
        {"whatsapp_enabled": True, "whatsapp_number": "9876543210", "reminders_enabled": False},
        format="json",
    )
    assert ok.status_code == 200
    assert ok.data["data"]["whatsapp_opt_in_at"] is not None
    assert ok.data["data"]["reminders_enabled"] is False


@pytest.mark.django_db
@pytest.mark.parametrize("fixture", ["admin_user", "doctor", "patient"])
def test_messaging_admin_is_super_admin_only(api_client, request, fixture):
    api_client.force_authenticate(user=request.getfixturevalue(fixture))
    assert api_client.get("/api/v1/messaging/status/").status_code == 403
    assert api_client.get("/api/v1/messaging/templates/").status_code == 403
    assert (
        api_client.post(
            "/api/v1/messaging/test/", {"channel": "EMAIL", "to": "a@b.com"}, format="json"
        ).status_code
        == 403
    )


@pytest.mark.django_db
def test_admin_can_read_delivery_log_but_patient_cannot(api_client, admin_user, patient):
    api_client.force_authenticate(user=admin_user)
    assert api_client.get("/api/v1/messaging/logs/").status_code == 200
    api_client.force_authenticate(user=patient)
    assert api_client.get("/api/v1/messaging/logs/").status_code == 403


@pytest.mark.django_db
def test_super_admin_manages_templates_and_sends_test(api_client, super_admin):
    api_client.force_authenticate(user=super_admin)
    status = api_client.get("/api/v1/messaging/status/").data["data"]
    assert status["email"]["mode"] == "test" and status["whatsapp"]["provider"] == "console"
    assert "token" not in json.dumps(status).lower()

    templates = api_client.get("/api/v1/messaging/templates/").data["data"]
    assert len(templates) >= 18
    welcome = next(t for t in templates if t["event"] == "WELCOME" and t["channel"] == "EMAIL")
    edited = api_client.patch(
        f"/api/v1/messaging/templates/{welcome['id']}/",
        {"subject": "Hello {first_name}!", "event": "TEST"},
        format="json",
    )
    assert edited.status_code == 200
    assert edited.data["data"]["subject"] == "Hello {first_name}!"
    assert edited.data["data"]["event"] == "WELCOME"  # read-only
    reset = api_client.post(f"/api/v1/messaging/templates/{welcome['id']}/reset/")
    assert reset.data["data"]["subject"] == "Welcome to {site_name}"

    test = api_client.post(
        "/api/v1/messaging/test/", {"channel": "EMAIL", "to": "owner@example.com"}, format="json"
    )
    assert test.status_code == 200
    assert test.data["data"]["status"] == "SENT"
    assert mail.outbox[-1].to == ["owner@example.com"]
    skipped = api_client.post(
        "/api/v1/messaging/test/", {"channel": "EMAIL", "to": "x@medicine.demo"}, format="json"
    )
    assert skipped.data["data"]["status"] == "SKIPPED"
    wa = api_client.post(
        "/api/v1/messaging/test/", {"channel": "WHATSAPP", "to": "9876543210"}, format="json"
    )
    assert wa.data["data"]["status"] == "SENT" and wa.data["data"]["to_address"] == "919876543210"


@pytest.mark.django_db
def test_run_reminders_endpoint(api_client, super_admin, real_patient, real_doctor):
    Consultation.objects.create(
        patient=real_patient, doctor=real_doctor, scheduled_at=timezone.now() + timedelta(hours=2)
    )
    api_client.force_authenticate(user=super_admin)
    response = api_client.post("/api/v1/messaging/reminders/run/")
    assert response.data["data"]["sent"] == 1
