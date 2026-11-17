import hashlib
import hmac
import re
from flask import Blueprint, render_template, request, flash, redirect, url_for
from .models import User
from werkzeug.security import generate_password_hash, check_password_hash
from . import db
from flask_login import login_user, login_required, logout_user, current_user

auth = Blueprint('auth', __name__)

def verify_password(user, password):
    """
    Modern Werkzeug's check_password_hash() raises ValueError on hashes
    created by the old pre-2.x default (format 'sha256$salt$hash', a
    single-round salted digest, not PBKDF2). Accounts created before the
    Werkzeug upgrade still have those stored, so we fall back to manually
    verifying that legacy format and transparently re-hash to the modern
    scheme on successful login.
    """
    if not isinstance(password, str) or not password or len(password) > 1024:
        return False
    if not isinstance(user.password, str):
        return False
    try:
        return check_password_hash(user.password, password)
    except ValueError:
        parts = user.password.split('$')
        if len(parts) != 3:
            return False
        method, salt, hashval = parts
        if method != 'sha256' or not re.fullmatch(r'[0-9a-f]{64}', hashval):
            return False
        try:
            computed = hashlib.new(method, (salt + password).encode('utf-8')).hexdigest()
        except ValueError:
            return False
        if hmac.compare_digest(computed, hashval):
            user.password = generate_password_hash(password)
            db.session.commit()
            return True
        return False

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST' :
        email = (request.form.get('email') or '').strip()
        password = request.form.get('password') or ''
        user = User.query.filter_by(email=email).first()

        if user:
            if verify_password(user, password):
                flash('Logged in Successfully', category='success')
                login_user(user, remember=True)
                return redirect(url_for('views.home'))
            else :
                flash('Invalid email or password', category='error')
        else :
            flash('Invalid email or password', category='error')
    return render_template('login.html', user=current_user)

# POST juga diterima: tombol Keluar di base.html adalah form POST (dengan
# csrf_token), sedangkan route ini dulu cuma GET -- tombolnya selalu 405.
@auth.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    # Keluar kembali ke halaman depan (landing), bukan langsung ke form login.
    return redirect(url_for('views.home'))

@auth.route('/sign-up', methods=['GET', 'POST'])
def sign_up():
    if request.method == "POST":
        email = (request.form.get('email') or '').strip()
        firstName = (request.form.get('firstName') or '').strip()
        password1 = request.form.get('password1') or ''
        password2 = request.form.get('password2') or ''

        user = User.query.filter_by(email=email).first()
        if user :
            flash('Email already exist', category='error')
        elif len(email) > 150 or not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', email):
            flash('Enter a valid email address', category='error')
        elif not 2 <= len(firstName) <= 150:
            flash("Fist Name is Short", category='error')
        elif password1 != password2:
            flash("Password gk sama", category='error')
        elif not 10 <= len(password1) <= 1024:
            flash('Password must contain between 10 and 1024 characters', category='error')
        else :
            # Note: 'sha256' is not a valid method name in modern Werkzeug
            # versions (it now expects 'pbkdf2:sha256', 'scrypt', etc., or
            # no method arg at all to use the secure default).
            newUser = User(email=email, firstName = firstName, password=generate_password_hash(password1))
            db.session.add(newUser)
            db.session.commit()
            #login_user(user, remember=True)
            flash("Account created", category='success')
            return redirect(url_for('views.home'))
    return render_template("sign_up.html", user=current_user)
