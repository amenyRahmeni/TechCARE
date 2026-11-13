import json
from datetime import timedelta

import jwt
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.hashers import make_password
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .models import EmailAddress
from .tokens import issue_token, signing_key

User = get_user_model()


class AccountTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("existing_client", email="existing@example.test", password="StrongTest2026!")
        cls.staff = User.objects.create_user("account_admin", password="StrongTest2026!", is_staff=True, is_superuser=True)

    def payload(self, **changes):
        data = {"email": "nouveau@example.test", "first_name": "Nour", "last_name": "Ben Ali",
                "password1": "SecureRegistration2026!", "password2": "SecureRegistration2026!"}
        data.update(changes)
        return data

    def test_registration_creates_active_client_with_bcrypt_and_session(self):
        response = self.client.post(reverse("accounts:signup"), self.payload(is_staff="1", is_superuser="1", role="technician", is_active="0"))
        self.assertRedirects(response, "/")
        user = User.objects.get(email="nouveau@example.test")
        self.assertTrue(user.username.startswith("client_"))
        self.assertEqual(authenticate(username=user.email, password="SecureRegistration2026!"), user)
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff or user.is_superuser)
        self.assertFalse(hasattr(user, "technician_profile"))
        self.assertTrue(user.password.startswith("bcrypt_sha256$"))
        self.assertTrue(user.check_password("SecureRegistration2026!"))
        self.assertEqual(EmailAddress.objects.get(user=user).address, "nouveau@example.test")
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_registration_rejects_duplicate_email_case_insensitive(self):
        response = self.client.post(reverse("accounts:signup"), self.payload(email="EXISTING@example.test"))
        self.assertContains(response, "déjà utilisée")
        self.assertEqual(User.objects.count(), 2)

    def test_registration_validates_password_confirmation_and_names(self):
        response = self.client.post(reverse("accounts:signup"), self.payload(first_name="  ", password2="wrong"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.count(), 2)

    def test_weak_password_is_rejected(self):
        self.client.post(reverse("accounts:signup"), self.payload(password1="12345678", password2="12345678"))
        self.assertEqual(User.objects.count(), 2)

    def test_registration_ignores_forged_username(self):
        response = self.client.post(reverse("accounts:signup"), self.payload(username=self.staff.username))
        self.assertRedirects(response, "/")
        user = User.objects.get(email="nouveau@example.test")
        self.assertNotEqual(user.username, self.staff.username)
        self.staff.refresh_from_db()
        self.assertEqual(self.staff.email, "")

    def test_registration_rejects_email_matching_legacy_username(self):
        User.objects.create_user("legacy@example.test")
        response = self.client.post(reverse("accounts:signup"), self.payload(email="LEGACY@example.test"))
        self.assertContains(response, "déjà utilisée")
        self.assertEqual(User.objects.count(), 3)

    def test_registration_accepts_email_longer_than_internal_username_limit(self):
        address = "n" * 64 + "@" + "a" * 60 + "." + "b" * 60 + ".test"
        self.assertGreater(len(address), User._meta.get_field("username").max_length)
        response = self.client.post(reverse("accounts:signup"), self.payload(email=address))
        self.assertRedirects(response, "/")
        user = User.objects.get(email=address)
        self.assertLessEqual(len(user.username), 150)

    def test_login_by_email_or_legacy_identifier(self):
        for name in ("EXISTING@example.test", "existing_client"):
            self.assertEqual(authenticate(username=name, password="StrongTest2026!"), self.user)
        response = self.client.post(reverse("login"), {"username": "existing@example.test", "password": "StrongTest2026!"})
        self.assertRedirects(response, "/")

    def test_ambiguous_email_and_suspended_account_cannot_login(self):
        User.objects.create_user("legacy_duplicate", email=self.user.email, password="OtherStrong2026!")
        self.assertIsNone(authenticate(username=self.user.email, password="StrongTest2026!"))
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        self.assertIsNone(authenticate(username=self.user.username, password="StrongTest2026!"))

    def test_legacy_pbkdf2_password_is_accepted_and_upgraded(self):
        self.user.password = make_password("OldStrong2026!", hasher="pbkdf2_sha256")
        self.user.save(update_fields=["password"])
        self.assertEqual(authenticate(username=self.user.username, password="OldStrong2026!"), self.user)
        self.user.refresh_from_db()
        self.assertTrue(self.user.password.startswith("bcrypt_sha256$"))

    def test_profile_and_password_changes_preserve_role_and_session(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("accounts:profile")).status_code, 200)
        self.assertRedirects(self.client.post(reverse("accounts:profile"), {"first_name": "Nour", "last_name": "Test", "email": "updated@example.test", "is_staff": "1"}), reverse("accounts:profile"))
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_staff)
        self.assertEqual(EmailAddress.objects.get(user=self.user).address, "updated@example.test")
        response = self.client.post(reverse("accounts:password"), {"old_password": "StrongTest2026!", "new_password1": "ChangedSecure2026!", "new_password2": "ChangedSecure2026!"})
        self.assertRedirects(response, reverse("accounts:profile"))
        self.assertIn("_auth_user_id", self.client.session)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("ChangedSecure2026!"))

    def test_profile_cannot_claim_another_account_email(self):
        self.client.force_login(self.staff)
        response = self.client.post(reverse("accounts:profile"), {"first_name": "Admin", "last_name": "Test", "email": self.user.email})
        self.assertContains(response, "déjà utilisée")
        self.staff.refresh_from_db()
        self.assertEqual(self.staff.email, "")

    def test_email_claim_unique_database_constraint(self):
        EmailAddress.objects.create(user=self.user, address="unique@example.test")
        with self.assertRaises(IntegrityError), transaction.atomic():
            EmailAddress.objects.create(user=self.staff, address="unique@example.test")

    def test_jwt_login_me_and_password_revocation(self):
        response = self.client.post(reverse("accounts:token"), json.dumps({"email": self.user.email, "password": "StrongTest2026!"}), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        token = response.json()["access_token"]
        headers = {"HTTP_AUTHORIZATION": "Bearer " + token}
        self.assertEqual(self.client.get(reverse("accounts:me"), **headers).json()["role"], "client")
        self.user.set_password("ChangedAgain2026!")
        self.user.save(update_fields=["password"])
        self.assertEqual(self.client.get(reverse("accounts:me"), **headers).status_code, 401)

    def test_jwt_rejects_tampering_expiration_and_suspended_users(self):
        token = issue_token(self.user)
        claims = jwt.decode(token, signing_key(), algorithms=["HS256"], audience="techcare-api", issuer="techcare")
        claims["exp"] = timezone.now() - timedelta(seconds=1)
        expired = jwt.encode(claims, signing_key(), algorithm="HS256")
        for value in (token + "x", expired, "nonsense"):
            self.assertEqual(self.client.get(reverse("accounts:me"), HTTP_AUTHORIZATION="Bearer " + value).status_code, 401)
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        self.assertEqual(self.client.get(reverse("accounts:me"), HTTP_AUTHORIZATION="Bearer " + token).status_code, 401)

    def test_jwt_validation_and_csrf(self):
        url = reverse("accounts:token")
        self.assertEqual(self.client.get(url).status_code, 405)
        for value in ("[]", "{}", '{"email":3,"password":[]}', "broken"):
            self.assertEqual(self.client.post(url, value, content_type="application/json").status_code, 400)
        self.assertEqual(self.client.post(url, {"email": self.user.email, "password": "wrong"}).status_code, 401)
        self.assertEqual(Client(enforce_csrf_checks=True).post(url, {"email": self.user.email, "password": "StrongTest2026!"}).status_code, 403)

    def test_admin_rejects_email_duplicate(self):
        self.client.force_login(self.staff)
        response = self.client.post(reverse("backoffice:account_create"), self.payload(username="new_client", role="client", email=self.user.email))
        self.assertContains(response, "déjà utilisée")
        self.assertFalse(User.objects.filter(username="new_client").exists())
