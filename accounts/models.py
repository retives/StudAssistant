from django.db import models
from django.contrib.auth.models import AbstractUser

class Faculty(models.Model):
    name = models.CharField(max_length=100)
    def __str__(self): return self.name

class Department(models.Model):
    faculty = models.ForeignKey(Faculty, on_delete=models.CASCADE, related_name="departments")
    name = models.CharField(max_length=100)
    def __str__(self): return self.name

class Group(models.Model):
    name = models.CharField(max_length=100, primary_key=True)
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name="groups")
    def __str__(self): return self.name

class User(AbstractUser):
    is_bot = models.BooleanField(default=False)
    faculty = models.ForeignKey(Faculty, on_delete=models.CASCADE, related_name="users", null=True, blank=True)
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name="users", null=True, blank=True)
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="users", null=True, blank=True)