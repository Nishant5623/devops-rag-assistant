"""
Locust load-testing script for the DevOps RAG Assistant.

Run against a running instance:
    locust -f loadtest/locustfile.py --host http://localhost:8000
Then open http://localhost:8009 to start a load test.
"""
from locust import HttpUser, between, task


class RagUser(HttpUser):
    wait_time = between(1, 3)

    @task(3)
    def ask_question(self):
        self.client.post(
            "/api/v1/ask",
            json={"question": "What is a Kubernetes Deployment?", "k": 3},
        )

    @task(1)
    def ask_docker_question(self):
        self.client.post(
            "/api/v1/ask",
            json={"question": "How do Docker volumes work?", "k": 3},
        )

    @task(1)
    def health_check(self):
        self.client.get("/api/v1/health")
