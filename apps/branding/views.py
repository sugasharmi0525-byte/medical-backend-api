from rest_framework import permissions
from rest_framework.views import APIView

from apps.audit.services import log_action
from apps.branding.models import DEFAULT_PRESET, PRESETS, SiteTheme
from apps.branding.serializers import PublicThemeSerializer, SiteThemeSerializer
from common.permissions import IsSuperAdmin
from common.responses import success_response


class PublicThemeView(APIView):
    """GET /api/v1/public/theme/ — the active look, read by every page before sign-in."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request):
        return success_response(PublicThemeSerializer(SiteTheme.load()).data)


class ThemeAdminView(APIView):
    """
    GET    /api/v1/theme/  current theme plus the preset catalogue
    PATCH  /api/v1/theme/  change preset, colours, fonts or corner style
    DELETE /api/v1/theme/  reset to the default Medicine Green theme
    Super Admin only.
    """

    permission_classes = [permissions.IsAuthenticated, IsSuperAdmin]

    def _payload(self, theme):
        data = SiteThemeSerializer(theme).data
        data["presets"] = {key: values for key, values in PRESETS.items()}
        return data

    def get(self, request):
        return success_response(self._payload(SiteTheme.load()))

    def patch(self, request):
        theme = SiteTheme.load()
        old = SiteThemeSerializer(theme).data
        serializer = SiteThemeSerializer(theme, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        theme = serializer.save(updated_by=request.user)
        log_action(
            actor=request.user,
            action="THEME_UPDATED",
            entity_type="SiteTheme",
            entity_id=theme.pk,
            old_values=old,
            new_values=SiteThemeSerializer(theme).data,
            request=request,
        )
        return success_response(self._payload(theme), message="Theme saved.")

    def delete(self, request):
        theme = SiteTheme.load()
        theme.apply_preset(DEFAULT_PRESET)
        theme.updated_by = request.user
        theme.save()
        log_action(
            actor=request.user,
            action="THEME_RESET",
            entity_type="SiteTheme",
            entity_id=theme.pk,
            request=request,
        )
        return success_response(self._payload(theme), message="Theme reset to default.")
