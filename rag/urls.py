from django.urls import path

from . import views

urlpatterns = [
    path("", views.chat_home, name="chat_home"),
    path("create/", views.chat_create, name="chat_create"),
    path("<uuid:chat_id>/", views.chat_page, name="chat_page"),
    path("<uuid:chat_id>/send/", views.send_message, name="send_message"),
    path("<uuid:chat_id>/rename/", views.rename_chat, name="rename_chat"),
    path("<uuid:chat_id>/delete", views.delete_chat, name="delete_chat"),
]