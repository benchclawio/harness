import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
// Read-only public-document audit; no authentication, retries or product executions.
const root=path.dirname(fileURLToPath(import.meta.url));
const output=process.argv[2]||path.join(root,'source-records.json');
const sources=[
 ['cursor-pricing','https://cursor.com/pricing'],
 ['cursor-models','https://cursor.com/docs/models-and-pricing'],
 ['cursor-download','https://cursor.com/download'],
 ['cursor-changelog','https://cursor.com/changelog'],
 ['cursor-agent','https://cursor.com/docs/agent/overview'],
 ['cursor-ownership','https://cursor.com/blog/joining-spacex'],
 ['cursor-security','https://cursor.com/security'],
 ['devin-pricing','https://devin.ai/pricing'],
 ['devin-billing','https://docs.devin.ai/admin/billing/self-serve.md'],
 ['devin-releases','https://docs.devin.ai/desktop/releases'],
 ['devin-changelog','https://docs.devin.ai/desktop/changelog'],
 ['devin-rename','https://devin.ai/blog/windsurf-is-now-devin-desktop'],
 ['devin-faq','https://docs.devin.ai/desktop/devin-desktop-faq'],
 ['devin-local','https://docs.devin.ai/desktop/devin-local/overview.md'],
 ['devin-download','https://devin.ai/download'],
 ['historical-disclosure','https://www.ox.security/blog/94-vulnerabilities-in-cursor-and-windsurf-put-1-8m-developers-at-risk/'],
];
const strip=s=>s.replace(/<script[\s\S]*?<\/script>/gi,' ').replace(/<style[\s\S]*?<\/style>/gi,' ').replace(/<[^>]+>/g,' ').replace(/&nbsp;|&#160;/g,' ').replace(/&amp;/g,'&').replace(/&quot;/g,'"').replace(/&#(?:x27|39);/g,"'").replace(/\s+/g,' ').trim();
const patterns=[/Plus/i,/Premium/i,/Super/i,/Ultra/i,/Teams/i,/legacy/i,/weekly/i,/third.party/i,/Token Rate/i,/per full/i,/prepaid/i,/daily/i,/maintenance mode/i,/Agent Command Center/i,/Cascade/i,/Restricted Mode/i,/sandbox/i,/3\.30/i,/3\.14\.30825/i,/3\.12\.57/i,/Electron 43\.8\.8/i,/November 1[789]/i,/acquired by SpaceX/i,/June 2/i,/October 21, 2025/i,/Chromium/i,/checkpoint/i,/independently/i,/Privacy Mode/i];
const report={checked_at:new Date().toISOString(),method:'Single public GET per URL. Source excerpts plus raw-response hashes, not a product benchmark. No editors installed, no agents run, no paid services.',sources:[]};
try{
 for(const [kind,url] of sources){
  const response=await fetch(url,{headers:{'User-Agent':'BenchClawResearch/1.0','Accept':'text/markdown,text/html;q=0.9'},signal:AbortSignal.timeout(25000)});
  const body=await response.text(),text=strip(body);
  const excerpts=[];
  for(const pattern of patterns){const i=text.search(pattern);if(i>=0){const s=text.slice(Math.max(0,i-70),i+470);if(!excerpts.includes(s))excerpts.push(s);}}
  const row={kind,url,final_url:response.url,status:response.status,checked_at:new Date().toISOString(),sha256:createHash('sha256').update(body).digest('hex'),excerpts:excerpts.slice(0,16),agent_directed_index_header:/Documentation Index[\s\S]{0,100}Fetch the complete documentation index/i.test(text)};
  report.sources.push(row);
  await fs.writeFile(output,JSON.stringify(report,null,2)+'\n',{mode:0o600,flag:'w'});
  console.log(JSON.stringify(row));
  if(!response.ok)throw new Error('Source '+kind+' returned HTTP '+response.status+'; no retry.');
 }
}catch(error){console.error('Evidence collection stopped: '+error.message);process.exitCode=1;}
