# Importa as classes e funções necessárias
import os
import io
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, or_, cast
from datetime import datetime, date
from markupsafe import Markup
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user

# --- CONFIGURAÇÃO DA APLICAÇÃO ---

app = Flask(__name__)

# Configura a Secret Key a partir de uma variável de ambiente ou usa um valor padrão (NÃO use em produção)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'uma-chave-secreta-bem-segura-para-desenvolvimento')

# Configura o URI do banco de dados a partir de uma variável de ambiente (para Supabase/PostgreSQL)
# Se não encontrar, usa o SQLite local para desenvolvimento.
db_uri = os.environ.get('DATABASE_URL')
if db_uri and db_uri.startswith("postgres://"):
    db_uri = db_uri.replace("postgres://", "postgresql://", 1) # Necessário para compatibilidade do SQLAlchemy
app.config['SQLALCHEMY_DATABASE_URI'] = db_uri or 'sqlite:///' + os.path.join(os.path.abspath(os.path.dirname(__file__)), 'clientes.db')

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- CONFIGURAÇÃO DO FLASK-LOGIN ---

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' # Rota para onde o usuário é redirecionado se não estiver logado
login_manager.login_message = "Por favor, faça login para acessar esta página."
login_manager.login_message_category = "info"

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# --- DEFINIÇÃO DOS MODELOS (BANCO DE DADOS) ---

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Cliente(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    telefone = db.Column(db.String(20), nullable=True)
    valor_a_pagar = db.Column(db.Float, nullable=False, default=0.0)
    status_pagamento = db.Column(db.String(20), nullable=False, default='A Pagar')
    anotacoes = db.Column(db.Text, nullable=True)
    data_vencimento = db.Column(db.Date, nullable=True)

# --- ROTAS DE AUTENTICAÇÃO ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('Login inválido. Verifique seu usuário e senha.', 'danger')
            
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Você foi desconectado com sucesso.', 'success')
    return redirect(url_for('login'))

# --- ROTAS DA APLICAÇÃO (PROTEGIDAS) ---

@app.route('/')
@login_required
def dashboard():
    # ... (código do dashboard permanece o mesmo)
    total_clientes = db.session.query(func.count(Cliente.id)).scalar() or 0
    a_pagar_count = db.session.query(func.count(Cliente.id)).filter(Cliente.status_pagamento == 'A Pagar').scalar() or 0
    pago_count = db.session.query(func.count(Cliente.id)).filter(Cliente.status_pagamento == 'Pago').scalar() or 0
    parcial_count = db.session.query(func.count(Cliente.id)).filter(Cliente.status_pagamento == 'Parcial').scalar() or 0
    total_a_receber = db.session.query(func.sum(Cliente.valor_a_pagar)).filter(Cliente.status_pagamento.in_(['A Pagar', 'Parcial'])).scalar() or 0.0
    hoje = date.today()
    vencimentos_hoje = Cliente.query.filter(Cliente.data_vencimento == hoje, Cliente.status_pagamento != 'Pago').all()
    return render_template('dashboard.html', total_clientes=total_clientes, a_pagar_count=a_pagar_count, pago_count=pago_count, parcial_count=parcial_count, total_a_receber=total_a_receber, vencimentos_hoje=vencimentos_hoje)

@app.route('/clientes')
@login_required
def listar_clientes():
    # ... (código de listar_clientes permanece o mesmo)
    status_filtro = request.args.get('status', '')
    search_query = request.args.get('q', '').strip()
    query = Cliente.query
    if status_filtro and status_filtro != 'Todos':
        query = query.filter_by(status_pagamento=status_filtro)
    if search_query:
        search_term = f"%{search_query}%"
        query = query.filter(or_(Cliente.nome.ilike(search_term), Cliente.email.ilike(search_term), Cliente.anotacoes.ilike(search_term), Cliente.telefone.ilike(search_term), Cliente.status_pagamento.ilike(search_term), cast(Cliente.id, db.String).ilike(search_term), cast(Cliente.valor_a_pagar, db.String).ilike(search_term)))
    clientes = query.order_by(Cliente.nome).all()
    return render_template('lista_clientes.html', clientes=clientes, status_atual=status_filtro, search_atual=search_query, hoje=date.today())

# ... (todas as outras rotas como novo_cliente, editar_cliente, etc. permanecem as mesmas, mas com @login_required)

@app.route('/clientes/novo', methods=['GET', 'POST'])
@login_required
def novo_cliente():
    # ... (código inalterado)
    if request.method == 'POST':
        # ...
        try:
            # ...
            return redirect(url_for('listar_clientes'))
        except Exception as e:
            # ...
            flash(f'Erro ao cadastrar cliente (verifique se o e-mail já existe): {e}', 'danger')

    return render_template('form_cliente.html', titulo='Novo Cliente', cliente=None, form_action=url_for('novo_cliente'))


@app.route('/clientes/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_cliente(id):
    # ... (código inalterado)
    cliente = Cliente.query.get_or_404(id)
    if request.method == 'POST':
        # ...
        try:
            db.session.commit()
            flash('Cliente atualizado com sucesso!', 'success')
            return redirect(url_for('listar_clientes'))
        except Exception as e:
            # ...
            flash(f'Erro ao editar cliente: {e}', 'danger')

    return render_template('form_cliente.html', titulo='Editar Cliente', cliente=cliente, form_action=url_for('editar_cliente', id=id))

@app.route('/clientes/excluir/<int:id>', methods=['POST'])
@login_required
def excluir_cliente(id):
    # ... (código inalterado)
    cliente = Cliente.query.get_or_404(id)
    try:
        db.session.delete(cliente)
        db.session.commit()
        flash('Cliente excluído com sucesso!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao excluir cliente: {e}', 'danger')
        
    return redirect(url_for('listar_clientes'))

@app.route('/clientes/exportar')
@login_required
def exportar_clientes():
    # ... (código inalterado)
    try:
        # ...
        return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', as_attachment=True, download_name=f'clientes_{date.today()}.xlsx')
    except Exception as e:
        flash(f'Ocorreu um erro ao exportar os dados: {e}', 'danger')
        return redirect(url_for('listar_clientes'))

# --- COMANDOS CLI ---
@app.cli.command("create-user")
def create_user():
    """Cria o usuário de teste inicial."""
    with app.app_context():
        db.create_all()
        username = "teste"
        password = "teste1"
        user = User.query.filter_by(username=username).first()
        if user:
            print(f"Usuário '{username}' já existe.")
        else:
            new_user = User(username=username)
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            print(f"Usuário '{username}' criado com sucesso!")

# --- FILTROS E PROCESSADORES DE CONTEXTO ---

@app.context_processor
def inject_year():
    return {'year': date.today().year}

def nl2br(value):
    if value:
        return Markup(str(value).replace('\n', '<br>\n'))
    return ''

app.jinja_env.filters['nl2br'] = nl2br

# --- EXECUÇÃO DA APLICAÇÃO ---

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)

