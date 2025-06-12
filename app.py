import os
import sqlite3
from flask import Flask, render_template, request, redirect, make_response, url_for, session
from datetime import datetime
import tempfile

app = Flask(__name__)

# Caminho do banco na pasta temporária (Render permite gravação aqui)
DB_PATH = os.path.join(tempfile.gettempdir(), 'estoque.db')

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

def cria_tabela_produtos():
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
    # Cria todas as tabelas
    cria_tabela_usuarios()
    cria_tabela_produtos()
    cria_tabela_movimentacoes()

    # Insere usuário admin padrão se não existir
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE username = 'admin'")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO usuarios (username, senha) VALUES (?, ?)", ('admin', 'admin123'))
        print("Usuário admin criado com senha 'admin123'")
    conn.commit()
    conn.close()

# Chama init_db ao iniciar a aplicação (garante criação do banco/tabelas)
init_db()

# --- Rotas ---

@app.route('/')
def index():
    return redirect('/login')

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

@app.route('/logout')
def logout():
    resp = make_response(redirect('/login'))
    resp.delete_cookie('user')
    return resp

from functools import wraps

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = request.cookies.get('user')
        if not user:
            return redirect('/login')
        return f(*args, **kwargs, user=user)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = request.cookies.get('user')
        if user != 'admin':
            return redirect('/login')
        return f(*args, **kwargs, user=user)
    return decorated

@app.route('/produtos')
@login_required
def produtos(user):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM produtos')
    produtos = cursor.fetchall()
    conn.close()
    return render_template('produtos.html', produtos=produtos, user=user)

@app.route('/add_produto', methods=['POST'])
@login_required
def add_produto(user):
    nome = request.form['nome']
    categoria = request.form.get('categoria', '')
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
        if not produto:
            return "Produto não encontrado", 404
        return render_template('movimentar.html', produto=produto, user=user)

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

@app.route('/alterar_senha', methods=['GET', 'POST'])
def alterar_senha():
    erro = None

    if request.method == 'POST':
        username = session.get('usuario')
        if not username:
            return redirect(url_for('login'))

        senha_atual = request.form.get('senha_atual')
        nova_senha = request.form.get('nova_senha')
        confirmar_senha = request.form.get('confirmar_senha')

        # Verifica se algum campo está vazio
        if not senha_atual or not nova_senha or not confirmar_senha:
            erro = 'Por favor, preencha todos os campos.'
            return render_template('alterar_senha.html', erro=erro)

        conn = sqlite3.connect('banco.db')
        c = conn.cursor()
        c.execute("SELECT senha FROM usuarios WHERE username=?", (username,))
        user = c.fetchone()

        if not user:
            erro = 'Usuário não encontrado.'
        elif user[0] != senha_atual:
            erro = 'Senha atual incorreta.'
        elif nova_senha != confirmar_senha:
            erro = 'As senhas novas não coincidem.'
        else:
            c.execute("UPDATE usuarios SET senha=? WHERE username=?", (nova_senha, username))
            conn.commit()
            conn.close()
            return redirect(url_for('login'))

        conn.close()
        return render_template('alterar_senha.html', erro=erro)

    return render_template('alterar_senha.html')


@app.route('/editar_movimentacao/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_movimentacao(id, user):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    if request.method == 'POST':
        tipo = request.form['tipo']
        quantidade = int(request.form['quantidade'])
        responsavel = request.form['responsavel']

        # Pega dados antigos para ajustar estoque
        cursor.execute('SELECT produto_id, quantidade, tipo FROM movimentacoes WHERE id = ?', (id,))
        mov = cursor.fetchone()
        if not mov:
            conn.close()
            return "Movimentação não encontrada", 404
        produto_id = mov[0]
        quantidade_antiga = mov[1]
        tipo_antigo = mov[2]

        # Atualiza movimentação
        cursor.execute('''
            UPDATE movimentacoes 
            SET tipo = ?, quantidade = ?, responsavel = ?
            WHERE id = ?
        ''', (tipo, quantidade, responsavel, id))

        # Ajusta estoque
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
    
@app.route('/api/movimentacoes')
@login_required
def api_movimentacoes(user):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT m.id, p.nome, m.tipo, m.quantidade, m.data_mov, m.responsavel
        FROM movimentacoes m
        JOIN produtos p ON m.produto_id = p.id
        ORDER BY m.data_mov DESC
    ''')
    rows = cursor.fetchall()
    conn.close()

    # Converte para lista de dicts
    result = []
    for r in rows:
        result.append({
            'id': r[0],
            'produto': r[1],
            'tipo': r[2],
            'quantidade': r[3],
            'data_mov': r[4],
            'responsavel': r[5]
        })
    return {'movimentacoes': result}

from flask import send_file

@app.route('/download_db')
@admin_required
def download_db(user):
    return send_file(DB_PATH, as_attachment=True, download_name='estoque.db')

@app.route('/cadastro', methods=['GET', 'POST'])
@admin_required
def cadastro(user):
    if request.method == 'POST':
        username = request.form['username']
        senha = request.form['senha']
        senha_confirma = request.form['senha_confirma']

        if senha != senha_confirma:
            return render_template('cadastro.html', erro='As senhas não coincidem', user=user)

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        try:
            cursor.execute('INSERT INTO usuarios (username, senha) VALUES (?, ?)', (username, senha))
            conn.commit()
            conn.close()
            return redirect('/login')
        except sqlite3.IntegrityError:
            conn.close()
            return render_template('cadastro.html', erro='Usuário já existe', user=user)

    return render_template('cadastro.html', user=user)

if __name__ == '__main__':
    # No Render, normalmente você não executa app.run, mas para testes locais:
    app.run(host='0.0.0.0', port=5000, debug=True)
