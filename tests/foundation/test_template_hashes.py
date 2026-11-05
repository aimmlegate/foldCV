"""The hash check prints one line per public bundled template and fails on a changed value."""

from tools import check_template_hashes


def test_one_line_per_public_template():
    lines = check_template_hashes.lines()
    assert [line.split()[0] for line in lines] == list(check_template_hashes.PUBLIC)
    assert all(len(line.split()) == 5 for line in lines)


def test_expect_fails_on_a_changed_hash(tmp_path, capsys):
    lines = check_template_hashes.lines()
    recorded = tmp_path / "hashes.txt"
    recorded.write_text("\n".join(lines) + "\n")
    assert check_template_hashes.main(["--expect", str(recorded)]) == 0
    first = lines[0].split()
    first[2] = "0" * 64
    recorded.write_text("\n".join([" ".join(first), *lines[1:]]) + "\n")
    assert check_template_hashes.main(["--expect", str(recorded)]) == 1
    recorded.write_text("\n".join(lines[1:]) + "\n")
    assert check_template_hashes.main(["--expect", str(recorded)]) == 1
