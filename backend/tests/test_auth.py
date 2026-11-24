import time
import pyotp
from .conftest import login, login_staff_with_2fa, auth_headers, unique_email


class TestRegistrationAndLogin:
    def test_register_new_passenger(self, client):
        resp = client.post("/api/v1/auth/register", json={
            "email": unique_email("newpax"),
            "password": "SecureP@ssw0rd1!",
            "full_name": "New Passenger",
            "passport_number": "AB123456",
        })
        assert resp.status_code == 201
        assert resp.json()["role"] == "passenger"

    def test_register_rejects_weak_password(self, client):
        resp = client.post("/api/v1/auth/register", json={
            "email": unique_email("weak"),
            "password": "weakpass",
            "full_name": "Weak Pw",
            "passport_number": "AB123456",
        })
        assert resp.status_code == 422

    def test_register_rejects_bad_passport_format(self, client):
        resp = client.post("/api/v1/auth/register", json={
            "email": unique_email("badpp"),
            "password": "SecureP@ssw0rd1!",
            "full_name": "Bad Passport",
            "passport_number": "bad-passport",
        })
        assert resp.status_code == 422

    def test_duplicate_registration_rejected(self, client, passenger_account):
        resp = client.post("/api/v1/auth/register", json={
            "email": passenger_account["email"],
            "password": "SecureP@ssw0rd1!",
            "full_name": "Duplicate",
            "passport_number": "AB123456",
        })
        assert resp.status_code == 400

    def test_login_success_passenger(self, client, passenger_account):
        resp = login(client, passenger_account["email"], passenger_account["password"])
        assert resp.status_code == 200
        assert resp.json()["access_token"]
        assert resp.json()["requires_2fa"] is False

    def test_login_invalid_password_generic_error(self, client, passenger_account):
        resp = login(client, passenger_account["email"], "WrongPassword1!")
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid credentials"

    def test_login_nonexistent_email_generic_error(self, client):
        resp = login(client, "nobody@example.com", "whatever12345")
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid credentials"

    def test_account_lockout_after_repeated_failures(self, client, passenger_account):
        for _ in range(5):
            login(client, passenger_account["email"], "WrongPassword1!")
        resp = login(client, passenger_account["email"], passenger_account["password"])
        assert resp.status_code in (423, 429)

    def test_staff_login_requires_2fa_step(self, client, agent_account):
        resp = login(client, agent_account["email"], agent_account["password"])
        assert resp.status_code == 200
        body = resp.json()
        assert body["requires_2fa"] is True
        assert body["access_token"] == ""

    def test_staff_2fa_verify_success(self, client, agent_account):
        resp = login_staff_with_2fa(client, agent_account["email"], agent_account["password"], agent_account["totp_secret"])
        assert resp.status_code == 200
        assert resp.json()["access_token"]

    def test_staff_2fa_verify_wrong_code_rejected(self, client, agent_account):
        login_resp = login(client, agent_account["email"], agent_account["password"])
        user_id = login_resp.json()["user_id"]
        resp = client.post("/api/v1/auth/2fa-verify", json={"user_id": user_id, "totp_code": "000000"})
        assert resp.status_code == 401

    def test_staff_without_totp_can_bootstrap_via_emailed_otp(self, client, db_session, capsys):
        """A staff account created via /admin/create-staff has no TOTP secret yet.
        It must still be able to log in - via the emailed OTP - since there's no
        other way to reach /2fa-enroll (which itself requires being logged in)."""
        import re
        from .conftest import unique_email as ue
        from src import models
        from src.security import hash_password
        email = ue("noenroll")
        user = models.User(email=email, hashed_password=hash_password("StaffP@ssw0rd1!"), role="agent", is_active=True)
        db_session.add(user)
        db_session.commit()

        resp = login(client, email, "StaffP@ssw0rd1!")
        assert resp.status_code == 200
        assert resp.json()["requires_2fa"] is True

        captured = capsys.readouterr()
        emailed_code = re.search(r"OTP for [^:]+: (\d{6})", captured.out).group(1)
        verify_resp = client.post("/api/v1/auth/2fa-verify", json={"user_id": resp.json()["user_id"], "totp_code": emailed_code})
        assert verify_resp.status_code == 200
        assert verify_resp.json()["access_token"]

    def test_protected_endpoint_requires_token(self, client):
        resp = client.get("/api/v1/passenger/profile")
        assert resp.status_code == 401

    def test_protected_endpoint_with_valid_token(self, client, passenger_account):
        token = login(client, passenger_account["email"], passenger_account["password"]).json()["access_token"]
        resp = client.get("/api/v1/passenger/profile", headers=auth_headers(token))
        assert resp.status_code == 200
        assert resp.json()["email"] == passenger_account["email"]

    def test_2fa_enroll_requires_authentication(self, client):
        resp = client.post("/api/v1/auth/2fa-enroll")
        assert resp.status_code == 401

    def test_2fa_enroll_returns_provisioning_uri(self, client, passenger_account):
        token = login(client, passenger_account["email"], passenger_account["password"]).json()["access_token"]
        resp = client.post("/api/v1/auth/2fa-enroll", headers=auth_headers(token))
        assert resp.status_code == 200
        body = resp.json()
        assert "secret" in body
        assert body["provisioning_uri"].startswith("otpauth://")

    def test_login_rate_limited_after_five_attempts(self, client, passenger_account):
        for _ in range(5):
            login(client, passenger_account["email"], "WrongPassword1!")
        resp = login(client, passenger_account["email"], "WrongPassword1!")
        assert resp.status_code == 429

    def test_staff_can_verify_with_emailed_otp_instead_of_totp(self, client, agent_account, capsys):
        import re
        login_resp = login(client, agent_account["email"], agent_account["password"])
        user_id = login_resp.json()["user_id"]

        captured = capsys.readouterr()
        match = re.search(r"OTP for [^:]+: (\d{6})", captured.out)
        assert match, "expected the OTP fallback print when RESEND_API_KEY is unset"
        emailed_code = match.group(1)

        resp = client.post("/api/v1/auth/2fa-verify", json={"user_id": user_id, "totp_code": emailed_code})
        assert resp.status_code == 200
        assert resp.json()["access_token"]

    def test_emailed_otp_is_single_use(self, client, agent_account, capsys):
        import re
        login_resp = login(client, agent_account["email"], agent_account["password"])
        user_id = login_resp.json()["user_id"]
        captured = capsys.readouterr()
        emailed_code = re.search(r"OTP for [^:]+: (\d{6})", captured.out).group(1)

        first = client.post("/api/v1/auth/2fa-verify", json={"user_id": user_id, "totp_code": emailed_code})
        assert first.status_code == 200

        second = client.post("/api/v1/auth/2fa-verify", json={"user_id": user_id, "totp_code": emailed_code})
        assert second.status_code == 401
