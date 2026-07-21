from rest_framework.authentication import BaseAuthentication


class PortalRequestUserAuthentication(BaseAuthentication):
    def authenticate(self, request):
        user = getattr(request._request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            return user, getattr(request._request, "auth", None)
        return None
