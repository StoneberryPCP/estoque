import os
import sqlite3
from flask import Flask, render_template, request, redirect, make_response
from datetime import datetime

app = Flask(__name__)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, 'estoque.db')

def cria_tabela_usuarios():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            senha TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

def cria_tabela_movimentacoes():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS movimentacoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        produto_id INTEGER NOT NULL,
        tipo TEXT NOT NULL CHECK(tipo IN ('entrada', 'saida')),
        quantidade INTEGER NOT NULL,
        data_mov DATETIME DEFAULT CURRENT_TIMESTAMP,
        responsavel TEXT,
        FOREIGN KEY(produto_id) REFERENCES produtos(id)
    )
    ''')
    conn.commit()
    conn.close()

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS produtos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        categoria TEXT,
        preco REAL,
        estoque INTEGER DEFAULT 0
    )
    ''')

    cria_tabela_movimentacoes()
    cria_tabela_usuarios()

    cursor.execute("SELECT * FROM usuarios WHERE username = 'admin'")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO usuarios (username, senha) VALUES (?, ?)", ('admin', '292078'))
        print("Usuário admin criado com senha 'admin123'")

    conn.commit()
    conn.close()

# --- Rota login ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        senha = request.form['senha']

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT senha FROM usuarios WHERE username = ?', (username,))
        resultado = cursor.fetchone()
        conn.close()

        if resultado and resultado[0] == senha:
            resp = make_response(redirect('/produtos'))
            resp.set_cookie('user', username)
            return resp
        else:
            return render_template('login.html', erro="Usuário ou senha incorretos")
    return render_template('login.html')

# --- Rota logout ---
@app.route('/logout')
def logout():
    resp = make_response(redirect('/login'))
    resp.delete_cookie('user')
    return resp

# Decorator para verificar login
def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        user = request.cookies.get('user')
        if not user:
            return redirect('/login')
        return f(*args, **kwargs, user=user)
    return decorated

# Decorator para verificar admin
def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        user = request.cookies.get('user')
        if user != 'admin':
            return redirect('/login')
        return f(*args, **kwargs, user=user)
    return decorated

# --- Rota index ---
@app.route('/')
def index():
    return render_template('index.html')

# --- Rota produtos ---
@app.route('/produtos')
@login_required
def produtos(user):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM produtos')
    produtos = cursor.fetchall()
    conn.close()
    return render_template('produtos.html', produtos=produtos, user=user)

# --- Rota adicionar produto ---
@app.route('/add_produto', methods=['POST'])
@login_required
def add_produto(user):
    nome = request.form['nome']
    categoria = request.form['categoria']
    preco_str = request.form['preco']
    estoque_str = request.form['estoque']

    if not nome or not preco_str or not estoque_str:
        return "Preencha todos os campos obrigatórios (nome, preço, estoque)!", 400

    try:
        preco = float(preco_str)
        estoque = int(estoque_str)
    except ValueError:
        return "Erro: Preço ou estoque inválido!", 400

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO produtos (nome, categoria, preco, estoque) VALUES (?, ?, ?, ?)',
                   (nome, categoria, preco, estoque))
    conn.commit()
    conn.close()
    return redirect('/produtos')

# --- Rota movimentar produto ---
@app.route('/movimentar/<int:produto_id>', methods=['GET', 'POST'])
@login_required
def movimentar(produto_id, user):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    if request.method == 'POST':
        tipo = request.form['tipo']
        quantidade = int(request.form['quantidade'])
        responsavel = request.form.get('responsavel') or user
        data = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        cursor.execute('SELECT estoque FROM produtos WHERE id = ?', (produto_id,))
        atual = cursor.fetchone()[0]
        novo = atual + quantidade if tipo == 'entrada' else atual - quantidade

        cursor.execute('UPDATE produtos SET estoque = ? WHERE id = ?', (novo, produto_id))
        cursor.execute('''
            INSERT INTO movimentacoes (produto_id, tipo, quantidade, data_mov, responsavel)
            VALUES (?, ?, ?, ?, ?)
        ''', (produto_id, tipo, quantidade, data, responsavel))

        conn.commit()
        conn.close()
        return redirect('/produtos')
    else:
        cursor.execute('SELECT * FROM produtos WHERE id = ?', (produto_id,))
        produto = cursor.fetchone()
        conn.close()
        return render_template('movimentar.html', produto=produto, user=user)

