import hashlib,json,os,re,uuid
from pathlib import Path
DATA=Path(os.environ.get('AUDIO_DATA','/data'))
LOCK=Path('/models/models-lock.json')
SPECS={
 'MossFormer2_SS_16K':('speech_separation',16000,[('Speaker1','说话人 A'),('Speaker2','说话人 B')]),
 'MossFormer2_SR_48K':('speech_super_resolution',48000,[('Enhanced','音质提升后人声')]),
 'MossFormer2_SE_48K':('speech_enhancement',48000,[('Clean','降噪后人声')]),
 'FRCRN_SE_16K':('speech_enhancement',16000,[('Clean','降噪后人声')]),
 'MossFormerGAN_SE_16K':('speech_enhancement',16000,[('Clean','降噪后人声')]),
}
def write(path,state):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp');temp.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n');temp.replace(path)
def valid_id(value):return bool(re.fullmatch(r'cv-[a-f0-9]{32}',value))
def model_row(model):
 name=model.removeprefix('cv:')
 if name not in SPECS:raise ValueError('未知的 ClearVoice 模型。')
 return next((r for r in json.loads(LOCK.read_text()) if r['name']==name),None)
def key(row):
 native=Path('/app/native-revision').read_text().strip()
 return hashlib.sha256((Path(__file__).with_name('worker.py').read_text()+native+json.dumps(row,sort_keys=True)).encode()).hexdigest()
def model_status():
 verified=json.loads((DATA/'verified-models.json').read_text()) if (DATA/'verified-models.json').exists() else {}
 rows=[]
 for name,(_,sr,stems) in SPECS.items():
  row=model_row(name);downloaded=bool(row and all((Path('/models/checkpoints')/name/a['file']).is_file() for a in row['artifacts']))
  ready=downloaded and verified.get(name,{}).get('key')==key(row) and verified[name].get('passed',False)
  rows.append(dict(id='cv:'+name,available=bool(ready),downloaded=downloaded,stems=[dict(id=k,label=v) for k,v in stems],size=sum(a['bytes'] for a in row['artifacts']) if row else 0,reason='' if ready else '正在验证' if downloaded else '正在准备模型',native_sample_rate=sr))
 return rows
