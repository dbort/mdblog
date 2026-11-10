from pathlib import Path

import pytest

from mdblog.config import ConfigError, SiteConfig, WorkerConfig, load_config

VALID = 'base_url = "https://example.test/"\ntitle = "A title"\nauthor = "An author"\n'


def _write_config(vault: Path, text: str | bytes) -> Path:
    path = vault / "_site" / "mdblog.toml"
    path.parent.mkdir(parents=True)
    if isinstance(text, str):
        path.write_text(text, encoding="utf-8")
    else:
        path.write_bytes(text)
    return path


def test_load_config_returns_the_values(tmp_path: Path) -> None:
    _write_config(tmp_path, VALID)

    assert load_config(tmp_path) == SiteConfig(
        base_url="https://example.test/", title="A title", author="An author"
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param("title = ", "invalid TOML", id="invalid-toml"),
        pytest.param(b"title = '\xff'\n", "invalid TOML", id="not-utf-8"),
        pytest.param(
            'base_url = "u"\ntitle = "t"\n', "missing key 'author'", id="missing-key"
        ),
        pytest.param(
            'base_url = "u"\ntitle = "t"\nauthor = 1\n',
            "key 'author' must be a string",
            id="non-string",
        ),
        pytest.param(
            VALID + 'titel = "typo"\n', "unknown key 'titel'", id="unknown-key"
        ),
    ],
)
def test_load_config_names_the_file_and_the_problem(
    tmp_path: Path, text: str | bytes, expected: str
) -> None:
    path = _write_config(tmp_path, text)

    with pytest.raises(ConfigError) as exc:
        load_config(tmp_path)

    assert str(path) in str(exc.value)
    assert expected in str(exc.value)


def test_load_config_reads_the_worker_table(tmp_path: Path) -> None:
    _write_config(tmp_path, VALID + '[worker]\nname = "my-site-2"\n')

    assert load_config(tmp_path).worker == WorkerConfig(name="my-site-2")


def test_load_config_has_no_worker_without_the_table(tmp_path: Path) -> None:
    _write_config(tmp_path, VALID)

    assert load_config(tmp_path).worker is None


@pytest.mark.parametrize("name", ["a", "a1", "my-site", "x" * 63])
def test_load_config_accepts_a_valid_worker_name(tmp_path: Path, name: str) -> None:
    _write_config(tmp_path, VALID + f'[worker]\nname = "{name}"\n')

    assert load_config(tmp_path).worker == WorkerConfig(name=name)


def test_load_config_reads_routes_in_order(tmp_path: Path) -> None:
    _write_config(
        tmp_path,
        VALID + '[worker]\nname = "site"\nroutes = ["b.test/x/*", "a.test/x/*"]\n',
    )

    assert load_config(tmp_path).worker == WorkerConfig(
        name="site", routes=("b.test/x/*", "a.test/x/*")
    )


INVALID_NAME = "is not a valid Worker name"
NOT_AN_ARRAY = "[worker] routes must be a non-empty array of strings"
NOT_STRINGS = "[worker] routes must hold only non-empty strings"


@pytest.mark.parametrize(
    ("worker", "expected"),
    [
        pytest.param('worker = "site"\n', "[worker] must be a table", id="not-table"),
        pytest.param("[worker]\n", "[worker] is missing key 'name'", id="no-name"),
        pytest.param(
            "[worker]\nname = 3\n", "[worker] key 'name' must be a string", id="int"
        ),
        pytest.param('[worker]\nname = ""\n', INVALID_NAME, id="empty"),
        pytest.param('[worker]\nname = "My-Site"\n', INVALID_NAME, id="uppercase"),
        pytest.param('[worker]\nname = "my_site"\n', INVALID_NAME, id="underscore"),
        pytest.param('[worker]\nname = "-site"\n', INVALID_NAME, id="leading-dash"),
        pytest.param('[worker]\nname = "site-"\n', INVALID_NAME, id="trailing-dash"),
        pytest.param(f'[worker]\nname = "{"x" * 64}"\n', INVALID_NAME, id="too-long"),
        pytest.param(
            '[worker]\nname = "site"\nroute = "x"\n',
            "[worker] has unknown key 'route'",
            id="unknown-key",
        ),
        pytest.param(
            '[worker]\nname = "site"\nroutes = "a.test/*"\n',
            NOT_AN_ARRAY,
            id="routes-string",
        ),
        pytest.param(
            '[worker]\nname = "site"\nroutes = []\n', NOT_AN_ARRAY, id="routes-empty"
        ),
        pytest.param(
            '[worker]\nname = "site"\nroutes = ["a.test/*", 3]\n',
            NOT_STRINGS,
            id="routes-int",
        ),
        pytest.param(
            '[worker]\nname = "site"\nroutes = ["a.test/*", ""]\n',
            NOT_STRINGS,
            id="routes-empty-string",
        ),
    ],
)
def test_load_config_names_the_file_and_the_worker_problem(
    tmp_path: Path, worker: str, expected: str
) -> None:
    path = _write_config(tmp_path, VALID + worker)

    with pytest.raises(ConfigError) as exc:
        load_config(tmp_path)

    assert str(path) in str(exc.value)
    assert expected in str(exc.value)


def test_load_config_lists_every_bad_key_in_one_error(tmp_path: Path) -> None:
    _write_config(tmp_path, 'title = 1\nextra = "x"\n')

    with pytest.raises(ConfigError) as exc:
        load_config(tmp_path)

    for expected in ("'base_url'", "'title'", "'author'", "'extra'"):
        assert expected in str(exc.value)


def test_load_config_names_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as exc:
        load_config(tmp_path)

    assert str(tmp_path / "_site" / "mdblog.toml") in str(exc.value)


def test_load_config_names_a_path_it_cannot_read(tmp_path: Path) -> None:
    (tmp_path / "_site" / "mdblog.toml").mkdir(parents=True)

    with pytest.raises(ConfigError, match="cannot read"):
        load_config(tmp_path)


def test_load_config_does_not_follow_a_symlinked_file(tmp_path: Path) -> None:
    elsewhere = tmp_path / "elsewhere.toml"
    elsewhere.write_text(VALID, encoding="utf-8")
    vault = tmp_path / "vault"
    (vault / "_site").mkdir(parents=True)
    (vault / "_site" / "mdblog.toml").symlink_to(elsewhere)

    with pytest.raises(ConfigError, match="symbolic link"):
        load_config(vault)


def test_load_config_does_not_follow_a_symlinked_site_directory(tmp_path: Path) -> None:
    elsewhere = tmp_path / "elsewhere"
    _write_config(elsewhere, VALID)
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "_site").symlink_to(elsewhere / "_site")

    with pytest.raises(ConfigError, match="symbolic link"):
        load_config(vault)
