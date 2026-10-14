import unittest,json,time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from servidor import Loja
class Testes(unittest.TestCase):
 def setUp(self): self.l=Loja(':memory:')
 def tearDown(self): self.l.db.close()
 def dados(self,**kw):
  d=dict(cliente='cliente1',unidade='A',chave='compra1',itens=[{'id':1,'qtd':2}],modo='aprovado');d.update(kw);return d
 def test_total(self): self.assertEqual(self.l.comprar(self.dados())['total'],2400)
 def test_desconto(self): self.assertEqual(self.l.comprar(self.dados(cupom='RAIZES10'))['total'],2160)
 def test_cupom_invalido(self):
  with self.assertRaises(ValueError):self.l.comprar(self.dados(cupom='VENCIDO'))
 def test_quantidade_invalida(self):
  with self.assertRaises(ValueError):self.l.comprar(self.dados(itens=[{'id':1,'qtd':-1}]))
 def test_esgotado(self):
  with self.assertRaises(ValueError):self.l.comprar(self.dados(unidade='B',itens=[{'id':2,'qtd':1}]))
 def test_repeticao(self):
  ps=[self.l.comprar(self.dados()) for _ in range(10)]
  self.assertEqual(len({p['id']for p in ps}),1);self.assertEqual(self.l.catalogo('A')[0]['estoque'],18);self.assertEqual(len(self.l.registros()),2)
 def test_ultima_unidade(self):
  def compra(i):
   try:return self.l.comprar(self.dados(chave=str(i),itens=[{'id':4,'qtd':1}]))
   except ValueError:return None
  with ThreadPoolExecutor(2)as ex:r=list(ex.map(compra,range(2)))
  self.assertEqual(sum(x is not None for x in r),1);self.assertEqual(self.l.catalogo('A')[3]['estoque'],0)
 def test_recusa_libera(self):
  p=self.l.comprar(self.dados(modo='recusado'));self.assertEqual(p['estado'],'recusado');self.assertEqual(self.l.catalogo('A')[0]['estoque'],20)
 def test_pendente_preserva(self):
  p=self.l.comprar(self.dados(modo='pendente'));self.assertEqual(p['estado'],'pendente');self.assertEqual(self.l.catalogo('A')[0]['estoque'],18)
 def test_aprovacao_repetida(self):
  p=self.l.comprar(self.dados(modo='pendente'))
  for _ in range(10):self.l.resolver(p['id'],'cliente1','aprovado')
  self.assertEqual(len(self.l.registros()),2);self.assertEqual(self.l.catalogo('A')[0]['estoque'],18)
 def test_valor_divergente(self): self.assertEqual(self.l.comprar(self.dados(modo='divergente'))['estado'],'pendente')
 def test_cliente_sem_acesso(self):
  p=self.l.comprar(self.dados())
  with self.assertRaises(ValueError):self.l.pedido(p['id'],'cliente2')
 def test_estoque_outra_unidade(self): self.l.comprar(self.dados());self.assertEqual(self.l.catalogo('B')[0]['estoque'],20)
 def test_retirada_unica(self):
  p=self.l.comprar(self.dados());self.l.avancar(p['id'],'cliente1');self.assertEqual(self.l.avancar(p['id'],'cliente1')['estado'],'entregue')
  with self.assertRaises(ValueError):self.l.avancar(p['id'],'cliente1')
 def test_promocao_opcional(self): self.assertEqual(self.l.comprar(self.dados(promo=False))['promo'],0)
 def test_auditoria(self):
  self.l.comprar(self.dados());r=self.l.registros()[0];self.assertTrue(all(r[k] for k in ['instante','pedido','unidade','acao']))
if __name__=='__main__':
 suite=unittest.defaultTestLoader.loadTestsFromTestCase(Testes);r=unittest.TextTestRunner(verbosity=2).run(suite)
 Path('evidencias').mkdir(exist_ok=True);Path('evidencias/resultado_testes.json').write_text(json.dumps({'executado_em':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'tipo':'Testes das regras em Python e SQLite em memória','total':r.testsRun,'falhas':len(r.failures),'erros':len(r.errors),'limites':'Não inclui navegador, carga, segurança de produção ou participantes.'},ensure_ascii=False,indent=2),encoding='utf-8')
 raise SystemExit(not r.wasSuccessful())
