import json, sqlite3, threading, uuid, time
from pathlib import Path
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
ROOT=Path(__file__).parent
class Loja:
 def __init__(self,arquivo):
  self.db=sqlite3.connect(arquivo,check_same_thread=False); self.db.row_factory=sqlite3.Row; self.lock=threading.RLock(); self.reset()
 def reset(self):
  with self.lock:
   self.db.executescript('DROP TABLE IF EXISTS pedidos; DROP TABLE IF EXISTS produtos; DROP TABLE IF EXISTS auditoria; CREATE TABLE produtos(id INTEGER, unidade TEXT, nome TEXT, preco INTEGER, estoque INTEGER, PRIMARY KEY(id,unidade)); CREATE TABLE pedidos(id TEXT PRIMARY KEY, chave TEXT UNIQUE, cliente TEXT, unidade TEXT, total INTEGER, estado TEXT, itens TEXT, modo TEXT, promo INTEGER); CREATE TABLE auditoria(instante TEXT, pedido TEXT, unidade TEXT, acao TEXT);')
   for u in ['A','B']:
    self.db.executemany('INSERT INTO produtos VALUES(?,?,?,?,?)',[(1,u,'Cuscuz com queijo',1200 if u=='A' else 1300,20),(2,u,'Tapioca de frango',1800,10 if u=='A' else 0),(3,u,'Café coado',500,30),(4,u,'Bolo de macaxeira',900,1)])
   self.db.commit()
 def log(self,p,u,a): self.db.execute('INSERT INTO auditoria VALUES(?,?,?,?)',(time.strftime('%Y-%m-%dT%H:%M:%S'),p,u,a))
 def catalogo(self,u): return [dict(r) for r in self.db.execute('SELECT * FROM produtos WHERE unidade=?',(u,))]
 def pedido(self,i,c):
  r=self.db.execute('SELECT * FROM pedidos WHERE id=?',(i,)).fetchone()
  if not r or r['cliente']!=c: raise ValueError('Acesso negado ao pedido.')
  d=dict(r); d['itens']=json.loads(d['itens']); return d
 def comprar(self,d):
  with self.lock:
   c=d.get('cliente'); u=d.get('unidade'); chave=d.get('chave'); modo=d.get('modo')
   if c not in ['cliente1','cliente2'] or u not in ['A','B'] or not chave: raise ValueError('Dados de identificação inválidos.')
   r=self.db.execute('SELECT id,cliente FROM pedidos WHERE chave=?',(chave,)).fetchone()
   if r:
    if r['cliente']!=c: raise ValueError('Chave já utilizada.')
    return self.pedido(r['id'],c)
   if modo not in ['aprovado','recusado','pendente','divergente']: raise ValueError('Pagamento inválido.')
   itens=d.get('itens',[])
   if not itens: raise ValueError('Inclua pelo menos um produto.')
   total=0; vistos=set(); normal=[]
   for item in itens:
    i=item.get('id'); q=item.get('qtd')
    if type(q)!=int or q<=0 or i in vistos: raise ValueError('Quantidade ou item inválido.')
    vistos.add(i); r=self.db.execute('SELECT * FROM produtos WHERE id=? AND unidade=?',(i,u)).fetchone()
    if not r or q>r['estoque']: raise ValueError('Produto indisponível na unidade selecionada.')
    total+=q*r['preco']; normal.append({'id':i,'qtd':q})
   cupom=d.get('cupom','').strip().upper()
   if cupom and cupom!='RAIZES10': raise ValueError('Cupom inválido ou vencido.')
   if cupom: total=(total*90+50)//100
   p=uuid.uuid4().hex[:12].upper()
   try:
    for item in normal: self.db.execute('UPDATE produtos SET estoque=estoque-? WHERE id=? AND unidade=?',(item['qtd'],item['id'],u))
    self.db.execute('INSERT INTO pedidos VALUES(?,?,?,?,?,?,?,?,?)',(p,chave,c,u,total,'pendente',json.dumps(normal),modo,int(bool(d.get('promo')))))
    self.log(p,u,'pedido reservado; pagamento solicitado')
    self.db.commit()
    if modo!='pendente': self.resolver(p,c,modo)
    return self.pedido(p,c)
   except Exception: self.db.rollback(); raise
 def resolver(self,p,c,resultado):
  with self.lock:
   d=self.pedido(p,c)
   if d['estado']!='pendente': return d
   if resultado not in ['aprovado','recusado','divergente']: raise ValueError('Resultado inválido.')
   if resultado=='divergente': self.log(p,d['unidade'],'resposta divergente bloqueada'); self.db.commit(); return d
   if resultado=='recusado':
    for item in d['itens']: self.db.execute('UPDATE produtos SET estoque=estoque+? WHERE id=? AND unidade=?',(item['qtd'],item['id'],d['unidade']))
   self.db.execute('UPDATE pedidos SET estado=? WHERE id=?',('em preparo' if resultado=='aprovado' else 'recusado',p)); self.log(p,d['unidade'],'pagamento '+resultado); self.db.commit(); return self.pedido(p,c)
 def avancar(self,p,c):
  with self.lock:
   d=self.pedido(p,c); proximo={'em preparo':'pronto','pronto':'entregue'}.get(d['estado'])
   if not proximo: raise ValueError('Mudança de situação não autorizada.')
   self.db.execute('UPDATE pedidos SET estado=? WHERE id=?',(proximo,p)); self.log(p,d['unidade'],proximo); self.db.commit(); return self.pedido(p,c)
 def registros(self): return [dict(r) for r in self.db.execute('SELECT * FROM auditoria ORDER BY rowid DESC')]
class Handler(SimpleHTTPRequestHandler):
 def __init__(self,*a,**k): super().__init__(*a,directory=str(ROOT/'web'),**k)
 def resposta(self,d,status=200):
  b=json.dumps(d,ensure_ascii=False).encode(); self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(b)
 def do_GET(self):
  from urllib.parse import urlparse,parse_qs
  url=urlparse(self.path); q=parse_qs(url.query)
  try:
   if url.path=='/api/catalogo': return self.resposta(loja.catalogo(q.get('unidade',['A'])[0]))
   if url.path=='/api/registros': return self.resposta(loja.registros())
   if url.path=='/api/pedido': return self.resposta(loja.pedido(q['id'][0],q['cliente'][0]))
   super().do_GET()
  except (ValueError,KeyError) as e: self.resposta({'erro':str(e)},400)
 def do_POST(self):
  try:
   d=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))))
   if self.path=='/api/comprar': r=loja.comprar(d)
   elif self.path=='/api/resolver': r=loja.resolver(d['id'],d['cliente'],d['resultado'])
   elif self.path=='/api/avancar': r=loja.avancar(d['id'],d['cliente'])
   elif self.path=='/api/reset': loja.reset(); r={'ok':True}
   else: raise ValueError('Operação inexistente.')
   self.resposta(r)
  except (ValueError,KeyError,TypeError) as e: self.resposta({'erro':str(e)},400)
if __name__=='__main__':
 loja=Loja(ROOT/'dados.sqlite'); print('Abra http://localhost:8000 — Ctrl+C para encerrar. Dados reiniciados a cada execução.'); ThreadingHTTPServer(('127.0.0.1',8000),Handler).serve_forever()
