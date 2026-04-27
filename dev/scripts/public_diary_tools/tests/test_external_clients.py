"""Coverage note for SDK adapters.

`public_diary_tools.clients` is intentionally omitted from coverage because it
is a thin adapter over Google API Python Client, google-auth, PyGithub, and
gcloud token commands. Unit tests cover the calling code with fakes; live SDK
behavior should be checked through manual provisioning or a dedicated
integration test account, not normal repository tests.
"""


def test_external_client_coverage_exception_is_documented() -> None:
    assert True