# --- Rota relatório ---
@app.route('/relatorio')
@login_required
def relatorio(user):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT m.id, p.nome, m.tipo, m.quantidade, m.data_mov, m.responsavel
        FROM movimentacoes m
        JOIN produtos p ON m.produto_id = p.id
        ORDER BY m.data_mov DESC
    ''')
    movimentacoes = cursor.fetchall()
    conn.close()

    return render_template('relatorio.html', movimentacoes=movimentacoes, user=user)

# --- Rota editar movimentação ---
@app.route('/editar_movimentacao/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_movimentacao(id, user):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    if request.method == 'POST':
        tipo = request.form['tipo']
        quantidade = int(request.form['quantidade'])
        responsavel = request.form['responsavel']

        cursor.execute('SELECT produto_id, quantidade, tipo FROM movimentacoes WHERE id = ?', (id,))
        mov = cursor.fetchone()
        produto_id = mov[0]
        quantidade_antiga = mov[1]
        tipo_antigo = mov[2]

        cursor.execute('''
            UPDATE movimentacoes 
            SET tipo = ?, quantidade = ?, responsavel = ?
            WHERE id = ?
        ''', (tipo, quantidade, responsavel, id))

        cursor.execute('SELECT estoque FROM produtos WHERE id = ?', (produto_id,))
        estoque_atual = cursor.fetchone()[0]

        if tipo_antigo == 'entrada':
            estoque_atual -= quantidade_antiga
        else:
            estoque_atual += quantidade_antiga

        if tipo == 'entrada':
            estoque_atual += quantidade
        else:
            estoque_atual -= quantidade

        cursor.execute('UPDATE produtos SET estoque = ? WHERE id = ?', (estoque_atual, produto_id))

        conn.commit()
        conn.close()
        return redirect('/relatorio')

    else:
        cursor.execute('''
            SELECT m.id, m.tipo, m.quantidade, m.responsavel, p.nome
            FROM movimentacoes m
            JOIN produtos p ON m.produto_id = p.id
            WHERE m.id = ?
        ''', (id,))
        movimentacao = cursor.fetchone()
        conn.close()
        if not movimentacao:
            return "Movimentação não encontrada", 404
        return render_template('editar_movimentacao.html', movimentacao=movimentacao, user=user)

# --- Rota para cadastrar novos usuários (só admin) ---
@app.route('/cadastro', methods=['GET', 'POST'])
@admin_required
def cadastro(user):
    if request.method == 'POST':
        username = request.form['username']
        senha = request.form['senha']
        senha_conf = request.form['senha_conf']

        if not username or not senha or not senha_conf:
            return render_template('cadastro.html', erro='Preencha todos os campos', user=user)

        if senha != senha_conf:
            return render_template('cadastro.html', erro='Senhas não conferem', user=user)

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        try:
            cursor.execute('INSERT INTO usuarios (username, senha) VALUES (?, ?)', (username, senha))
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            return render_template('cadastro.html', erro='Usuário já existe', user=user)
        conn.close()
        return redirect('/produtos')

    return render_template('cadastro.html', user=user)

# --- Rota relatório PDF ---
@app.route('/relatorio_pdf')
@login_required
def relatorio_pdf(user):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT m.id, p.nome, m.tipo, m.quantidade, m.data_mov, m.responsavel
        FROM movimentacoes m
        JOIN produtos p ON m.produto_id = p.id
        ORDER BY m.data_mov DESC
    ''')
    movimentacoes = cursor.fetchall()
    conn.close()

    rendered = render_template('relatorio.html', movimentacoes=movimentacoes, user=user)
    return rendered

if __name__ == '__main__':
    init_db()
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
