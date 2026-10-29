'use strict';
const $ = id => document.getElementById(id);
const STORAGE = 'lessonvoice-draft-v1';
const VOICES=['warm-female','clear-male','storyteller-female','calm-male'];
const fresh = () => ({version:1,title:'',language:'en',rate:150,voice:'warm-female',sections:[],pronunciations:[],questions:[]});
let project=fresh(), sourceText='', busy=false, revision=0, engine=null, flowTimer=null, activeStep=0, storageLocked=false, voicePreviewUrl=null;
const audioCache=new Map(), staleAudio=new Set(), previews=new Map();
const make=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
const normalize=s=>s.replace(/\r\n?/g,'\n').trim();
const escapeRegex=s=>Array.from(s,c=>'.*+?^${}()|[]'.includes(c)||c.charCodeAt(0)===92?String.fromCharCode(92)+c:c).join('');
function localSpoken(text){
  const rules=project.pronunciations.filter(r=>r.term.trim()).map(r=>({term:normalize(r.term),say:normalize(r.say)}));
  if(!rules.length)return normalize(text);
  const replacements=new Map(rules.map(r=>[r.term,r.say]));
  const terms=[...replacements.keys()].sort((a,b)=>Array.from(b).length-Array.from(a).length);
  return normalize(text).replace(new RegExp(terms.map(escapeRegex).join('|'),'gu'),match=>replacements.get(match));
}
const speechKey=text=>JSON.stringify([project.language,project.rate,project.voice,text]);
const currentAudio=section=>{const cached=audioCache.get(section.id);return cached&&cached.key===speechKey(localSpoken(section.text))?cached:null;};
function clearError(){$('error').hidden=true;$('error').textContent='';}
function showError(message){$('error').textContent=message;$('error').hidden=false;$('error').scrollIntoView({block:'nearest',behavior:'auto'});}
function status(message){$('status').textContent=message;}
function persist(){
  if(storageLocked){$('saved-state').textContent='Previous draft preserved — save this draft to a file';return;}
  try{localStorage.setItem(STORAGE,JSON.stringify({lessonvoiceDraft:1,sourceText,project}));$('saved-state').textContent='Draft saved in this browser';}
  catch{$('saved-state').textContent='Browser storage unavailable — save a draft file';}
}
function validateDraft(raw){
  const object=(value,label)=>{if(!value||typeof value!=='object'||Array.isArray(value))throw Error(`${label} must be an object.`);return value;};
  const text=(value,label,max,multiline=true)=>{if(typeof value!=='string'||value.length>max)throw Error(`${label} must be text of ${max.toLocaleString()} characters or fewer.`);for(const c of value){const n=c.charCodeAt(0);if((n<32&&(!multiline||!['\n','\r','\t'].includes(c)))||(c.length===1&&n>=0xd800&&n<=0xdfff))throw Error(`${label} contains unsupported characters.`);}return value.replace(/\r\n?/g,'\n');};
  const list=(value,label,max)=>{if(!Array.isArray(value)||value.length>max)throw Error(`${label} must contain at most ${max} items.`);return value;};
  object(raw,'Draft');let p=raw,source='';if(raw.lessonvoiceDraft!==undefined){if(raw.lessonvoiceDraft!==1)throw Error('Unsupported draft version.');p=object(raw.project,'Project');source=text(raw.sourceText,'Teaching notes',20000);}
  object(p,'Project');if(p.version!==1)throw Error('Unsupported project version.');if(!['en','ur'].includes(p.language))throw Error('Draft language must be English or Urdu.');if(!Number.isInteger(p.rate)||p.rate<100||p.rate>220)throw Error('Draft pace must be from 100 to 220.');const voice=p.voice===undefined?'warm-female':p.voice;if(!VOICES.includes(voice))throw Error('Choose one of the four supported voice characters.');
  const seen=new Set();const sections=list(p.sections,'Chapters',24).map(s=>{object(s,'Chapter');if(typeof s.id!=='string'||!/^[A-Za-z0-9_-]{1,64}$/.test(s.id)||seen.has(s.id))throw Error('Chapter IDs must be unique and use letters, numbers, underscores or hyphens.');seen.add(s.id);return{id:s.id,title:text(s.title,'Chapter title',120),text:text(s.text,'Chapter text',1500)};});
  if(sections.reduce((n,s)=>n+Array.from(s.text).length,0)>20000)throw Error('Total chapter text exceeds 20,000 characters.');
  const pronunciations=list(p.pronunciations??[],'Pronunciation rules',30).map(r=>{object(r,'Pronunciation rule');return{term:text(r.term,'Written term',80,false),say:text(r.say,'Spoken replacement',120,false)};});
  const questions=list(p.questions??[],'Questions',30).map(q=>{object(q,'Question');return{question:text(q.question,'Question',500),answer:text(q.answer,'Answer',1500)};});
  return{sourceText:source,project:{version:1,title:text(p.title,'Lesson title',120),language:p.language,rate:p.rate,voice,sections,pronunciations,questions}};
}
function changed(speech=false){revision++;persist();if(speech){previews.clear();refreshAudio();}updateSummary();}
function setBusy(value){
  busy=value;document.body.classList.toggle('busy',value);$('workspace').setAttribute('aria-busy',String(value));
  $('settings-fields').disabled=value;
  $('workspace').querySelectorAll('button,input,textarea,select').forEach(e=>{if(!e.closest('#settings-fields'))e.disabled=value;});
  updateSummary();
}
async function request(path,data,kind='json'){
  const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),['/api/audio','/api/voice-preview'].includes(path)?900000:120000);
  try{
    const response=await fetch(path,{...(data!==undefined?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)}:{}),signal:controller.signal});
    if(!response.ok){let error;try{error=(await response.json()).error;}catch{error=`Request failed (${response.status}).`;}throw Error(error||'The local service could not complete the request.');}
    return kind==='blob'?await response.blob():await response.json();
  }catch(e){if(e.name==='AbortError')throw Error('The local request reached its time limit. Your draft is safe. Neural speech on a CPU can be slow; try a shorter chapter.');if(e instanceof TypeError)throw Error('Cannot reach the local server. Keep LessonVoice running, then try again.');throw e;}
  finally{clearTimeout(timeout);}
}
async function run(action){if(busy)return;clearError();setBusy(true);try{await action();}catch(e){showError(e.message||'Something went wrong. Your draft has been kept.');status('Your draft has been kept. Fix the issue above and try again.');}finally{setBusy(false);}}
function disposeAudio(id){const a=audioCache.get(id);if(a)URL.revokeObjectURL(a.url);audioCache.delete(id);}
function disposeAll(){for(const id of audioCache.keys())disposeAudio(id);staleAudio.clear();previews.clear();clearVoicePreview();}
function clearVoicePreview(){if(voicePreviewUrl)URL.revokeObjectURL(voicePreviewUrl);voicePreviewUrl=null;$('voice-preview-player').hidden=true;$('voice-preview-player').removeAttribute('src');}
function download(blob,name){const url=URL.createObjectURL(blob);const a=make('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),10000);}
function validForExport(){return project.title.trim()&&project.sections.length&&project.sections.every(s=>s.title.trim()&&s.text.trim()&&currentAudio(s))&&project.pronunciations.every(r=>r.term.trim()&&r.say.trim())&&project.questions.every(q=>q.question.trim()&&q.answer.trim());}
function updateSummary(){
  const total=project.sections.length,ready=project.sections.filter(currentAudio).length;
  $('ready-count').textContent=`${ready} ready`;$('chapter-count').textContent=`${total} ${total===1?'chapter':'chapters'}`;$('section-tab-count').textContent=total;$('question-tab-count').textContent=project.questions.length;$('rule-count').textContent=`${project.pronunciations.length} rules`;
  $('audio-summary').textContent=ready===total&&total?'Your learning pack is ready':total?'Make a lesson worth listening to':'Ready when you are';
  $('audio-detail').textContent=total?`${ready} of ${total} chapters have current audio. Listen before sharing.`:'Create a chapter, generate its audio, then listen.';
  $('export-pack').disabled=busy||!validForExport();$('generate-all').disabled=busy||!total||!engine?.available||!engine.languages?.includes(project.language);
  $('preview-voice').disabled=busy||!engine?.available||!engine.languages?.includes(project.language);
  $('add-section').disabled=busy||total>=24;$('add-rule').disabled=busy||project.pronunciations.length>=30;$('add-question').disabled=busy||project.questions.length>=30;$('preview-all').disabled=busy||!total;
  document.querySelectorAll('[data-generate]').forEach(b=>{b.disabled=busy||!engine?.available||!engine.languages?.includes(project.language);});
}
function makeInput(id,label,value,limit,tag='input'){
  const box=make('div'),l=make('label',label),input=make(tag);l.htmlFor=id;input.id=id;input.maxLength=limit;input.value=value;input.dir='auto';if(tag==='textarea')input.rows=3;else input.type='text';box.append(l,input);return{box,input};
}
function renderChapters(){
  const host=$('chapters');host.replaceChildren();
  if(!project.sections.length){const e=make('div',undefined,'empty');const wave=make('div',undefined,'empty-wave');wave.setAttribute('aria-hidden','true');for(let i=0;i<7;i++)wave.append(make('i'));e.append(wave,make('h4','Small chapters. More ways to learn.'),make('p','Add your teaching notes or try a sample. Your editable audio chapters will appear here.'));host.append(e);return;}
  project.sections.forEach((section,index)=>{
    const card=make('article',undefined,'chapter');card.dataset.section=section.id;
    const top=make('div',undefined,'chapter-top'),label=make('div',undefined,'chapter-index');label.append(make('span',`CHAPTER ${String(index+1).padStart(2,'0')}`));const state=make('span','Not generated','audio-state');state.dataset.state=section.id;label.append(state);
    const remove=make('button','Remove','remove');remove.type='button';remove.setAttribute('aria-label',`Remove chapter ${index+1}`);remove.addEventListener('click',()=>{if(busy)return;if(!confirm('Remove this chapter and its generated audio?'))return;disposeAudio(section.id);staleAudio.delete(section.id);project.sections=project.sections.filter(s=>s.id!==section.id);changed(true);renderChapters();});top.append(label,remove);
    const body=make('div',undefined,'chapter-body');const title=makeInput(`title-${section.id}`,'Chapter title',section.title,120),text=makeInput(`text-${section.id}`,'Chapter text',section.text,1500,'textarea');
    title.input.addEventListener('input',()=>{section.title=title.input.value;changed();});
    const meta=make('div',undefined,'chapter-meta'),count=make('span',`${Array.from(section.text).length} / 1,500 characters`);meta.append(count,make('span','Original transcript'));
    text.input.addEventListener('input',()=>{section.text=text.input.value;count.textContent=`${Array.from(section.text).length} / 1,500 characters`;changed(true);});
    const details=make('details',undefined,'spoken-preview'),summary=make('summary','Spoken-text preview'),spoken=make('p','Select “Preview spoken text” to see the exact text sent to the voice engine.');spoken.dir='auto';spoken.dataset.preview=section.id;details.append(summary,spoken);body.append(title.box,text.box,meta,details);
    const audio=make('div',undefined,'chapter-audio');audio.dataset.audio=section.id;card.append(top,body,audio);host.append(card);
  });refreshAudio();
}
function refreshAudio(){
  for(const s of project.sections){
    const cached=audioCache.get(s.id);if(cached&&!currentAudio(s)){disposeAudio(s.id);staleAudio.add(s.id);}
    const state=document.querySelector('[data-state="'+s.id+'"]'),area=document.querySelector('[data-audio="'+s.id+'"]');if(!state||!area)continue;
    const a=currentAudio(s);state.textContent=a?'Audio ready':staleAudio.has(s.id)?'Needs regeneration':'Not generated';state.className='audio-state'+(a?' ready':staleAudio.has(s.id)?' stale':'');
    area.replaceChildren();const button=make('button',a?'Regenerate':'Generate chapter','button secondary');button.type='button';button.dataset.generate=s.id;button.addEventListener('click',()=>run(()=>generate([s.id])));area.append(button);
    if(a){const player=make('audio');player.controls=true;player.preload='none';player.src=a.url;player.setAttribute('aria-label',`Listen to ${s.title}`);const link=make('a','WAV ↓','download-audio');link.href=a.url;link.download=`lessonvoice-chapter-${project.sections.indexOf(s)+1}.wav`;link.setAttribute('aria-label',`Download audio for ${s.title}`);area.append(player,link);}
    const p=document.querySelector('[data-preview="'+s.id+'"]');if(p)p.textContent=previews.get(s.id)||'Select “Preview spoken text” to see the exact text sent to the voice engine.';
  }updateSummary();
}
function renderRules(){
  $('rules').replaceChildren();project.pronunciations.forEach((rule,i)=>{const row=make('div',undefined,'rule'),fields=make('div',undefined,'rule-fields'),term=makeInput(`term-${i}`,'Written term',rule.term,80),say=makeInput(`say-${i}`,'Say it as',rule.say,120);term.input.placeholder='e.g. H2O';say.input.placeholder='e.g. water';for(const[field,input]of[['term',term.input],['say',say.input]])input.addEventListener('input',()=>{rule[field]=input.value;changed(true);});fields.append(term.box,say.box);const remove=make('button','Remove rule','remove');remove.type='button';remove.setAttribute('aria-label',`Remove pronunciation rule ${i+1}`);remove.addEventListener('click',()=>{project.pronunciations.splice(i,1);changed(true);renderRules();});row.append(fields,remove);$('rules').append(row);});
}
function renderQuestions(){
  const host=$('questions');host.replaceChildren();if(!project.questions.length)host.append(make('p','No questions yet. Add a short check for understanding, or export audio and transcripts without questions.','editor-help'));
  project.questions.forEach((q,i)=>{const card=make('div',undefined,'question-card'),head=make('div',undefined,'question-heading');head.append(make('strong',`QUESTION ${String(i+1).padStart(2,'0')}`));const remove=make('button','Remove','remove');remove.type='button';remove.setAttribute('aria-label',`Remove question ${i+1}`);remove.addEventListener('click',()=>{project.questions.splice(i,1);changed();renderQuestions();});head.append(remove);const question=makeInput(`question-${i}`,'Question',q.question,500,'textarea'),answer=makeInput(`answer-${i}`,'Teacher answer',q.answer,1500,'textarea');question.input.addEventListener('input',()=>{q.question=question.input.value;changed();});answer.input.addEventListener('input',()=>{q.answer=answer.input.value;changed();});card.append(head,question.box,answer.box);host.append(card);});
}
function render(){
  $('lesson-title').value=project.title;$('language').value=project.language;$('rate').value=project.rate;$('voice').value=project.voice;$('rate-value').textContent=project.rate;$('lesson-text').value=sourceText;$('source-count').textContent=`${Array.from(sourceText).length.toLocaleString()} / 20,000`;
  $('language-note').textContent=project.language==='ur'?'Use native-script Urdu. Neural pronunciation varies; listen before sharing. No automatic translation.':'Offline neural speech. Install the model once, then generate on your own computer. CPU generation can take several minutes.';
  renderRules();renderQuestions();renderChapters();updateSummary();
}
async function spokenSnapshot(){
  const snapshot=structuredClone(project),stamp=revision;const result=await request('/api/spoken',{project:snapshot});
  if(stamp!==revision)throw Error('The lesson changed while it was being prepared. Try again.');
  if(!Array.isArray(result.sections)||result.sections.length!==snapshot.sections.length)throw Error('The local service returned an incomplete spoken-text preview.');
  for(const s of result.sections)previews.set(s.id,s.text);return{snapshot,stamp,sections:result.sections};
}
async function hash(value){const buffer=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(value));return Array.from(new Uint8Array(buffer),b=>b.toString(16).padStart(2,'0')).join('');}
async function generate(ids){
  if(!engine?.available)throw Error('The voice engine is not ready. Check its status before generating audio.');
  if(!engine.languages?.includes(project.language))throw Error('The selected language is unavailable in this voice engine.');
  const prepared=await spokenSnapshot();const list=prepared.sections.filter(s=>ids.includes(s.id));$('generation-progress').hidden=false;$('generation-progress').max=list.length;$('generation-progress').value=0;
  try{for(const [index,section]of list.entries()){
    const chapter=prepared.snapshot.sections.find(s=>s.id===section.id);status(`Generating ${index+1} of ${list.length}: ${chapter.title}… Neural speech runs locally; CPU generation may take several minutes.`);
    const key=JSON.stringify([prepared.snapshot.language,prepared.snapshot.rate,prepared.snapshot.voice,section.text]);const signature=await hash(key);
    const blob=await request('/api/audio',{project:prepared.snapshot,sectionId:section.id},'blob');
    if(prepared.stamp!==revision)throw Error('The lesson changed. Generated audio was discarded; please try again.');
    if(!blob.size||!blob.type.startsWith('audio/'))throw Error('The voice service returned no valid audio.');
    disposeAudio(section.id);audioCache.set(section.id,{blob,url:URL.createObjectURL(blob),key,signature});staleAudio.delete(section.id);$('generation-progress').value=index+1;refreshAudio();
  }status(`${list.length} ${list.length===1?'chapter is':'chapters are'} ready. Listen and check pronunciation before exporting.`);selectStep(5);}
  finally{$('generation-progress').hidden=true;}
}
async function base64(blob){const bytes=new Uint8Array(await blob.arrayBuffer());let binary='';for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));return btoa(binary);}
async function exportPack(){
  const prepared=await spokenSnapshot(),audio=[];
  for(const s of prepared.sections){const cached=audioCache.get(s.id),key=JSON.stringify([prepared.snapshot.language,prepared.snapshot.rate,prepared.snapshot.voice,s.text]);if(!cached||cached.signature!==await hash(key))throw Error('Some chapters have missing or outdated audio. Generate them again before exporting.');audio.push({id:s.id,data:await base64(cached.blob),signature:cached.signature});}
  status('Assembling audio, transcripts and teacher answer key…');const blob=await request('/api/export',{project:prepared.snapshot,audio},'blob');if(prepared.stamp!==revision)throw Error('Lesson changed during export. Please export again.');download(blob,'lessonvoice-pack.zip');status('Learning pack downloaded. Check the separate answer key before sharing with students.');selectStep(6);
}
async function checkEngine(){
  $('check-engine').disabled=true;
  try{const data=await request('/api/health');engine=data.engine;if(!engine||!Array.isArray(engine.languages))throw Error('The local service did not return a voice-engine status.');$('engine-dot').className='engine-dot '+(engine.available?'ready':'unavailable');$('engine-message').textContent=`${engine.available?'Offline neural files installed':'Offline neural files unavailable'} · ${engine.name||'Local neural speech'}. ${engine.message||'The first generation loads the model. CPU generation can be slow; review audio before sharing.'}`;}
  catch(e){engine=null;$('engine-dot').className='engine-dot unavailable';$('engine-message').textContent=e.message;}
  finally{$('check-engine').disabled=busy;updateSummary();}
}
const samples={
  en:{title:'The water cycle',text:'The sun warms water in rivers, lakes and oceans. Some liquid water changes into water vapour and rises into the air. This process is called evaporation.\n\nAs water vapour rises, the air becomes cooler. The vapour changes into tiny droplets of liquid water. These droplets gather to form clouds. This process is called condensation.\n\nWhen droplets in clouds become heavy, water falls to the ground as rain. This is called precipitation. Water collects in rivers, lakes and oceans, and the cycle begins again.',questions:[{question:'What provides the energy for evaporation?',answer:'The sun provides the energy.'},{question:'How are clouds formed?',answer:'Water vapour cools and condenses into tiny droplets that gather into clouds.'}]},
  ur:{title:'پانی کا چکر',text:'سورج کی گرمی سے دریاؤں، جھیلوں اور سمندروں کا پانی گرم ہوتا ہے۔ کچھ پانی بھاپ بن کر ہوا میں اوپر اٹھتا ہے۔ اس عمل کو تبخیر کہتے ہیں۔\n\nجب بھاپ اوپر اٹھتی ہے تو ہوا ٹھنڈی ہوتی جاتی ہے۔ بھاپ پانی کے چھوٹے قطروں میں بدل جاتی ہے۔ یہ قطرے مل کر بادل بناتے ہیں۔\n\nجب بادلوں میں پانی کے قطرے بھاری ہو جاتے ہیں تو بارش ہوتی ہے۔ پانی دوبارہ دریاؤں، جھیلوں اور سمندروں میں جمع ہو جاتا ہے۔ اس طرح پانی کا چکر جاری رہتا ہے۔',questions:[{question:'پانی کو گرم کرنے کے لیے توانائی کہاں سے آتی ہے؟',answer:'توانائی سورج سے آتی ہے۔'}]}
};
async function sample(language){
  if((storageLocked||sourceText.trim()||project.sections.length)&&!confirm('Replace this draft with the sample lesson? Existing chapter audio and the saved browser draft will be discarded.'))return;
  await run(async()=>{const s=samples[language];const data=await request('/api/segment',{text:s.text});disposeAll();storageLocked=false;project={...fresh(),title:s.title,language,sections:data.sections,questions:structuredClone(s.questions)};sourceText=s.text;changed();render();status('Sample ready. Edit the chapters, then generate real audio.');selectTab('sections');selectStep(2);});
}
function selectTab(name){for(const tab of ['sections','questions']){const selected=tab===name;$('tab-'+tab).setAttribute('aria-selected',String(selected));$('tab-'+tab).tabIndex=selected?0:-1;$(tab+'-panel').hidden=!selected;}}
$('lesson-title').addEventListener('input',()=>{project.title=$('lesson-title').value;changed();});
$('lesson-text').addEventListener('input',()=>{sourceText=$('lesson-text').value;$('source-count').textContent=`${Array.from(sourceText).length.toLocaleString()} / 20,000`;changed();});
$('language').addEventListener('change',()=>{project.language=$('language').value;clearVoicePreview();$('language-note').textContent=project.language==='ur'?'Use native-script Urdu. Neural pronunciation varies; listen before sharing. No automatic translation.':'Offline neural speech. Install the model once, then generate on your own computer. CPU generation can take several minutes.';changed(true);});
$('rate').addEventListener('input',()=>{project.rate=Number($('rate').value);$('rate-value').textContent=project.rate;clearVoicePreview();changed(true);});
$('voice').addEventListener('change',()=>{project.voice=$('voice').value;clearVoicePreview();changed(true);});
$('preview-voice').addEventListener('click',()=>run(async()=>{const stamp=revision;status('Generating a short voice sample locally… CPU generation may take several minutes.');const blob=await request('/api/voice-preview',{language:project.language,rate:project.rate,voice:project.voice},'blob');if(stamp!==revision)throw Error('Voice settings changed. Please preview again.');if(!blob.size||!blob.type.startsWith('audio/'))throw Error('No valid voice preview was returned.');clearVoicePreview();voicePreviewUrl=URL.createObjectURL(blob);$('voice-preview-player').src=voicePreviewUrl;$('voice-preview-player').hidden=false;status('Voice sample ready. Press play to listen; review the pronunciation yourself.');}));
$('sample-en').addEventListener('click',()=>sample('en'));$('sample-ur').addEventListener('click',()=>sample('ur'));
$('split').addEventListener('click',()=>{if(project.sections.length&&!confirm('Replace existing chapters with the current teaching notes? Their generated audio will be discarded.'))return;run(async()=>{const data=await request('/api/segment',{text:sourceText});disposeAll();project.sections=data.sections;if(!project.title.trim())project.title='Untitled lesson';changed();render();selectTab('sections');selectStep(2);status(`${project.sections.length} editable chapters created. Review them before generating audio.`);});});
$('add-section').addEventListener('click',()=>{if(busy||project.sections.length>=24)return;project.sections.push({id:'chapter-'+crypto.randomUUID(),title:`Chapter ${project.sections.length+1}`,text:''});changed();renderChapters();const input=$('text-'+project.sections.at(-1).id);input.focus();});
$('add-rule').addEventListener('click',()=>{if(busy||project.pronunciations.length>=30)return;project.pronunciations.push({term:'',say:''});changed(true);renderRules();$('term-'+(project.pronunciations.length-1)).focus();});
$('add-question').addEventListener('click',()=>{if(busy||project.questions.length>=30)return;project.questions.push({question:'',answer:''});changed();renderQuestions();$('question-'+(project.questions.length-1)).focus();});
$('preview-all').addEventListener('click',()=>run(async()=>{await spokenSnapshot();refreshAudio();document.querySelectorAll('.spoken-preview').forEach(e=>e.open=true);status('Exact spoken text is shown beneath each chapter. Original text remains unchanged.');selectStep(3);}));
$('generate-all').addEventListener('click',()=>run(()=>generate(project.sections.map(s=>s.id))));$('export-pack').addEventListener('click',()=>run(exportPack));$('check-engine').addEventListener('click',checkEngine);
$('save-draft').addEventListener('click',()=>{download(new Blob([JSON.stringify({lessonvoiceDraft:1,sourceText,project},null,2)],{type:'application/json'}),'lessonvoice-draft.json');status('Draft file downloaded. It contains text and settings; audio is downloaded separately or in a learning pack.');});
$('import-draft').addEventListener('click',()=>$('draft-file').click());
$('draft-file').addEventListener('change',async event=>{const file=event.target.files[0];if(!file)return;await run(async()=>{if(file.size>300000)throw Error('Draft files must be 300 KB or smaller.');let raw;try{raw=JSON.parse(await file.text());}catch{throw Error('This file is not valid JSON. Your current draft is unchanged.');}const incoming=validateDraft(raw);if((storageLocked||sourceText.trim()||project.sections.length)&&!confirm('Open this draft and replace the current lesson and saved browser draft? Generated audio will be discarded.'))return;disposeAll();storageLocked=false;project=incoming.project;sourceText=incoming.sourceText;changed();render();status('Validated draft opened. Incomplete fields are preserved; complete them before generating audio.');});event.target.value='';});
$('clear-draft').addEventListener('click',()=>{if(busy||!confirm('Clear the saved lesson from this browser and discard generated audio? Downloaded files are kept.'))return;disposeAll();project=fresh();sourceText='';revision++;storageLocked=false;try{localStorage.removeItem(STORAGE);}catch{}clearError();render();status('Draft cleared from this browser.');});
for(const name of ['sections','questions']){$('tab-'+name).addEventListener('click',()=>selectTab(name));$('tab-'+name).addEventListener('keydown',event=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(event.key)){event.preventDefault();const next=event.key==='Home'?'sections':event.key==='End'?'questions':name==='sections'?'questions':'sections';selectTab(next);$('tab-'+next).focus();}});}
const flowDescriptions=[
  ['WRITE','Paste teacher-written text in English or Urdu. Your draft is saved in this browser; no lesson is sent to a cloud AI service.'],
  ['SPLIT','The local server separates paragraphs into chapters of up to 1,500 characters. You can edit every chapter before it is spoken.'],
  ['EDIT','Choose the title, chapter text, language and pace. Add your own questions and answers. LessonVoice does not generate or verify teaching content.'],
  ['PRONOUNCE','Exact written terms are replaced only in the spoken version. You can inspect the resulting text; the original transcript is preserved.'],
  ['GENERATE','After a one-time model installation, the local neural speech engine produces a real WAV file for each chapter. Choose a preset voice character; no cloud speech service or personal voice cloning is used. CPU generation can be slow.'],
  ['LISTEN','Play each chapter and review pronunciation. If spoken text, language, pace or voice character changes, the old audio becomes unavailable until regenerated.'],
  ['EXPORT','The server validates the current audio and bundles WAV files, original and spoken transcripts, questions, a separate answer key and an offline player in one ZIP.']
];
function selectStep(index){activeStep=index;document.querySelectorAll('[data-step]').forEach(b=>b.setAttribute('aria-pressed',String(Number(b.dataset.step)===index)));$('flow-label').textContent=`${String(index+1).padStart(2,'0')} / ${flowDescriptions[index][0]}`;$('flow-description').textContent=flowDescriptions[index][1];}
function stopFlow(){clearInterval(flowTimer);flowTimer=null;$('flow-play').setAttribute('aria-pressed','false');$('flow-play').textContent='Play walkthrough ▷';}
document.querySelectorAll('[data-step]').forEach(button=>button.addEventListener('click',()=>{stopFlow();selectStep(Number(button.dataset.step));}));
$('flow-play').addEventListener('click',()=>{if(flowTimer){stopFlow();return;}selectStep(0);$('flow-play').setAttribute('aria-pressed','true');$('flow-play').textContent='Pause walkthrough Ⅱ';flowTimer=setInterval(()=>{if(activeStep>=6){stopFlow();return;}selectStep(activeStep+1);},3500);});
document.addEventListener('visibilitychange',()=>{if(document.hidden)stopFlow();});
async function restore(){
  try{const raw=localStorage.getItem(STORAGE);if(raw){if(raw.length>300000)throw Error('Saved draft too large.');const saved=validateDraft(JSON.parse(raw));project=saved.project;sourceText=saved.sourceText;status('Saved draft restored, including unfinished fields. Audio is not stored between visits; generate it again when ready.');}}
  catch{storageLocked=true;$('saved-state').textContent='Previous draft preserved — save this draft to a file';showError('The saved browser draft could not be read safely and has not been overwritten. Save any new work to a draft file. Use Open draft or Clear to explicitly replace it.');}
  render();await checkEngine();
}
render();restore();
