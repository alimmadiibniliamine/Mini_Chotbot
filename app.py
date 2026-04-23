from flask import Flask, request, jsonify, render_template, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import ollama
import datetime
import os

app = Flask(__name__)

# --- Configuration ---
app.config['SECRET_KEY'] = 'une_cle_secrete_tres_longue_et_aleatoire_12345'
# Utilisation d'un chemin absolu pour éviter les problèmes sous Windows
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'database.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = "Veuillez vous connecter pour accéder à cette page."
login_manager.login_message_category = "info"

# --- Modèles de Données ---

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(256), nullable=False)
    chats = db.relationship('ChatHistory', backref='user', lazy=True)

class ChatHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    role = db.Column(db.String(10), nullable=False) # 'user' ou 'bot'
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

# Création automatique de la base de données
with app.app_context():
    db.create_all()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Routes d'Authentification ---

@app.route("/register", methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user_exists = User.query.filter_by(username=username).first()
        if user_exists:
            flash("Cet utilisateur existe déjà.", "error")
            return redirect(url_for('register'))

        hashed_pw = generate_password_hash(password)
        new_user = User(username=username, password=hashed_pw)
        
        try:
            db.session.add(new_user)
            db.session.commit()
            flash("Compte créé avec succès ! Connectez-vous.", "success")
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash("Une erreur est survenue lors de l'inscription.", "error")
            
    return render_template("register.html")

@app.route("/login", methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('home'))
        else:
            flash("Identifiants incorrects.", "error")
            
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- Routes du Chat ---

@app.route("/")
@login_required
def home():
    # On récupère l'historique complet pour l'afficher au chargement
    history = ChatHistory.query.filter_by(user_id=current_user.id).order_by(ChatHistory.timestamp.asc()).all()
    return render_template("index.html", history=history, username=current_user.username)

@app.route("/chat", methods=["POST"])
@login_required
def chat():
    user_message = request.json.get("message")
    if not user_message:
        return jsonify({"error": "Message vide"}), 400

    try:
        # 1. Sauvegarder le message utilisateur
        user_chat = ChatHistory(content=user_message, role='user', user_id=current_user.id)
        db.session.add(user_chat)

        # 2. Appeler Ollama (Ministral)
        # Note: On pourrait envoyer l'historique ici pour donner de la mémoire à l'IA
        response = ollama.chat(
            model="ministral-3:14b-cloud",
            messages=[{"role": "user", "content": user_message}]
        )
        bot_response = response["message"]["content"]

        # 3. Sauvegarder la réponse du bot
        bot_chat = ChatHistory(content=bot_response, role='bot', user_id=current_user.id)
        db.session.add(bot_chat)
        db.session.commit()

        return jsonify({"response": bot_response})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"response": f"Erreur avec Ollama : {str(e)}"}), 500

if __name__ == "__main__":
    app.run(debug=True, port=5000)