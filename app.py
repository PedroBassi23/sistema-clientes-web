import os
from datetime import datetime, date
from functools import wraps
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from sqlalchemy import or_, inspect
from sqlalchemy.exc import OperationalError
import io
from markupsafe import Markup

# --- CRIAR TABELAS E USUÁRIO PADRÃO NO INÍCIO ---
with app.app_context():
    # Cria todas as tabelas se não existirem
    db.create_all()

    # Cria usuário 'teste' se não existir
    if not User.query.filter_by(username='teste').first():
        new_user = User(username='teste')
        new_user.set_password('teste1')
        db.session.add(new_user)
        db.session.commit()
        print("Usuário 'teste' criado automaticamente!")
# --- CONFIGURAÇÃO DA APLICAÇÃO ---
app = Flask(__name__)

# Configura a Secret Key e o URI do Banco de Dados a partir de variáveis de ambiente
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'uma-chave-secreta-padrao-para-desenvolvimento')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///clientes.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = "Por favor, faça login para acessar esta página."
login_manager.login_message_category = "info"

# --- MODELOS DO BANCO DE DADOS ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Cliente(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=True)
    telefone = db.Column(db.String(20), nullable=True)
    valor_a_pagar = db.Column(db.Float, nullable=False)
    status_pagamento = db.Column(db.String(20), nullable=False, default='A Pagar')
    anotacoes = db.Column(db.Text, nullable=True)
    data_vencimento = db.Column(db.Date, nullable=True)

# --- FUNÇÕES DE INICIALIZAÇÃO AUTOMÁTICA ---
try:
    with app.app_context():
        inspector = inspect(db.engine)
        if not inspector.has_table("user"):
            print("Banco de dados não encontrado, criando tabelas...")
            db.create_all()
            print("Tabelas criadas com sucesso.")
            
            user_teste = User.query.filter_by(username='teste').first()
            if not user_teste:
                new_user = User(username='teste')
                new_user.set_password('teste1')
                db.session.add(new_user)
                db.session.commit()
                print("Usuário 'teste' criado com sucesso.")
        else:
            print("Tabelas do banco de dados já existem.")
except OperationalError as e:
    print("!!!!!!!!!! ERRO DE CONEXÃO COM O BANCO DE DADOS !!!!!!!!!!")
    print("Verifique se a DATABASE_URL está correta e se as regras de rede no Supabase permitem a conexão.")
    print(f"Erro específico: {e}")
except Exception as e:
    print(f"Ocorreu um erro inesperado durante a inicialização: {e}")


# --- FUNÇÕES AUXILIARES E FILTROS JINJA ---
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def nl2br(value):
    if value is None:
        return ''
    return Markup(str(value).replace('\n', '<br>\n'))

app.jinja_env.filters['nl2br'] = nl2br

@app.context_processor
def inject_today():
    return {'hoje': date.today()}

# --- ROTAS DA APLICAÇÃO ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        try:
            user = User.query.filter_by(username=username).first()
            if user and user.check_password(password):
                login_user(user)
                return redirect(url_for('dashboard'))
            else:
                flash('Login ou senha inválidos.', 'danger')
        except OperationalError:
            flash('Erro de comunicação com o banco de dados. O servidor não está conseguindo se conectar.', 'danger')
            return redirect(url_for('login'))
            
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Você foi desconectado com sucesso.', 'success')
    return redirect(url_for('login'))

@app.route('/')
@login_required
def dashboard():
    total_clientes = db.session.query(db.func.count(Cliente.id)).scalar()
    status_counts = db.session.query(Cliente.status_pagamento, db.func.count(Cliente.id)).group_by(Cliente.status_pagamento).all()
    total_a_receber = db.session.query(db.func.sum(Cliente.valor_a_pagar)).filter(Cliente.status_pagamento != 'Pago').scalar()
    
    counts = {s: c for s, c in status_counts}
    contagem_pagar = counts.get('A Pagar', 0)
    contagem_pago = counts.get('Pago', 0)
    contagem_parcial = counts.get('Parcial', 0)
    
    vencimentos_hoje = Cliente.query.filter(Cliente.data_vencimento == date.today(), Cliente.status_pagamento != 'Pago').all()
    
    return render_template('dashboard.html',
                           total_clientes=total_clientes,
                           contagem_pagar=contagem_pagar,
                           contagem_pago=contagem_pago,
                           contagem_parcial=contagem_parcial,
                           total_a_receber=total_a_receber or 0.0,
                           vencimentos_hoje=vencimentos_hoje)

