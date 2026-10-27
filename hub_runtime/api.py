"""Isolated ClearVoice preview, consuming immutable PYMSS input assets read-only."""
import asyncio,hashlib,json,math,os,re,shutil,subprocess,sys,time,urllib.request,uuid,zipfile
from ttd_model_runtime.protocol import AdmissionRejected
from pathlib import Path
import numpy as np
import soundfile as sf
from fastapi import FastAPI,HTTPException,Request
from fastapi.responses import FileResponse
from audio_api.common import DATA,SPECS,model_status,valid_id,write
app=FastAPI(title='ClearVoice Audio Preview')
INPUTS=Path('/studio-inputs').resolve();ORIGIN=os.environ.get('STUDIO_ORIGIN','http://192.168.100.18:17896')
for part in ['jobs','batches','exports']:(DATA/part).mkdir(parents=True,exist_ok=True)
active=False
mutation_lock=asyncio.Lock()

def load(kind,identity):
 if not valid_id(identity):raise HTTPException(404,'记录不存在。')
 path=DATA/kind/identity/('job.json' if kind=='jobs' else 'batch.json')
 if not path.is_file():raise HTTPException(404,'记录不存在。')
 return path,json.loads(path.read_text())
def public_job(identity):
 _,job=load('jobs',identity);result={k:v for k,v in job.items() if k not in ['input'] and not k.startswith('_hub_')}
 result['outputs']=[dict(o,url=f'/api/speech/jobs/{identity}/files/{o["file"]}',waveform_url=f'/api/speech/jobs/{identity}/files/{o["file"]}/waveform',bytes=(DATA/'jobs'/identity/o['file']).stat().st_size) for o in job['outputs']]
 return result
def describe(batch):
 jobs=[public_job(j) for j in batch['jobs']]
 return {k:v for k,v in batch.items() if not k.startswith('_hub_')}|dict(jobs=jobs,completed=sum(j['status']=='succeeded' for j in jobs))
def selection(model,stems):
 row=next((m for m in model_status() if m['id']==model),None)
 if not row or not row['available']:raise HTTPException(409,'该模型尚未通过验证，请选择可使用模型。')
 try:values=json.loads(stems)
 except ValueError:raise HTTPException(400,'输出音轨无效。')
 if not isinstance(values,list) or not values or any(s not in [x['id'] for x in row['stems']] for s in values):raise HTTPException(400,'请选择模型支持的输出音轨。')
 return list(dict.fromkeys(values))
@app.on_event('startup')
def recover():
 for kind in ['jobs','batches']:
  for path in (DATA/kind).glob('*/*.json'):
   try:
    state=json.loads(path.read_text())
    if state.get('_hub_actor_id')==os.environ.get('HUB_RUNTIME_ACTOR_ID') and state.get('status') in ['running','queued','waiting']:
     state.update(status='interrupted' if kind=='batches' else 'failed',error='服务重启，已上传音频及完成结果已保留，可继续处理。');write(path,state)
   except (ValueError,OSError):pass
@app.get('/healthz')
def health():return dict(status='ok',busy=active)
@app.get('/api/speech/models')
def models():return dict(models=model_status())
@app.get('/api/speech/batches/{identity}')
def read_batch(identity:str):return describe(load('batches',identity)[1])
@app.get('/api/speech/jobs/{identity}')
def read_job(identity:str):return public_job(identity)
@app.post('/api/speech/batches',status_code=201)
def create(model:str,stems:str,purpose:str):
 selected=selection(model,stems);identity='cv-'+uuid.uuid4().hex
 state=dict(_hub_actor_id=os.environ.get('HUB_RUNTIME_ACTOR_ID'),id=identity,model=model,stems=selected,purpose=purpose,status='preparing',jobs=[],bytes=0,uploaded_bytes=0,reused_files=0,error='')
 write(DATA/'batches'/identity/'batch.json',state);return describe(state)
