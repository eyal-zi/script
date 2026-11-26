import pytest

from repo_rename.casing import split_words, with_case_variants


@pytest.mark.parametrize(
    ("name", "words"),
    [
        ("training", ["training"]),
        ("DataLoader", ["data", "loader"]),
        ("dataLoader", ["data", "loader"]),
        ("data_loader", ["data", "loader"]),
        ("DATA-LOADER", ["data", "loader"]),
        ("data loader", ["data", "loader"]),
        ("HTTPServer", ["http", "server"]),
        ("v2Api", ["v2", "api"]),
        ("com.example", None),
        ("_private", None),
    ],
)
def test_split_words(name: str, words: list[str] | None) -> None:
    assert split_words(name) == words


def test_single_word_variants() -> None:
    assert with_case_variants({"training": "hello"}) == {
        "training": "hello",
        "TRAINING": "HELLO",
        "Training": "Hello",
    }


def test_multi_word_variants() -> None:
    assert with_case_variants({"data_loader": "batch_reader"}) == {
        "data_loader": "batch_reader",
        "DATA_LOADER": "BATCH_READER",
        "dataLoader": "batchReader",
        "DataLoader": "BatchReader",
        "data-loader": "batch-reader",
        "DATA-LOADER": "BATCH-READER",
        "Data-Loader": "Batch-Reader",
        "data loader": "batch reader",
        "Data Loader": "Batch Reader",
        "Data loader": "Batch reader",
        "DATA LOADER": "BATCH READER",
    }


def test_old_and_new_may_have_different_word_counts() -> None:
    assert with_case_variants({"model": "neural_net"}) == {
        "model": "neural_net",
        "MODEL": "NEURAL_NET",
        "Model": "NeuralNet",
    }


def test_explicit_rules_win_over_generated_variants() -> None:
    variants = with_case_variants({"training": "hello", "Training": "Greeting"})
    assert variants["Training"] == "Greeting"
    assert variants["TRAINING"] == "HELLO"


def test_non_identifier_names_are_only_renamed_exactly() -> None:
    assert with_case_variants({"com.example": "org.sample"}) == {"com.example": "org.sample"}
