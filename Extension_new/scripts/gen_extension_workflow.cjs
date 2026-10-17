/* Editable Excalidraw + matching SVG. Run with Node; no dependencies. */
const fs = require('node:fs');
const path = require('node:path');
const out = path.resolve(__dirname, '../docs');
const elements = [], svg = [];
const C = { blue: '#1971c2', green: '#2f9e44', amber: '#e67700', red: '#e03131', violet: '#6741d9', gray: '#495057' };
const B = { blue: '#a5d8ff', green: '#ebfbee', amber: '#ffec99', red: '#ffc9c9', violet: '#e5dbff', gray: '#f1f3f5' };
const escape = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
function base(type,x,y,width,height,color,bg='transparent') {
  return {id:`extension-${elements.length}`,type,x,y,width,height,angle:0,strokeColor:color,backgroundColor:bg,fillStyle:'solid',strokeWidth:2,strokeStyle:'solid',roughness:0,opacity:100,groupIds:[],frameId:null,roundness:type==='rectangle'?{type:3}:null,seed:1000+elements.length,version:1,versionNonce:2000+elements.length,isDeleted:false,boundElements:null,updated:1,link:null,locked:false};
}
function text(s,x,y,size=16,color='#343a40',width=1200) {
  const lines=s.split('\n'), height=lines.length*size*1.35;
  const e={...base('text',x,y,width,height,color),text:s,originalText:s,fontSize:size,fontFamily:2,textAlign:'left',verticalAlign:'top',containerId:null,autoResize:false,lineHeight:1.35};
  elements.push(e);
  svg.push(`<text x="${x}" y="${y+size}" font-size="${size}" fill="${color}">${lines.map((l,i)=>`<tspan x="${x}" dy="${i?size*1.35:0}">${escape(l)}</tspan>`).join('')}</text>`);
  return e;
}
function rect(x,y,w,h,c='gray',dashed=false) {
  const e=base('rectangle',x,y,w,h,C[c],B[c]); if(dashed)e.strokeStyle='dashed'; elements.push(e);
  svg.push(`<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="14" fill="${B[c]}" stroke="${C[c]}" stroke-width="2" ${dashed?'stroke-dasharray="8 6"':''}/>`);
  return e;
}
function box(x,y,w,h,title,body,c='blue') {
  rect(x,y,w,h,c);text(title,x+18,y+14,21,C[c],w-36);
  const size=w<350?14:16;
  const limit=Math.floor((w-36)/(size*0.54));
  const lines=body.split('\n').flatMap(line=>{
    const result=[];let current='';
    for(const word of line.split(' ')){
      if(current && current.length+word.length+1>limit){result.push(current);current=word;}
      else current+=(current?' ':'')+word;
    }result.push(current);return result;
  });
  const t=text(lines.join('\n'),x+18,y+51,size,'#343a40',w-36);
  if(t.height>h-65)throw new Error(`Box text too tall: ${title}`);
}
function arrow(x,y,x2,y2,dashed=false,label='') {
  const e={...base('arrow',x,y,Math.abs(x2-x),Math.abs(y2-y),C.gray),points:[[0,0],[x2-x,y2-y]],lastCommittedPoint:null,startBinding:null,endBinding:null,startArrowhead:null,endArrowhead:'arrow',elbowed:false};
  if(dashed)e.strokeStyle='dashed'; elements.push(e);
  svg.push(`<path d="M ${x} ${y} L ${x2} ${y2}" fill="none" stroke="${C.gray}" stroke-width="2" marker-end="url(#arrow)" ${dashed?'stroke-dasharray="8 6"':''}/>`);
  if(label)text(label,x+15,y+8,14,C.gray,Math.min(550,1296-x-15));
}
function section(n,title,y,c='blue'){text(`${n} · ${title}`,36,y,24,C[c]);}

