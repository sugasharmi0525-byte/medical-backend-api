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

    @transaction.atomic
    def handle(self, *args, **options):
        changed_fields = 0
        changed_rows = 0

        for model in apps.get_models():
            for field in model._meta.get_fields():
                if not isinstance(field, (CharField, TextField)) or not field.concrete:
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