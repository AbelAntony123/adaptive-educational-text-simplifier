from ui.diff import word_diff_html


def test_identical_texts_have_no_markup():
    left, right = word_diff_html("the cat sat", "the cat sat")
    assert left == right == "the cat sat"


def test_removed_and_added_words_are_marked():
    left, right = word_diff_html("the cat sat down", "the cat rested")
    assert "<del>sat down</del>" in left
    assert "<ins>rested</ins>" in right
    assert "<ins>" not in left and "<del>" not in right


def test_html_in_the_text_is_escaped():
    left, right = word_diff_html("a <script>alert(1)</script> b", "a b")
    assert "<script>" not in left
    assert "&lt;script&gt;" in left


def test_empty_text_does_not_crash():
    assert word_diff_html("", "") == ("", "")
    left, right = word_diff_html("hello", "")
    assert left == "<del>hello</del>" and right == ""
