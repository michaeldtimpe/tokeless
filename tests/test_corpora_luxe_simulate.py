"""Tests for the synthetic luxe-trace generator.

The simulator's contracts that these tests pin:
- Byte-identical output for same (archetype, seed).
- Valid JSONL — `load_jsonl_with_stats` reports skip_rate == 0.0.
- Hostile archetype produces zero fires across all 4 registered
  compressors (the floor — confirms the no-fire branch holds on a
  non-synthetic-corpus shape).
- Bundle layout: four archetype_<name>/ subdirs each with a .jsonl
  and a manifest.json with required keys.
"""

import json
from pathlib import Path

import pytest

from tokeless.compressors import compress_messages
from tokeless.corpora.luxe_simulate import (
    ARCHETYPES,
    simulate_archetype,
    write_archetype_bundle,
)
from tokeless.corpora.luxe_trace import load_jsonl, load_jsonl_with_stats


@pytest.mark.parametrize("archetype", ARCHETYPES)
def test_simulate_archetype_writes_valid_jsonl(tmp_path: Path, archetype: str):
    """Generated JSONL loads cleanly (no schema drift)."""
    path = simulate_archetype(archetype, tmp_path)
    assert path.exists()
    item, stats = load_jsonl_with_stats(path)
    assert stats.skip_rate == 0.0, (
        f"{archetype} generated content that fails ingestion: "
        f"skip_rate={stats.skip_rate}, shapes={stats.sample_skipped_shapes}"
    )
    # All archetypes produce at least 20 events.
    assert len(item.messages) >= 20


@pytest.mark.parametrize("archetype", ARCHETYPES)
def test_simulate_archetype_deterministic(tmp_path: Path, archetype: str):
    """Same seed → byte-identical JSONL across runs."""
    a = simulate_archetype(archetype, tmp_path / "a", seed=7)
    b = simulate_archetype(archetype, tmp_path / "b", seed=7)
    assert a.read_bytes() == b.read_bytes(), (
        f"{archetype} is not deterministic at seed=7"
    )


def test_simulate_archetype_different_seeds_differ_for_hostile(tmp_path: Path):
    """Hostile archetype uses the seed (random bodies). Other archetypes
    use deterministic content and are seed-invariant — which is fine,
    determinism for them is implicit. Pin only hostile here."""
    a = simulate_archetype("hostile", tmp_path / "a", seed=1)
    b = simulate_archetype("hostile", tmp_path / "b", seed=2)
    assert a.read_bytes() != b.read_bytes()


def test_simulate_archetype_unknown_raises(tmp_path: Path):
    with pytest.raises(ValueError, match="Unknown archetype"):
        simulate_archetype("definitely_not_a_real_archetype", tmp_path)


def test_hostile_zero_fires_across_all_compressors(tmp_path: Path):
    """The mechanism-pinned claim: hostile produces fires == 0 for
    every registered non-noop compressor. This is the floor — proves
    the no-fire branch works on a non-synthetic-corpus shape.
    """
    path = simulate_archetype("hostile", tmp_path, seed=0)
    item = load_jsonl(path)
    for compressor_id in (
        "exact_hash_dedup",
        "structural_dedup",
        "structured_normalize",
        "dedup_then_normalize",
    ):
        _out, stats = compress_messages(item.messages, compressor_id)
        assert stats.fires == 0, (
            f"{compressor_id} unexpectedly fired on hostile fixture: "
            f"fires={stats.fires}"
        )


def test_lint_heavy_normalizer_fires(tmp_path: Path):
    """Lint-heavy should fire structured_normalize on mypy + ruff bodies.
    Sanity check that the recipe actually exercises what it claims to.
    """
    path = simulate_archetype("lint_heavy", tmp_path, seed=0)
    item = load_jsonl(path)
    _out, stats = compress_messages(item.messages, "structured_normalize")
    assert stats.fires > 0, "lint_heavy did not exercise structured_normalize"


