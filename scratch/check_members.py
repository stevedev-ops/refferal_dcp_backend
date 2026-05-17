import os
import sys
import django

sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.db.models import Q
from api.models import Member, VoterRecord

print("\n--- ALL MUTWIRI RECORDS ---")
voters = VoterRecord.objects.filter(full_name__icontains="MUTWIRI")
for v in voters:
    print(f"Name: {v.full_name}, ID: {v.id_number}, YOB: {v.date_of_birth}")
