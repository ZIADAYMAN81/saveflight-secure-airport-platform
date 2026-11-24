from datetime import datetime, timedelta
from .conftest import login, auth_headers


def _token(client, account):
    return login(client, account["email"], account["password"]).json()["access_token"]


class TestSeatMap:
    def test_generates_300_seats(self, client, passenger_account, sample_flight):
        token = _token(client, passenger_account)
        resp = client.get(f"/api/v1/flights/{sample_flight.id}/seats", headers=auth_headers(token))
        assert resp.status_code == 200
        assert len(resp.json()["seats"]) == 300

    def test_class_distribution(self, client, passenger_account, sample_flight):
        token = _token(client, passenger_account)
        seats = client.get(f"/api/v1/flights/{sample_flight.id}/seats", headers=auth_headers(token)).json()["seats"]
        counts = {}
        for s in seats:
            counts[s["seat_class"]] = counts.get(s["seat_class"], 0) + 1
        assert counts["first"] == 24    # rows 1-4 x 6
        assert counts["business"] == 48  # rows 5-12 x 6
        assert counts["economy"] == 228  # rows 13-50 x 6

    def test_restricted_seats_marked(self, client, passenger_account, sample_flight):
        token = _token(client, passenger_account)
        seats = client.get(f"/api/v1/flights/{sample_flight.id}/seats", headers=auth_headers(token)).json()["seats"]
        restricted = [s for s in seats if s["status"] == "restricted"]
        assert len(restricted) == 2
        assert {s["seat_number"] for s in restricted} == {"50B", "50E"}

    def test_pricing_scales_by_class(self, client, passenger_account, sample_flight):
        token = _token(client, passenger_account)
        seats = client.get(f"/api/v1/flights/{sample_flight.id}/seats", headers=auth_headers(token)).json()["seats"]
        base = float(sample_flight.base_price)
        first_seat = next(s for s in seats if s["seat_class"] == "first")
        business_seat = next(s for s in seats if s["seat_class"] == "business")
        economy_seat = next(s for s in seats if s["seat_class"] == "economy")
        assert first_seat["price"] == round(base * 3.0, 2)
        assert business_seat["price"] == round(base * 1.8, 2)
        assert economy_seat["price"] == round(base * 1.0, 2)

    def test_seat_generation_is_idempotent(self, client, passenger_account, sample_flight):
        token = _token(client, passenger_account)
        first = client.get(f"/api/v1/flights/{sample_flight.id}/seats", headers=auth_headers(token)).json()
        second = client.get(f"/api/v1/flights/{sample_flight.id}/seats", headers=auth_headers(token)).json()
        assert len(first["seats"]) == len(second["seats"]) == 300


