import os
import psycopg2
from flask import Flask, render_template, request, redirect, make_response, url_for, session, send_file
from datetime import datetime
from functools import wraps

# Use DATABASE_URL do Render
DATABASE_URL = os.environ.get('DATABASE_URL') or 'postgresql://stoneberry_user:Wt71F648f1uEgsdEin0ZP3NjNiHykQCa@dpg-d15i2pm3jp1c73fu5m20-a.oregon-postgres.render.com/stoneberry'

app = Flask(__name__)

def connect_db():
    return psycopg2.connect(DATABASE_URL)

def cria_tabela_usuarios(conn):
    with conn.cursor() as cursor:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS usuarios (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                senha TEXT NOT NULL
            )
        ''')
        conn.commit()

def cria_tabela_produtos(conn):
    with conn.cursor() as cursor:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS produtos (
                id SERIAL PRIMARY KEY,
                nome TEXT NOT NULL,
                categoria TEXT,
                preco REAL,
                estoque INTEGER DEFAULT 0
            )
        ''')
        conn.commit()

def cria_tabela_movimentacoes(conn):
    with conn.cursor() as cursor:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS movimentacoes (
                id SERIAL PRIMARY KEY,
                produto_id INTEGER NOT NULL,
                tipo TEXT NOT NULL CHECK(tipo IN ('entrada', 'saida')),
                quantidade INTEGER NOT NULL,
                data_mov TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                responsavel TEXT,
                FOREIGN KEY(produto_id) REFERENCES produtos(id)
            )
        ''')
        conn.commit()

def init_db():
    conn = connect_db()
    cria_tabela_usuarios(conn)
    cria_tabela_produtos(conn)
    cria_tabela_movimentacoes(conn)

    # Cria admin se não existir
    with conn.cursor() as cursor:
        cursor.execute("SELECT * FROM usuarios WHERE username = 'admin'")
        if not cursor.fetchone():
            cursor.execute("INSERT INTO usuarios (username, senha) VALUES (%s, %s)", ('admin', 'admin123'))
            print("Usuário admin criado com senha 'admin123'")
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def index():
    return redirect('/login')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        senha = request.form['senha']
        conn = connect_db()
        cursor = conn.cursor()
        cursor.execute('SELECT senha FROM usuarios WHERE username = %s', (username,))
        resultado = cursor.fetchone()
        conn.close()

        if resultado and resultado[0] == senha:
            resp = make_response(redirect('/produtos'))
            resp.set_cookie('user', username)
            return resp
        else:
            return render_template('login.html', erro="Usuário ou senha incorretos")
    return render_template('index.html')

@app.route('/logout')
def logout():
    resp = make_response(redirect('/login'))
    resp.delete_cookie('user')
    return resp

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
    conn = connect_db()
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
        return "Preencha todos os campos obrigatórios!", 400

    try:
        preco = float(preco_str)
        estoque = int(estoque_str)
    except ValueError:
        return "Erro: Preço ou estoque inválido!", 400

    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO produtos (nome, categoria, preco, estoque) VALUES (%s, %s, %s, %s)',
                   (nome, categoria, preco, estoque))
    conn.commit()
    conn.close()
    return redirect('/produtos')

@app.route('/movimentar/<int:produto_id>', methods=['GET', 'POST'])
@login_required
def movimentar(produto_id, user):
    conn = connect_db()
    cursor = conn.cursor()

    if request.method == 'POST':
        tipo = request.form['tipo']
        quantidade = int(request.form['quantidade'])
        responsavel = request.form.get('responsavel') or user
        data = datetime.now()

        cursor.execute('SELECT estoque FROM produtos WHERE id = %s', (produto_id,))
        atual = cursor.fetchone()[0]
        novo = atual + quantidade if tipo == 'entrada' else atual - quantidade

        cursor.execute('UPDATE produtos SET estoque = %s WHERE id = %s', (novo, produto_id))
        cursor.execute('''
            INSERT INTO movimentacoes (produto_id, tipo, quantidade, data_mov, responsavel)
            VALUES (%s, %s, %s, %s, %s)
        ''', (produto_id, tipo, quantidade, data, responsavel))

        conn.commit()
        conn.close()
        return redirect('/produtos')

    else:
        cursor.execute('SELECT * FROM produtos WHERE id = %s', (produto_id,))
        produto = cursor.fetchone()
        conn.close()
        if not produto:
            return "Produto não encontrado", 404
        return render_template('movimentar.html', produto=produto, user=user)

@app.route('/relatorio')
@login_required
def relatorio(user):
    conn = connect_db()
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
@login_required
def alterar_senha(user):
    erro = None
    if request.method == 'POST':
        senha_atual = request.form.get('senha_atual')
        nova_senha = request.form.get('nova_senha')
        confirmar_senha = request.form.get('confirmar_senha')

        if not senha_atual or not nova_senha or not confirmar_senha:
            erro = 'Preencha todos os campos.'
        else:
            conn = connect_db()
            cursor = conn.cursor()
            cursor.execute("SELECT senha FROM usuarios WHERE username = %s", (user,))
            resultado = cursor.fetchone()

            if not resultado:
                erro = 'Usuário não encontrado.'
            elif resultado[0] != senha_atual:
                erro = 'Senha atual incorreta.'
            elif nova_senha != confirmar_senha:
                erro = 'As senhas não coincidem.'
            else:
                cursor.execute("UPDATE usuarios SET senha = %s WHERE username = %s", (nova_senha, user))
                conn.commit()
                conn.close()
                return redirect(url_for('logout'))

            conn.close()
    return render_template('alterar_senha.html', erro=erro, user=user)

@app.route('/editar_movimentacao/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_movimentacao(id, user):
    conn = connect_db()
    cursor = conn.cursor()

    if request.method == 'POST':
        tipo = request.form['tipo']
        quantidade = int(request.form['quantidade'])
        responsavel = request.form['responsavel']

        cursor.execute('SELECT produto_id, quantidade, tipo FROM movimentacoes WHERE id = %s', (id,))
        mov = cursor.fetchone()
        if not mov:
            conn.close()
            return "Movimentação não encontrada", 404

        produto_id, quantidade_antiga, tipo_antigo = mov

        cursor.execute('SELECT estoque FROM produtos WHERE id = %s', (produto_id,))
        estoque_atual = cursor.fetchone()[0]

        if tipo_antigo == 'entrada':
            estoque_atual -= quantidade_antiga
        else:
            estoque_atual += quantidade_antiga

        if tipo == 'entrada':
            estoque_atual += quantidade
        else:
            estoque_atual -= quantidade

        cursor.execute('UPDATE movimentacoes SET tipo = %s, quantidade = %s, responsavel = %s WHERE id = %s',
                       (tipo, quantidade, responsavel, id))
        cursor.execute('UPDATE produtos SET estoque = %s WHERE id = %s', (estoque_atual, produto_id))

        conn.commit()
        conn.close()
        return redirect('/relatorio')

    else:
        cursor.execute('''
            SELECT m.id, m.tipo, m.quantidade, m.responsavel, p.nome
            FROM movimentacoes m
            JOIN produtos p ON m.produto_id = p.id
            WHERE m.id = %s
        ''', (id,))
        movimentacao = cursor.fetchone()
        conn.close()
        if not movimentacao:
            return "Movimentação não encontrada", 404
        return render_template('editar_movimentacao.html', movimentacao=movimentacao, user=user)

@app.route('/api/movimentacoes')
@login_required
def api_movimentacoes(user):
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT m.id, p.nome, m.tipo, m.quantidade, m.data_mov, m.responsavel
        FROM movimentacoes m
        JOIN produtos p ON m.produto_id = p.id
        ORDER BY m.data_mov DESC
    ''')
    rows = cursor.fetchall()
    conn.close()
    result = [{
        'id': r[0], 'produto': r[1], 'tipo': r[2],
        'quantidade': r[3], 'data_mov': r[4], 'responsavel': r[5]
    } for r in rows]
    return {'movimentacoes': result}

@app.route('/cadastro', methods=['GET', 'POST'])
@admin_required
def cadastro(user):
    if request.method == 'POST':
        username = request.form['username']
        senha = request.form['senha']
        senha_confirma = request.form['senha_confirma']
        if senha != senha_confirma:
            return render_template('cadastro.html', erro='As senhas não coincidem', user=user)
        conn = connect_db()
        cursor = conn.cursor()
        try:
            cursor.execute('INSERT INTO usuarios (username, senha) VALUES (%s, %s)', (username, senha))
            conn.commit()
            conn.close()
            return redirect('/login')
        except:
            conn.close()
            return render_template('cadastro.html', erro='Usuário já existe', user=user)
    return render_template('cadastro.html', user=user)

if __name__ == '__main__':
    app.run(debug=True)
