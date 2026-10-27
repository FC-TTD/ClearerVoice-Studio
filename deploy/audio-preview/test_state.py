"""CPU-only protocol/recovery tests; never counted as native inference evidence."""
import os,tempfile,json,io
from pathlib import Path
with tempfile.TemporaryDirectory() as folder:
 os.environ['AUDIO_DATA']=folder
 from audio_api import app as api
 from audio_api.common import DATA,write
 from fastapi.testclient import TestClient
 model='cv:MossFormer2_SS_16K'
 api.model_status=lambda:[dict(id=model,available=True,stems=[dict(id='Speaker1'),dict(id='Speaker2')])]
 api.INPUTS=Path(folder)/'inputs';asset='a'*32;source=api.INPUTS/asset/'input.audio';source.parent.mkdir(parents=True);source.write_bytes(b'x'*64)
 original=api.urllib.request.urlopen
 api.urllib.request.urlopen=lambda *args,**kwargs:io.BytesIO(json.dumps(dict(input_asset_id=asset,filename='输入.wav',input_duration=1.0)).encode())
 def create(client,stems='["Speaker1","Speaker2"]'):
  return client.post('/api/speech/batches',params=dict(model=model,stems=stems,purpose='speakers'))
 with TestClient(api.app) as client:
  assert create(client,'[]').status_code==400
  assert create(client,'not-json').status_code==400
  assert client.post('/api/speech/batches',params=dict(model='bad',stems='[]',purpose='speakers')).status_code==409
  batch=create(client).json();identity=batch['id'];assert identity.startswith('cv-')
  assert client.post('/api/speech/batches/'+identity+'/start').status_code==400
  assert client.post('/api/speech/batches/'+identity+'/reuse',params=dict(asset_id='../bad')).status_code==404
  for i in range(20):assert client.post('/api/speech/batches/'+identity+'/reuse',params=dict(asset_id=asset)).status_code==201
  assert client.post('/api/speech/batches/'+identity+'/reuse',params=dict(asset_id=asset)).status_code==413
  saved=client.get('/api/speech/batches/'+identity).json();assert len(saved['jobs'])==20 and saved['uploaded_bytes']==0 and saved['reused_files']==20
  assert all(j['input_asset_id']==asset and 'input' not in j for j in saved['jobs'])
  assert not any((DATA/'jobs').glob('*/input.audio'))
  assert client.post('/api/speech/exports',content=b'bad').status_code==400
  assert client.post('/api/speech/exports',content=b'x'*65537).status_code==413
  assert client.post('/api/speech/exports',json={'tracks':[{'job_id':'../bad','stem':'Speaker1'}]}).status_code==404
  path,b=api.load('batches',identity);b['status']='running';write(path,b)
  jp,j=api.load('jobs',b['jobs'][0]);j['status']='running';write(jp,j)
  successp,success=api.load('jobs',b['jobs'][1]);success['status']='succeeded';write(successp,success)
  api.recover();assert api.load('batches',identity)[1]['status']=='interrupted';assert api.load('jobs',b['jobs'][0])[1]['status']=='failed';assert api.load('jobs',b['jobs'][1])[1]['status']=='succeeded'
 api.urllib.request.urlopen=original
 print(json.dumps(dict(cpu_protocol='PASS',limits='20 inputs enforced',reuse='canonical input reference without copies',recovery='incomplete interrupted; success retained',model_inference='NOT_THIS_TEST')))
