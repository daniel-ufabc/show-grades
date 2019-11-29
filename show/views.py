# -*- coding: utf-8 -*-
from flask import Flask, Response, request, abort, \
    render_template, redirect, jsonify
import csv
import os
import getpass
from flask_bootstrap import Bootstrap
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from jinja2 import Environment, BaseLoader


app = Flask(__name__, template_folder='/var/www/show/templates',
            static_folder='/var/www/show/static')
Bootstrap(app)

with open('sgapikey') as f:
    app.config['SENDGRID_API_KEY'] = f.read().strip()    

venues = ['p1', 'p2']

@app.template_filter('sc2nl')
def semicolon2br(value):
    return value.replace(';', '\n')


def search_csv(key, key_column_index, filename, visit_header=None, visit=None):
    if not os.path.exists(filename):
        return
    
    key = str(key).strip()
    with open (filename, 'r', encoding='utf-8') as csvfile:
        rows = csv.reader(csvfile)
        if visit_header:
            header = next(rows)
            if callable(visit_header):
                visit_header(header)
        for row in rows:
            this_key = str(row[key_column_index]).strip()
            if this_key == key:
                if visit:
                    visit(row)
                else:
                    return row

                
def authorize(ra, turma, code):
    authorized = False
    def check_code(row):
        nonlocal authorized
        if row[5].strip() == code:
            authorized = True
        
    for venue in venues:
        filename = '/var/www/html/up/files/' + venue + '/' + turma + '/index.csv'
        search_csv(ra, 3, filename, visit=check_code)
        if authorized:
            break

    return authorized


def get_all_codes(ra, turma, obj=None):
    codes = []
    for venue in venues:
        
        def grab_code(row):
            if not obj or venue == obj:
                codes.append((row[5].strip(), row[-1][-3:].lower(), row[0].strip()))
                
        filename = '/var/www/html/up/files/' + venue + '/' + turma + '/index.csv'
        
        search_csv(ra, 3, filename, visit=grab_code)

    return codes


def lookup(ra, turma):
    ra = str(ra).strip()

    header = list()
    def visit_header(row):
        nonlocal header
        header = row

    row = search_csv(ra, 4, 'notas.csv', visit_header=visit_header)
    if row:
        row_dict = {header[i]: value for i, value in enumerate(row)}
        return row_dict
 
    return None


@app.route('/bcc')
def index():
    return render_template('index.html')


@app.route('/bcc/choose', methods=['POST'])
def choose():
    try:
        ra = str(int(request.form['ra']))
    except ValueError:
        return 'O RA deve conter apenas dígitos... ', 400

    turma = str(request.form['turma']).strip().lower()[:3]
    code = str(request.form['code'].strip())

    if not authorize(ra, turma, code):
        return 'Código de submissão, turma, ou RA não batem.', 404

    objs = []
    for obj in venues:
        codes = get_all_codes(ra, turma, obj)
        if codes:
            objs.append((obj, codes[0][0]))

    row_dict = lookup(ra, turma)
    return render_template('choose.html', data=row_dict, ra=ra, turma=turma, objs=objs)
            
   
@app.route('/bcc/nota/<obj>', methods=['POST'])
def nota(obj):
    try:
        ra = str(int(request.form['ra']))
    except ValueError:
        return 'O RA deve conter apenas dígitos... ', 400

    if obj not in venues:
        return 'Objeto %s inválido.' % obj, 400
    
    turma = str(request.form['turma']).strip().lower()[:3]
    code = str(request.form['code']).strip()

    if not authorize(ra, turma, code):
        return 'Código de submissão, turma, ou RA não batem.', 404
    
    codes = get_all_codes(ra, turma, obj)
    row_dict = lookup(ra, turma)
    return render_template(obj + '.html', data=row_dict, turma=turma, codes=codes, obj=obj)
                              
    
@app.route('/bcc/info/<ra>')
def get_info(ra):
    try:
        ra = str(int(ra))
    except:
        return 'O RA deve conter apenas dígitos.', 400

    row = search_csv(ra, 4, 'notas.csv', visit_header=True)
    if row:
        return jsonify(ra=ra, nome=row[5].strip(), turma=row[2][:3])
        
    return 'RA não encontrado.', 404


@app.route('/status')
def status():
    txt = 'cdir: ' + os.getcwd()
    txt += '\n'
    txt += 'user: ' + getpass.getuser()
    return Response(txt, mimetype="text/plain")


