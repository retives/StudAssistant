import pytest
from django.contrib.auth import get_user_model

User = get_user_model()

VALID_PASSWORD = "SecureTestPass123!"
SIGNUP_URL = "/accounts/signup/"
LOGIN_URL = "/accounts/login/"


@pytest.fixture
def signup_payload():
    return {
        "email": "student@nung.edu.ua",
        "username": "student",
        "password1": VALID_PASSWORD,
        "password2": VALID_PASSWORD,
    }


@pytest.fixture
def registered_user(client, signup_payload):
    response = client.post(SIGNUP_URL, signup_payload)
    assert response.status_code == 302, response.content
    user = User.objects.get(email=signup_payload["email"])
    return user
