#!/usr/bin/env python3
"""tools/asset_agent.py — Smart Reusable Asset Agent & Library Manager.

Implements an automated, semantic asset cache and procedural generation engine:
1. Video scripts request an asset (e.g. 'grass', 'character', 'prop', 'umbrella') with specific attributes.
2. The agent queries the centralized asset library (assets/library/catalog.json).
3. If an asset matching the category, tags, AND required attributes exists (e.g. dry grass):
   -> Reuses the asset immediately (0 sec, 0 GPU compute).
4. If an asset is missing OR the requested attributes differ (e.g. 'grass with water droplets' vs 'dry grass'):
   -> Automatically creates the tailored asset, saves it to assets/library/<category>/,
      indexes it with its specific attributes, and returns the path for rendering.
5. All future videos needing that specific asset can reuse it immediately.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import shutil
import sys
from typing import Any, Dict, List, Optional

import numpy as np
from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parent.parent
LIBRARY_DIR = REPO_ROOT / "assets" / "library"
CATALOG_PATH = LIBRARY_DIR / "catalog.json"

CATEGORIES = ("nature", "characters", "props", "landmarks", "textures")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("asset_agent")


class AssetEntry:
    def __init__(
        self,
        asset_id: str,
        name: str,
        category: str,
        rel_path: str,
        tags: List[str],
        attributes: Dict[str, Any],
        style: str = "3d_pbr",
        source: str = "procedural",
        usage_count: int = 0,
        created_at: Optional[str] = None,
    ):
        self.asset_id = asset_id
        self.name = name
        self.category = category
        self.rel_path = rel_path
        self.tags = [t.lower().strip() for t in tags]
        self.attributes = attributes or {}
        self.style = style
        self.source = source
        self.usage_count = usage_count
        self.created_at = created_at or datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.asset_id,
            "name": self.name,
            "category": self.category,
            "rel_path": self.rel_path,
            "tags": self.tags,
            "attributes": self.attributes,
            "style": self.style,
            "source": self.source,
            "usage_count": self.usage_count,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AssetEntry:
        return cls(
            asset_id=data["id"],
            name=data["name"],
            category=data.get("category", "props"),
            rel_path=data["rel_path"],
            tags=data.get("tags", []),
            attributes=data.get("attributes", {}),
            style=data.get("style", "3d_pbr"),
            source=data.get("source", "procedural"),
            usage_count=data.get("usage_count", 0),
            created_at=data.get("created_at"),
        )


class AssetCatalog:
    def __init__(self, catalog_path: Path = CATALOG_PATH):
        self.path = catalog_path
        self.assets: Dict[str, AssetEntry] = {}
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            self.assets = {}
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.assets = {item["id"]: AssetEntry.from_dict(item) for item in data.get("assets", [])}
        except Exception as exc:
            logger.warning("Could not read asset catalog %s: %s", self.path, exc)
            self.assets = {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "schema_version": "1.0",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "total_assets": len(self.assets),
            "assets": [entry.to_dict() for entry in self.assets.values()],
        }
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def search(
        self,
        query: str,
        category: Optional[str] = None,
        required_attributes: Optional[Dict[str, Any]] = None,
        style: Optional[str] = None,
    ) -> List[AssetEntry]:
        """Search assets by query keyword, category, and strict attribute matching."""
        query_terms = [q.lower().strip() for q in query.split() if q.strip()]
        results: List[AssetEntry] = []

        for asset in self.assets.values():
            if category and asset.category.lower() != category.lower():
                continue
            if style and asset.style.lower() != style.lower():
                continue

            # Tag / Name match
            matches_query = False
            if not query_terms:
                matches_query = True
            else:
                for term in query_terms:
                    if term in asset.tags or term in asset.name.lower() or term in asset.asset_id.lower():
                        matches_query = True
                        break

            if not matches_query:
                continue

            # Strict attribute check (e.g. wet=True vs wet=False)
            if required_attributes:
                attribute_conflict = False
                for req_k, req_v in required_attributes.items():
                    asset_val = asset.attributes.get(req_k)
                    if asset_val is not None:
                        # If both define it, they must match
                        if asset_val != req_v:
                            attribute_conflict = True
                            break
                    else:
                        # Asset does not declare this required attribute
                        if req_v is True:
                            # A positive boolean requirement missing is a mismatch
                            attribute_conflict = True
                            break
                if attribute_conflict:
                    continue

            results.append(asset)

        return results

    def register(
        self,
        asset_id: str,
        name: str,
        category: str,
        rel_path: str,
        tags: List[str],
        attributes: Dict[str, Any],
        style: str = "3d_pbr",
        source: str = "procedural",
    ) -> AssetEntry:
        entry = AssetEntry(
            asset_id=asset_id,
            name=name,
            category=category,
            rel_path=rel_path,
            tags=tags,
            attributes=attributes,
            style=style,
            source=source,
            usage_count=1,
        )
        self.assets[asset_id] = entry
        self.save()
        return entry

    def increment_usage(self, asset_id: str) -> None:
        if asset_id in self.assets:
            self.assets[asset_id].usage_count += 1
            self.save()


class SmartAssetAgent:
    """The central manager that handles semantic asset lookup, reuse, and procedural creation."""

    def __init__(self, catalog: Optional[AssetCatalog] = None):
        self.catalog = catalog or AssetCatalog()

    def get_or_create(
        self,
        name: str,
        category: str,
        query: str,
        required_attributes: Optional[Dict[str, Any]] = None,
        style: str = "3d_pbr",
        prompt: Optional[str] = None,
    ) -> Path:
        """Find an existing asset with matching attributes, or generate and register a new one."""
        required_attributes = required_attributes or {}
        matches = self.catalog.search(query, category=category, required_attributes=required_attributes, style=style)

        if matches:
            best_match = matches[0]
            full_path = LIBRARY_DIR / best_match.rel_path
            if full_path.exists():
                logger.info(
                    "✓ [ASSET REUSE] Found matching asset '%s' (reused %d times): %s",
                    best_match.name,
                    best_match.usage_count,
                    full_path,
                )
                self.catalog.increment_usage(best_match.asset_id)
                return full_path
            else:
                logger.warning("Catalog listed %s but file was missing on disk; recreating...", full_path)

        # No compatible match found or attributes differ -> Generate fresh asset
        logger.info(
            "⚙ [ASSET GENERATION] Generating new tailored asset for '%s' (category=%s, attributes=%s)",
            name,
            category,
            required_attributes,
        )
        asset_path, asset_id = self._generate_asset(
            name=name,
            category=category,
            query=query,
            attributes=required_attributes,
            style=style,
            prompt=prompt,
        )
        return asset_path

    def _generate_asset(
        self,
        name: str,
        category: str,
        query: str,
        attributes: Dict[str, Any],
        style: str,
        prompt: Optional[str],
    ) -> tuple[Path, str]:
        """Generate the visual asset file and index it in the catalog."""
        cat_dir = LIBRARY_DIR / category
        cat_dir.mkdir(parents=True, exist_ok=True)

        # Generate unique ID based on attributes (e.g. nature_grass_wet_01)
        attr_slug = "_".join(f"{k}_{v}" for k, v in sorted(attributes.items()) if isinstance(v, (bool, str, int)))
        safe_name = name.lower().replace(" ", "_").replace("-", "_")
        asset_id = f"{safe_name}_{attr_slug}" if attr_slug else safe_name

        rel_path = f"{category}/{asset_id}.png"
        out_path = LIBRARY_DIR / rel_path

        # Generate the visual media
        if category == "nature" and "grass" in query.lower():
            self._create_grass_texture(out_path, attributes=attributes)
        else:
            self._create_procedural_plate(out_path, name=name, category=category, attributes=attributes)

        tags = list(set([safe_name, category] + query.lower().split() + list(attributes.keys())))
        self.catalog.register(
            asset_id=asset_id,
            name=name,
            category=category,
            rel_path=rel_path,
            tags=tags,
            attributes=attributes,
            style=style,
            source="procedural_generator",
        )
        logger.info("  ✓ Successfully registered new asset '%s' at %s", asset_id, out_path)
        return out_path, asset_id

    def _create_grass_texture(self, out_path: Path, attributes: Dict[str, Any]) -> None:
        """Create a clean 4K-ready transparent grass patch, adding water drops if wet=True."""
        w, h = 1080, 720
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        is_wet = attributes.get("wet", False) or attributes.get("water_droplets", False)
        base_green = (46, 125, 50, 255) if not is_wet else (30, 95, 35, 255)  # Darker, saturated when wet
        highlight_green = (102, 187, 106, 255) if not is_wet else (129, 199, 132, 255)

        rng = np.random.default_rng(42)

        # Draw grass blades
        num_blades = 280
        for _ in range(num_blades):
            bx = rng.integers(20, w - 20)
            by = rng.integers(h - 180, h - 20)
            bh = rng.integers(120, 260)
            curve = rng.integers(-40, 40)
            tip_x = bx + curve
            tip_y = by - bh

            color = base_green if rng.random() > 0.4 else highlight_green
            width = rng.integers(3, 7)
            draw.line([(bx, by), (tip_x, tip_y)], fill=color, width=width)

        # If wet, add glistening transparent water droplets and specular highlights
        if is_wet:
            num_droplets = 95
            for _ in range(num_droplets):
                dx = rng.integers(40, w - 40)
                dy = rng.integers(h - 240, h - 40)
                radius = rng.integers(3, 8)
                # Outer water droplet bubble
                draw.ellipse(
                    [(dx - radius, dy - radius), (dx + radius, dy + radius)],
                    fill=(200, 235, 255, 180),
                    outline=(255, 255, 255, 240),
                    width=1,
                )
                # Specular white light glint
                draw.ellipse(
                    [(dx - radius // 2, dy - radius // 2), (dx, dy)],
                    fill=(255, 255, 255, 250),
                )

        img.save(out_path, format="PNG")

    def _create_procedural_plate(
        self, out_path: Path, name: str, category: str, attributes: Dict[str, Any]
    ) -> None:
        """Create a clean procedural transparent asset placeholder."""
        w, h = 512, 512
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Draw clean glowing geometric plate
        cx, cy, r = w // 2, h // 2, 180
        draw.ellipse([(cx - r, cy - r), (cx + r, cy + r)], fill=(30, 41, 59, 230), outline=(0, 229, 255, 255), width=4)
        draw.text((cx - 80, cy - 10), name[:18], fill=(255, 255, 255, 255))
        img.save(out_path, format="PNG")

    def seed_defaults(self) -> int:
        """Seed initial library with existing emojis and standard nature textures."""
        count = 0
        emojis_dir = REPO_ROOT / "assets" / "emojis"
        if emojis_dir.exists():
            for emoji_path in emojis_dir.glob("*.png"):
                stem = emoji_path.stem
                clean_name = stem.replace("_3d", "").replace("_", " ").title()
                cat = "props"
                if any(k in stem for k in ("cloud", "fire", "lightning")):
                    cat = "nature"

                dest = LIBRARY_DIR / cat / f"{stem}.png"
                if not dest.exists():
                    shutil.copy2(emoji_path, dest)

                self.catalog.register(
                    asset_id=f"{cat}_{stem}",
                    name=clean_name,
                    category=cat,
                    rel_path=f"{cat}/{stem}.png",
                    tags=[stem, clean_name.lower(), cat] + stem.split("_"),
                    attributes={"style": "3d_emoji", "transparent": True},
                    style="3d_pbr",
                    source="bundled_emoji",
                )
                count += 1

        # Seed dry grass
        self.get_or_create(
            name="Dry Green Grass Lawn",
            category="nature",
            query="grass lawn green",
            required_attributes={"wet": False, "water_droplets": False},
        )
        count += 1

        # Seed wet grass with water droplets
        self.get_or_create(
            name="Wet Grass with Morning Dew",
            category="nature",
            query="grass lawn green",
            required_attributes={"wet": True, "water_droplets": True},
        )
        count += 1

        logger.info("Seeded %d assets into the library catalog at %s", count, CATALOG_PATH)
        return count


def main() -> int:
    parser = argparse.ArgumentParser(description="Smart Reusable Asset Agent & Library Manager")
    parser.add_argument("--search", type=str, help="Search library by query term")
    parser.add_argument("--category", type=str, choices=CATEGORIES, help="Filter search by category")
    parser.add_argument("--attributes", type=str, help="JSON string of required attributes, e.g. '{\"wet\": true}'")
    parser.add_argument("--get-or-create", type=str, help="Name of asset to get or create")
    parser.add_argument("--list", action="store_true", help="List all assets in catalog")
    parser.add_argument("--seed-defaults", action="store_true", help="Seed default assets from assets/emojis")
    parser.add_argument("--status", action="store_true", help="Show library health & asset counts")

    args = parser.parse_args()
    agent = SmartAssetAgent()

    if args.seed_defaults:
        count = agent.seed_defaults()
        print(f"✓ Seeded {count} assets into library.")
        return 0

    if args.status or args.list:
        print("\n" + "=" * 65)
        print("📦 FRAMEFORGE SMART ASSET LIBRARY CATALOG")
        print("=" * 65)
        print(f"Total Assets: {len(agent.catalog.assets)}")
        for cat in CATEGORIES:
            cat_assets = [a for a in agent.catalog.assets.values() if a.category == cat]
            print(f"  • {cat.capitalize():12} : {len(cat_assets)} asset(s)")
        print("-" * 65)
        if args.list:
            for a in agent.catalog.assets.values():
                print(f"[{a.category.upper():10}] {a.name} (id={a.asset_id}, reused={a.usage_count}x)")
                print(f"             Path: {a.rel_path}")
                print(f"             Attrs: {a.attributes}")
        print("=" * 65)
        return 0

    if args.search:
        attrs = json.loads(args.attributes) if args.attributes else None
        results = agent.catalog.search(args.search, category=args.category, required_attributes=attrs)
        print(f"\nFound {len(results)} matching asset(s) for query='{args.search}' (attrs={attrs}):")
        for r in results:
            print(f"  • {r.name} [{r.category}] -> assets/library/{r.rel_path}")
            print(f"    Attributes: {r.attributes}")
        return 0

    if args.get_or_create:
        if not args.category:
            print("Error: --category is required with --get-or-create", file=sys.stderr)
            return 1
        attrs = json.loads(args.attributes) if args.attributes else {}
        path = agent.get_or_create(
            name=args.get_or_create,
            category=args.category,
            query=args.get_or_create,
            required_attributes=attrs,
        )
        print(f"✓ Asset ready at: {path}")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
