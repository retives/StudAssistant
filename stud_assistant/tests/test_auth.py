import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from tests.conftest import LOGIN_URL, SIGNUP_URL, VALID_PASSWORD

User = get_user_model()
pytestmark = pytest.mark.django_db


class TestSignup:
    def test_signup_success(self, client, signup_payload):
        response = client.post(SIGNUP_URL, signup_payload)

        assert response.status_code == 302
        assert response.url == reverse("chat_home")
        user = User.objects.get(email=signup_payload["email"])
        assert user.username == signup_payload["username"]
        assert user.check_password(VALID_PASSWORD)

    def test_signup_password_mismatch(self, client, signup_payload):
        signup_payload["password2"] = "DifferentPass123!"

        response = client.post(SIGNUP_URL, signup_payload)

        assert response.status_code == 200
        assert not User.objects.filter(email=signup_payload["email"]).exists()

    def test_signup_wrong_email_domain(self, client, signup_payload):
        signup_payload["email"] = "student@gmail.com"

        response = client.post(SIGNUP_URL, signup_payload)

        assert response.status_code == 200
        assert not User.objects.filter(email=signup_payload["email"]).exists()
        assert b"nung.edu.ua" in response.content


class TestLogin:
    def test_login_success(self, client, registered_user, signup_payload):
        client.logout()
        response = client.post(
            LOGIN_URL,
            {
                "login": signup_payload["username"],
                "password": VALID_PASSWORD,
            },
        )

        assert response.status_code == 302
        assert response.url == reverse("chat_home")

    def test_login_wrong_password(self, client, registered_user, signup_payload):
        client.logout()
        response = client.post(
            LOGIN_URL,
            {
                "login": signup_payload["email"],
                "password": "WrongPassword123!",
            },
        )

        assert response.status_code == 200
        assert not response.wsgi_request.user.is_authenticated
