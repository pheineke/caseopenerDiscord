# Case Opener Simulator (Prototype)

A Flask prototype for a case opening simulator with user accounts, SQLite persistence, and a dark futuristic UI.

## Features
- User registration & login (session based, password hashing)  
- SQLite database via SQLAlchemy (auto-initialized with demo data)  
- User inventory with items (name, value, image, quantity)  
- Basic seed data (demo user only; items come solely from `scan_items.py`)  
- Themed UI (see `static/base.css`)  
 - Case selection & opening prototype (`/cases`, roulette animation, weighted rarity spin)  

## Data Model
`models.py` defines the structure:
- `User`: id, username (unique), password_hash, avatar, money, created_at
- `Item`: id, name (unique), value (int), image, created_at
- `InventoryItem`: id, user_id, item_id, quantity, created_at (acts as inventory association)

## Running
Create / activate a Python 3.10+ environment then install Flask & SQLAlchemy:

```bash
pip install flask flask_sqlalchemy werkzeug
python app.py
```

Navigate to: http://127.0.0.1:8000/

Demo credentials (seeded):
- username: `johndoe`
- password: `password`

## Next Ideas
- Case definitions & opening logic w/ random drops
	- (Prototype implemented – move cases & odds to DB)
- Transactions & balance updates
- Rarity tiers & animations
- API endpoints for AJAX inventory updates
- CSRF protection & Flask-WTF forms

---
Prototype only: not production hardened (no rate limiting, CSRF, input validation rigor, etc.).


# TODOS
- (DONE) Add home page: shows balance, inventory total value, item count, and quick links.

- (DONE) Header nav with Home/Cases + avatar dropdown (profile, items, cases, logout).
