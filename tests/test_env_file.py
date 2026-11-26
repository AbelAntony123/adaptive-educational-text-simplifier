from services.env_file import load_env_file


def write(tmp_path, text):
    path = tmp_path / ".env"
    path.write_text(text, encoding="utf-8")
    return path


def test_values_are_loaded_and_only_names_are_returned(tmp_path):
    path = write(tmp_path, "GEMINI_API_KEY=secret-value\nGEMINI_MODEL=gemini-test\n")
    environ = {}
    names = load_env_file(path, environ)
    assert names == ["GEMINI_API_KEY", "GEMINI_MODEL"]
    assert environ == {"GEMINI_API_KEY": "secret-value", "GEMINI_MODEL": "gemini-test"}
    assert "secret-value" not in repr(names)


def test_existing_environment_variables_are_not_overwritten(tmp_path):
    path = write(tmp_path, "GEMINI_MODEL=from-file\n")
    environ = {"GEMINI_MODEL": "from-terminal"}
    load_env_file(path, environ)
    assert environ["GEMINI_MODEL"] == "from-terminal"


def test_comments_blank_lines_export_and_quotes(tmp_path):
    path = write(tmp_path, "# comment\n\nexport A=1\nB=\"two words\"\nC='single'\n  D = spaced  \n")
    environ = {}
    load_env_file(path, environ)
    assert environ == {"A": "1", "B": "two words", "C": "single", "D": "spaced"}


def test_empty_placeholders_are_ignored(tmp_path):
    path = write(tmp_path, "GEMINI_API_KEY=\nGEMINI_MODEL=\n")
    environ = {}
    assert load_env_file(path, environ) == []
    assert environ == {}


def test_bad_lines_are_skipped_without_error(tmp_path):
    path = write(tmp_path, "no equals sign\n=novalue\n1BAD=x\nGOOD=ok\n")
    environ = {}
    assert load_env_file(path, environ) == ["GOOD"]


def test_value_containing_an_equals_sign_is_kept_whole(tmp_path):
    path = write(tmp_path, "TOKEN=abc=def==\n")
    environ = {}
    load_env_file(path, environ)
    assert environ["TOKEN"] == "abc=def=="


def test_the_default_path_is_used_when_none_is_given(tmp_path, monkeypatch):
    from services import env_file

    path = write(tmp_path, "FROM_DEFAULT=yes\n")
    monkeypatch.setattr(env_file, "DEFAULT_ENV_PATH", path)
    environ = {}
    assert load_env_file(environ=environ) == ["FROM_DEFAULT"]
    assert environ == {"FROM_DEFAULT": "yes"}


def test_missing_file_is_not_an_error(tmp_path):
    assert load_env_file(tmp_path / "does-not-exist.env", {}) == []


def test_file_with_a_byte_order_mark_is_read(tmp_path):
    path = tmp_path / ".env"
    path.write_bytes("﻿GEMINI_MODEL=ok\n".encode("utf-8"))
    environ = {}
    load_env_file(path, environ)
    assert environ == {"GEMINI_MODEL": "ok"}
