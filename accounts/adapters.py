from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from allauth.account.adapter import DefaultAccountAdapter

ALLOWED_EMAIL_DOMAIN = "nung.edu.ua"


class NungAccountAdapter(DefaultAccountAdapter):
    def clean_email(self, email):
        email = super().clean_email(email)
        domain = email.rpartition("@")[2].lower()
        if domain != ALLOWED_EMAIL_DOMAIN:
            raise ValidationError(
                _("Registration is only allowed with an @%(domain)s email address."),
                params={"domain": ALLOWED_EMAIL_DOMAIN},
            )
        return email
