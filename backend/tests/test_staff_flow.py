from .conftest import login, login_staff_with_2fa, auth_headers


def _staff_token(client, account):
    return login_staff_with_2fa(client, account["email"], account["password"], account["totp_secret"]).json()["access_token"]


def _passenger_token(client, account):
    return login(client, account["email"], account["password"]).json()["access_token"]


class TestStaffOperations:
    def test_staff_dashboard_returns_stats(self, client, agent_account):
        token = _staff_token(client, agent_account)
        resp = client.get("/api/v1/staff/dashboard", headers=auth_headers(token))
        assert resp.status_code == 200
        body = resp.json()
        assert "flights_today" in body and "checkins_completed" in body

    def test_agent_can_redeem_boarding_pass(self, client, agent_account, passenger_account, sample_flight):
        pax_token = _passenger_token(client, passenger_account)
        booking = client.post("/api/v1/booking/create", json={"flight_id": sample_flight.id}, headers=auth_headers(pax_token)).json()
        bp_token = client.post("/api/v1/passenger/checkin", json={"booking_id": booking["id"]}, headers=auth_headers(pax_token)).json()["boarding_pass_token"]

        agent_token = _staff_token(client, agent_account)
        resp = client.post("/api/v1/staff/checkin-passenger", json={"boarding_pass_token": bp_token}, headers=auth_headers(agent_token))
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_boarding_pass_cannot_be_reused(self, client, agent_account, passenger_account, sample_flight):
        pax_token = _passenger_token(client, passenger_account)
        booking = client.post("/api/v1/booking/create", json={"flight_id": sample_flight.id}, headers=auth_headers(pax_token)).json()
        bp_token = client.post("/api/v1/passenger/checkin", json={"booking_id": booking["id"]}, headers=auth_headers(pax_token)).json()["boarding_pass_token"]

        agent_token = _staff_token(client, agent_account)
        first = client.post("/api/v1/staff/checkin-passenger", json={"boarding_pass_token": bp_token}, headers=auth_headers(agent_token))
        assert first.status_code == 200

        second = client.post("/api/v1/staff/checkin-passenger", json={"boarding_pass_token": bp_token}, headers=auth_headers(agent_token))
        assert second.status_code == 410

    def test_invalid_boarding_pass_token_rejected(self, client, agent_account):
        token = _staff_token(client, agent_account)
        resp = client.post("/api/v1/staff/checkin-passenger", json={"boarding_pass_token": "totally-fake-token-1234567890"}, headers=auth_headers(token))
        assert resp.status_code == 404

    def test_crew_manifest_lists_booked_passengers(self, client, crew_account, passenger_account, sample_flight):
        pax_token = _passenger_token(client, passenger_account)
        client.post("/api/v1/booking/create", json={"flight_id": sample_flight.id, "seat_number": "3B"}, headers=auth_headers(pax_token))

        token = _staff_token(client, crew_account)
        resp = client.get(f"/api/v1/staff/flights/{sample_flight.id}/manifest", headers=auth_headers(token))
        assert resp.status_code == 200
        names = [p["passenger_name"] for p in resp.json()["manifest"]]
        assert "Test Passenger" in names