@app.route('/clientes')
@login_required
def listar_clientes():
    status = request.args.get('status', 'Todos')
    search = request.args.get('q', '')
    
    query = Cliente.query
    
    if status != 'Todos':
        query = query.filter(Cliente.status_pagamento == status)
        
    if search:
        search_term = f"%{search}%"
        query = query.filter(or_(
            Cliente.nome.ilike(search_term),
            Cliente.email.ilike(search_term),
            Cliente.telefone.ilike(search_term),
            Cliente.anotacoes.ilike(search_term),
            Cliente.status_pagamento.ilike(search_term)
        ))
        
    clientes = query.order_by(Cliente.nome).all()
    return render_template('lista_clientes.html',
                           clientes=clientes,
                           status_atual=status,
                           search_atual=search)

@app.route('/clientes/novo', methods=['GET', 'POST'])
@login_required
def novo_cliente():
    if request.method == 'POST':
        nome = request.form['nome']
        email = request.form['email']
        telefone = request.form['telefone']
        valor_a_pagar = float(request.form['valor_a_pagar'].replace(',', '.'))
        status_pagamento = request.form['status_pagamento']
        anotacoes = request.form['anotacoes']
        data_vencimento_str = request.form['data_vencimento']
        
        data_vencimento = datetime.strptime(data_vencimento_str, '%Y-%m-%d').date() if data_vencimento_str else None

        novo_cliente = Cliente(nome=nome, email=email, telefone=telefone, 
                               valor_a_pagar=valor_a_pagar, status_pagamento=status_pagamento,
                               anotacoes=anotacoes, data_vencimento=data_vencimento)
        db.session.add(novo_cliente)
        db.session.commit()
        flash('Cliente cadastrado com sucesso!', 'success')
        return redirect(url_for('listar_clientes'))
    return render_template('form_cliente.html', titulo='Novo Cliente', cliente=None)

@app.route('/clientes/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_cliente(id):
    cliente = Cliente.query.get_or_404(id)
    if request.method == 'POST':
        cliente.nome = request.form['nome']
        cliente.email = request.form['email']
        cliente.telefone = request.form['telefone']
        cliente.valor_a_pagar = float(request.form['valor_a_pagar'].replace(',', '.'))
        cliente.status_pagamento = request.form['status_pagamento']
        cliente.anotacoes = request.form['anotacoes']
        data_vencimento_str = request.form['data_vencimento']

        cliente.data_vencimento = datetime.strptime(data_vencimento_str, '%Y-%m-%d').date() if data_vencimento_str else None

        db.session.commit()
        flash('Cliente atualizado com sucesso!', 'success')
        return redirect(url_for('listar_clientes'))
    return render_template('form_cliente.html', titulo='Editar Cliente', cliente=cliente)

@app.route('/clientes/excluir/<int:id>', methods=['POST'])
@login_required
def excluir_cliente(id):
    cliente = Cliente.query.get_or_404(id)
    db.session.delete(cliente)
    db.session.commit()
    flash('Cliente excluído com sucesso!', 'danger')
    return redirect(url_for('listar_clientes'))

@app.route('/exportar')
@login_required
def exportar_clientes():
    clientes = Cliente.query.all()
    dados = [{
        "Nome": c.nome, "Email": c.email, "Telefone": c.telefone,
        "Valor a Pagar": c.valor_a_pagar, "Status": c.status_pagamento,
        "Data de Vencimento": c.data_vencimento.strftime('%d/%m/%Y') if c.data_vencimento else '',
        "Anotações": c.anotacoes
    } for c in clientes]
    df = pd.DataFrame(dados)
    
    output = io.BytesIO()
    writer = pd.ExcelWriter(output, engine='openpyxl')
    df.to_excel(writer, index=False, sheet_name='Clientes')
    writer.close()
    output.seek(0)
    
    return send_file(output, as_attachment=True, download_name='clientes.xlsx',
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

if __name__ == '__main__':
    app.run(debug=True)


