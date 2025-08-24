from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import List

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

# SQLAlchemy instance (initialized in app.py)
db = SQLAlchemy()

# Association table modeling inventory entries.
class InventoryItem(db.Model):
    __tablename__ = 'inventory_items'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    item_id = db.Column(db.Integer, db.ForeignKey('items.id'), nullable=False, index=True)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship('User', back_populates='inventory_items')
    item = db.relationship('Item', back_populates='inventory_entries')

    def __repr__(self):  # pragma: no cover simple repr
        return f"<InventoryItem user={self.user_id} item={self.item_id} qty={self.quantity}>"

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    avatar = db.Column(db.String(255), nullable=True)
    money = db.Column(db.Integer, default=0, nullable=False)
    public_enabled = db.Column(db.Boolean, default=False, nullable=False)
    public_slug = db.Column(db.String(120), unique=True, nullable=True, index=True)
    total_spent = db.Column(db.Integer, default=0, nullable=False)  # cumulative case spending
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    inventory_items = db.relationship('InventoryItem', back_populates='user', cascade='all, delete-orphan')

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def inventory_total_value(self) -> int:
        total = 0
        for inv in self.inventory_items:
            if inv.item:
                total += inv.item.value * inv.quantity
        return total

    def __repr__(self):  # pragma: no cover simple repr
        return f"<User {self.username}>"

    @property
    def roi_value(self) -> int:
        """Return profit/loss (inventory value - total spent)."""
        return self.inventory_total_value - (self.total_spent or 0)

class PublicShowcase(db.Model):
    __tablename__ = 'public_showcase'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    item_id = db.Column(db.Integer, db.ForeignKey('items.id'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship('User', backref=db.backref('showcase_items', cascade='all, delete-orphan'))
    item = db.relationship('Item')

    __table_args__ = (db.UniqueConstraint('user_id','item_id', name='uq_user_item_showcase'),)

class Item(db.Model):
    __tablename__ = 'items'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False, index=True)
    value = db.Column(db.Integer, nullable=False, default=0)
    image = db.Column(db.String(255), nullable=True)
    rarity = db.Column(db.String(32), nullable=True, index=True)  # added later; may be null for legacy rows
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    inventory_entries = db.relationship('InventoryItem', back_populates='item')

    def __repr__(self):  # pragma: no cover simple repr
        return f"<Item {self.name} (${self.value})>"
