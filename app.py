import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, g, session, flash
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'change_this_secret_key'

DATABASE = 'forum.db'

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        with open('schema.sql', 'r') as f:
            db.executescript(f.read())
        db.commit()

@app.cli.command('initdb')
def initdb_command():
    if os.path.exists(DATABASE):
        os.remove(DATABASE)
        print('Ancienne base supprimée.')
    init_db()
    print('Base recréée avec succès.')

def get_current_user():
    user_id = session.get('user_id')
    if user_id:
        db = get_db()
        return db.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    return None

def get_messages_tree(db, subject_id):
    messages = db.execute(
        'SELECT * FROM messages WHERE subject_id = ? ORDER BY created_at',
        (subject_id,)
    ).fetchall()

    messages_dict = {}
    for msg in messages:
        msg = dict(msg)
        msg['replies'] = []
        messages_dict[msg['id']] = msg

    root_messages = []
    for msg in messages_dict.values():
        if msg['parent_id']:
            parent = messages_dict.get(msg['parent_id'])
            if parent:
                parent['replies'].append(msg)
            else:
                root_messages.append(msg)
        else:
            root_messages.append(msg)

    return root_messages

@app.route('/')
def index():
    db = get_db()
    subjects = db.execute('SELECT * FROM subjects ORDER BY created_at DESC').fetchall()
    user = get_current_user()
    return render_template('index.html', subjects=subjects, user=user)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        db = get_db()
        existing_user = db.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
        if existing_user:
            flash('Nom d’utilisateur déjà pris.')
            return redirect(url_for('register'))
        password_hash = generate_password_hash(password)
        db.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)', (username, password_hash))
        db.commit()
        flash('Inscription réussie, connectez-vous !')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        if user and check_password_hash(user['password_hash'], password):
            session.clear()
            session['user_id'] = user['id']
            flash('Connecté avec succès.')
            return redirect(url_for('index'))
        flash('Identifiants invalides.')
        return redirect(url_for('login'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Déconnecté.')
    return redirect(url_for('index'))

@app.route('/account', methods=['GET', 'POST'])
def account():
    user = get_current_user()
    if not user:
        flash("Vous devez être connecté pour accéder à votre compte.")
        return redirect(url_for('login'))

    if request.method == 'POST':
        new_username = request.form['username'].strip()
        new_password = request.form['password']
        db = get_db()

        if new_username != user['username']:
            existing_user = db.execute('SELECT id FROM users WHERE username = ?', (new_username,)).fetchone()
            if existing_user:
                flash('Ce nom d’utilisateur est déjà pris.')
                return redirect(url_for('account'))

        db.execute('UPDATE users SET username = ? WHERE id = ?', (new_username, user['id']))

        if new_password:
            password_hash = generate_password_hash(new_password)
            db.execute('UPDATE users SET password_hash = ? WHERE id = ?', (password_hash, user['id']))

        db.commit()
        flash('Compte mis à jour avec succès.')
        session['user_id'] = user['id']
        return redirect(url_for('account'))

    return render_template('account.html', user=user)

@app.route('/new_subject', methods=['GET', 'POST'])
def new_subject():
    user = get_current_user()
    if not user:
        flash("Vous devez être connecté pour créer un sujet.")
        return redirect(url_for('login'))
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        db = get_db()
        db.execute('INSERT INTO subjects (title, content) VALUES (?, ?)', (title, content))
        db.commit()
        flash('Sujet créé avec succès.')
        return redirect(url_for('index'))
    return render_template('new_subject.html', user=user)

@app.route('/subject/<int:subject_id>', methods=['GET', 'POST'])
def subject(subject_id):
    db = get_db()
    user = get_current_user()
    subject = db.execute('SELECT * FROM subjects WHERE id = ?', (subject_id,)).fetchone()
    if not subject:
        return 'Sujet non trouvé', 404

    if request.method == 'POST':
        if not user:
            flash("Vous devez être connecté pour poster un message.")
            return redirect(url_for('login'))
        content = request.form['content']
        parent_id = request.form.get('parent_id')
        if parent_id == '':
            parent_id = None
        db.execute(
            'INSERT INTO messages (subject_id, parent_id, user_id, author, content) VALUES (?, ?, ?, ?, ?)',
            (subject_id, parent_id, user['id'], user['username'], content)
        )
        db.commit()
        flash('Message posté avec succès.')
        return redirect(url_for('subject', subject_id=subject_id))

    messages_tree = get_messages_tree(db, subject_id)
    return render_template('subject.html', subject=subject, messages=messages_tree, user=user)

@app.route('/delete_message/<int:message_id>', methods=['POST'])
def delete_message(message_id):
    user = get_current_user()
    if not user:
        flash("Vous devez être connecté pour supprimer un message.")
        return redirect(url_for('login'))
    db = get_db()
    message = db.execute('SELECT * FROM messages WHERE id = ?', (message_id,)).fetchone()
    if not message:
        flash('Message introuvable.')
        return redirect(url_for('index'))
    if message['user_id'] != user['id']:
        flash('Vous ne pouvez supprimer que vos propres messages.')
        return redirect(url_for('subject', subject_id=message['subject_id']))
    db.execute('DELETE FROM messages WHERE id = ?', (message_id,))
    db.commit()
    flash('Message supprimé.')
    return redirect(url_for('subject', subject_id=message['subject_id']))

@app.route('/edit_message/<int:message_id>', methods=['GET', 'POST'])
def edit_message(message_id):
    user = get_current_user()
    if not user:
        flash("Vous devez être connecté pour modifier un message.")
        return redirect(url_for('login'))

    db = get_db()
    message = db.execute('SELECT * FROM messages WHERE id = ?', (message_id,)).fetchone()
    if not message:
        flash('Message introuvable.')
        return redirect(url_for('index'))

    if message['user_id'] != user['id']:
        flash('Vous ne pouvez modifier que vos propres messages.')
        return redirect(url_for('subject', subject_id=message['subject_id']))

    if request.method == 'POST':
        new_content = request.form['content'].strip()
        db.execute('UPDATE messages SET content = ? WHERE id = ?', (new_content, message_id))
        db.commit()
        flash('Message modifié avec succès.')
        return redirect(url_for('subject', subject_id=message['subject_id']))

    return render_template('edit_message.html', message=message)

if __name__ == '__main__':
    app.run(debug=True)