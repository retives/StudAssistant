import logging

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import AbstractUser
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST, require_GET
from accounts.models import User
from .models import Chat, Message
from .agent import StudAgent
# Create your views here.


@login_required
def chat_home(request):
    chats = Chat.objects.filter(user=request.user).order_by("-last_updated")
    return render(
        request,
        "rag/chat_home.html",
        {
            "chats": chats,
            "active_chat": None,
            "last_chat": chats.first(),
        },
    )


@login_required
@require_POST
def chat_create(request):
    chat = Chat.objects.filter(user=request.user).order_by("-last_updated").first()
    if chat.messages.count() == 0:
        return redirect("chat_page", chat_id=chat.id)
    new_chat = Chat.objects.create(user=request.user, name="New Chat")
    return redirect("chat_page", chat_id=new_chat.id)


@login_required
def chat_page(request, chat_id):
    chats = Chat.objects.filter(user=request.user).order_by("-last_updated")
    chat = get_object_or_404(Chat, id=chat_id, user=request.user)
    messages = chat.messages.select_related("sender").all()
    return render(
        request,
        "rag/chat_detail.html",
        {
            "chats": chats,
            "active_chat": chat,
            "messages": messages,
        },
    )


@login_required
@require_POST
def send_message(request, chat_id):
    chat = get_object_or_404(Chat, id=chat_id, user=request.user)
    content = (request.POST.get("message") or "").strip()
    if content:
        Message.objects.create(chat=chat, sender=request.user, content=content)
        # Ask agent
        try:
            agent = StudAgent("Факультет інформаційних технологій", "Інженерія програмного забезпечення", "ІП-22-1")
            response = agent.ask(content, chat_id)
            logging.info("Response successful")
            if chat.name == "New Chat":
                chat.name = agent.get_title(content)
                chat.save()
            Message.objects.create(chat=chat, sender=User.objects.get(id=0), content=response)
        except Exception as e:
            print(e)
        Chat.objects.filter(id=chat.id).update(last_updated=timezone.now())
    return redirect("chat_page", chat_id=chat.id)

@login_required
def delete_chat(request, chat_id):
    if request.method != "POST":
        return redirect("chat_page", chat_id=chat_id)
    chat = get_object_or_404(Chat, id=chat_id, user=request.user)
    chat.delete()
    return redirect("chat_home")


@login_required
@require_POST
def rename_chat(request, chat_id):
    chat = get_object_or_404(Chat, id=chat_id, user=request.user)
    new_name = (request.POST.get("name") or "").strip()
    if new_name:
        chat.name = new_name[:200]
        chat.save(update_fields=["name", "last_updated"])
    return redirect("chat_page", chat_id=chat.id)
