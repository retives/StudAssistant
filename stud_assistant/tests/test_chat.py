import pytest
from django.urls import reverse

from rag.models import Chat

pytestmark = pytest.mark.django_db


class TestChatCreate:
    def test_chat_create_requires_login(self, client):
        response = client.post(reverse("chat_create"))

        assert response.status_code == 302
        assert "/accounts/login" in response.url

    def test_chat_create_creates_chat(self, client, registered_user):
        response = client.post(reverse("chat_create"))

        assert response.status_code == 302
        chat = Chat.objects.get(user=registered_user)
        assert chat.name == "New Chat"
        assert response.url == reverse("chat_page", kwargs={"chat_id": chat.id})

    def test_chat_create_reuses_empty_chat(self, client, registered_user):
        first = client.post(reverse("chat_create"))
        assert Chat.objects.filter(user=registered_user).count() == 1

        second = client.post(reverse("chat_create"))

        assert Chat.objects.filter(user=registered_user).count() == 1
        assert second.url == first.url