def reuse_input(identity:str,asset_id:str):
 path,b=load('batches',identity)
 if b['status']!='preparing':raise HTTPException(409,'批次已开始，不能添加输入。')
 if not re.fullmatch(r'[a-f0-9]{32}',asset_id):raise HTTPException(404,'输入音频不存在。')
 try:source=json.load(urllib.request.urlopen(ORIGIN+'/api/studio/jobs/'+asset_id,timeout=15))
 except Exception:raise HTTPException(503,'暂时无法读取已上传音频，请稍后重试，无需重传。')
 canonical=source.get('input_asset_id','')
 if not re.fullmatch(r'[a-f0-9]{32}',canonical):raise HTTPException(404,'原始音频不存在。')
 target=(INPUTS/canonical/'input.audio').resolve()
 if not target.is_relative_to(INPUTS) or not target.is_file():raise HTTPException(404,'原始音频文件不存在。')
 size=target.stat().st_size
 if len(b['jobs'])>=20 or b['bytes']+size>2*1024**3:raise HTTPException(413,'每批最多20文件、合计2 GB。')
 job_id='cv-'+uuid.uuid4().hex
 job=dict(_hub_actor_id=os.environ.get('HUB_RUNTIME_ACTOR_ID'),id=job_id,model=b['model'],stems=b['stems'],purpose=b['purpose'],filename=source['filename'],input=str(target),input_asset_id=canonical,input_url='/api/studio/assets/'+canonical+'/audio',input_bytes=size,input_duration=source.get('input_duration',0),input_sha256=source.get('input_sha256'),status='uploaded',outputs=[],error='')
 write(DATA/'jobs'/job_id/'job.json',job);b['jobs'].append(job_id);b['bytes']+=size;b['reused_files']+=1;write(path,b);return describe(b)
@app.post('/api/speech/batches/{identity}/reuse',status_code=201)
async def reuse(identity:str,asset_id:str):
 async with mutation_lock:return await asyncio.to_thread(reuse_input,identity,asset_id)
async def run(path):
 global active
 b=json.loads(path.read_text());known_complete=b['status']!='unknown'
 try:
  for identity in b['jobs']:
   p,j=load('jobs',identity)
   if j['status']=='succeeded':continue
   if j['status']=='unknown':known_complete=False;raise RuntimeError('任务状态待核对，不能重复执行')
   j.update(status='queued',error='');write(p,j)
   log=p.with_name('job-attempt-'+uuid.uuid4().hex+'.log')
   try:
    # A thread owns the complete synchronous SDK activity; native API polling
    # remains responsive while the original per-job CLI runs in the GPU engine.
    deadline=time.monotonic()+600
    while True:
     try:
      await asyncio.to_thread(run_native,p,log);break
     except AdmissionRejected as exc:
      # Admission-only metadata retries: the native worker has not started.
      if exc.code not in ['resource_busy','model_preparing'] or time.monotonic()>=deadline:raise
      j.update(status='waiting',message='等待Hub显卡资源');write(p,j);await asyncio.sleep(3)
   except Exception as exc:
    if getattr(exc,'code','') in ['execution_unknown','node_unavailable']:
     known_complete=False;j=load('jobs',identity)[1]
     j.update(status='unknown',error='执行状态待核对，输入与输出已保留，请勿重复提交');write(p,j)
     b.update(status='unknown',error=j['error']);write(path,b);raise
    j=load('jobs',identity)[1]
    if j['status']!='succeeded':j.update(status='failed',error=j.get('error') or '处理未完成，输入与已有结果已保留');write(p,j)
  ok=all(load('jobs',i)[1]['status']=='succeeded' for i in b['jobs'])
  b.update(status='succeeded' if ok else 'partial',error='' if ok else '部分文件未完成，可继续重试。');write(path,b)
 except Exception:
  if known_complete:b.update(status='partial',error='处理未完成，输入和已有结果已保留，可继续重试。');write(path,b)
 finally:
  active=False
  if known_complete:runtime.complete_background_work()


def run_native(path,log):
 with runtime.execution():
  result=runtime.get().run([sys.executable,'-m','audio_api.worker',str(path)],
   timeout=3600,log_path=str(log))
  job=load('jobs',path.parent.name)[1]
  if result['returncode'] or job['status']!='succeeded':
   raise RuntimeError('Native worker did not complete successfully')

@app.post('/api/speech/batches/{identity}/start',status_code=202)
async def start(identity:str):
 global active
 async with mutation_lock:
  if any(load('jobs',i)[1]['status']=='unknown' for i in load('batches',identity)[1]['jobs']):raise HTTPException(409,'执行状态待核对，不能重复提交。')
  path,b=load('batches',identity)
  if b['status']=='unknown' or runtime.status()['residency']=='unknown':raise HTTPException(409,'执行状态待核对，不能重复提交。')
  if b['status'] in ['running','succeeded']:return describe(b)
  if not b['jobs']:raise HTTPException(400,'请先导入音频。')
  selection(b['model'],json.dumps(b['stems']))
  if active:raise HTTPException(429,'正在处理另一批音频，当前导入已保留，请稍后开始。')
  runtime.accept_background_work();active=True;b.update(status='running',error='');write(path,b);asyncio.create_task(run(path));return describe(b)

