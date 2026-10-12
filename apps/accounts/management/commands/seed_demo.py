import random
from datetime import date, datetime, time, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import RoleCode, User
from apps.campaigns.models import Campaign, CampaignPlatform, CampaignStatus
from apps.clinical.models import (
    BloodGroup,
    Consultation,
    ConsultationMode,
    ConsultationStatus,
    DoctorProfile,
    DocumentType,
    Gender,
    MedicalDocument,
    PatientProfile,
    PrescriptionItem,
    VitalReading,
)
from apps.followups.models import FollowUp, FollowUpStatus
from apps.leads.models import Lead, LeadNote, LeadPriority, LeadStatus, LeadStatusHistory
from apps.notifications.models import Notification, NotificationCategory
from apps.products.models import Product, ProductMedia, ProductMediaType, ProductStatus
from common.demo_images import avatar_image, product_image, report_pdf, scan_image

# Development-only demo accounts (nosec) — never used in production.
# Keep in sync with LOGIN_CREDENTIALS.txt in the project root.
DEMO_USERS = [
    ("superadmin@medicine.demo", RoleCode.SUPER_ADMIN, "Super", "Admin", "SuperAdmin@123"),
    ("admin@medicine.demo", RoleCode.ADMIN, "Anjali", "Admin", "Admin@123"),
    ("manager@medicine.demo", RoleCode.SALES_MANAGER, "Manager", "User", "Manager@123"),
    ("sales1@medicine.demo", RoleCode.SALES_EXECUTIVE, "Sales", "One", "Sales@123"),
    ("sales2@medicine.demo", RoleCode.SALES_EXECUTIVE, "Sales", "Two", "Sales@123"),
    ("sales3@medicine.demo", RoleCode.SALES_EXECUTIVE, "Sales", "Three", "Sales@123"),
    ("doctor1@medicine.demo", RoleCode.DOCTOR, "Kavya", "Raghavan", "Doctor@123"),
    ("doctor2@medicine.demo", RoleCode.DOCTOR, "Arvind", "Menon", "Doctor@123"),
    ("doctor3@medicine.demo", RoleCode.DOCTOR, "Farah", "Siddiqui", "Doctor@123"),
    ("patient1@medicine.demo", RoleCode.PATIENT, "Ramesh", "Kumar", "Patient@123"),
    ("patient2@medicine.demo", RoleCode.PATIENT, "Lakshmi", "Iyer", "Patient@123"),
    ("patient3@medicine.demo", RoleCode.PATIENT, "Suresh", "Patel", "Patient@123"),
    ("patient4@medicine.demo", RoleCode.PATIENT, "Deepa", "Nair", "Patient@123"),
    ("patient5@medicine.demo", RoleCode.PATIENT, "Imran", "Khan", "Patient@123"),
    ("patient6@medicine.demo", RoleCode.PATIENT, "Pooja", "Reddy", "Patient@123"),
]

# (email, specialization, qualification, registration no., years, clinic, fee, avatar colour)
DOCTORS = [
    (
        "doctor1@medicine.demo",
        "Neurology",
        "MBBS, MD, DM (Neurology)",
        "DEMO-REG-1001",
        12,
        "Medicine Neuro Clinic (demo)",
        800,
        (37, 99, 235),
    ),
    (
        "doctor2@medicine.demo",
        "Psychiatry",
        "MBBS, MD (Psychiatry)",
        "DEMO-REG-1002",
        9,
        "Medicine Mind Care (demo)",
        700,
        (124, 58, 237),
    ),
    (
        "doctor3@medicine.demo",
        "General Medicine",
        "MBBS, MD (General Medicine)",
        "DEMO-REG-1003",
        15,
        "Medicine Family Clinic (demo)",
        500,
        (5, 150, 105),
    ),
]

