from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.shortcuts import get_object_or_404, redirect, render

from .models import Department, Faculty, Group, User


@login_required
def account_settings(request):
    user: User = request.user

    faculties = Faculty.objects.all().order_by("name")
    departments = Department.objects.select_related("faculty").all().order_by("name")
    groups = Group.objects.select_related("department", "department__faculty").all().order_by("name")

    errors = {}
    success = None

    if request.method == "POST":
        pwd_form = PasswordChangeForm(user)
        for name in ("old_password", "new_password1", "new_password2"):
            if name in pwd_form.fields:
                pwd_form.fields[name].widget.attrs.update({"class": "input"})

        username = (request.POST.get("username") or "").strip()
        email = (request.POST.get("email") or "").strip()

        faculty_id = (request.POST.get("faculty") or "").strip() or None
        department_id = (request.POST.get("department") or "").strip() or None
        group_id = (request.POST.get("group") or "").strip() or None

        if not username:
            errors["username"] = "Username is required."
        elif User.objects.exclude(pk=user.pk).filter(username=username).exists():
            errors["username"] = "This username is already taken."

        if email and User.objects.exclude(pk=user.pk).filter(email=email).exists():
            errors["email"] = "This email is already in use."

        faculty = None
        department = None
        group = None

        if faculty_id:
            faculty = get_object_or_404(Faculty, pk=faculty_id)
        if department_id:
            department = get_object_or_404(Department, pk=department_id)
        if group_id:
            group = get_object_or_404(Group, pk=group_id)

        if department and faculty and department.faculty_id != faculty.id:
            errors["department"] = "Department does not belong to selected faculty."

        if group and department and group.department_id != department.id:
            errors["group"] = "Group does not belong to selected department."
        if group and not department:
            errors["group"] = "Select a department first."

        if not errors:
            user.username = username
            user.email = email
            user.faculty = faculty
            user.department = department
            user.group = group
            user.save(update_fields=["username", "email", "faculty", "department", "group"])
            success = "profile"
            return redirect("account_settings")
    else:
        pwd_form = PasswordChangeForm(user)
        for name in ("old_password", "new_password1", "new_password2"):
            if name in pwd_form.fields:
                pwd_form.fields[name].widget.attrs.update({"class": "input"})

    selected_faculty_id = user.faculty_id or ""
    selected_department_id = user.department_id or ""
    selected_group_id = user.group_id or ""

    return render(
        request,
        "accounts/settings.html",
        {
            "faculties": faculties,
            "departments": departments,
            "groups": groups,
            "errors": errors,
            "success": success,
            "pwd_form": pwd_form,
            "selected_faculty_id": str(selected_faculty_id),
            "selected_department_id": str(selected_department_id),
            "selected_group_id": str(selected_group_id),
        },
    )

# Create your views here.


@login_required
def account_password(request):
    user: User = request.user
    success = False

    if request.method == "POST":
        form = PasswordChangeForm(user, request.POST)
    else:
        form = PasswordChangeForm(user)

    for name in ("old_password", "new_password1", "new_password2"):
        if name in form.fields:
            form.fields[name].widget.attrs.update({"class": "input"})

    if request.method == "POST" and form.is_valid():
        updated_user = form.save()
        update_session_auth_hash(request, updated_user)
        return redirect("account_settings")

    return render(
        request,
        "accounts/password.html",
        {
            "form": form,
            "success": success,
        },
    )
