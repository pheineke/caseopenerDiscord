"""Scan weapon image folders and sync them into the SQLite item pool.

Rules / Assumptions:
- Directory structure: static/imgs/weapon/<index>_<rarity>/<image files>
- Rarity directory names after numeric prefix map directly to Item.rarity (lowercase).
- Item name derived from file name (strip numeric prefix if present, replace underscores with spaces, title case).
- Value heuristic per rarity tier (can be customized below).
- Existing items (by unique name) are updated for image path + rarity; value only updated if 0.

Usage:
    python scan_items.py

Run from project root (where app.py resides). Requires virtualenv with Flask & SQLAlchemy installed.
"""
from __future__ import annotations
import os
from pathlib import Path
from typing import Dict

from flask import Flask
from models import db, Item

# Value mapping per rarity (fallback if we can't parse index) - tune as needed
RARITY_VALUE_BASE: Dict[str, int] = {
    'common': 5,
    'uncommon': 15,
    'rare': 60,
    'mythical': 140,
    'legendary': 400,
    'ancient': 750,
    'exceedinglyrare': 1100,
    'immortal': 2000,
    'unique': 3500,
}

BASE_DIR = Path(__file__).parent
STATIC_WEAPON_DIR = BASE_DIR / 'static' / 'imgs' / 'weapon'
DB_PATH = BASE_DIR / 'app.db'

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_PATH.as_posix()}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'dev'

db.init_app(app)


def derive_item_name(file_stem: str) -> str:
    # Remove leading numeric prefix + underscore if present (e.g., 00_common_pistol -> common_pistol)
    parts = file_stem.split('_')
    if parts and parts[0].isdigit():
        parts = parts[1:]
    # Title case words
    return ' '.join(p.capitalize() for p in parts)


def rarity_from_dir(dir_name: str) -> str:
    # dir pattern: 0_common, 1_uncommon, etc.
    if '_' in dir_name:
        return dir_name.split('_', 1)[1].lower()
    return dir_name.lower()


def value_for_rarity(rarity: str) -> int:
    return RARITY_VALUE_BASE.get(rarity, 10)


def scan_and_sync():
    created = 0
    updated = 0
    if not STATIC_WEAPON_DIR.exists():
        print(f"No weapon directory found: {STATIC_WEAPON_DIR}")
        return

    for rarity_dir in sorted(STATIC_WEAPON_DIR.iterdir()):
        if not rarity_dir.is_dir():
            continue
        rarity = rarity_from_dir(rarity_dir.name)
        for img in sorted(rarity_dir.iterdir()):
            if img.is_dir():
                continue
            if img.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.gif', '.webp'}:
                continue
            stem = img.stem
            item_name = derive_item_name(stem)
            rel_path = img.relative_to(BASE_DIR).as_posix()  # store relative path for use with url_for('static', ...)?
            # Normalize image path to be served under static - since path includes 'static/...'
            # Ensure uniqueness by name
            existing = Item.query.filter_by(name=item_name).first()
            if existing:
                changed = False
                if existing.image != rel_path:
                    existing.image = rel_path
                    changed = True
                if not existing.rarity:
                    existing.rarity = rarity
                    changed = True
                if existing.value == 0:
                    existing.value = value_for_rarity(rarity)
                    changed = True
                if changed:
                    updated += 1
            else:
                itm = Item(
                    name=item_name,
                    rarity=rarity,
                    value=value_for_rarity(rarity),
                    image=rel_path,
                )
                db.session.add(itm)
                created += 1
    if created or updated:
        db.session.commit()
    print(f"Scan complete. Created: {created}, Updated: {updated}")


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        # Ensure rarity column exists (if app didn't run migration yet)
        cols = [c['name'] for c in db.session.execute(db.text("PRAGMA table_info(items)")).mappings().all()]
        if 'rarity' not in cols:
            db.session.execute(db.text('ALTER TABLE items ADD COLUMN rarity VARCHAR(32)'))
            db.session.commit()
        scan_and_sync()