# (email, date of birth, gender, blood group, city, state, doctor email, allergies)
PATIENTS = [
    (
        "patient1@medicine.demo",
        date(1968, 4, 12),
        Gender.MALE,
        BloodGroup.B_POS,
        "Bengaluru",
        "Karnataka",
        "doctor1@medicine.demo",
        "None known",
    ),
    (
        "patient2@medicine.demo",
        date(1975, 9, 3),
        Gender.FEMALE,
        BloodGroup.O_POS,
        "Chennai",
        "Tamil Nadu",
        "doctor1@medicine.demo",
        "Penicillin (demo)",
    ),
    (
        "patient3@medicine.demo",
        date(1982, 1, 27),
        Gender.MALE,
        BloodGroup.A_POS,
        "Pune",
        "Maharashtra",
        "doctor2@medicine.demo",
        "None known",
    ),
    (
        "patient4@medicine.demo",
        date(1990, 6, 18),
        Gender.FEMALE,
        BloodGroup.AB_POS,
        "Kochi",
        "Kerala",
        "doctor2@medicine.demo",
        "Dust (demo)",
    ),
    (
        "patient5@medicine.demo",
        date(1959, 11, 30),
        Gender.MALE,
        BloodGroup.O_NEG,
        "Hyderabad",
        "Telangana",
        "doctor3@medicine.demo",
        "None known",
    ),
    (
        "patient6@medicine.demo",
        date(1995, 2, 8),
        Gender.FEMALE,
        BloodGroup.B_NEG,
        "Mumbai",
        "Maharashtra",
        "doctor3@medicine.demo",
        "Sulfa drugs (demo)",
    ),
]

DEMO_NOTE = "Demo record — fictional data for local testing only."

# Extra catalogue items. Names, prices and pack sizes are fictional placeholders; every
# medical field (benefits, usage, precautions, composition) stays as the demo notice until
# the client supplies approved wording.
EXTRA_PRODUCTS = [
    {
        "slug": "medicine-sleep-calm",
        "name": "Medicine Sleep Calm",
        "label": "SLEEP CALM",
        "shape": "bottle",
        "short": "Demo product — night-time wellness capsules. Replace with approved wording.",
        "pack": "30 capsules (demo)",
        "mrp": 749,
        "price": 649,
        "colors": ((124, 92, 246), (76, 29, 149)),
    },
    {
        "slug": "medicine-focus-plus",
        "name": "Medicine Focus Plus",
        "label": "FOCUS PLUS",
        "shape": "box",
        "short": "Demo product — daytime focus tablets. Replace with approved wording.",
        "pack": "60 tablets (demo)",
        "mrp": 899,
        "price": 799,
        "colors": ((217, 119, 6), (146, 64, 14)),
    },
    {
        "slug": "medicine-omega-brain",
        "name": "Medicine Omega Brain",
        "label": "OMEGA BRAIN",
        "shape": "jar",
        "short": "Demo product — omega softgels. Replace with approved wording.",
        "pack": "60 softgels (demo)",
        "mrp": 1199,
        "price": 1049,
        "colors": ((13, 148, 136), (17, 94, 89)),
    },
    {
        "slug": "medicine-b12-complex",
        "name": "Medicine B12 Complex",
        "label": "B12 COMPLEX",
        "shape": "box",
        "short": "Demo product — vitamin B12 tablets. Replace with approved wording.",
        "pack": "30 tablets (demo)",
        "mrp": 499,
        "price": 449,
        "colors": ((219, 39, 119), (131, 24, 67)),
    },
    {
        "slug": "medicine-stress-ease",
        "name": "Medicine Stress Ease",
        "label": "STRESS EASE",
        "shape": "bottle",
        "short": "Demo product — everyday calm capsules. Replace with approved wording.",
        "pack": "30 capsules (demo)",
        "mrp": 799,
        "price": 699,
        "colors": ((2, 132, 199), (7, 89, 133)),
    },
]
COMPLAINTS = [
    "Routine review (demo)",
    "Sleep difficulty (demo)",
    "Headache follow-up (demo)",
    "Memory concerns (demo)",
]

