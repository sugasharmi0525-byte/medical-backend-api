from django.db import transaction
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.accounts.auth_serializers import MedicineTokenObtainPairSerializer
from apps.accounts.models import Role, RoleCode, User
from apps.accounts.serializers import (
    ChangePasswordSerializer,
    PatientRegistrationSerializer,
    ProfileUpdateSerializer,
    RoleSerializer,
    UserCreateSerializer,
    UserRolesUpdateSerializer,
    UserSerializer,
    UserUpdateSerializer,
)
from apps.audit.services import log_action
from apps.clinical.models import PatientProfile
from apps.notifications.models import MessageEvent, NotificationCategory
from apps.notifications.services import dispatch, preferences_for
from common.mixins import EnvelopeMixin
from common.permissions import IsAdmin, IsSalesManagerOrAbove
from common.responses import success_response


class LoginView(TokenObtainPairView):
    serializer_class = MedicineTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            user_id = response.data.get("user", {}).get("id", "")
            log_action(
                actor=User.objects.filter(id=user_id).first() if user_id else None,
                action="LOGIN",
                entity_type="User",
                entity_id=user_id,
                request=request,
            )
        return response


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            raise ValidationError({"refresh": ["This field is required."]})
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except TokenError as exc:
            raise ValidationError({"refresh": ["Invalid or expired token."]}) from exc
        return success_response(message="Logged out successfully.")


class MeView(EnvelopeMixin, APIView):
    permission_classes = [IsAuthenticated]
    success_message = "OK"

    def get(self, request):
        return success_response(UserSerializer(request.user).data)

    def patch(self, request):
        serializer = ProfileUpdateSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return success_response(serializer.data, message="Profile updated.")


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save(update_fields=["password", "updated_at"])
        log_action(
            actor=request.user,
            action="PASSWORD_CHANGED",
            entity_type="User",
            entity_id=request.user.id,
            request=request,
        )
        return success_response(message="Password changed.")


class PatientRegisterView(APIView):
    """POST /api/v1/auth/register/ — public self sign-up; always creates a PATIENT."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "register"

    def post(self, request):
        serializer = PatientRegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        with transaction.atomic():
            user = User.objects.create_user(
                email=data["email"],
                password=data["password"],
                first_name=data["first_name"],
                last_name=data["last_name"],
                phone=data["phone"],
                role=RoleCode.PATIENT,
            )
            PatientProfile.objects.create(
                user=user,
                date_of_birth=data.get("date_of_birth"),
                gender=data["gender"],
                city=data["city"],
            )
        prefs = preferences_for(user)
        if data["whatsapp_opt_in"] and data["phone"]:
            prefs.whatsapp_enabled = True
            prefs.whatsapp_opt_in_at = timezone.now()
            prefs.save(update_fields=["whatsapp_enabled", "whatsapp_opt_in_at", "updated_at"])
        dispatch(
            MessageEvent.WELCOME,
            user=user,
            link="/book",
            in_app={
                "title": "Welcome to Medicine Neuro Life",
                "message": "Your patient account is ready. You can now book a consultation.",
            },
            category=NotificationCategory.ACCOUNT,
        )
        log_action(
            actor=user,
            action="PATIENT_REGISTERED",
            entity_type="User",
            entity_id=user.id,
            request=request,
        )
        return success_response(
            UserSerializer(user).data, message="Account created.", status_code=201
        )


class AssignableUsersView(APIView):
    """GET /api/v1/users/assignable/ — sales staff that leads can be assigned to."""

    permission_classes = [IsAuthenticated, IsSalesManagerOrAbove]

    def get(self, request):
        users = (
            User.objects.filter(
                is_active=True,
                roles__code__in=[RoleCode.SALES_MANAGER, RoleCode.SALES_EXECUTIVE],
            )
            .distinct()
            .order_by("first_name", "last_name")
        )
        return success_response(
            [{"id": str(u.id), "full_name": u.full_name, "email": u.email} for u in users]
        )


def _check_can_grant(actor, codes):
    """Only a Super Admin may grant the SUPER_ADMIN or ADMIN roles."""
    if not actor.has_role(RoleCode.SUPER_ADMIN) and set(codes) & {
        RoleCode.SUPER_ADMIN,
        RoleCode.ADMIN,
    }:
        raise PermissionDenied("Only a Super Admin can grant admin roles.")


class RoleViewSet(EnvelopeMixin, viewsets.ReadOnlyModelViewSet):
    """GET /api/v1/roles/ — the rows of the `roles` table."""

    queryset = Role.objects.all()
    serializer_class = RoleSerializer
    permission_classes = [IsAuthenticated, IsAdmin]
    pagination_class = None


class UserViewSet(EnvelopeMixin, viewsets.ModelViewSet):
    """User management for Super Admin / Admin. Roles are stored in `user_roles`."""

    permission_classes = [IsAuthenticated, IsAdmin]
    search_fields = ["email", "first_name", "last_name", "phone"]
    ordering_fields = ["created_at", "email"]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        queryset = User.objects.prefetch_related("roles")
        role = self.request.query_params.get("role")
        if role:
            queryset = queryset.filter(roles__code=role)
        return queryset.distinct()

    def get_serializer_class(self):
        if self.action == "create":
            return UserCreateSerializer
        if self.action in ("update", "partial_update"):
            return UserUpdateSerializer
        return UserSerializer

    def perform_create(self, serializer):
        _check_can_grant(self.request.user, serializer.validated_data["roles"])
        instance = serializer.save()
        log_action(
            actor=self.request.user,
            action="USER_CREATED",
            entity_type="User",
            entity_id=instance.id,
            new_values={"email": instance.email, "roles": instance.role_codes},
            request=self.request,
        )

    def perform_update(self, serializer):
        target = self.get_object()
        if target.is_super_admin and not self.request.user.is_super_admin:
            raise PermissionDenied("Only a Super Admin can modify a Super Admin.")
        serializer.save()

    @action(detail=True, methods=["post"])
    def roles(self, request, pk=None):
        """POST /api/v1/users/{id}/roles/ {"roles": [...]} — replace the user's roles."""
        user = self.get_object()
        serializer = UserRolesUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        codes = serializer.validated_data["roles"]
        _check_can_grant(request.user, set(codes) | set(user.role_codes))
        if user.pk == request.user.pk and RoleCode.SUPER_ADMIN in user.role_codes:
            if RoleCode.SUPER_ADMIN not in codes:
                raise ValidationError({"roles": ["You cannot remove your own Super Admin role."]})
        old_roles = user.role_codes
        user.set_roles(codes, assigned_by=request.user)
        log_action(
            actor=request.user,
            action="USER_ROLES_UPDATED",
            entity_type="User",
            entity_id=user.id,
            old_values={"roles": old_roles},
            new_values={"roles": user.role_codes},
            request=request,
        )
        return success_response(UserSerializer(user).data, message="Roles updated.")
