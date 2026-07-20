"""State-derived onboarding never accepts frontend completion claims."""


def test_onboarding_is_opt_in_and_progress_is_server_derived(make_client) -> None:
    with make_client(onboarding_enabled=True) as client:
        started = client.post("/onboarding/start")
        assert started.status_code == 200
        payload = started.json()
        assert payload["status"] == "in_progress"
        assert payload["activated"] is False
        assert any(step["step_key"] == "identity" for step in payload["steps"])
        assert all(step["status"] != "completed" for step in payload["steps"])


def test_onboarding_has_no_client_completion_endpoint(client) -> None:
    assert client.post("/onboarding/steps/identity/complete").status_code == 404


def test_detection_test_requires_a_verified_monitored_deployment(make_client) -> None:
    with make_client(
        onboarding_enabled=True,
        onboarding_detection_test_enabled=True,
    ) as client:
        assert (
            client.post(
                "/onboarding/detection-tests",
                json={"deployment_id": "00000000-0000-0000-0000-000000000001"},
            ).status_code
            == 409
        )
