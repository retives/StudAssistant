from django.urls import path

from . import views

urlpatterns = [
    path("settings/", views.account_settings, name="account_settings"),
    path("settings/password/", views.account_password, name="account_password"),
]

