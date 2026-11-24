from datetime import datetime, timedelta
from .conftest import login, login_staff_with_2fa, auth_headers


def _passenger_token(client, account):
    return login(client, account["email"], account["password"]).json()["access_token"]


def _admin_token(client, admin_account):
    return login_staff_with_2fa(client, admin_account["email"], admin_account["password"], admin_account["totp_secret"]).json()["access_token"]


class TestAnalyticsAccessControl:
    def test_requires_admin_role(self, client, passenger_account):
        token = _passenger_token(client, passenger_account)
        resp = client.get("/api/v1/admin/analytics/overview", headers=auth_headers(token))
        assert resp.status_code == 403

    def test_requires_authentication(self, client):
        resp = client.get("/api/v1/admin/analytics/overview")
        assert resp.status_code == 401


class TestAnalyticsRealData:
    def test_overview_counts_todays_flight(self, client, admin_account, sample_flight):
        token = _admin_token(client, admin_account)
        resp = client.get("/api/v1/admin/analytics/overview", headers=auth_headers(token))
        assert resp.status_code == 200
        body = resp.json()
        assert body["flights_today"] >= 1  # sample_flight departs in 2h, i.e. today
        assert "monitoring_note" in body

    def test_overview_revenue_reflects_real_payment(self, client, admin_account, passenger_account, sample_flight):
        pax_token = _passenger_token(client, passenger_account)
        booking = client.post("/api/v1/booking/create", json={"flight_id": sample_flight.id}, headers=auth_headers(pax_token)).json()
        pay_resp = client.post("/api/v1/payment/process", json={
            "booking_id": booking["id"], "card_number": "4111111111111111", "card_expiry": "12/29", "card_cvc": "123",
        }, headers=auth_headers(pax_token))
        amount = pay_resp.json()["amount"]

        admin_token = _admin_token(client, admin_account)
        overview = client.get("/api/v1/admin/analytics/overview", headers=auth_headers(admin_token)).json()
        assert overview["revenue_today"] >= amount

    def test_popular_routes_reflects_real_booking(self, client, admin_account, passenger_account, sample_flight):
        pax_token = _passenger_token(client, passenger_account)
        client.post("/api/v1/booking/create", json={"flight_id": sample_flight.id}, headers=auth_headers(pax_token))

        admin_token = _admin_token(client, admin_account)
        routes = client.get("/api/v1/admin/analytics/popular-routes", headers=auth_headers(admin_token)).json()
        match = next((r for r in routes if r["from_airport"] == sample_flight.from_airport and r["to_airport"] == sample_flight.to_airport), None)
        assert match is not None
        assert match["bookings"] >= 1

    def test_revenue_by_airline_derives_code_from_flight_number(self, client, admin_account, passenger_account, db_session):
        # A real-looking flight number (letters-then-digits) rather than the
        # random-hex sample_flight, since the airline code is the *leading*
        # 2-3 letters specifically, not just any letters in the string.
        from src import models
        from datetime import datetime, timedelta
        flight = models.Flight(
            flight_number="ZZ777", departure_time=datetime.utcnow() + timedelta(hours=2),
            arrival_time=datetime.utcnow() + timedelta(hours=5), from_airport="YVR", to_airport="YYZ",
            aircraft_id="A320", base_price=250.00, status="scheduled",
        )
        db_session.add(flight)
        db_session.commit()
        db_session.refresh(flight)

        pax_token = _passenger_token(client, passenger_account)
        booking = client.post("/api/v1/booking/create", json={"flight_id": flight.id}, headers=auth_headers(pax_token)).json()
        client.post("/api/v1/payment/process", json={
            "booking_id": booking["id"], "card_number": "4111111111111111", "card_expiry": "12/29", "card_cvc": "123",
        }, headers=auth_headers(pax_token))

        admin_token = _admin_token(client, admin_account)
        revenue = client.get("/api/v1/admin/analytics/revenue-by-airline", headers=auth_headers(admin_token)).json()
        assert any(r["airline"] == "ZZ" for r in revenue)

    def test_hourly_checkins_reflects_real_checkin(self, client, admin_account, passenger_account, sample_flight):
        pax_token = _passenger_token(client, passenger_account)
        booking = client.post("/api/v1/booking/create", json={"flight_id": sample_flight.id}, headers=auth_headers(pax_token)).json()
        client.post("/api/v1/passenger/checkin", json={"booking_id": booking["id"]}, headers=auth_headers(pax_token))

        admin_token = _admin_token(client, admin_account)
        hourly = client.get("/api/v1/admin/analytics/hourly-checkins", headers=auth_headers(admin_token)).json()
        assert sum(h["count"] for h in hourly) >= 1

    def test_realtime_stats_shape(self, client, admin_account):
        admin_token = _admin_token(client, admin_account)
        resp = client.get("/api/v1/admin/analytics/realtime", headers=auth_headers(admin_token))
        assert resp.status_code == 200
        body = resp.json()
        assert "flights_departing_next_2h" in body
        assert "staff_by_department" in body

    def test_activity_feed_reflects_recent_action(self, client, admin_account, passenger_account):
        login(client, passenger_account["email"], passenger_account["password"])
        admin_token = _admin_token(client, admin_account)
        feed = client.get("/api/v1/admin/analytics/activity-feed", headers=auth_headers(admin_token)).json()
        assert any(entry["action"] == "LOGIN_SUCCESS" for entry in feed)

    def test_alerts_flag_delayed_flight(self, client, admin_account, sample_flight, db_session):
        sample_flight.departure_time = datetime.utcnow() - timedelta(hours=1)
        sample_flight.status = "scheduled"
        db_session.commit()

        admin_token = _admin_token(client, admin_account)
        alerts = client.get("/api/v1/admin/analytics/alerts", headers=auth_headers(admin_token)).json()
        assert any(a["type"] == "flight_delay" for a in alerts)

    def test_no_fabricated_uptime_metric(self, client, admin_account):
        """No literal uptime-percentage field - the honest 'go check Grafana'
        pointer is fine, a made-up number would not be."""
        admin_token = _admin_token(client, admin_account)
        overview = client.get("/api/v1/admin/analytics/overview", headers=auth_headers(admin_token)).json()
        assert "uptime_percentage" not in overview
        assert "system_uptime" not in overview
