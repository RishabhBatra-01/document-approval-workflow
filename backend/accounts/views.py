"""Identity and health."""

from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response


@api_view(["GET"])
# No authentication at all. DRF authenticates whenever a token is present,
# even where permission is AllowAny — which made this "dependency-free" check
# verify a token with Supabase and load a profile from the database, the two
# slowest things the service does. A liveness probe must not do either.
@authentication_classes([])
@permission_classes([AllowAny])
def health(request):
    """Liveness only.

    A 200 here means the process is up. It does NOT mean the database,
    Auth or Storage are reachable, and it must never be read as proof that the
    workflow works.
    """
    return Response({"status": "ok"})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    """The verified caller and the role this application granted them."""
    profile = request.user
    return Response(
        {
            "id": str(profile.id),
            "email": profile.email,
            "display_name": profile.display_name,
            "role": profile.role,
        }
    )