text('Phisherman AI — Extension Workflow',36,24,38);
text('Chrome MV3 · on-device by default · optional server enhancement',36,82,20,C.gray);
section(1,'WHERE WE WATCH',140);
box(36,184,300,110,'Link hover','Check links before clicking','blue');
box(356,184,300,110,'Page / email','Page signals or open email','blue');
box(676,184,300,110,'Chats','WhatsApp / Telegram messages','blue');
box(996,184,300,110,'Selected input','Quick check or verification','blue');
[186,506,826,1146].forEach(x=>arrow(x,302,x,336));
box(36,348,1260,120,'2 · EXTRACT THE RIGHT CONTENT','content_script.js + WhatsApp modules\nJudge the message, not the whole inbox. No isolated email → no verdict.','gray');
arrow(666,476,666,516,false,'Snapshot');
rect(36,530,1260,300,'green');
text('3 · ON-DEVICE CHECKS — background.js',60,550,26,C.green);
text('Local checks run first. Results appear immediately.',60,593,19);
box(60,635,288,146,'LINKS','Real domain / lookalikes\nDeceptive URLs','blue');
box(368,635,288,146,'IDENTITY','Registration + UPI checks\nBundled URL model','violet');
box(676,635,288,146,'SCAM CUES','Money / urgency tactics\nCredential-form risks','amber');
box(984,635,288,146,'FILES','Suspicious APK offers\nFilename + context only','red');
text('Output: score + signals + source + coverage',60,795,17,C.green);
arrow(356,838,356,884,true,'Optional enhancement');
arrow(1026,838,1026,884,false,'Local result');
rect(36,896,620,224,'gray',true);
text('4 · OPTIONAL SERVER',56,916,24,C.gray);
text('On-device: no analysis network requests.\nLocal server: 127.0.0.1:8000.\nRemote mode: backend → cloud fallback.\nRemote checks can send page / message text.\nNetwork failure keeps the local result.',56,965,18);
box(696,896,600,224,'5 · WHAT THE USER SEES','Hover card: link findings\nTrust island + badge: quick warning\nPopup / side panel: score + evidence\nSettings: mode + personal preferences','amber');
rect(36,1156,1260,152,'violet');
text('6 · FINANCIAL VERIFICATION',60,1176,24,C.violet);
text('Selected input + consent → redact phone / email → server /verify → verdict + reasons\nRequires local-server or remote mode. Result stays in memory, separate from the trust score.',60,1225,19);
box(36,1344,620,174,'LOCAL STORAGE','Settings · last 50 scan summaries\nPersonal site preferences · review queue\nFinancial verification results are not persisted.','blue');
box(696,1344,600,174,'SAFEGUARDS','Reject stale results after page / chat changes.\nPreferences never hide strong evidence.\nA score is not proof of safety.','red');
text('Solid arrows: normal flow · dashed: optional network path',36,1552,16,C.gray);
text('Based on extension source + docs/MVP.md · 3 October 2026',36,1583,16,C.gray);

const drawing={type:'excalidraw',version:2,source:'https://excalidraw.com',elements,appState:{viewBackgroundColor:'#ffffff',gridSize:null},files:{}};
// Validate text stays inside the diagram and each declared text width is plausible.
for(const e of elements){
  if(e.type==='text'){
    const max=Math.max(...e.text.split('\n').map(l=>l.length))*e.fontSize*0.54;
    if(max>e.width+10)throw new Error(`Text too wide: ${e.text.split('\n')[0]} (${max} > ${e.width})`);
  }
  if(e.x<0||e.y<0||e.x+e.width>1332||e.y+e.height>1630)throw new Error(`Out of bounds: ${e.id}`);
}
fs.writeFileSync(path.join(out,'workflow.excalidraw'),JSON.stringify(drawing,null,2)+'\n');
fs.writeFileSync(path.join(out,'workflow.svg'),`<svg xmlns="http://www.w3.org/2000/svg" width="1332" height="1630" viewBox="0 0 1332 1630"><title>Phisherman AI — extension workflow</title><desc>Source-backed extension workflow with local checks, optional network enhancement, financial verification, storage and safeguards.</desc><defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10" fill="none" stroke="#495057" stroke-width="1.5"/></marker></defs><rect width="1332" height="1630" fill="white"/><g font-family="Arial, Helvetica, sans-serif">${svg.join('\n')}</g></svg>\n`);
console.log(`Generated ${elements.length} editable elements and matching SVG in ${out}`);