def output_file(identity,name):
 _,j=load('jobs',identity)
 if j['status']!='succeeded' or name not in [o['file'] for o in j['outputs']]:raise HTTPException(404,'音轨不存在。')
 return DATA/'jobs'/identity/name
@app.get('/api/speech/jobs/{identity}/files/{name}')
def download(identity:str,name:str):return FileResponse(output_file(identity,name),media_type='audio/wav')
@app.get('/api/speech/jobs/{identity}/files/{name}/waveform')
def waveform(identity:str,name:str):
 source=output_file(identity,name);cached=source.with_suffix('.peaks.json')
 if cached.exists():return json.loads(cached.read_text())
 with sf.SoundFile(source) as audio:
  count=900;edges=np.linspace(0,len(audio),count+1,dtype=int);peaks=[]
  for left,right in zip(edges[:-1],edges[1:]):
   audio.seek(int(left));block=audio.read(int(right-left),dtype='float32',always_2d=True);peaks.append(float(np.max(np.abs(block))) if len(block) else 0.)
  result=dict(peaks=peaks,duration=len(audio)/audio.samplerate,sample_rate=audio.samplerate,frames=len(audio))
 write(cached,result);return result
@app.post('/api/speech/exports',status_code=201)
async def export(request:Request):
 body=bytearray()
 async for block in request.stream():
  body.extend(block)
  if len(body)>65536:raise HTTPException(413,'导出请求过大。')
 try:tracks=json.loads(body)['tracks']
 except (ValueError,KeyError,TypeError):raise HTTPException(400,'请选择要导出的音轨。')
 if not isinstance(tracks,list) or not 1<=len(tracks)<=400:raise HTTPException(400,'请选择1至400条音轨。')
 entries=[];seen=set()
 for item in tracks:
  if not isinstance(item,dict):raise HTTPException(400,'音轨选择无效。')
  jid,stem=item.get('job_id',''),item.get('stem','')
  if not isinstance(jid,str) or not isinstance(stem,str):raise HTTPException(400,'音轨选择无效。')
  if (jid,stem) in seen:continue
  seen.add((jid,stem));_,job=load('jobs',jid);o=next((o for o in job['outputs'] if o['stem']==stem),None)
  if not o:raise HTTPException(404,'音轨不存在。')
  source=output_file(jid,o['file']);title=re.sub(r'[\x00-\x1f/\\:*?"<>|]','_',Path(job['filename']).stem)[:100] or '音频';entries.append((jid,title,o,source))
 identity=hashlib.sha256(json.dumps([(j,o['stem'],p.stat().st_size,p.stat().st_mtime_ns) for j,_,o,p in entries]).encode()).hexdigest();target=DATA/'exports'/(identity+'.zip')
 if not target.exists():
  if shutil.disk_usage(DATA).free<sum(p.stat().st_size for _,_,_,p in entries)+256*1024**2:raise HTTPException(507,'导出空间不足。')
  def pack():
   temp=target.with_name(target.name+'.'+uuid.uuid4().hex+'.tmp');files=list(dict.fromkeys(j for j,_,_,_ in entries))
   with zipfile.ZipFile(temp,'w',compression=zipfile.ZIP_STORED,allowZip64=True) as archive:
    for n,(j,title,o,p) in enumerate(entries,1):archive.write(p,f'{files.index(j)+1:02d}-{title}/{n:03d}-{o["label"]}.wav')
   temp.replace(target)
  await asyncio.to_thread(pack)
 return dict(url='/api/speech/exports/'+identity+'.zip',filename='人声处理音轨.zip',bytes=target.stat().st_size,tracks=len(entries))
@app.get('/api/speech/exports/{name}')
def zip_download(name:str):
 if not re.fullmatch(r'[a-f0-9]{64}\.zip',name) or not (DATA/'exports'/name).exists():raise HTTPException(404,'导出文件不存在。')
 return FileResponse(DATA/'exports'/name,media_type='application/zip',filename='人声处理音轨.zip')


def build_api(managed_runtime):
 global runtime
 runtime=managed_runtime
 runtime.pending_work=lambda:int(active)
 return app
