from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
from datetime import datetime
import markdown
from markupsafe import Markup
import mimetypes

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-very-secure-key-change-me-2025'
app.config['SQLALCHEMY_DATABASE_URI'] = 'DATABASE_URL=postgresql://postgres:321456@localhost:5432/devconnect_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'

db = SQLAlchemy(app)

# Папки
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'avatars'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'articles/images'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'articles/files'), exist_ok=True)
CHAT_UPLOAD_FOLDER = os.path.join(app.config['UPLOAD_FOLDER'], 'chat_files')
os.makedirs(CHAT_UPLOAD_FOLDER, exist_ok=True)

# Модели
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    avatar = db.Column(db.String(255))
    description = db.Column(db.Text)
    skills = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    articles = db.relationship('Article', backref='author', lazy=True)
    sent_messages = db.relationship('Message', backref='sender', lazy=True)
    chats = db.relationship('Chat', secondary='chat_participant',
                            backref=db.backref('participants', lazy='dynamic'))


class Article(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    image_path = db.Column(db.String(255))
    file_path = db.Column(db.String(255))
    file_name = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Chat(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    messages = db.relationship('Message', backref='chat', lazy='dynamic')


class ChatParticipant(db.Model):
    __tablename__ = 'chat_participant'
    chat_id = db.Column(db.Integer, db.ForeignKey('chat.id'), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.Integer, db.ForeignKey('chat.id'), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text)
    file_path = db.Column(db.String(255))           # путь к файлу
    file_name = db.Column(db.String(255))           # оригинальное имя
    mime_type = db.Column(db.String(100))           # тип файла
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


with app.app_context():
    db.create_all()

ALLOWED_IMAGE = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
ALLOWED_FILE = {'pdf', 'doc', 'docx', 'txt', 'md', 'zip', 'rar', '7z', 'py', 'js', 'cpp', 'java', 'html', 'css'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 МБ


def allowed_image(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_FILE


def render_message_content(content):
    html = markdown.markdown(
        content,
        extensions=['fenced_code', 'codehilite'],
        extension_configs={'codehilite': {'css_class': 'hljs'}}
    )
    return Markup(html)


def get_or_create_chat(user1_id, user2_id):
    chat = Chat.query.filter(
        Chat.participants.any(User.id == user1_id),
        Chat.participants.any(User.id == user2_id)
    ).first()

    if not chat:
        chat = Chat()
        db.session.add(chat)
        db.session.flush()

        p1 = ChatParticipant(chat_id=chat.id, user_id=user1_id)
        p2 = ChatParticipant(chat_id=chat.id, user_id=user2_id)
        db.session.add_all([p1, p2])
        db.session.commit()

    return chat


@app.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('profile'))
    return render_template('index.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            flash('Вход выполнен', 'success')
            return redirect(url_for('profile'))
        else:
            flash('Неверный email или пароль', 'error')

    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        description = request.form.get('description', '')
        skills = request.form.getlist('skills')
        password = request.form.get('password')
        confirm = request.form.get('confirm_password')

        if password != confirm:
            flash('Пароли не совпадают', 'error')
            return render_template('register.html')

        if User.query.filter_by(username=username).first() or User.query.filter_by(email=email).first():
            flash('Username или email занят', 'error')
            return render_template('register.html')

        avatar_path = None
        if 'avatar' in request.files and request.files['avatar'].filename:
            file = request.files['avatar']
            if allowed_image(file.filename):
                filename = secure_filename(f"{username}_{int(datetime.now().timestamp())}.png")
                path = os.path.join(app.config['UPLOAD_FOLDER'], 'avatars', filename)
                file.save(path)
                avatar_path = f'/static/uploads/avatars/{filename}'

        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
            avatar=avatar_path,
            description=description,
            skills=skills
        )
        db.session.add(user)
        db.session.commit()

        flash('Регистрация успешна. Войдите.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/profile')
def profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = db.session.get(User, session['user_id'])
    articles = Article.query.filter_by(user_id=user.id).order_by(Article.created_at.desc()).all()
    return render_template('profile.html', user=user, articles=articles)


@app.route('/profile/<string:username>')
def user_profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    articles = Article.query.filter_by(user_id=user.id).order_by(Article.created_at.desc()).all()
    is_own = session.get('user_id') == user.id
    return render_template('profile.html', user=user, articles=articles, is_own_profile=is_own)


@app.route('/articles')
def articles():
    all_articles = Article.query.order_by(Article.created_at.desc()).all()
    return render_template('articles.html', articles=all_articles)


@app.route('/profile', methods=['POST'])
@app.route('/profile/<string:username>', methods=['POST'])
def add_article(username=None):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = db.session.get(User, session['user_id'])
    title = request.form.get('title', '').strip()
    content = request.form.get('content', '').strip()

    if not title or not content:
        flash('Название и текст обязательны', 'error')
        return redirect(url_for('profile'))

    image_path = file_path = file_name = None

    if 'image' in request.files and request.files['image'].filename:
        f = request.files['image']
        if allowed_image(f.filename):
            ext = f.filename.rsplit('.', 1)[1].lower()
            fn = f"{user.id}_{int(datetime.now().timestamp())}.{ext}"
            path = os.path.join(app.config['UPLOAD_FOLDER'], 'articles/images', fn)
            f.save(path)
            image_path = f"/static/uploads/articles/images/{fn}"

    if 'file' in request.files and request.files['file'].filename:
        f = request.files['file']
        if allowed_file(f.filename):
            fn = f"{user.id}_{int(datetime.now().timestamp())}_{secure_filename(f.filename)}"
            path = os.path.join(app.config['UPLOAD_FOLDER'], 'articles/files', fn)
            f.save(path)
            file_path = f"/static/uploads/articles/files/{fn}"
            file_name = f.filename

    article = Article(
        user_id=user.id,
        title=title,
        content=content,
        image_path=image_path,
        file_path=file_path,
        file_name=file_name
    )
    db.session.add(article)
    db.session.commit()

    flash('Статья добавлена', 'success')
    return redirect(url_for('profile'))


@app.route('/download/<path:filename>')
def download_file(filename):
    if 'user_id' not in session:
        flash('Нужно войти', 'error')
        return redirect(url_for('login'))
    dir_path = os.path.join(app.config['UPLOAD_FOLDER'], 'articles/files')
    return send_from_directory(dir_path, filename, as_attachment=True)


@app.route('/messages')
def messages_list():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = db.session.get(User, session['user_id'])

    chats = Chat.query\
        .join(ChatParticipant)\
        .filter(ChatParticipant.user_id == user.id)\
        .order_by(Chat.created_at.desc())\
        .all()

    chat_list = []
    for chat in chats:
        other_user = next((p for p in chat.participants if p.id != user.id), None)
        if other_user:
            last_message = Message.query.filter_by(chat_id=chat.id).order_by(Message.created_at.desc()).first()
            chat_list.append({
                'chat_id': chat.id,
                'other_user': other_user,
                'last_message': last_message.content[:50] + '...' if last_message else 'Нет сообщений',
                'last_time': last_message.created_at if last_message else chat.created_at
            })

    return render_template('messages.html', chats=chat_list, user=user)


@app.route('/chat/<int:chat_id>')
def chat(chat_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = db.session.get(User, session['user_id'])
    chat = Chat.query.get_or_404(chat_id)

    if user not in chat.participants:
        flash('Нет доступа к этому чату', 'error')
        return redirect(url_for('messages_list'))

    other_user = next((p for p in chat.participants if p.id != user.id), None)

    messages = Message.query\
        .filter(Message.chat_id == chat.id)\
        .order_by(Message.created_at.asc())\
        .all()

    return render_template('chat.html',
                           chat=chat,
                           messages=messages,
                           user=user,
                           other_user=other_user,
                           render_message_content=render_message_content)


@app.route('/chat/<int:chat_id>/send', methods=['POST'])
def send_message(chat_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    content = request.form.get('content', '').strip()
    file_path = None
    file_name = None
    mime_type = None

    # Обработка файла
    if 'file' in request.files:
        file = request.files['file']
        if file and file.filename:
            file.seek(0, os.SEEK_END)
            file_size = file.tell()
            file.seek(0)
            if file_size > 10 * 1024 * 1024:
                flash('Файл слишком большой (макс. 10 МБ)', 'error')
                return redirect(url_for('chat', chat_id=chat_id))

            ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
            if ext in ALLOWED_IMAGE or ext in ALLOWED_FILE:
                filename = secure_filename(f"{session['user_id']}_{int(datetime.now().timestamp())}_{file.filename}")
                path = os.path.join(CHAT_UPLOAD_FOLDER, filename)
                file.save(path)
                file_path = f"/static/uploads/chat_files/{filename}"
                file_name = file.filename
                mime_type = mimetypes.guess_type(path)[0] or 'application/octet-stream'
            else:
                flash('Недопустимый тип файла', 'error')
                return redirect(url_for('chat', chat_id=chat_id))

    if not content and not file_path:
        flash('Напишите сообщение или прикрепите файл', 'error')
        return redirect(url_for('chat', chat_id=chat_id))

    user = db.session.get(User, session['user_id'])
    chat = Chat.query.get_or_404(chat_id)

    if user not in chat.participants:
        flash('Нет доступа', 'error')
        return redirect(url_for('messages_list'))

    message = Message(
        chat_id=chat.id,
        sender_id=user.id,
        content=content,
        file_path=file_path,
        file_name=file_name,
        mime_type=mime_type
    )
    db.session.add(message)
    db.session.commit()

    return redirect(url_for('chat', chat_id=chat_id))


@app.route('/start_chat/<string:username>')
def start_chat(username):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    current = db.session.get(User, session['user_id'])
    other = User.query.filter_by(username=username).first_or_404()

    if other.id == current.id:
        flash('Нельзя написать самому себе', 'error')
        return redirect(url_for('profile'))

    chat = get_or_create_chat(current.id, other.id)
    return redirect(url_for('chat', chat_id=chat.id))


@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('Вы вышли', 'success')
    return redirect(url_for('home'))


if __name__ == '__main__':
    app.run(debug=True)
