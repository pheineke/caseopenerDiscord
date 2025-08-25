from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import random, base64
from pathlib import Path
from models import db, User, Item, InventoryItem, PublicShowcase, Friend, AcquisitionHistory
import string, secrets
from sqlalchemy.exc import IntegrityError

BASE_DIR = Path(__file__).parent
DEFAULT_AVATAR_FILE = BASE_DIR / 'static' / 'default-avatar.svg'
DEFAULT_AVATAR_PATH = '/static/default-avatar.svg'
DEFAULT_AVATAR_VERSION = '4'

app = Flask(__name__)
app.config['SECRET_KEY'] = 'dev-secret-change-me'
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{(BASE_DIR / 'app.db').as_posix()}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

@app.context_processor
def inject_current_user():
    uid = session.get('user_id')
    user = User.query.get(uid) if uid else None
    def avatar_url(u):
        if not u or not u.avatar or 'default-avatar' in u.avatar:
            return f"{DEFAULT_AVATAR_PATH}?v={DEFAULT_AVATAR_VERSION}"
        return u.avatar if (u.avatar.startswith('http') or u.avatar.startswith('/')) else '/' + u.avatar
    return {'current_user': user, 'avatar_url': avatar_url}

_DB_INITIALIZED = False

@app.before_request
def ensure_db_seeded():
    global _DB_INITIALIZED
    if _DB_INITIALIZED:
        return
    db.create_all()
    # Always rewrite a valid SVG avatar to avoid PNG corruption issues
    _SVG_AVATAR = '''<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">
    <rect width="64" height="64" fill="#263347"/>
    <circle cx="32" cy="24" r="12" fill="#3fa9f5" opacity="0.8"/>
    <path d="M12 52 Q32 40 52 52 L52 64 L12 64 Z" fill="#3fa9f5" opacity="0.6"/>
</svg>'''
    try:
        DEFAULT_AVATAR_FILE.write_text(_SVG_AVATAR)
    except Exception:
        pass  # non-fatal
    # Simple in-code migration: add rarity column if missing (SQLite pragma)
    # (Non-destructive: if column exists this no-ops)
    try:
        cols = [c['name'] for c in db.session.execute(db.text("PRAGMA table_info(items)")).mappings().all()]
        if 'rarity' not in cols:
            db.session.execute(db.text('ALTER TABLE items ADD COLUMN rarity VARCHAR(32)'))
            db.session.commit()
    except Exception:
        db.session.rollback()
    # Lightweight migration: add total_spent to users if missing
    try:
        ucols = [c['name'] for c in db.session.execute(db.text("PRAGMA table_info(users)")).mappings().all()]
        if 'total_spent' not in ucols:
            db.session.execute(db.text('ALTER TABLE users ADD COLUMN total_spent INTEGER DEFAULT 0 NOT NULL'))
            db.session.commit()
        if 'public_enabled' not in ucols:
            db.session.execute(db.text('ALTER TABLE users ADD COLUMN public_enabled BOOLEAN DEFAULT 0 NOT NULL'))
            db.session.commit()
        if 'public_slug' not in ucols:
            db.session.execute(db.text('ALTER TABLE users ADD COLUMN public_slug VARCHAR(120)'))
            db.session.commit()
    except Exception:
        db.session.rollback()

    if not User.query.first():
        demo = User(username='johndoe', avatar='https://via.placeholder.com/150', money=500, total_spent=0, public_enabled=True, public_slug='johndoe')
        demo.set_password('password')
        db.session.add(demo)
        db.session.commit()
    # Migrate any stored avatars missing leading slash (e.g., 'static/default-avatar.png')
    dirty = False
    for u in User.query.all():
        if u.avatar and not (u.avatar.startswith('http://') or u.avatar.startswith('https://') or u.avatar.startswith('/')):
            u.avatar = '/' + u.avatar.lstrip('/')
            dirty = True
        if (not u.avatar) or ('default-avatar.png' in u.avatar) or (u.avatar.endswith('default-avatar.svg') and not u.avatar.startswith('/')):
            # ensure correct default path (migrate from PNG to SVG)
            u.avatar = DEFAULT_AVATAR_PATH
            dirty = True
    if dirty:
        db.session.commit()
    _DB_INITIALIZED = True
    # Backfill rarity for any existing rows missing it (value-based heuristic)
    missing = Item.query.filter((Item.rarity == None) | (Item.rarity == '')).all()  # noqa: E711
    for it in missing:
        if it.value >= 1000:
            it.rarity = 'legendary'
        elif it.value >= 200:
            it.rarity = 'rare'
        elif it.value >= 50:
            it.rarity = 'uncommon'
        else:
            it.rarity = 'common'
    if missing:
        db.session.commit()
    # Seed a minimal starter item pool if empty so case spins function before running scan_items.py
    if not Item.query.first():
        starter_items = [
            ("Starter Common", 5, None, "common"),
            ("Starter Uncommon", 45, None, "uncommon"),
            ("Starter Rare", 220, None, "rare"),
            ("Starter Mythic", 480, None, "mythical"),
            ("Starter Legendary", 1500, None, "legendary"),
        ]
        for name, value, image, rarity in starter_items:
            if not Item.query.filter_by(name=name).first():
                db.session.add(Item(name=name, value=value, image=image, rarity=rarity))
        db.session.commit()

