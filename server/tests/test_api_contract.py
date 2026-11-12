import unittest
try:
    from pydantic import ValidationError
    from basheco.api import RegisterRequest, TransferRequest
except ImportError:
    RegisterRequest = TransferRequest = None

@unittest.skipIf(RegisterRequest is None, "API requirements not installed")
class ApiContractTests(unittest.TestCase):
    def test_email_normalization(self):
        x = RegisterRequest(email="TEST@Example.org",display_name="Tester",password="a-long-secure-password")
        self.assertEqual(x.email,"test@example.org")
    def test_short_password_rejected(self):
        with self.assertRaises(ValidationError):
            RegisterRequest(email="a@example.org",display_name="Tester",password="short")
    def test_fractional_money_rejected(self):
        from uuid import uuid4
        with self.assertRaises(ValidationError):
            TransferRequest(debit_wallet=uuid4(),credit_wallet=uuid4(),amount_kopecks=1.5,idempotency_key="transaction-1")
    def test_bad_idempotency_rejected(self):
        from uuid import uuid4
        with self.assertRaises(ValidationError):
            TransferRequest(debit_wallet=uuid4(),credit_wallet=uuid4(),amount_kopecks=1,idempotency_key="invalid space")

class ProxyIdentityTests(unittest.TestCase):
    def test_untrusted_header_cannot_spoof(self):
        from unittest.mock import patch
        from starlette.requests import Request
        from basheco.api import client_identity
        request=Request({"type":"http","headers":[
            (b"x-basheco-client-ip",b"8.8.8.8"),
            (b"x-basheco-proxy-secret",b"wrong"),
        ],"client":("172.18.0.1",1234),"method":"GET","path":"/"})
        with patch.dict("os.environ",{"BASHECO_PROXY_SECRET":"real"},clear=False):
            self.assertEqual(client_identity(request),"172.18.0.1")

    def test_trusted_header_and_invalid_ip(self):
        from unittest.mock import patch
        from starlette.requests import Request
        from basheco.api import client_identity
        def req(ip):
            return Request({"type":"http","headers":[
                (b"x-basheco-client-ip",ip.encode()),
                (b"x-basheco-proxy-secret",b"real"),
            ],"client":("172.18.0.1",1234),"method":"GET","path":"/"})
        with patch.dict("os.environ",{"BASHECO_PROXY_SECRET":"real"},clear=False):
            self.assertEqual(client_identity(req("203.0.113.8")),"203.0.113.8")
            self.assertEqual(client_identity(req("bad,ip")),"172.18.0.1")


@unittest.skipIf(RegisterRequest is None, "API requirements not installed")
class WorldRouteContractTests(unittest.TestCase):
    def test_existing_world_routes_are_kept_and_global_ones_added(self):
        from basheco.api import app
        routes = {(sorted(r.methods - {"HEAD"})[0], r.path) for r in app.routes if hasattr(r, "methods")}
        for route in (("POST", "/v1/world/plots"), ("GET", "/v1/world/sectors/{sector_id}/viewport"),
                      ("GET", "/v1/world/sectors/{sector_id}"), ("POST", "/v1/world/buildings"),
                      ("GET", "/v1/geography/locations"), ("GET", "/v1/economy/catalog"),
                      ("GET", "/v1/market/listings"),
                      ("GET", "/v1/world/grid"), ("GET", "/v1/world/viewport")):
            self.assertIn(route, routes)

    def test_global_viewport_requires_a_session(self):
        try:
            from starlette.testclient import TestClient
        except Exception:  # httpx not installed in the runtime image
            self.skipTest("HTTP test client unavailable")
        from basheco.api import app
        client = TestClient(app)
        query = "?min_cell_x=0&min_cell_y=0&max_cell_x=10&max_cell_y=10"
        self.assertEqual(client.get("/v1/world/viewport" + query).status_code, 401)
        self.assertEqual(client.get("/v1/world/viewport" + query,
                                    headers={"Authorization": "Bearer nope"}).status_code, 401)
