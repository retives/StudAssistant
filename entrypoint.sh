#!/bin/sh

echo "Waiting for postgres..."

echo "Applying database migrations..."
python manage.py migrate

python manage.py collectstatic --noinput

python manage.py shell <<EOF
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='SYSTEM_USER').exists():
    User.objects.create_superuser(
        id=0,
        username='SYSTEM_USER',
        email='system@internal.local',
        password='KrfKJ5qHm@Xx3!&bJ3TD3I^3'
    )
    print("SYSTEM_USER created with ID 0")
else:
    print("SYSTEM_USER already exists")
EOF

python manage.py shell <<EOF
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='stud_admin').exists():
    User.objects.create_superuser(
        username='stud_admin',
        email='admin@studassistant.onrender.com',
        password='2-Bev45rt
    )
    print("Admin initialized")
else:
    print("Admin already exists")
EOF
exec "$@"