def hide(string):
    answer = list(string)
    n = len(answer)
    for i in range(2, 3 * n // 4):
        answer[i] = '.'
    return ''.join(answer)


def redact(email):
    i = email.find('@')
    if i < 0:
        return 'um email inválido. Por favor mande mensagem ao professor.'
    return hide(email[:i]) + email[i:]
        
    
@app.route('/bcc/forgotcode', methods=['GET', 'POST'])
def forgot_code():
    if request.method == 'GET':
        return render_template('forgot.html')

    try:
        ra = str(int(request.form['ra']))
    except:
        return 'O RA deve conter apenas dígitos.', 400

    turma = str(request.form['turma']).lower().strip()[:3]
    
    objs = []
    for obj in venues:
        codes = get_all_codes(ra, turma, obj)
        if codes:
            objs.append((obj, [code[0] for code in codes]))

    row = search_csv(ra, 4, 'notas.csv', visit_header=True)
    if not row:
        return 'Nenhum e-mail foi encontrado para o RA ' + str(ra), 404
    
    email = row[0]

    msg_template = '''
Os códigos (se houver) estão listados abaixo.

<ul>
{% for obj, codes in objs %}
<li><b>{{ obj }}</b>: {% for code in codes %}({{ code }}){% endfor %}</li>
{% endfor %}
</ul>

Cada código está delimitado por parênteses, mas os parênteses não fazem parte do código.
'''

    jinja2_template = Environment(loader=BaseLoader()).from_string(msg_template)
    msg = jinja2_template.render(objs=objs)

    if not [code for code in codes for obj, codes in objs]:
        msg = 'Nenhum código de submissão foi encontrado.'
        
    # using SendGrid's Python Library
    # https://github.com/sendgrid/sendgrid-python
    message = Mail(
        from_email='curso.bcc.ufabc@gmail.com',
        to_emails=email,
        subject='Código(s) de submissão',
        html_content=msg)
    try:
        sg = SendGridAPIClient(app.config['SENDGRID_API_KEY'])
        response = sg.send(message)
        print(response.status_code)
        print(response.body)
        print(response.headers)
    except Exception as e:
        print(e.message)

    return 'Se existe(m) código(s) cadastrado(s), ele(s) pode(m) ser visto(s) na mensagem enviada para ' + redact(email) + ' [Se você não recebeu o e-mail, por favor, verifique a pasta de SPAM.]', 200
    

"""
def get_row(RA, submission_code, turma=''):
    turma = turma[:3] if turma else '.'
    with open ('/var/www/html/up/files/' + turma + '/index.csv', 'r', encoding='utf-8') as csvfile:
        reader = csv.reader(csvfile, delimiter = ',', quotechar = '"')
        for row in reader:
            # t, ip, name, ra, turma, code, succ, blocks, basename = row
            if str(row[3]).strip() == str(RA).strip() and str(row[5]).strip() == str(submission_code).strip():
                return row
            
    return None


@app.route('/download', methods=['GET'])
def download():
    RA = request.args['RA']
    code = request.args['code']
    turma = request.args['turma'].lower()[:3]
    row = get_row(RA, code, turma)
    return redirect('http://177.104.60.13/up/files/' + turma + '/' + row[-1])
"""


"""
@app.route('/final/<ra>')
def media_final(ra):
    with open('finais-pre-rec.csv', encoding='utf-8') as f:
        rows = csv.reader(f)
        headers = next(rows)
        for row in rows:
            if row[0].strip() == ra.strip():
                response = '<pre>\n'
                for i, header in enumerate(headers):
                    response += header.rjust(20) + ': ' + row[i] + '\n'
                response += '</pre>\n'
                response += '''
<p>Lembre-se de que a média de provas é ponderada: 40% P1 + 60% P2.</p>
'''
                return response, 200
        return 'RA não encontrado.', 400


@app.route('/conceito/<ra>')
def conceito(ra):
    ra = ra.strip()
    with open('pi-final.csv', encoding='utf-8') as f:
        rows = csv.reader(f)
        headers = next(rows)
        for row in rows:
            if str(row[0]).strip() == ra:
                response = '<pre>\n'
                for i, header in enumerate(headers):
                    response += header.rjust(30) + ': ' + row[i] + '\n'

                return response, 200
        return 'RA não encontrado.', 400
"""
