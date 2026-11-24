from .conftest import login, login_staff_with_2fa, auth_headers


def _passenger_token(client, account):
    return login(client, account["email"], account["password"]).json()["access_token"]


def _staff_token(client, account):
    return login_staff_with_2fa(client, account["email"], account["password"], account["totp_secret"]).json()["access_token"]


class TestPaymentProcessing:
    def test_payment_succeeds_and_never_returns_full_card_number(self, client, passenger_account, sample_flight):
        token = _passenger_token(client, passenger_account)
        booking = client.post("/api/v1/booking/create", json={"flight_id": sample_flight.id}, headers=auth_headers(token)).json()

        resp = client.post("/api/v1/payment/process", json={
            "booking_id": booking["id"],
            "card_number": "4111111111111111",
            "card_expiry": "12/29",
            "card_cvc": "123",
        }, headers=auth_headers(token))
        assert resp.status_code == 201
        body = resp.json()
        assert body["card_last4"] == "1111"
        assert "4111111111111111" not in str(body)

    def test_payment_amount_is_derived_from_flight_price_not_client_input(self, client, passenger_account, sample_flight):
        """Regression test: the client must not be able to set its own charge amount (payment manipulation)."""
        token = _passenger_token(client, passenger_account)
        booking = client.post("/api/v1/booking/create", json={"flight_id": sample_flight.id}, headers=auth_headers(token)).json()

        resp = client.post("/api/v1/payment/process", json={
            "booking_id": booking["id"],
            "card_number": "4111111111111111",
            "card_expiry": "12/29",
            "card_cvc": "123",
            "amount": 0.01,  # attacker-supplied field, if present, must be ignored
        }, headers=auth_headers(token))
        assert resp.status_code == 201
        assert resp.json()["amount"] == float(sample_flight.base_price)

    def test_payment_cannot_be_processed_twice_for_same_booking(self, client, passenger_account, sample_flight):
        token = _passenger_token(client, passenger_account)
        booking = client.post("/api/v1/booking/create", json={"flight_id": sample_flight.id}, headers=auth_headers(token)).json()
        payload = {"booking_id": booking["id"], "card_number": "4111111111111111", "card_expiry": "12/29", "card_cvc": "123"}

        first = client.post("/api/v1/payment/process", json=payload, headers=auth_headers(token))
        assert first.status_code == 201

        second = client.post("/api/v1/payment/process", json=payload, headers=auth_headers(token))
        assert second.status_code == 400

    def test_payment_persists_token_not_raw_card_number(self, client, passenger_account, sample_flight, db_session):
        token = _passenger_token(client, passenger_account)
        booking = client.post("/api/v1/booking/create", json={"flight_id": sample_flight.id}, headers=auth_headers(token)).json()
        client.post("/api/v1/payment/process", json={
            "booking_id": booking["id"], "card_number": "4222222222222222",
            "card_expiry": "01/30", "card_cvc": "999",
        }, headers=auth_headers(token))

        from src import models
        record = db_session.query(models.PaymentRecord).filter(models.PaymentRecord.booking_id == booking["id"]).first()
        assert record is not None
        assert "4222222222222222" not in record.card_token
        assert record.card_last4 == "2222"

    def test_payment_rejects_invalid_card_number(self, client, passenger_account, sample_flight):
        token = _passenger_token(client, passenger_account)
        booking = client.post("/api/v1/booking/create", json={"flight_id": sample_flight.id}, headers=auth_headers(token)).json()
        resp = client.post("/api/v1/payment/process", json={
            "booking_id": booking["id"], "card_number": "123", "card_expiry": "12/29", "card_cvc": "123",
        }, headers=auth_headers(token))
        assert resp.status_code == 422

    def test_payment_for_other_passengers_booking_rejected(self, client, passenger_account, sample_flight, db_session):
        from .conftest import unique_email
        from src import models
        from src.security import hash_password, encrypt_data

        token1 = _passenger_token(client, passenger_account)
        booking = client.post("/api/v1/booking/create", json={"flight_id": sample_flight.id}, headers=auth_headers(token1)).json()

        email2 = unique_email("payer2")
        user2 = models.User(email=email2, hashed_password=hash_password("PayerP@ss1!"), role="passenger", is_active=True)
        db_session.add(user2)
        db_session.commit()
        db_session.refresh(user2)
        db_session.add(models.Passenger(user_id=user2.id, full_name=encrypt_data("Payer Two"), passport_number=encrypt_data("F0000002")))
        db_session.commit()
        token2 = login(client, email2, "PayerP@ss1!").json()["access_token"]

        resp = client.post("/api/v1/payment/process", json={
            "booking_id": booking["id"], "card_number": "4111111111111111", "card_expiry": "12/29", "card_cvc": "123",
        }, headers=auth_headers(token2))
        assert resp.status_code == 404


class TestTamperEvidentAuditLog:
    def test_audit_chain_is_intact_after_normal_activity(self, client, admin_account, passenger_account):
        login(client, passenger_account["email"], passenger_account["password"])
        token = _staff_token(client, admin_account)
        resp = client.get("/api/v1/admin/audit-logs/verify", headers=auth_headers(token))
        assert resp.status_code == 200
        assert resp.json()["intact"] is True

    def test_tampering_with_audit_log_breaks_chain(self, client, admin_account, passenger_account, db_session):
        login(client, passenger_account["email"], passenger_account["password"])
        from src import models
        entry = db_session.query(models.AuditLog).order_by(models.AuditLog.id.desc()).first()
        entry.details = "tampered by attacker"
        db_session.commit()

        token = _staff_token(client, admin_account)
        resp = client.get("/api/v1/admin/audit-logs/verify", headers=auth_headers(token))
        assert resp.json()["intact"] is False

    def test_non_admin_cannot_view_audit_logs(self, client, passenger_account):
        token = _passenger_token(client, passenger_account)
        resp = client.get("/api/v1/admin/audit-logs", headers=auth_headers(token))
        assert resp.status_code == 403
