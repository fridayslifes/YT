"""tests/test_asset_agent.py — Unit tests for SmartAssetAgent and AssetCatalog."""

from pathlib import Path
from tools.asset_agent import AssetCatalog, AssetEntry, SmartAssetAgent


def test_asset_entry_dict_roundtrip():
    entry = AssetEntry(
        asset_id="nature_grass_dry",
        name="Dry Grass",
        category="nature",
        rel_path="nature/grass_dry.png",
        tags=["grass", "lawn"],
        attributes={"wet": False},
        style="3d_pbr",
        source="procedural",
    )
    d = entry.to_dict()
    assert d["id"] == "nature_grass_dry"
    assert d["attributes"]["wet"] is False

    restored = AssetEntry.from_dict(d)
    assert restored.asset_id == entry.asset_id
    assert restored.name == entry.name
    assert restored.category == entry.category
    assert restored.attributes == entry.attributes


def test_catalog_search_and_attribute_isolation(tmp_path: Path):
    catalog_file = tmp_path / "catalog.json"
    catalog = AssetCatalog(catalog_file)

    catalog.register(
        asset_id="nature_grass_dry",
        name="Dry Grass Lawn",
        category="nature",
        rel_path="nature/grass_dry.png",
        tags=["grass", "lawn", "green"],
        attributes={"wet": False, "water_droplets": False},
        style="3d_pbr",
    )

    catalog.register(
        asset_id="nature_grass_wet",
        name="Wet Dew Grass Lawn",
        category="nature",
        rel_path="nature/grass_wet.png",
        tags=["grass", "lawn", "green", "dew"],
        attributes={"wet": True, "water_droplets": True},
        style="3d_pbr",
    )

    # Search for dry grass: must match only the dry asset
    dry_matches = catalog.search("grass", required_attributes={"wet": False})
    assert len(dry_matches) == 1
    assert dry_matches[0].asset_id == "nature_grass_dry"

    # Search for wet grass: must match only the wet asset
    wet_matches = catalog.search("grass", required_attributes={"wet": True})
    assert len(wet_matches) == 1
    assert wet_matches[0].asset_id == "nature_grass_wet"

    # Search with incompatible attribute: should return empty
    snow_matches = catalog.search("grass", required_attributes={"snow": True})
    assert len(snow_matches) == 0


def test_smart_asset_agent_reuse_and_generation(tmp_path: Path, monkeypatch):
    lib_dir = tmp_path / "library"
    lib_dir.mkdir(parents=True)
    catalog_file = lib_dir / "catalog.json"

    monkeypatch.setattr("tools.asset_agent.LIBRARY_DIR", lib_dir)
    monkeypatch.setattr("tools.asset_agent.CATALOG_PATH", catalog_file)

    catalog = AssetCatalog(catalog_file)
    agent = SmartAssetAgent(catalog)

    # First request: Creates wet grass
    path1 = agent.get_or_create(
        name="Grass",
        category="nature",
        query="grass",
        required_attributes={"wet": True, "water_droplets": True},
    )
    assert path1.exists()
    assert "wet_True" in path1.name

    # Second request with SAME attributes: Reuses existing asset!
    path2 = agent.get_or_create(
        name="Grass",
        category="nature",
        query="grass",
        required_attributes={"wet": True, "water_droplets": True},
    )
    assert path2 == path1
    assert catalog.assets["grass_water_droplets_True_wet_True"].usage_count >= 2

    # Third request with DIFFERENT attributes (dry): Generates new asset!
    path3 = agent.get_or_create(
        name="Grass",
        category="nature",
        query="grass",
        required_attributes={"wet": False, "water_droplets": False},
    )
    assert path3 != path1
    assert path3.exists()
    assert "wet_False" in path3.name
