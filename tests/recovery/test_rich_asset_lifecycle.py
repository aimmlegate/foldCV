import pytest

from packages.resume_core.models.rich_workspace import LocalImageAsset
from packages.resume_core.rich_asset_lifecycle import ImageOwner, ImageRetention
from packages.resume_core.rich_limits import ImageReferences, MIB


OWNER = ImageOwner("project-1", "session-1", 1)


def asset(id, size, hash_digit):
    return LocalImageAsset(id=id, sha256=hash_digit * 64, path=f"images/{hash_digit * 64}.png",
                           mimeType="image/png", size=size, width=100, height=100)


def test_rich_image_concurrent_reservations_and_replacement_keep_undo_bytes():
    old = asset("old", 8 * MIB, "a")
    ledger = ImageRetention(OWNER, [old], ImageReferences(live=("old",), durable=("old",)))
    ledger.reserve("replace", "action-1", MIB, 9 * MIB, replacement=True)
    with pytest.raises(ValueError, match="retained image byte"):
        ledger.reserve("parallel", "action-2", MIB, 4 * MIB)
    new = asset("new", 9 * MIB, "b")
    assert ledger.publish("replace", new, OWNER, "old") == "published"
    assert ledger.references.live == ("new",)
    assert set(ledger.references.history) == {"old", "new"}
    ledger.set_references(ImageReferences(live=("old",), durable=("old",), history=("old", "new")))
    assert not ledger.reclaimable_ids(True)
    ledger.set_references(ImageReferences(live=("new",), durable=("new",), history=("old", "new")))
    with pytest.raises(ValueError, match="retained image byte"):
        ledger.reserve("too-large", "action-3", MIB, 4 * MIB, replacement=True)
    assert ledger.references.history == ("old", "new")


@pytest.mark.parametrize("owner", [ImageOwner("project-2", "session-1", 1), ImageOwner("project-1", "session-2", 1), ImageOwner("project-1", "session-1", 2)])
def test_rich_image_stale_or_cancelled_publication_changes_no_document_or_history(owner):
    ledger = ImageRetention(OWNER, [], ImageReferences())
    ledger.reserve("image-1", "action-1", MIB, MIB)
    assert ledger.publish("image-1", asset("a", MIB, "a"), owner) == "stale"
    assert ledger.assets == [] and ledger.references == ImageReferences()
    ledger.reserve("image-2", "action-2", MIB, MIB)
    ledger.cancel("image-2")
    assert ledger.publish("image-2", asset("a", MIB, "a"), OWNER) == "stale"
    assert ledger.assets == [] and ledger.references.history == ()
    ledger.reserve("image-3", "action-3", 10 * MIB, 20 * MIB)
    with pytest.raises(ValueError, match="10 MiB"):
        ledger.reserve("oversized-input", "action-4", 10 * MIB + 1, MIB)


def test_rich_image_cleanup_waits_for_all_references_and_never_touches_unsupported_projects():
    old = asset("old", MIB, "a")
    ledger = ImageRetention(OWNER, [old], ImageReferences(in_flight=("old",)))
    assert ledger.reclaimable_ids(True) == set()
    ledger.set_references(ImageReferences())
    assert ledger.reclaimable_ids(False) == set()
    assert ledger.reclaimable_ids(True) == {"old"}
    ledger.reserve("pending", "action-1", MIB, MIB)
    assert ledger.reclaimable_ids(True) == set()
    ledger.cancel("pending")
    assert ledger.reclaimable_ids(True) == {"old"}


def test_rich_normalized_output_can_exceed_input_limit_within_retained_budget():
    ledger = ImageRetention(OWNER, [], ImageReferences())
    ledger.reserve("webp", "action-1", 9 * MIB, 9 * MIB)
    assert ledger.publish("webp", asset("png", 14 * MIB, "a"), OWNER) == "published"
    assert ledger.references.live == ("png",)


def test_rich_image_failed_conversion_or_capacity_releases_its_reservation():
    old = asset("old", 10 * MIB, "b")
    ledger = ImageRetention(OWNER, [old], ImageReferences(live=("old",)))
    ledger.reserve("conversion", "action-1", MIB, MIB)
    ledger.fail("conversion")
    ledger.reserve("publication", "action-2", MIB, MIB)
    with pytest.raises(ValueError, match="retained image byte"):
        ledger.publish("publication", asset("normalized", 11 * MIB, "a"), OWNER)
    assert ledger.references.live == ("old",) and ledger.references.history == ()
    assert ledger.reservations["publication"].status == "failed"
    ledger.reserve("remaining", "action-3", 10 * MIB, 10 * MIB)


def test_rich_full_byte_budget_can_probe_a_duplicate_without_evicting_undo_bytes():
    old = asset("old", 20 * MIB, "a")
    ledger = ImageRetention(OWNER, [old], ImageReferences(live=("old",), history=("old",)))
    ledger.reserve("duplicate", "action", MIB, 0, replacement=True)
    assert ledger.publish("duplicate", old, OWNER, "old") == "published"
    assert ledger.assets == [old] and ledger.references.live == ("old",)
    ledger.reserve("different", "action-2", MIB, 0, replacement=True)
    with pytest.raises(ValueError, match="retained image byte"):
        ledger.publish("different", asset("new", MIB, "b"), OWNER, "old")
    assert ledger.assets == [old] and ledger.references.live == ("old",)
