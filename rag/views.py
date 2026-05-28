import logging

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import AbstractUser
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST, require_GET
from accounts.models import User
from .models import Chat, Message
from .agent import get_cached_agent
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
    if chat and chat.messages.count() == 0:
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
    current_user = request.user
    chat = get_object_or_404(Chat, id=chat_id, user=request.user)
    content = (request.POST.get("message") or "").strip()
    if content:
        Message.objects.create(chat=chat, sender=request.user, content=content)
        # Ask agent
        try:
            # Require academic profile to be set (picked during signup/login/settings).
            if not current_user.faculty_id or not current_user.department_id or not current_user.group_id:
                return redirect("account_settings")

            # Reuse cached agent keyed by user profile.
            agent = get_cached_agent(
                group=str(current_user.group_id),
                faculty=str(current_user.faculty.name),
                department=str(current_user.department.name),
            )
            # Generate a chat title
            if chat.name == "New Chat":
                chat.name = agent.get_title(content)
                chat.save()
            # Handle bot response
            system_user = User.objects.get(id=0)
            if not system_user:
                logging.error("No system user")
                system_user = User.objects.create(id=0, username="RAG_SYSTEM_USER", first_name="", last_name="", password="ONEWINVERIW214@")
                logging.info("System user created")
            else:
                logging.info("System user assigned successfully")

            # Generate the response
            response = agent.ask(content, chat_id)
            Message.objects.create(chat=chat, sender=system_user, content=response)
            logging.info("Response successful")

        except Exception as e:
            Message.objects.create(chat=chat, sender=system_user, content="An Error Occurred. Try again later")
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
