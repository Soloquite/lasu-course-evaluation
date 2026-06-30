from functools import wraps
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin


def role_required(*allowed_roles):
    """Decorator: checks user is authenticated AND has one of the allowed roles.
    Returns 403 for wrong role (not a redirect to login — that's login_required's job)."""
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped(request, *args, **kwargs):
            if request.user.role not in allowed_roles:
                raise PermissionDenied
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator


class RoleRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """CBV mixin: set allowed_roles on the view class."""
    allowed_roles = []

    def test_func(self):
        return self.request.user.role in self.allowed_roles
