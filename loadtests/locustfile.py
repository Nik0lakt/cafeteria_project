"""
Load test simulating multiple cash terminals making concurrent payments.

Run:  make load-test
  or: locust -f loadtests/locustfile.py --headless -u 50 -r 10 -t 30s --host http://localhost:8000
"""

from locust import HttpUser, between, task


class CashTerminalUser(HttpUser):
    wait_time = between(1, 3)

    @task(3)
    def get_employee_info(self):
        self.client.get("/api/employee_info?card_uid=ABC123", name="/api/employee_info")

    @task(2)
    def start_liveness(self):
        resp = self.client.post("/api/start_liveness?card_uid=ABC123", name="/api/start_liveness")
        if resp.status_code == 200:
            self.session_id = resp.json().get("session_id")

    @task(1)
    def get_app_settings(self):
        self.client.get("/api/app_settings", name="/api/app_settings")

    @task(1)
    def get_categories(self):
        self.client.get("/api/categories?desk=desk1", name="/api/categories")

    @task(1)
    def get_products(self):
        self.client.get("/api/products?desk=desk1", name="/api/products")
