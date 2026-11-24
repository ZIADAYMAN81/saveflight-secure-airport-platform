from .conftest import login, auth_headers


def _token(client, account):
    return login(client, account["email"], account["password"]).json()["access_token"]


class TestBookingAndCheckin:
    def test_public_flight_search(self, client, sample_flight):
        resp = client.get("/api/v1/flights")
        assert resp.status_code == 200
        numbers = [f["flight_number"] for f in resp.json()]
        assert sample_flight.flight_number in numbers

    def test_create_booking(self, client, passenger_account, sample_flight):
        token = _token(client, passenger_account)
        resp = client.post("/api/v1/booking/create", json={
            "flight_id": sample_flight.id, "seat_number": "14C"
        }, headers=auth_headers(token))
        assert resp.status_code == 201
        assert resp.json()["status"] == "active"

    def test_booking_rejected_for_nonexistent_flight(self, client, passenger_account):
        token = _token(client, passenger_account)
        resp = client.post("/api/v1/booking/create", json={"flight_id": 999999}, headers=auth_headers(token))
        assert resp.status_code == 400

    def test_duplicate_seat_on_same_flight_rejected(self, client, passenger_account, sample_flight, db_session):
        from .conftest import unique_email
        from src import models
        from src.security import hash_password, encrypt_data

        token1 = _token(client, passenger_account)
        first = client.post("/api/v1/booking/create", json={
            "flight_id": sample_flight.id, "seat_number": "7A"
        }, headers=auth_headers(token1))
        assert first.status_code == 201

        email2 = unique_email("seatgrabber")
        password2 = "SeatP@ssw0rd1!"
        user2 = models.User(email=email2, hashed_password=hash_password(password2), role="passenger", is_active=True)
        db_session.add(user2)
        db_session.commit()
        db_session.refresh(user2)
        db_session.add(models.Passenger(user_id=user2.id, full_name=encrypt_data("Seat Grabber"), passport_number=encrypt_data("G0000001")))
        db_session.commit()
        token2 = login(client, email2, password2).json()["access_token"]

        second = client.post("/api/v1/booking/create", json={
            "flight_id": sample_flight.id, "seat_number": "7A"
        }, headers=auth_headers(token2))
        assert second.status_code == 409

    def test_full_checkin_flow_and_boarding_pass(self, client, passenger_account, sample_flight):
        token = _token(client, passenger_account)
        booking = client.post("/api/v1/booking/create", json={
            "flight_id": sample_flight.id, "seat_number": "9F"
        }, headers=auth_headers(token)).json()

        checkin_resp = client.post("/api/v1/passenger/checkin", json={"booking_id": booking["id"]}, headers=auth_headers(token))
        assert checkin_resp.status_code == 200
        bp_token = checkin_resp.json()["boarding_pass_token"]

        bp_resp = client.get(f"/api/v1/passenger/boarding-pass/{bp_token}", headers=auth_headers(token))
        assert bp_resp.status_code == 200
        body = bp_resp.json()
        assert body["passenger_name"] == "Test Passenger"
        assert body["flight_number"] == sample_flight.flight_number
        assert body["used"] is False

    def test_passenger_cannot_view_others_bookings(self, client, passenger_account, sample_flight, db_session):
        from .conftest import unique_email, auth_headers as ah
        from src import models
        from src.security import hash_password, encrypt_data

        token1 = _token(client, passenger_account)
        booking = client.post("/api/v1/booking/create", json={
            "flight_id": sample_flight.id
        }, headers=ah(token1)).json()

        email2 = unique_email("otherpax")
        password2 = "OtherP@ssw0rd1!"
        user2 = models.User(email=email2, hashed_password=hash_password(password2), role="passenger", is_active=True)
        db_session.add(user2)
        db_session.commit()
        db_session.refresh(user2)
        db_session.add(models.Passenger(user_id=user2.id, full_name=encrypt_data("Other Person"), passport_number=encrypt_data("C0000001")))
        db_session.commit()

        token2 = login(client, email2, password2).json()["access_token"]
        bookings_resp = client.get("/api/v1/passenger/bookings", headers=ah(token2))
        assert bookings_resp.status_code == 200
        assert all(b["id"] != booking["id"] for b in bookings_resp.json())

    def test_checkin_other_passengers_booking_forbidden(self, client, passenger_account, sample_flight, db_session):
        from .conftest import unique_email, auth_headers as ah
        from src import models
        from src.security import hash_password, encrypt_data

        token1 = _token(client, passenger_account)
        booking = client.post("/api/v1/booking/create", json={
            "flight_id": sample_flight.id
        }, headers=ah(token1)).json()

        email2 = unique_email("attacker")
        password2 = "AttackP@ssw0rd1!"
        user2 = models.User(email=email2, hashed_password=hash_password(password2), role="passenger", is_active=True)
        db_session.add(user2)
        db_session.commit()
        db_session.refresh(user2)
        db_session.add(models.Passenger(user_id=user2.id, full_name=encrypt_data("Attacker"), passport_number=encrypt_data("D0000001")))
        db_session.commit()

        token2 = login(client, email2, password2).json()["access_token"]
        resp = client.post("/api/v1/passenger/checkin", json={"booking_id": booking["id"]}, headers=ah(token2))
        assert resp.status_code == 400

    def test_boarding_pass_forbidden_for_wrong_passenger(self, client, passenger_account, sample_flight, db_session):
        from .conftest import unique_email, auth_headers as ah
        from src import models
        from src.security import hash_password, encrypt_data

        token1 = _token(client, passenger_account)
        booking = client.post("/api/v1/booking/create", json={
            "flight_id": sample_flight.id
        }, headers=ah(token1)).json()
        bp_token = client.post("/api/v1/passenger/checkin", json={"booking_id": booking["id"]}, headers=ah(token1)).json()["boarding_pass_token"]

        email2 = unique_email("snooper")
        password2 = "SnoopP@ssw0rd1!"
        user2 = models.User(email=email2, hashed_password=hash_password(password2), role="passenger", is_active=True)
        db_session.add(user2)
        db_session.commit()
        db_session.refresh(user2)
        db_session.add(models.Passenger(user_id=user2.id, full_name=encrypt_data("Snooper"), passport_number=encrypt_data("E0000001")))
        db_session.commit()

        token2 = login(client, email2, password2).json()["access_token"]
        resp = client.get(f"/api/v1/passenger/boarding-pass/{bp_token}", headers=ah(token2))
        assert resp.status_code == 403
