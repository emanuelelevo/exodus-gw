from logging import DEBUG

from exodus_gw.aws.util import uri_alias


def test_uri_alias(caplog):
    caplog.set_level(DEBUG, logger="exodus-gw")
    uri = "/content/origin/rpms/path/to/file.iso"
    aliases = [
        {"dest": "/origin", "src": "/content/origin"},
        {"dest": "/origin/rpms", "src": "/origin/rpm"},
    ]
    expected = "/origin/rpms/path/to/file.iso"

    assert uri_alias(uri, aliases) == "/origin/rpms/path/to/file.iso"
    assert (
        "Resolved alias:\n\tsrc: %s\n\tdest: %s" % (uri, expected)
        in caplog.text
    )
