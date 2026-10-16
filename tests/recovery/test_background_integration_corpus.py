"""Capacity-one traces drive the real API, compiler, store and synthetic children."""

import pytest

from spikes.background.corpus import FIXED_SEEDS, ORDERS, INTEGRATED_SEEDS, INTEGRATED_TRANSITIONS
from spikes.background.integration import IntegrationTrace


@pytest.mark.asyncio
@pytest.mark.parametrize("seed", FIXED_SEEDS, ids=lambda seed: f"seed-{seed:02d}")
async def test_capacity_one_production_corpus_preserves_the_independent_oracle(tmp_path, seed, background_evidence):
    trace = await IntegrationTrace(tmp_path / "bridge", seed).run()
    assert set(trace["orders"]) == set(ORDERS)
    background_evidence(trace)


@pytest.mark.asyncio
@pytest.mark.parametrize("seed", INTEGRATED_SEEDS, ids=lambda seed: f"seed-{seed:03d}")
async def test_integrated_serial_corpus_preserves_each_transition_and_order(tmp_path, seed, background_evidence):
    trace = await IntegrationTrace(tmp_path / "bridge", seed, transitions=INTEGRATED_TRANSITIONS,
        identity="NB07a:production").run()
    assert set(trace["orders"]) == set(ORDERS)
    background_evidence(trace)
