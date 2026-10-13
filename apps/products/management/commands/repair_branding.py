import posixpath

from django.apps import apps
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import CharField, F, FileField, TextField, Value
from django.db.models.functions import Replace

REPLACEMENTS = (
    ("MEDIANCE", "MEDICINE"),
    ("Mediance", "Medicine"),
    ("mediance", "medicine"),
)


class Command(BaseCommand):
    help = "Replace the old brand spelling in database text fields and media paths."

    def add_arguments(self, parser):
        parser.add_argument(
            "--images",
            action="store_true",
            help="Also redraw the demo images that show the brand (product shots, lab reports).",
        )

    @transaction.atomic
    def handle(self, *args, images=False, **options):
        changed_fields = 0
        changed_rows = 0

        for model in apps.get_models():
            for field in model._meta.get_fields():
                if not isinstance(field, CharField | TextField) or not field.concrete:
                    continue

                expression = F(field.name)
                for old, new in REPLACEMENTS:
                    expression = Replace(expression, Value(old), Value(new))
                updated = model.objects.exclude(**{f"{field.name}__isnull": True}).update(
                    **{field.name: expression}
                )
                if updated:
                    changed_fields += 1
                    changed_rows += updated

        media_count = 0
        for model in apps.get_models():
            for field in model._meta.get_fields():
                if not isinstance(field, FileField) or not field.concrete:
                    continue
                for instance in model.objects.exclude(**{f"{field.name}__isnull": True}).iterator():
                    file_field = getattr(instance, field.name)
                    old_name = file_field.name
                    new_name = old_name
                    for old, new in REPLACEMENTS:
                        new_name = new_name.replace(old, new)
                    if old_name == new_name:
                        continue
                    if default_storage.exists(new_name):
                        default_storage.delete(old_name)
                    elif default_storage.exists(old_name):
                        with default_storage.open(old_name, "rb") as source:
                            default_storage.save(new_name, source)
                        default_storage.delete(old_name)
                    setattr(instance, field.name, new_name)
                    instance.save(update_fields=[field.name])
                    media_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Updated {changed_rows} database rows across {changed_fields} fields "
                f"and {media_count} media paths."
            )
        )
        if images:
            redrawn = self._redraw_demo_images()
            self.stdout.write(self.style.SUCCESS(f"Redrew {redrawn} demo image(s)."))

    def _redraw_demo_images(self):
        """Re-render seeded images whose pixels still carry the old name.

        Only files that follow the seed's naming are touched, so real uploads are left alone.
        Each redraw is saved under a new name: /media/ responses are cached as immutable.
        """
        from apps.accounts.management.commands.seed_demo import (
            EXTRA_PRODUCTS,
            LAB_REPORT_ROWS,
            LAB_REPORT_TITLE,
            NEURO_LIFE_SHOTS,
            catalogue_shots,
        )
        from apps.clinical.models import DocumentType, MedicalDocument
        from apps.products.models import ProductMedia, ProductMediaType
        from common.demo_images import product_image, report_pdf

        specs = {spec["slug"]: spec for spec in EXTRA_PRODUCTS}
        count = 0
        media_rows = ProductMedia.objects.select_related("product").filter(
            media_type=ProductMediaType.IMAGE
        )
        for media in media_rows:
            slug, index = media.product.slug, media.sort_order
            if slug == "medicine-neuro-life" and index < len(NEURO_LIFE_SHOTS):
                prefix = f"neuro-life-{index + 1}"
                title, subtitle, top, bottom = NEURO_LIFE_SHOTS[index]
                extra = {}
            elif slug in specs and index < 2:
                spec = specs[slug]
                prefix = f"{slug}-{index + 1}"
                title = spec["name"]
                subtitle, top, bottom = catalogue_shots(spec)[index]
                extra = {"label": spec["label"], "shape": spec["shape"]}
            else:
                continue
            if posixpath.basename(media.file.name).startswith(prefix):
                content = product_image(title, subtitle, top, bottom, f"{prefix}.png", **extra)
                count += self._replace_file(media, "file", content)

        documents = MedicalDocument.objects.select_related("patient__user").filter(
            document_type=DocumentType.LAB_REPORT
        )
        for doc in documents:
            if posixpath.basename(doc.file.name).startswith("blood-report-"):
                name = f"blood-report-{doc.patient.patient_code.lower()}.pdf"
                content = report_pdf(
                    LAB_REPORT_TITLE, doc.patient.user.full_name, LAB_REPORT_ROWS, name
                )
                count += self._replace_file(doc, "file", content)
        return count

    @staticmethod
    def _replace_file(instance, field_name, content):
        field_file = getattr(instance, field_name)
        old_name = field_file.name
        field_file.save(content.name, content, save=True)  # storage picks a free (new) name
        if old_name and old_name != field_file.name:
            default_storage.delete(old_name)
        return 1
