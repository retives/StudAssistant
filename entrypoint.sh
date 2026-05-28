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
        password='2-Bev45rt'
    )
    print("Admin initialized")
else:
    print("Admin already exists")
EOF

python manage.py shell <<EOF
from accounts.models import Department, Faculty, Group

faculties = [
    "Факультет інформаційних технологій",
    "Факультет природничих наук",
    "Інститут нафтогазової інженерії",
    "Інститут інженерної механіки та робототехніки",
    "Факультет автоматизації та енергетики",
    "Інститут архітектури та будівництва",
    "Інститут гуманітарної підготовки та державного управління",
    "Інститут післядипломної освіти",
]

for name in faculties:
    Faculty.objects.get_or_create(name=name)

fit, _ = Faculty.objects.get_or_create(name="Факультет інформаційних технологій")
fit_departments = [
    "Кафедра інженерії програмного забезпечення",
    "Кафедра інформаційно-телекомунікаційних технологій та систем",
    "Кафедра комп'ютерних систем і мереж",
]

for name in fit_departments:
    Department.objects.get_or_create(faculty=fit, name=name)

ipz_group_names = [
  "ІП-22", "ІП-23", "ІП-24", "ІП-25"
]
for group_name in ipz_group_names:
  for i in range(1,4):
    group = f"{group_name}-{i}"
    ipz_dept = Department.objects.get(faculty=fit, name="Кафедра інженерії програмного забезпечення")
    Group.objects.get_or_create(department=ipz_dept, name=group)

print("Faculties and FIT departments seeded")
EOF
exec "$@"
