from .conftest import login, login_staff_with_2fa, auth_headers


def _passenger_token(client, passenger_account):
    return login(client, passenger_account["email"], passenger_account["password"]).json()["access_token"]


def _staff_token(client, account):
    return login_staff_with_2fa(client, account["email"], account["password"], account["totp_secret"]).json()["access_token"]


class TestRoleBasedAccessControl:
    def test_passenger_cannot_access_staff_dashboard(self, client, passenger_account):
        token = _passenger_token(client, passenger_account)
        resp = client.get("/api/v1/staff/dashboard", headers=auth_headers(token))
        assert resp.status_code == 403

    def test_passenger_cannot_access_admin_users(self, client, passenger_account):
        token = _passenger_token(client, passenger_account)
        resp = client.get("/api/v1/admin/users", headers=auth_headers(token))
        assert resp.status_code == 403

    def test_agent_cannot_access_admin_endpoints(self, client, agent_account):
        token = _staff_token(client, agent_account)
        resp = client.get("/api/v1/admin/users", headers=auth_headers(token))
        assert resp.status_code == 403

    def test_agent_can_access_staff_dashboard(self, client, agent_account):
        token = _staff_token(client, agent_account)
        resp = client.get("/api/v1/staff/dashboard", headers=auth_headers(token))
        assert resp.status_code == 200

    def test_agent_cannot_view_flight_manifest_crew_only(self, client, agent_account):
        token = _staff_token(client, agent_account)
        resp = client.get("/api/v1/staff/flights/1/manifest", headers=auth_headers(token))
        assert resp.status_code == 403

    def test_crew_can_view_flight_manifest(self, client, crew_account, sample_flight):
        token = _staff_token(client, crew_account)
        resp = client.get(f"/api/v1/staff/flights/{sample_flight.id}/manifest", headers=auth_headers(token))
        assert resp.status_code == 200

    def test_crew_cannot_report_incidents(self, client, crew_account):
        token = _staff_token(client, crew_account)
        resp = client.post("/api/v1/staff/incidents", json={
            "incident_type": "unauthorized_access", "description": "test", "severity": "low"
        }, headers=auth_headers(token))
        assert resp.status_code == 403

    def test_security_can_report_and_view_incidents(self, client, security_account):
        token = _staff_token(client, security_account)
        create_resp = client.post("/api/v1/staff/incidents", json={
            "incident_type": "unauthorized_access", "description": "Badge tailgating at gate B4", "severity": "medium"
        }, headers=auth_headers(token))
        assert create_resp.status_code == 201

        list_resp = client.get("/api/v1/staff/incidents", headers=auth_headers(token))
        assert list_resp.status_code == 200
        assert len(list_resp.json()) >= 1

    def test_admin_can_list_users(self, client, admin_account):
        token = _staff_token(client, admin_account)
        resp = client.get("/api/v1/admin/users", headers=auth_headers(token))
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_admin_can_create_staff_account(self, client, admin_account):
        token = _staff_token(client, admin_account)
        resp = client.post("/api/v1/admin/create-staff", json={
            "email": "newagent@example.com",
            "password": "NewAgentP@ss1!",
            "full_name": "Newly Hired",
            "role": "agent",
            "department": "Passenger Services",
            "employee_id": "EMP9999",
        }, headers=auth_headers(token))
        assert resp.status_code == 201
        assert resp.json()["role"] == "agent"

    def test_non_admin_cannot_create_staff_account(self, client, agent_account):
        token = _staff_token(client, agent_account)
        resp = client.post("/api/v1/admin/create-staff", json={
            "email": "sneaky@example.com",
            "password": "SneakyP@ss1!",
            "full_name": "Sneaky",
            "role": "admin",
            "employee_id": "EMP0001",
        }, headers=auth_headers(token))
        assert resp.status_code == 403

    def test_unauthenticated_request_denied_everywhere(self, client):
        for path in ["/api/v1/staff/dashboard", "/api/v1/admin/users", "/api/v1/passenger/bookings"]:
            resp = client.get(path)
            assert resp.status_code == 401
