from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models

HEX_COLOR = RegexValidator(r"^#[0-9a-fA-F]{6}$", "Use a 6-digit hex colour such as #D9467A.")


class ThemePreset(models.TextChoices):
    MEDICINE_GREEN = "MEDICINE_GREEN", "Medicine Green"
    ROSE_PLUM = "ROSE_PLUM", "Rose & Plum"
    LAVENDER_CALM = "LAVENDER_CALM", "Lavender Calm"
    PEACH_TEAL = "PEACH_TEAL", "Peach & Teal"
    MAUVE_MINIMAL = "MAUVE_MINIMAL", "Mauve Minimal"
    CUSTOM = "CUSTOM", "Custom"


class HeadingFont(models.TextChoices):
    PLUS_JAKARTA_SANS = "Plus Jakarta Sans", "Plus Jakarta Sans"
    FRAUNCES = "Fraunces", "Fraunces"
    QUICKSAND = "Quicksand", "Quicksand"
    DM_SERIF_DISPLAY = "DM Serif Display", "DM Serif Display"
    PLAYFAIR_DISPLAY = "Playfair Display", "Playfair Display"
    POPPINS = "Poppins", "Poppins"


class BodyFont(models.TextChoices):
    PLUS_JAKARTA_SANS = "Plus Jakarta Sans", "Plus Jakarta Sans"
    NUNITO = "Nunito", "Nunito"
    POPPINS = "Poppins", "Poppins"


class CornerStyle(models.TextChoices):
    STANDARD = "STANDARD", "Standard"
    ROUND = "ROUND", "Extra round"


# Concrete values for each preset (CUSTOM keeps whatever was saved).
PRESETS = {
    ThemePreset.MEDICINE_GREEN: {
        "primary_color": "#0F9D78",
        "accent_color": "#7C5CF6",
        "heading_font": HeadingFont.PLUS_JAKARTA_SANS,
        "body_font": BodyFont.PLUS_JAKARTA_SANS,
        "corner_style": CornerStyle.STANDARD,
    },
    ThemePreset.ROSE_PLUM: {
        "primary_color": "#D9467A",
        "accent_color": "#6B2D5C",
        "heading_font": HeadingFont.FRAUNCES,
        "body_font": BodyFont.NUNITO,
        "corner_style": CornerStyle.ROUND,
    },
    ThemePreset.LAVENDER_CALM: {
        "primary_color": "#8B6CEF",
        "accent_color": "#FF8A7A",
        "heading_font": HeadingFont.QUICKSAND,
        "body_font": BodyFont.NUNITO,
        "corner_style": CornerStyle.ROUND,
    },
    ThemePreset.PEACH_TEAL: {
        "primary_color": "#E0704E",
        "accent_color": "#1F7A7A",
        "heading_font": HeadingFont.DM_SERIF_DISPLAY,
        "body_font": BodyFont.NUNITO,
        "corner_style": CornerStyle.ROUND,
    },
    ThemePreset.MAUVE_MINIMAL: {
        "primary_color": "#B0607E",
        "accent_color": "#4A3F4F",
        "heading_font": HeadingFont.PLAYFAIR_DISPLAY,
        "body_font": BodyFont.PLUS_JAKARTA_SANS,
        "corner_style": CornerStyle.STANDARD,
    },
}

DEFAULT_PRESET = ThemePreset.MEDICINE_GREEN


class SiteTheme(models.Model):
    """Single-row table holding the site-wide look chosen by the Super Admin."""

    preset = models.CharField(max_length=32, choices=ThemePreset.choices, default=DEFAULT_PRESET)
    primary_color = models.CharField(max_length=7, validators=[HEX_COLOR], default="#0F9D78")
    accent_color = models.CharField(max_length=7, validators=[HEX_COLOR], default="#7C5CF6")
    heading_font = models.CharField(
        max_length=40, choices=HeadingFont.choices, default=HeadingFont.PLUS_JAKARTA_SANS
    )
    body_font = models.CharField(
        max_length=40, choices=BodyFont.choices, default=BodyFont.PLUS_JAKARTA_SANS
    )
    corner_style = models.CharField(
        max_length=16, choices=CornerStyle.choices, default=CornerStyle.STANDARD
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="+",
        null=True,
        blank=True,
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "site_theme"

    def __str__(self):
        return f"Site theme ({self.get_preset_display()})"

    @classmethod
    def load(cls):
        theme, _ = cls.objects.get_or_create(pk=1)
        return theme

    def apply_preset(self, preset):
        self.preset = preset
        for field, value in PRESETS.get(preset, {}).items():
            setattr(self, field, value)