@app.route('/')
def index():
    # Show home dashboard (with stats if logged in) or redirect to login
    uid = session.get('user_id')
    if not uid:
        return redirect(url_for('login'))
    user = User.query.get(uid)
    if not user:
        session.clear()
        return redirect(url_for('login'))
    # Aggregate simple stats
    inv_items = user.inventory_items
    inventory_value = user.inventory_total_value
    item_count = sum(inv.quantity for inv in inv_items)
    return render_template('home.html', user=user, inventory_value=inventory_value, item_count=item_count)

@app.route('/home')
def home():
    uid = session.get('user_id')
    if not uid:
        return redirect(url_for('login'))
    user = User.query.get(uid)
    if not user:
        session.clear()
        return redirect(url_for('login'))
    inv_items = user.inventory_items
    inventory_value = user.inventory_total_value
    item_count = sum(inv.quantity for inv in inv_items)
    return render_template('home.html', user=user, inventory_value=inventory_value, item_count=item_count)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username','').strip()
        password = request.form.get('password','')
        user = User.query.filter_by(username=username).first()
        if not user or not user.check_password(password):
            flash('Invalid credentials', 'error')
            return render_template('login.html')
        session['user_id'] = user.id
        flash('Logged in successfully', 'success')
        return redirect(url_for('profile'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out', 'info')
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username','').strip()
        password = request.form.get('password','')
        if not username or not password:
            flash('Username and password required', 'error')
            return render_template('login.html', register=True)
        user = User(username=username, avatar=DEFAULT_AVATAR_PATH, money=0)
        user.set_password(password)
        db.session.add(user)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash('Username already exists', 'error')
            return render_template('login.html', register=True)
        flash('Account created. Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('login.html', register=True)

@app.route('/upload_avatar', methods=['POST'])
def upload_avatar():
    uid = session.get('user_id')
    if not uid:
        return redirect(url_for('login'))
    user = User.query.get(uid)
    if not user:
        session.clear()
        return redirect(url_for('login'))
    file = request.files.get('avatar_file')
    if not file or file.filename == '':
        flash('No file provided', 'error')
        return redirect(url_for('public_profile_settings'))
    # Validate extension
    allowed = {'.png','.jpg','.jpeg','.webp','.svg'}
    suffix = Path(file.filename).suffix.lower()
    if suffix not in allowed:
        flash('Unsupported file type', 'error')
        return redirect(url_for('public_profile_settings'))
    # Size limit ~512KB
    file.seek(0,2)
    size = file.tell()
    if size > 512*1024:
        flash('File too large (max 512KB)', 'error')
        return redirect(url_for('public_profile_settings'))
    file.seek(0)
    avatars_dir = BASE_DIR / 'static' / 'avatars'
    avatars_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"user_{user.id}{suffix}"
    disk_path = avatars_dir / safe_name
    file.save(disk_path)
    # Store relative public path
    user.avatar = f"/static/avatars/{safe_name}"
    db.session.commit()
    flash('Avatar updated', 'success')
    return redirect(url_for('public_profile_settings'))

@app.route('/profile')
def profile():
    uid = session.get('user_id')
    if not uid:
        return redirect(url_for('login'))
    user = User.query.get(uid)
    if not user:
        session.clear()
        return redirect(url_for('login'))
    # Recent acquisition history (latest 25)
    history = AcquisitionHistory.query.filter_by(user_id=user.id).order_by(AcquisitionHistory.created_at.desc()).limit(25).all()
    return render_template('profile.html', user=user, history=history)

@app.route('/friends')
def friends():
    uid = session.get('user_id')
    if not uid:
        return redirect(url_for('login'))
    user = User.query.get(uid)
    if not user:
        session.clear()
        return redirect(url_for('login'))
    # Fetch friend relationships (outgoing)
    friend_links = Friend.query.filter_by(user_id=user.id).join(User, Friend.friend_id == User.id).all()
    friends = []
    for link in friend_links:
        f = link.friend
        friends.append({
            'username': f.username,
            'slug': f.public_slug,
            'public_enabled': f.public_enabled,
            'avatar': f.avatar,
            'inventory_value': f.inventory_total_value,
            'roi': f.roi_value,
        })
    return render_template('friends.html', friends=friends, user=user)

@app.route('/friends/add', methods=['GET','POST'])
def friends_add():
    uid = session.get('user_id')
    if not uid:
        return redirect(url_for('login'))
    user = User.query.get(uid)
    if not user:
        session.clear()
        return redirect(url_for('login'))
    if request.method == 'POST':
        slug = request.form.get('slug','').strip().lower()
        if not slug:
            flash('Enter a slug', 'error')
            return redirect(url_for('friends_add'))
        target = User.query.filter_by(public_slug=slug, public_enabled=True).first()
        if not target:
            flash('No public user with that slug', 'error')
            return redirect(url_for('friends_add'))
        if target.id == user.id:
            flash('You cannot add yourself', 'error')
            return redirect(url_for('friends_add'))
        # Prevent duplicate
        existing = Friend.query.filter_by(user_id=user.id, friend_id=target.id).first()
        if existing:
            flash('Already added', 'info')
            return redirect(url_for('friends'))
        db.session.add(Friend(user_id=user.id, friend_id=target.id))
        # Also add the reverse relationship if not already present
        if not Friend.query.filter_by(user_id=target.id, friend_id=user.id).first():
            db.session.add(Friend(user_id=target.id, friend_id=user.id))
        db.session.commit()
        flash(f'Added {target.username} as a friend', 'success')
        return redirect(url_for('friends'))
    return render_template('friends_add.html', user=user)

@app.route('/profile/public', methods=['GET','POST'])
def public_profile_settings():
    uid = session.get('user_id')
    if not uid:
        return redirect(url_for('login'))
    user = User.query.get(uid)
    if not user:
        session.clear()
        return redirect(url_for('login'))
    if request.method == 'POST':
        # Optional avatar file upload in unified settings form
        file = request.files.get('avatar_file')
        if file and file.filename:
            allowed = {'.png','.jpg','.jpeg','.webp','.svg'}
            suffix = Path(file.filename).suffix.lower()
            if suffix not in allowed:
                flash('Unsupported avatar file type', 'error')
                return redirect(url_for('public_profile_settings'))
            file.seek(0,2)
            size = file.tell()
            if size > 512*1024:
                flash('Avatar file too large (max 512KB)', 'error')
                return redirect(url_for('public_profile_settings'))
            file.seek(0)
            avatars_dir = BASE_DIR / 'static' / 'avatars'
            avatars_dir.mkdir(parents=True, exist_ok=True)
            safe_name = f"user_{user.id}{suffix}"
            disk_path = avatars_dir / safe_name
            file.save(disk_path)
            user.avatar = f"/static/avatars/{safe_name}"
        enabled = request.form.get('public_enabled') == 'on'
        slug = request.form.get('public_slug','').strip().lower() or None
        # Basic slug validation
        if slug:
            import re
            if not re.match(r'^[a-z0-9_-]{3,32}$', slug):
                flash('Slug must be 3-32 chars (a-z, 0-9, _, -)', 'error')
                return redirect(url_for('public_profile_settings'))
            existing = User.query.filter(User.public_slug == slug, User.id != user.id).first()
            if existing:
                flash('Slug already in use', 'error')
                return redirect(url_for('public_profile_settings'))
        # Auto-generate slug if enabled and none provided
        if enabled and not slug:
            alphabet = string.ascii_lowercase + string.digits
            for _ in range(10):
                candidate = ''.join(secrets.choice(alphabet) for _ in range(8))
                if not User.query.filter_by(public_slug=candidate).first():
                    slug = candidate
                    flash(f'Generated public URL: /u/{slug}', 'info')
                    break
            if not slug:
                flash('Could not generate a unique slug. Try again.', 'error')
                return redirect(url_for('public_profile_settings'))
        user.public_enabled = enabled
        user.public_slug = slug if enabled else None
        # Update showcase selection
        selected_ids = request.form.getlist('showcase_item')  # list of item_id strings
        # Remove old entries not selected
        keep_ids = set(int(i) for i in selected_ids if i.isdigit())
        for entry in list(user.showcase_items):
            if entry.item_id not in keep_ids:
                db.session.delete(entry)
        # Add new selections (limit 12)
        limit = 12
        added = 0
        for iid in keep_ids:
            if len([e for e in user.showcase_items if e.item_id == iid]) == 0 and added < limit:
                db.session.add(PublicShowcase(user_id=user.id, item_id=iid))
                added += 1
        db.session.commit()
        flash('Public profile updated', 'success')
        return redirect(url_for('public_profile_settings'))
    # Build inventory for selection list
    inv_entries = []
    for inv in user.inventory_items:
        if inv.item:
            inv_entries.append({'item_id': inv.item_id, 'name': inv.item.name, 'image': inv.item.image, 'rarity': inv.item.rarity, 'quantity': inv.quantity})
    selected_ids = {e.item_id for e in user.showcase_items}
    return render_template('public_profile_settings.html', user=user, inventory=inv_entries, selected_ids=selected_ids)

@app.route('/u/<slug>')
def public_profile(slug):
    user = User.query.filter_by(public_slug=slug, public_enabled=True).first()
    if not user:
        flash('Public profile not found', 'error')
        return redirect(url_for('login'))
    # Gather showcase items
    showcase = []
    for entry in user.showcase_items:
        if entry.item:
            showcase.append({
                'name': entry.item.name,
                'image': entry.item.image,
                'rarity': entry.item.rarity,
                'value': entry.item.value
            })
    return render_template('public_profile.html', profile_user=user, showcase=showcase)

@app.route('/inventory')
def inventory_page():
    uid = session.get('user_id')
    if not uid:
        return redirect(url_for('login'))
    user = User.query.get(uid)
    if not user:
        session.clear()
        return redirect(url_for('login'))
    inventory = [
        {
            'name': inv.item.name,
            'value': inv.item.value,
            'image': inv.item.image,
            'quantity': inv.quantity
        } for inv in user.inventory_items if inv.item
    ]
    return render_template('inventory.html', inventory=inventory)

# ---------------- Case Opening System ----------------

# Static definition of 10 cases (can be moved to DB later)
CASES = [
    { 'id': i, 'name': f'Alpha Case {i+1}', 'price': (i+1)*25, 'rarities': ['common','uncommon','rare','mythical','legendary'] } for i in range(5)
] + [
    { 'id': 5+i, 'name': f'Omega Case {i+1}', 'price': 200 + i*35, 'rarities': ['uncommon','rare','mythical','legendary','ancient','exceedinglyrare','immortal'] } for i in range(5)
]

RARITY_WEIGHTS = {
    'common': 60,
    'uncommon': 25,
    'rare': 10,
    'mythical': 4,
    'legendary': 1.5,
    'ancient': 0.75,
    'exceedinglyrare': 0.4,
    'immortal': 0.2,
    'unique': 0.1,
}

def get_case(case_id: int):
    return next((c for c in CASES if c['id'] == case_id), None)

def pick_weighted(items):
    total = sum(RARITY_WEIGHTS.get(it.rarity or 'common', 1) for it in items)
    r = random.random() * total
    upto = 0
    for it in items:
        w = RARITY_WEIGHTS.get(it.rarity or 'common', 1)
        if upto + w >= r:
            return it
        upto += w
    return items[-1]

def _auto_seed_items_if_empty():
    """Create a minimal pool of placeholder items if the items table is empty.

    This prevents 'empty_pool' errors for fresh setups where scan_items.py
    hasn't been run yet. Safe / idempotent: only runs when no items exist.
    """
    if Item.query.first():
        return False
    seed_defs = [
        ("Rusty Pistol", 5, "static/imgs/weapon/placeholder_pistol.png", "common"),
        ("Worn SMG", 18, "static/imgs/weapon/placeholder_smg.png", "uncommon"),
        ("Shiny Rifle", 120, "static/imgs/weapon/placeholder_rifle.png", "rare"),
        ("Mythic Blade", 480, "static/imgs/weapon/placeholder_blade.png", "mythical"),
        ("Dragon Relic", 1500, "static/imgs/weapon/placeholder_relic.png", "legendary"),
    ]
    for name, value, image, rarity in seed_defs:
        # Avoid unique constraint issues if partially seeded already
        if not Item.query.filter_by(name=name).first():
            db.session.add(Item(name=name, value=value, image=image, rarity=rarity))
    db.session.commit()
    return True

@app.route('/cases')
def case_selector():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    # Map case ids to dedicated artwork in static/imgs/weapon/case/{alpha|omega}
    enriched = []
    for c in CASES:
        if c['id'] < 5:  # Alpha set
            idx = c['id'] + 1  # 1..5
            img = f"static/imgs/weapon/case/alpha/alpha_case_{idx:02d}.png"
        else:  # Omega set
            idx = c['id'] - 4  # 1..5 for ids 5..9
            img = f"static/imgs/weapon/case/omega/omega_case_{idx:02d}.png"
        enriched.append({**c, 'image': img})
    return render_template('case_selector.html', cases=enriched)

@app.route('/open_case/<int:case_id>')
def open_case(case_id: int):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    case = get_case(case_id)
    if not case:
        flash('Case not found', 'error')
        return redirect(url_for('case_selector'))
    return render_template('case_opening.html', case=case)

@app.route('/api/case/<int:case_id>/spin', methods=['POST'])
def api_spin(case_id: int):
    uid = session.get('user_id')
    if not uid:
        return jsonify({'error': 'auth'}), 401
    case = get_case(case_id)
    if not case:
        return jsonify({'error': 'case_not_found'}), 404
    user = User.query.get(uid)
    if not user:
        return jsonify({'error': 'auth'}), 401
    # Fetch eligible items by rarity filter
    q = Item.query
    if case['rarities']:
        q = q.filter(Item.rarity.in_(case['rarities']))
    pool = q.all()
    auto_seeded = False
    if not pool:
        # Fallback 1: broaden to all items ignoring rarity filter
        pool = Item.query.all()
    if not pool:
        # Fallback 2: auto-seed a small placeholder set
        auto_seeded = _auto_seed_items_if_empty()
        pool = Item.query.all()
    if not pool:
        return jsonify({'error':'empty_pool','message':'No items available. Run scan_items.py to ingest assets.'}), 400
    # Deduct case price (if user lacks funds, allow negative? choose to block)
    price = case.get('price', 0)
    # Always count spending based on cases opened (independent of current balance)
    user.total_spent = (user.total_spent or 0) + price
    # Optionally deduct balance only if they can afford it (no forced negative balance)
    if user.money >= price:
        user.money -= price
    # Pick winning item
    winning = pick_weighted(pool)
    # Build reel with weighted random items and choose a random stop index so it doesn't always appear last.
    # Longer reel length produces more perceived spin time.
    reel_length = 80
    weights = [RARITY_WEIGHTS.get(it.rarity or 'common',1) for it in pool]
    reel = [random.choices(pool, weights=weights)[0] for _ in range(reel_length)]
    # Choose stop index safely away from edges so animation has lead-in and small tail.
    stop_index = random.randint(25, reel_length - 8)
    reel[stop_index] = winning  # ensure winning item at chosen stop
    # Award item (increment quantity or add new)
    inv = next((inv for inv in user.inventory_items if inv.item_id == winning.id), None)
    if inv:
        inv.quantity += 1
    else:
        db.session.add(InventoryItem(user_id=user.id, item_id=winning.id, quantity=1))
    # Persist item award and history
    db.session.commit()
    try:
        db.session.add(AcquisitionHistory(user_id=user.id, item_id=winning.id, case_id=case_id, case_name=case.get('name')))
        db.session.commit()
    except Exception:
        db.session.rollback()
    # Serialize reel
    def ser(it):
        img = it.image or 'static/placeholder-item.svg'
        # Normalize: strip leading slash for consistency then front-end can add if needed
        img = img.lstrip('/')
        return {
            'id': it.id,
            'name': it.name,
            'rarity': it.rarity,
            'value': it.value,
            'image': img,
        }
    return jsonify({
        'reel': [ser(it) for it in reel],
        'stopIndex': stop_index,
        'win': ser(winning),
        'inventoryValue': user.inventory_total_value,
        'autoSeeded': auto_seeded,
    })

if __name__ == '__main__':
    import os, argparse, socket

    def is_port_free(host: str, port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.2)
            return s.connect_ex((host, port)) != 0

    parser = argparse.ArgumentParser(description='Run CaseOpener Flask app.')
    parser.add_argument('--host', default=os.environ.get('APP_HOST', '0.0.0.0'), help='Host interface to bind (default 127.0.0.1)')
    parser.add_argument('--port', type=int, default=int(os.environ.get('APP_PORT', 8000)), help='Port to bind (default 8000)')
    parser.add_argument('--auto-port', action='store_true', help='If set, automatically find the next free port if desired one is busy.')
    args = parser.parse_args()

    host = args.host
    port = args.port
    if args.auto_port and not is_port_free(host, port):
        base = port
        for candidate in range(base + 1, base + 25):
            if is_port_free(host, candidate):
                print(f"[auto-port] Port {base} busy; using {candidate} instead.")
                port = candidate
                break
        else:
            raise SystemExit('No free port found in search range.')

    try:
        app.run(host=host, port=port, debug=True)
    except OSError as e:
        if 'Address already in use' in str(e):
            print(f"Error: Port {port} already in use. Options:\n  1) Kill process using it (see instructions below).\n  2) Choose another port: python app.py --port {port+1}\n  3) Let auto-pick: python app.py --auto-port\n")
        raise
