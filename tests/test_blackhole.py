"""Tests for BlackHoleEngine - memory compression and cleanup."""

import pytest
from server.services.blackhole_engine import BlackHoleEngine, CompressionResult


class TestBlackHoleEngine:
    def test_next_layer_progression(self):
        engine = BlackHoleEngine()
        assert engine._next_layer("L0") == "L1"
        assert engine._next_layer("L1") == "L2"
        assert engine._next_layer("L2") == "L3"
        assert engine._next_layer("L3") == "L4"
        assert engine._next_layer("L4") == "L5"
        assert engine._next_layer("L5") is None

    def test_compression_result_structure(self):
        result = CompressionResult(
            success=True, source_layer="L1", target_layer="L2",
            source_count=8, new_memory={"title": "test"}, compressed_ids=[1, 2, 3],
        )
        assert isinstance(result, CompressionResult)
        assert result.success is True
        assert result.source_count == 8
        assert len(result.compressed_ids) == 3

    def test_compaction_thresholds_exist(self):
        engine = BlackHoleEngine()
        assert "L0" in engine.COMPACTION_THRESHOLDS
        assert "L1" in engine.COMPACTION_THRESHOLDS
        assert "L2" in engine.COMPACTION_THRESHOLDS
        assert engine.COMPACTION_THRESHOLDS["L0"] > 0
