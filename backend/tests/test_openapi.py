"""Tests for OpenAPI schema generation and example restoration."""

import unittest

from app.main import app


class OpenApiTests(unittest.TestCase):
    def test_openapi_schema_contains_all_auth_and_user_endpoints(self):
        schema = app.openapi()
        paths = schema.get("paths", {})

        expected_paths = [
            "/health",
            "/api/v1/tickets",
            "/api/v1/tickets/{id}",
            "/api/v1/tickets/{id}/assign",
            "/api/v1/auth/login",
            "/api/v1/auth/refresh",
            "/api/v1/auth/logout",
            "/api/v1/users",
            "/api/v1/users/me",
            "/api/v1/users/{id}",
            "/api/v1/worker/skills",
        ]
        for path in expected_paths:
            self.assertIn(path, paths, f"Path {path} missing in OpenAPI schema")

        ticket_by_id_ops = paths["/api/v1/tickets/{id}"]
        self.assertIn("get", ticket_by_id_ops)
        self.assertIn("patch", ticket_by_id_ops)

        user_by_id_ops = paths["/api/v1/users/{id}"]
        self.assertIn("get", user_by_id_ops)
        self.assertIn("patch", user_by_id_ops)
        self.assertIn("delete", user_by_id_ops)

    def test_openapi_schema_contains_custom_examples(self):
        schema = app.openapi()
        schemas = schema["components"]["schemas"]

        for schema_name in (
            "TicketCreate",
            "TicketRead",
            "TicketUpdate",
            "TicketAssignWorkersRequest",
            "UserCreate",
            "UserUpdate",
            "UserRead",
            "WorkerSkillCreate",
            "WorkerSkillRead",
            "LoginRequest",
            "RefreshTokenRequest",
            "TokenResponse",
        ):
            self.assertIn(schema_name, schemas)
            self.assertIn("examples", schemas[schema_name])
            self.assertGreater(len(schemas[schema_name]["examples"]), 0)
