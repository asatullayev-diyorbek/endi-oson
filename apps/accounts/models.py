from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, telegram_user_id, **extra_fields):
        if not telegram_user_id:
            raise ValueError("telegram_user_id majburiy")
        user = self.model(telegram_user_id=telegram_user_id, **extra_fields)
        user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, telegram_user_id, password, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        user = self.model(telegram_user_id=telegram_user_id, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user


class User(AbstractBaseUser, PermissionsMixin):
    # Telegram'ning o'zgarmas raqamli foydalanuvchi ID'si — akkaunt shu bilan
    # bog'lanadi, username bilan emas (username o'zgarishi mumkin).
    telegram_user_id = models.BigIntegerField(unique=True, db_index=True)
    telegram_username = models.CharField(max_length=64, null=True, blank=True)
    display_name = models.CharField(max_length=128, blank=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = UserManager()

    USERNAME_FIELD = "telegram_user_id"
    REQUIRED_FIELDS = []

    def __str__(self):
        return self.display_name or self.telegram_username or str(self.telegram_user_id)