class TestSeatBasedBooking:
    def test_booking_with_seat_id_marks_seat_occupied(self, client, passenger_account, sample_flight):
        token = _token(client, passenger_account)
        seats = client.get(f"/api/v1/flights/{sample_flight.id}/seats", headers=auth_headers(token)).json()["seats"]
        seat = next(s for s in seats if s["status"] == "available")

        booking_resp = client.post("/api/v1/booking/create", json={
            "flight_id": sample_flight.id, "seat_id": seat["id"],
        }, headers=auth_headers(token))
        assert booking_resp.status_code == 201
        assert booking_resp.json()["seat_number"] == seat["seat_number"]

        refreshed = client.get(f"/api/v1/flights/{sample_flight.id}/seats", headers=auth_headers(token)).json()["seats"]
        same_seat = next(s for s in refreshed if s["id"] == seat["id"])
        assert same_seat["status"] == "occupied"

    def test_booking_rejects_restricted_seat(self, client, passenger_account, sample_flight):
        token = _token(client, passenger_account)
        seats = client.get(f"/api/v1/flights/{sample_flight.id}/seats", headers=auth_headers(token)).json()["seats"]
        restricted = next(s for s in seats if s["status"] == "restricted")
        resp = client.post("/api/v1/booking/create", json={
            "flight_id": sample_flight.id, "seat_id": restricted["id"],
        }, headers=auth_headers(token))
        assert resp.status_code == 409

    def test_booking_rejects_already_taken_seat(self, client, passenger_account, sample_flight, db_session):
        from .conftest import unique_email
        from src import models
        from src.security import hash_password, encrypt_data

        token1 = _token(client, passenger_account)
        seats = client.get(f"/api/v1/flights/{sample_flight.id}/seats", headers=auth_headers(token1)).json()["seats"]
        seat = next(s for s in seats if s["status"] == "available")
        first = client.post("/api/v1/booking/create", json={"flight_id": sample_flight.id, "seat_id": seat["id"]}, headers=auth_headers(token1))
        assert first.status_code == 201

        email2 = unique_email("seatrace")
        password2 = "SeatRaceP@ss1!"
        user2 = models.User(email=email2, hashed_password=hash_password(password2), role="passenger", is_active=True)
        db_session.add(user2)
        db_session.commit()
        db_session.refresh(user2)
        db_session.add(models.Passenger(user_id=user2.id, full_name=encrypt_data("Race Passenger"), passport_number=encrypt_data("R0000001")))
        db_session.commit()
        token2 = login(client, email2, password2).json()["access_token"]

        second = client.post("/api/v1/booking/create", json={"flight_id": sample_flight.id, "seat_id": seat["id"]}, headers=auth_headers(token2))
        assert second.status_code == 409

    def test_payment_amount_reflects_seat_class(self, client, passenger_account, sample_flight):
        token = _token(client, passenger_account)
        seats = client.get(f"/api/v1/flights/{sample_flight.id}/seats", headers=auth_headers(token)).json()["seats"]
        first_class_seat = next(s for s in seats if s["seat_class"] == "first")

        booking = client.post("/api/v1/booking/create", json={
            "flight_id": sample_flight.id, "seat_id": first_class_seat["id"],
        }, headers=auth_headers(token)).json()

        pay_resp = client.post("/api/v1/payment/process", json={
            "booking_id": booking["id"], "card_number": "4111111111111111", "card_expiry": "12/29", "card_cvc": "123",
        }, headers=auth_headers(token))
        assert pay_resp.status_code == 201
        assert pay_resp.json()["amount"] == round(float(sample_flight.base_price) * 3.0, 2)


class TestFlightStatus:
    def test_scheduled_flight_has_no_live_data(self, client, passenger_account, sample_flight):
        token = _token(client, passenger_account)
        resp = client.get(f"/api/v1/flights/{sample_flight.id}/status", headers=auth_headers(token))
        assert resp.status_code == 200
        body = resp.json()
        assert body["live"] is None
        assert len(body["timeline"]) == 5

    def test_departed_flight_has_simulated_live_data(self, client, passenger_account, sample_flight, db_session):
        sample_flight.status = "departed"
        sample_flight.departure_time = datetime.utcnow() - timedelta(hours=1)
        sample_flight.arrival_time = datetime.utcnow() + timedelta(hours=2)
        db_session.commit()

        token = _token(client, passenger_account)
        resp = client.get(f"/api/v1/flights/{sample_flight.id}/status", headers=auth_headers(token))
        body = resp.json()
        assert body["live"]["simulated"] is True
        assert 0 < body["live"]["progress_fraction"] < 1
        assert body["live"]["altitude_ft"] >= 0

    def test_delay_alert_for_overdue_flight(self, client, passenger_account, sample_flight, db_session):
        sample_flight.departure_time = datetime.utcnow() - timedelta(hours=1)
        sample_flight.status = "scheduled"
        db_session.commit()

        token = _token(client, passenger_account)
        resp = client.get(f"/api/v1/flights/{sample_flight.id}/status", headers=auth_headers(token))
        alerts = resp.json()["alerts"]
        assert any(a["type"] == "delay" for a in alerts)

    def test_status_requires_authentication(self, client, sample_flight):
        resp = client.get(f"/api/v1/flights/{sample_flight.id}/status")
        assert resp.status_code == 401