FIRST_NAMES = [
    "Arjun",
    "Priya",
    "Rahul",
    "Sneha",
    "Vikram",
    "Anita",
    "Karan",
    "Divya",
    "Rohan",
    "Meera",
]
LAST_NAMES = [
    "Sharma",
    "Verma",
    "Iyer",
    "Nair",
    "Reddy",
    "Gupta",
    "Kapoor",
    "Menon",
    "Rao",
    "Singh",
]
CITIES = [
    ("Bengaluru", "Karnataka"),
    ("Mumbai", "Maharashtra"),
    ("Chennai", "Tamil Nadu"),
    ("Hyderabad", "Telangana"),
    ("Pune", "Maharashtra"),
    ("Delhi", "Delhi"),
]
SOURCES = ["META", "GOOGLE", "INSTAGRAM", "ORGANIC", "REFERRAL"]


class Command(BaseCommand):
    help = "Seed demo/dummy data for local development and client demos (not for production)."

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("Seeding demo data...")

        users = self._seed_users()
        product = self._seed_product()
        campaigns = self._seed_campaigns()
        self._seed_product_media(product)
        self._seed_catalogue()
        leads = self._seed_leads(users, product, campaigns)
        self._spread_lead_dates()
        self._seed_followups(leads, users)
        self._seed_doctors(users)
        self._seed_patients(users, leads)
        self._seed_consultations()
        self._seed_today_schedule()
        self._seed_prescriptions()
        self._seed_vitals()
        self._seed_documents()
        self._seed_notifications(users)

        self.stdout.write(self.style.SUCCESS("Demo data seeded successfully."))
        self.stdout.write("Demo logins (see LOGIN_CREDENTIALS.txt):")
        for email, role, _first, _last, password in DEMO_USERS:
            self.stdout.write(f"  {role:<16} {email:<28} {password}")

    def _seed_users(self):
        users = {}
        for email, role, first_name, last_name, password in DEMO_USERS:
            user, _ = User.objects.get_or_create(
                email=email,
                defaults={"first_name": first_name, "last_name": last_name},
            )
            user.first_name = first_name
            user.last_name = last_name
            user.is_staff = role == RoleCode.SUPER_ADMIN
            user.is_superuser = role == RoleCode.SUPER_ADMIN
            user.is_active = True
            # Demo accounts always get their documented password back.
            user.set_password(password)
            user.save()
            user.set_roles([role])
            users[email] = user
        return users

    def _seed_product(self):
        demo_notice = "Demo content — replace with client-approved product information."
        product, _ = Product.objects.get_or_create(
            slug="medicine-neuro-life",
            defaults={
                "name": "Medicine Neuro Life",
                "short_description": demo_notice,
                "description": demo_notice,
                "composition": demo_notice,
                "approved_benefits": demo_notice,
                "approved_usage": demo_notice,
                "precautions": demo_notice,
                "manufacturer": "Medicine Neuro Life (demo manufacturer)",
                "pack_size": "1 pack (demo)",
                "mrp": 999,
                "selling_price": 899,
                "gst_percentage": 12,
                "status": ProductStatus.ACTIVE,
            },
        )
        return product

    def _seed_catalogue(self):
        """Extra demo products so the catalogue has variety. All text is placeholder."""
        demo_notice = "Demo content — replace with client-approved product information."
        for spec in EXTRA_PRODUCTS:
            product, _ = Product.objects.get_or_create(
                slug=spec["slug"],
                defaults={
                    "name": spec["name"],
                    "short_description": spec["short"],
                    "description": demo_notice,
                    "composition": demo_notice,
                    "approved_benefits": demo_notice,
                    "approved_usage": demo_notice,
                    "precautions": demo_notice,
                    "manufacturer": "Medicine Neuro Life (demo manufacturer)",
                    "pack_size": spec["pack"],
                    "mrp": spec["mrp"],
                    "selling_price": spec["price"],
                    "gst_percentage": 12,
                    "status": spec.get("status", ProductStatus.ACTIVE),
                },
            )
            if product.media.exists():
                continue
            top, bottom = spec["colors"]
            shots = [
                ("Front view (demo image)", top, bottom),
                ("Pack shot (demo image)", bottom, top),
            ]
            for index, (subtitle, c1, c2) in enumerate(shots):
                ProductMedia.objects.create(
                    product=product,
                    file=product_image(
                        spec["name"],
                        subtitle,
                        c1,
                        c2,
                        f"{spec['slug']}-{index + 1}.png",
                        label=spec["label"],
                        shape=spec["shape"],
                    ),
                    media_type=ProductMediaType.IMAGE,
                    alt_text=f"{spec['name']} — {subtitle}",
                    sort_order=index,
                    is_primary=index == 0,
                )

    def _seed_campaigns(self):
        specs = [
            ("Instagram Launch", CampaignPlatform.INSTAGRAM, "INSTA-LAUNCH-01"),
            ("Facebook Awareness", CampaignPlatform.META, "META-AWARE-01"),
            ("Google Search", CampaignPlatform.GOOGLE, "GOOGLE-SEARCH-01"),
            ("Organic Website", CampaignPlatform.ORGANIC, "ORGANIC-SITE-01"),
            ("WhatsApp Referral", CampaignPlatform.WHATSAPP, "WA-REFERRAL-01"),
        ]
        campaigns = []
        for name, platform, code in specs:
            campaign, _ = Campaign.objects.get_or_create(
                campaign_code=code,
                defaults={
                    "name": name,
                    "platform": platform,
                    "description": f"Demo campaign: {name}",
                    "start_date": timezone.now().date() - timedelta(days=30),
                    "status": CampaignStatus.ACTIVE,
                },
            )
            campaigns.append(campaign)
        return campaigns

    def _seed_leads(self, users, product, campaigns):
        if Lead.objects.count() >= 25:
            return list(Lead.objects.all()[:25])

        sales_execs = [u for email, u in users.items() if u.role == RoleCode.SALES_EXECUTIVE]
        statuses = (
            [LeadStatus.NEW] * 6
            + [LeadStatus.CONTACTED] * 4
            + [LeadStatus.INTERESTED] * 4
            + [LeadStatus.FOLLOW_UP] * 4
            + [LeadStatus.CONVERTED] * 3
            + [LeadStatus.NOT_INTERESTED] * 2
            + [LeadStatus.NO_RESPONSE] * 2
        )
        leads = []
        for i in range(25):
            city, state = random.choice(CITIES)
            first_name = random.choice(FIRST_NAMES)
            last_name = random.choice(LAST_NAMES)
            status = statuses[i % len(statuses)]
            campaign = random.choice(campaigns)
            source = random.choice(SOURCES)
            assigned_to = random.choice(sales_execs) if sales_execs else None

            lead = Lead.objects.create(
                first_name=first_name,
                last_name=last_name,
                phone=f"9{random.randint(100000000, 999999999)}",
                email=f"{first_name.lower()}.{last_name.lower()}{i}@example.demo",
                city=city,
                state=state,
                quantity=random.choice([1, 1, 2, 3]),
                preferred_contact_method=random.choice(["PHONE", "WHATSAPP"]),
                message="Demo enquiry message — sample data only.",
                product=product,
                campaign=campaign,
                source=source,
                medium="paid_social" if source in ("META", "INSTAGRAM") else "organic",
                campaign_name=campaign.name,
                landing_page="https://example.demo/enquiry",
                utm_source=source.lower(),
                utm_medium="paid_social",
                utm_campaign=campaign.campaign_code,
                status=status,
                priority=random.choice(LeadPriority.values),
                assigned_to=assigned_to,
                consent_given=True,
                consent_timestamp=timezone.now(),
            )
            LeadStatusHistory.objects.create(
                lead=lead, old_status=None, new_status=LeadStatus.NEW, note="Lead created (demo)."
            )
            if status != LeadStatus.NEW:
                LeadStatusHistory.objects.create(
                    lead=lead,
                    old_status=LeadStatus.NEW,
                    new_status=status,
                    note="Status updated (demo).",
                )
            LeadNote.objects.create(
                lead=lead,
                created_by=assigned_to,
                note="Demo sales note — fictional content for local testing only.",
            )
            leads.append(lead)
        return leads

    def _seed_followups(self, leads, users):
        if FollowUp.objects.count() >= 15:
            return
        sales_execs = [u for email, u in users.items() if u.role == RoleCode.SALES_EXECUTIVE]
        for i in range(15):
            lead = leads[i % len(leads)]
            scheduled_at = timezone.now() + timedelta(days=random.randint(-3, 7))
            FollowUp.objects.create(
                lead=lead,
                assigned_to=lead.assigned_to
                or (random.choice(sales_execs) if sales_execs else None),
                scheduled_at=scheduled_at,
                status=(
                    FollowUpStatus.PENDING
                    if scheduled_at > timezone.now()
                    else FollowUpStatus.COMPLETED
                ),
                notes="Demo follow-up — fictional content for local testing only.",
            )

    def _seed_product_media(self, product):
        if product.media.exists():
            return
        shots = [
            ("Medicine Neuro Life", "Front view (demo image)", (37, 99, 235), (30, 64, 175)),
            ("Medicine Neuro Life", "Pack shot (demo image)", (13, 148, 136), (17, 94, 89)),
            ("Medicine Neuro Life", "Lifestyle (demo image)", (124, 58, 237), (76, 29, 149)),
        ]
        for index, (title, subtitle, top, bottom) in enumerate(shots):
            ProductMedia.objects.create(
                product=product,
                file=product_image(title, subtitle, top, bottom, f"neuro-life-{index + 1}.png"),
                media_type=ProductMediaType.IMAGE,
                alt_text=f"{title} — {subtitle}",
                sort_order=index,
                is_primary=index == 0,
            )

    def _seed_doctors(self, users):
        for email, specialization, qualification, reg_no, years, clinic, fee, color in DOCTORS:
            user = users[email]
            profile, _ = DoctorProfile.objects.get_or_create(
                user=user,
                defaults={
                    "specialization": specialization,
                    "qualification": qualification,
                    "registration_number": reg_no,
                    "years_of_experience": years,
                    "clinic_name": clinic,
                    "consultation_fee": fee,
                    "bio": f"Dr. {user.full_name} — {DEMO_NOTE}",
                },
            )
            if not profile.photo:
                initials = user.first_name[:1] + user.last_name[:1]
                profile.photo = avatar_image(initials, color, f"doctor-{initials.lower()}.png")
                profile.save(update_fields=["photo", "updated_at"])

    def _seed_patients(self, users, leads):
        converted = [lead for lead in leads if lead.status == LeadStatus.CONVERTED]
        palette = [
            (234, 88, 12),
            (219, 39, 119),
            (2, 132, 199),
            (101, 163, 13),
            (147, 51, 234),
            (220, 38, 38),
        ]
        for index, patient in enumerate(PATIENTS):
            email, dob, gender, blood, city, state, doctor_email, allergies = patient
            user = users[email]
            profile, _ = PatientProfile.objects.get_or_create(
                user=user,
                defaults={
                    "date_of_birth": dob,
                    "gender": gender,
                    "blood_group": blood,
                    "address": f"{index + 1}, Demo Street, {city}",
                    "city": city,
                    "state": state,
                    "emergency_contact_name": f"Family of {user.first_name} (demo)",
                    "emergency_contact_phone": f"90000000{index + 10}",
                    "medical_history": DEMO_NOTE,
                    "allergies": allergies,
                    "current_medications": "None (demo)",
                    "assigned_doctor": users[doctor_email],
                    "source_lead": converted[index] if index < len(converted) else None,
                },
            )
            if not profile.photo:
                initials = user.first_name[:1] + user.last_name[:1]
                profile.photo = avatar_image(
                    initials, palette[index % len(palette)], f"patient-{initials.lower()}.png"
                )
                profile.save(update_fields=["photo", "updated_at"])

    def _seed_consultations(self):
        if Consultation.objects.exists():
            return
        today = timezone.localdate()
        tz = timezone.get_current_timezone()

        def at(days, slot):
            """Clinic-hours timestamp: `days` from today at 10:00 + slot * 30 min."""
            moment = datetime.combine(today + timedelta(days=days), time(10, 0)) + timedelta(
                minutes=30 * (slot % 14)
            )
            return timezone.make_aware(moment, tz)

        profiles = PatientProfile.objects.select_related("user", "assigned_doctor").order_by(
            "user__email"
        )
        for index, profile in enumerate(profiles):
            doctor = profile.assigned_doctor
            Consultation.objects.create(
                patient=profile.user,
                doctor=doctor,
                scheduled_at=at(-(14 + index), index * 3),
                mode=ConsultationMode.IN_PERSON,
                status=ConsultationStatus.COMPLETED,
                chief_complaint=COMPLAINTS[index % len(COMPLAINTS)],
                clinical_notes=DEMO_NOTE,
                recommendations="Review in two weeks (demo).",
                follow_up_date=today + timedelta(days=3 + index),
                created_by=doctor,
            )
            Consultation.objects.create(
                patient=profile.user,
                doctor=doctor,
                scheduled_at=at(3 + index, index * 2 + 1),
                mode=ConsultationMode.VIDEO if index % 2 else ConsultationMode.IN_PERSON,
                status=ConsultationStatus.SCHEDULED,
                chief_complaint="Follow-up review (demo)",
                created_by=doctor,
            )
        # A cancelled visit so every status appears in the UI.
        first = profiles.first()
        if first:
            Consultation.objects.create(
                patient=first.user,
                doctor=first.assigned_doctor,
                scheduled_at=at(-2, 4),
                mode=ConsultationMode.PHONE,
                status=ConsultationStatus.CANCELLED,
                chief_complaint="Cancelled by patient (demo)",
                created_by=first.assigned_doctor,
            )

    def _seed_today_schedule(self):
        """Give every doctor a few consultations today so the doctor home page has content."""
        today = timezone.localdate()
        tz = timezone.get_current_timezone()
        start = timezone.make_aware(datetime.combine(today, time.min), tz)
        for doctor_profile in DoctorProfile.objects.select_related("user"):
            doctor = doctor_profile.user
            if Consultation.objects.filter(
                doctor=doctor, scheduled_at__gte=start, scheduled_at__lt=start + timedelta(days=1)
            ).exists():
                continue
            patients = list(
                PatientProfile.objects.filter(assigned_doctor=doctor).select_related("user")
            )
            if not patients:
                continue
            for index, slot in enumerate([time(10, 30), time(12, 0), time(15, 30)]):
                moment = timezone.make_aware(datetime.combine(today, slot), tz)
                past = moment < timezone.now()
                Consultation.objects.create(
                    patient=patients[index % len(patients)].user,
                    doctor=doctor,
                    scheduled_at=moment,
                    mode=[ConsultationMode.IN_PERSON, ConsultationMode.VIDEO][index % 2],
                    status=ConsultationStatus.COMPLETED if past else ConsultationStatus.SCHEDULED,
                    chief_complaint=COMPLAINTS[index % len(COMPLAINTS)],
                    clinical_notes=DEMO_NOTE if past else "",
                    created_by=doctor,
                )

    def _seed_prescriptions(self):
        lines = [
            ("Demo Tablet A 10 mg", "1 tablet", "Once daily (night)", "30 days", "After food"),
            ("Demo Capsule B 250 mg", "1 capsule", "Twice daily", "14 days", "Placeholder"),
            ("Demo Syrup C", "5 ml", "As needed", "7 days", "Demo only - not advice"),
        ]
        for index, consultation in enumerate(
            Consultation.objects.filter(
                status=ConsultationStatus.COMPLETED, prescription_items=None
            )
        ):
            for order, (medicine, dosage, frequency, duration, instructions) in enumerate(
                lines[: 2 + index % 2]
            ):
                PrescriptionItem.objects.create(
                    consultation=consultation,
                    medicine=medicine,
                    dosage=dosage,
                    frequency=frequency,
                    duration=duration,
                    instructions=instructions,
                    sort_order=order,
                )

    def _seed_vitals(self):
        now = timezone.now()
        for index, profile in enumerate(PatientProfile.objects.order_by("user__email")):
            if profile.vitals.exists():
                continue
            rng = random.Random(index)
            weight = 58 + index * 4
            for week in range(10, -1, -1):
                VitalReading.objects.create(
                    patient=profile,
                    recorded_at=now - timedelta(weeks=week, hours=index),
                    systolic_bp=rng.randint(112, 138),
                    diastolic_bp=rng.randint(72, 88),
                    heart_rate=rng.randint(64, 86),
                    weight_kg=round(weight + rng.uniform(-1.2, 1.2), 1),
                    sleep_hours=round(rng.uniform(5.5, 8.2), 1),
                    notes="Demo reading",
                    recorded_by=profile.assigned_doctor,
                )

    def _seed_documents(self):
        rows = [
            ("Haemoglobin", "13.8 g/dL", "12 - 16"),
            ("Vitamin B12", "410 pg/mL", "200 - 900"),
            ("Vitamin D", "28 ng/mL", "30 - 100"),
            ("Fasting glucose", "92 mg/dL", "70 - 100"),
            ("TSH", "2.1 uIU/mL", "0.4 - 4.0"),
        ]
        for profile in PatientProfile.objects.select_related("user", "assigned_doctor"):
            if profile.documents.exists():
                continue
            slug = profile.patient_code.lower()
            MedicalDocument.objects.create(
                patient=profile,
                title="Blood test report (demo)",
                document_type=DocumentType.LAB_REPORT,
                file=report_pdf(
                    "Blood test report", profile.user.full_name, rows, f"blood-report-{slug}.pdf"
                ),
                notes=DEMO_NOTE,
                uploaded_by=profile.assigned_doctor,
            )
            MedicalDocument.objects.create(
                patient=profile,
                title="Brain MRI (demo image)",
                document_type=DocumentType.SCAN,
                file=scan_image(f"MRI BRAIN - {profile.patient_code}", f"mri-{slug}.png"),
                notes=DEMO_NOTE,
                uploaded_by=profile.assigned_doctor,
            )

    def _seed_notifications(self, users):
        for user in users.values():
            if Notification.objects.filter(recipient=user).exists():
                continue
            items = [
                (
                    "Welcome to Medicine Neuro Life",
                    "Your demo account is ready.",
                    "",
                    NotificationCategory.ACCOUNT,
                ),
            ]
            if user.has_role(RoleCode.DOCTOR):
                items.append(
                    (
                        "Today's schedule is ready",
                        "Open the doctor home page.",
                        "/doctor",
                        NotificationCategory.CONSULTATION,
                    )
                )
            if user.has_role(RoleCode.PATIENT):
                items += [
                    (
                        "New lab report available",
                        "Blood test report (demo)",
                        "/my-health",
                        NotificationCategory.DOCUMENT,
                    ),
                    (
                        "Upcoming consultation",
                        "See My Health for details.",
                        "/my-health",
                        NotificationCategory.CONSULTATION,
                    ),
                ]
            if user.has_role(RoleCode.SALES_EXECUTIVE, RoleCode.SALES_MANAGER):
                items.append(
                    (
                        "Leads waiting",
                        "You have leads to follow up.",
                        "/leads",
                        NotificationCategory.LEAD,
                    )
                )
            for title, message, link, category in items:
                Notification.objects.create(
                    recipient=user, title=title, message=message, link=link, category=category
                )

    def _spread_lead_dates(self):
        """Backdate demo leads over the last 30 days so dashboards show a realistic trend."""
        leads = list(Lead.objects.order_by("lead_number"))
        if not leads:
            return
        oldest = min(lead.created_at for lead in leads)
        if timezone.now() - oldest > timedelta(days=7):
            return  # already spread out
        rng = random.Random(42)
        for index, lead in enumerate(leads):
            created = timezone.now() - timedelta(
                days=(len(leads) - index) * 30 // len(leads), hours=rng.randint(0, 9)
            )
            Lead.objects.filter(pk=lead.pk).update(created_at=created)
            lead.status_history.update(created_at=created)
            lead.notes.update(created_at=created + timedelta(hours=2))