def test_diff_heavy_structural_dedup_fires(tmp_path: Path):
    """Diff-heavy should fire structural_dedup on the shifted-anchor
    diffs. Sanity check that the recipe actually exercises what it
    claims to."""
    path = simulate_archetype("diff_heavy", tmp_path, seed=0)
    item = load_jsonl(path)
    _out, stats = compress_messages(item.messages, "structural_dedup")
    assert stats.fires > 0, "diff_heavy did not exercise structural_dedup"


def test_long_session_preserves_uuid(tmp_path: Path):
    """The recall UUID emitted in turn 3 must survive every compressor.
    This is the inverse of the no-fire test — preservation-under-firing.
    """
    path = simulate_archetype("long_session", tmp_path, seed=0)
    item = load_jsonl(path)
    uuid = "7c3b1f4e-2a8d-4e9f-b1c2-5d4e3f2a1b9c"
    assert any(uuid in (m.get("content") or "") for m in item.messages)
    for compressor_id in (
        "exact_hash_dedup",
        "structural_dedup",
        "structured_normalize",
        "dedup_then_normalize",
    ):
        out, _stats = compress_messages(item.messages, compressor_id)
        # UUID still appears in at least one message after compression
        assert any(uuid in (m.get("content") or "") for m in out), (
            f"{compressor_id} dropped the recall UUID — integrity violation"
        )


def test_write_archetype_bundle_creates_all_four(tmp_path: Path):
    written = write_archetype_bundle(tmp_path)
    assert sorted(written.keys()) == sorted(ARCHETYPES)
    for archetype in ARCHETYPES:
        subdir = tmp_path / f"archetype_{archetype}"
        assert subdir.is_dir()
        jsonl = subdir / f"{archetype}.jsonl"
        manifest = subdir / "manifest.json"
        assert jsonl.exists()
        assert manifest.exists()


def test_write_archetype_bundle_deterministic(tmp_path: Path):
    """Whole-bundle byte-identical determinism for same seed."""
    write_archetype_bundle(tmp_path / "a", seed=42)
    write_archetype_bundle(tmp_path / "b", seed=42)
    for archetype in ARCHETYPES:
        a_jsonl = (tmp_path / "a" / f"archetype_{archetype}"
                   / f"{archetype}.jsonl").read_bytes()
        b_jsonl = (tmp_path / "b" / f"archetype_{archetype}"
                   / f"{archetype}.jsonl").read_bytes()
        assert a_jsonl == b_jsonl, f"{archetype} JSONL differs across seed=42 runs"
        a_manifest = (tmp_path / "a" / f"archetype_{archetype}"
                      / "manifest.json").read_bytes()
        b_manifest = (tmp_path / "b" / f"archetype_{archetype}"
                      / "manifest.json").read_bytes()
        assert a_manifest == b_manifest, (
            f"{archetype} manifest differs across seed=42 runs"
        )


def test_manifest_schema_keys(tmp_path: Path):
    """Pin the manifest shape so a future bash-loop / automation can
    rely on the keys. Adding keys is fine; removing or renaming
    breaks the contract."""
    write_archetype_bundle(tmp_path, seed=0)
    manifest = json.loads(
        (tmp_path / "archetype_lint_heavy" / "manifest.json").read_text()
    )
    required = {
        "archetype", "synthetic", "seed", "turns",
        "generator_version", "generated_at", "jsonl",
        "expected_compression",
    }
    assert required.issubset(set(manifest.keys())), (
        f"manifest missing required keys: {required - set(manifest.keys())}"
    )
    assert manifest["synthetic"] is True
    assert manifest["archetype"] == "lint_heavy"
    assert manifest["seed"] == 0
    assert manifest["expected_compression"] in {"high", "moderate", "low", "zero"}
    assert manifest["jsonl"] == "lint_heavy.jsonl"


def test_hostile_expected_compression_is_zero(tmp_path: Path):
    """The hostile archetype's manifest must encode the floor
    expectation so a future verdict pipeline can refuse to count it
    as positive evidence."""
    write_archetype_bundle(tmp_path, seed=0)
    manifest = json.loads(
        (tmp_path / "archetype_hostile" / "manifest.json").read_text()
    )
    assert manifest["expected_compression"] == "zero"
