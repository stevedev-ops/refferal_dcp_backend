import uuid
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin

class MemberManager(BaseUserManager):
    def create_user(self, national_id, full_name, phone, password=None, **extra_fields):
        if not national_id:
            raise ValueError('The National ID must be set')
        user = self.model(national_id=national_id, full_name=full_name, phone=phone, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, national_id, full_name, phone, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_admin', True)
        return self.create_user(national_id, full_name, phone, password, **extra_fields)

class Member(AbstractBaseUser, PermissionsMixin):
    full_name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20, unique=True)
    national_id = models.CharField(max_length=20, unique=True)
    email = models.EmailField(blank=True, null=True)
    yob = models.IntegerField(null=True, blank=True)
    ward = models.CharField(max_length=255, blank=True, null=True)
    polling_station = models.CharField(max_length=255, blank=True, null=True)
    # Official IEBC names — auto-populated from voter register on match
    official_ward = models.CharField(max_length=255, blank=True, null=True)
    official_polling_station = models.CharField(max_length=255, blank=True, null=True)
    referred_by = models.ForeignKey(
        'self', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='recruits'
    )
    is_admin = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_voter_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = MemberManager()

    USERNAME_FIELD = 'national_id'
    REQUIRED_FIELDS = ['full_name', 'phone']

    @property
    def referral_code(self):
        return str(self.id)

    def __str__(self):
        return self.full_name

class VoterRecord(models.Model):
    id_number = models.CharField(max_length=20, null=True, blank=True, db_index=True)
    phone_number = models.CharField(max_length=20, null=True, blank=True, db_index=True)
    full_name = models.CharField(max_length=255, db_index=True)
    date_of_birth = models.IntegerField(null=True, blank=True, db_index=True)  # year only e.g. 1994
    ward = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    polling_station = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.full_name} ({self.id_number or self.phone_number})"

class Invite(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    target_role = models.CharField(max_length=50, default='root')
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Invite {self.id} ({self.target_role})"
